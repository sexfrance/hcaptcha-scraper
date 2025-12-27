import asyncio
import random
import tempfile
import time
import threading
from urllib.parse import urlparse
from patchright.async_api import async_playwright
import unicodedata
import toml
from functools import wraps
import re
import os
import shutil
import uuid
import concurrent.futures
from PIL import Image
import pytesseract
import traceback

from logmagix import Logger

log = Logger()
config = toml.load("input/config.toml")

# Configuration
OUTPUT_DIR = "output"
SITE_URL = "https://accounts.hcaptcha.com/demo?sitekey=a9b5fb07-92ff-493f-86fe-352a2803b3df"
DEBUG = config["dev"].get("Debug", False)

# Read additional dev config
DEV_CONF = config.get("dev", {}) if isinstance(config, dict) else {}
# Minimal logging boolean: when true only `log.message` calls will be shown
MINIMAL = bool(DEV_CONF.get("minimal", False))
# Normalized ignore lists
IGNORE_TYPES = [t.strip() for t in DEV_CONF.get("ignore_types", []) if t]
IGNORE_QUESTIONS = [q.strip().lower() for q in DEV_CONF.get("ignore_questions", []) if q]

# If minimal logging requested, suppress non-message logger methods
if MINIMAL:
    try:
        log.debug = lambda *a, **k: None
        log.info = lambda *a, **k: None
        log.warning = lambda *a, **k: None
        log.failure = lambda *a, **k: None
        log.success = lambda *a, **k: None
    except Exception:
        pass

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# lock file to prevent multiple instances
_LOCK_PATH = os.path.join(tempfile.gettempdir(), "hcaptcha_challenger.lock")

def debug(func_or_message, *args, **kwargs) -> callable:
    logger = log
    if callable(func_or_message):
        @wraps(func_or_message)
        async def async_wrapper(*args, **kwargs):
            if DEBUG:
                logger.debug(f"Currently running: {func_or_message.__name__}")
                result = await func_or_message(*args, **kwargs)
                logger.debug(f"{func_or_message.__name__} returned: {result}")
                return result
            return await func_or_message(*args, **kwargs)
        
        @wraps(func_or_message)
        def sync_wrapper(*args, **kwargs):
            if DEBUG:
                logger.debug(f"Currently running: {func_or_message.__name__}")
                result = func_or_message(*args, **kwargs)
                logger.debug(f"{func_or_message.__name__} returned: {result}")
                return result
            return func_or_message(*args, **kwargs)
        
        # Check if the function is async
        if asyncio.iscoroutinefunction(func_or_message):
            return async_wrapper
        else:
            return sync_wrapper
    else:
        if DEBUG:
            logger.debug(f"Debug: {func_or_message}")


@debug
def obtain_lock_or_exit():
    # If lock exists, try to detect whether it's stale. If so, remove it.
    if os.path.exists(_LOCK_PATH):
        try:
            with open(_LOCK_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                pid = int(content) if content else None
        except Exception:
            pid = None

        if pid:
            try:
                # signal 0 to test existence of process
                os.kill(pid, 0)
                log.warning(f"Another instance (pid {pid}) appears to be running. Exiting.")
                return False
            except OSError:
                # process not running -> stale lock
                try:
                    os.remove(_LOCK_PATH)
                    log.info("Removed stale lock file.")
                except Exception:
                    pass
        else:
            try:
                os.remove(_LOCK_PATH)
                log.info("Removed invalid lock file.")
            except Exception:
                pass

    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        fd = os.open(_LOCK_PATH, flags)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        log.warning("Another instance appears to be running (lock file present). Exiting.")
        return False

@debug
def remove_lock():
    try:
        if os.path.exists(_LOCK_PATH):
            os.remove(_LOCK_PATH)
    except Exception:
        pass



@debug
def process_existing_captures():
    """Process any existing raw captures in OUTPUT_DIR root (unclassified files)."""
    try:
        for nm in os.listdir(OUTPUT_DIR):
            path = os.path.join(OUTPUT_DIR, nm)
            if not os.path.isfile(path):
                continue
            ln = nm.lower()
            if ln.startswith("challenge_") and ln.endswith(".png"):
                log.info(f"Scheduling existing capture for processing: {path}")
                _EXECUTOR.submit(process_and_save_background, path, "UNCLASSIFIED", None, time.time())
            if ln.startswith("challenge_iframe_") and ln.endswith(".png"):
                log.info(f"Scheduling existing capture for processing: {path}")
                _EXECUTOR.submit(process_and_save_background, path, "UNCLASSIFIED", None, time.time())
    except Exception as e:
        log.failure(f"Error while scanning existing captures: {repr(e)}")


@debug
def parse_proxy_line(line: str):
    """Parse a proxy line in many common formats and return a dict suitable for Playwright.

    Supported formats:
    - user:pass@ip:port
    - user:pass:ip:port
    - http://user:pass@ip:port
    - ip:port
    """
    s = line.strip()
    if not s:
        return None
    # try URL parse first
    try:
        if s.startswith("http://") or s.startswith("https://") or s.startswith("socks"):
            up = urlparse(s)
            server = f"{up.scheme}://{up.hostname}:{up.port}"
            username = up.username
            password = up.password
            out = {"server": server}
            if username:
                out["username"] = username
            if password:
                out["password"] = password
            return out
    except Exception:
        pass

    # user:pass@ip:port
    if "@" in s:
        auth, host = s.split("@", 1)
        if ":" in host:
            ip, port = host.split(":", 1)
            server = f"http://{ip}:{port}"
            if ":" in auth:
                user, pwd = auth.split(":", 1)
            else:
                user, pwd = auth, None
            out = {"server": server}
            if user:
                out["username"] = user
            if pwd:
                out["password"] = pwd
            return out

    # user:pass:ip:port (legacy)
    parts = s.split(":")
    if len(parts) == 4:
        user, pwd, ip, port = parts
        server = f"http://{ip}:{port}"
        out = {"server": server, "username": user, "password": pwd}
        return out

    # ip:port
    if ":" in s:
        ip, port = s.split(":", 1)
        server = f"http://{ip}:{port}"
        return {"server": server}

    return None


@debug
def load_proxies(path: str):
    proxies = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                p = parse_proxy_line(ln)
                if p:
                    proxies.append(p)
    except FileNotFoundError:
        pass
    return proxies

@debug
async def handle_retry(page, challenge_element=None):

    try:
        debug("Moving to another challenge...")
        # click a neutral spot (top-left small offset) to defocus the widget
        try:
            await page.mouse.click(10, 10)
        except Exception:
            try:
                await page.evaluate("() => document.body.click()")
            except Exception:
                pass

        # try to click the challenge iframe to refocus and retake pictures
        if challenge_element:
            try:
                fb = await challenge_element.bounding_box()
                if fb:
                    x = fb["x"] + fb["width"] / 2
                    y = fb["y"] + fb["height"] / 2
                    await page.mouse.click(x, y)
                    debug("handle_retry: clicked challenge iframe to refocus")
                    return True
            except Exception:
                pass

        # fallback: click center of page
        try:
            w = await page.evaluate("() => window.innerWidth")
            h = await page.evaluate("() => window.innerHeight")
            await page.mouse.click(w/2, h/2)
            debug("handle_retry: clicked center of page as fallback")
        except Exception:
            pass

        debug("handle_retry: finished recovery routine (returning True)")
        return True
    except Exception as e:
        debug(f"handle_retry failed: {e}")
        return False


@debug
async def smart_reload_or_recover(page, challenge_element=None):
    """Attempt lightweight recovery: handle rate-limited, remove iframe or click around.
    Falls back to a full reload if recovery does not seem applicable.
    """
    try:
        ok = await handle_retry(page, challenge_element)
        if ok:
            return True
    except Exception:
        pass
    try:
        await page.reload()
        return True
    except Exception:
        try:
            await page.goto(SITE_URL)
            return True
        except Exception:
            return False
        
@debug
async def smart_reload_or_recover(page, challenge_element=None, wait_ms=1000):
    """Try to recover via handle_retry; if not possible, reload or goto SITE_URL and wait."""
    try:
        recovered = False
        try:
            recovered = await handle_retry(page, challenge_element)
        except Exception:
            recovered = False

        if recovered:
            await page.wait_for_timeout(wait_ms)
            return True

        try:
            await page.reload()
        except Exception:
            try:
                await page.goto(SITE_URL)
            except Exception:
                pass
        await page.wait_for_timeout(wait_ms)
        return False
    except Exception as e:
        debug(f"smart_reload_or_recover failed: {e}")
        try:
            await page.goto(SITE_URL)
            await page.wait_for_timeout(wait_ms)
        except Exception:
            pass
        return False

@debug
def sanitize_folder_name(name):
    if not name:
        return "no_prompt"
    s = unicodedata.normalize('NFKD', str(name))
    # replace any whitespace (spaces, newlines, tabs) with underscore
    s = re.sub(r"\s+", "_", s)
    # remove characters invalid in Windows filenames
    s = re.sub(r'[<>:\"/\\|\?\*]', '', s)
    # strip leading/trailing dots/underscores/spaces
    s = s.strip(' ._')
    # collapse multiple underscores
    s = re.sub(r'_+', '_', s)
    return s

@debug
def save_image(image_path, classification, prompt):
    try:
        class_name = getattr(classification, "name", None) or str(classification)
    except Exception:
        class_name = str(classification)
    class_sanitized = sanitize_folder_name(class_name)
    prompt_sanitized = sanitize_folder_name(prompt)
    classification_dir = os.path.join(OUTPUT_DIR, class_sanitized)
    target_dir = os.path.join(classification_dir, prompt_sanitized)
    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, os.path.basename(image_path))
    shutil.copy(image_path, dest_path)
    try:
        # count images in this specific prompt/type folder
        files = [n for n in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, n))]
        debug(f"Saved to {target_dir} ({len(files)} image(s) for this question/type)")
    except Exception:
        pass


@debug
def is_blank_image(path: str, mean_threshold: int = 250, std_threshold: float = 6.0, sat_threshold: float = 20.0) -> bool:
    """Return True if the image at `path` is effectively blank/empty/loading (mostly uniform gray/white/black).

    Checks grayscale uniformity and low color saturation to detect loading states with gray squares.
    """
    try:
        img = Image.open(path)
        # Check grayscale uniformity
        gray = img.convert('L')
        hist = gray.histogram()
        total = sum(hist)
        if total == 0:
            return True
        # compute mean
        s = 0
        for i, cnt in enumerate(hist):
            s += i * cnt
        mean = s / total
        # compute std dev
        ss = 0
        for i, cnt in enumerate(hist):
            ss += ((i - mean) ** 2) * cnt
        var = ss / total
        std = var ** 0.5

        # Check color saturation (low saturation means gray)
        hsv = img.convert('HSV')
        pixels = list(hsv.getdata())
        avg_sat = sum(p[1] for p in pixels) / len(pixels) if pixels else 0

        # Consider blank if: mostly bright (white), uniform (low std), or uniform gray (low sat and low std)
        if mean >= mean_threshold or std <= std_threshold or (avg_sat <= sat_threshold and std <= std_threshold):
            return True
        return False
    except Exception:
        return False

@debug
def _ocr_image(path: str) -> str:
    """Try to OCR the image using pytesseract if available; return extracted text or empty string."""
    try:
        img = Image.open(path)
        w, h = img.size
        crop_h = min(100, h)
        # crop top 100 pixels where hCaptcha often places the prompt text
        top_crop = img.crop((0, 0, w, crop_h))
        text = pytesseract.image_to_string(top_crop)
        text = (text or "").strip()
        if text:
            return text
        # fallback to full-image OCR
        text = pytesseract.image_to_string(img)
        return (text or "").strip()
    except Exception as e:
        log.failure(f"OCR failed: {e}")

@debug
def process_and_save_background(image_path: str, type_hint: str, prompt_hint: str, start_time: float):
    """Background worker: run OCR if available, decide prompt text, and save image to dataset."""
    try:
        # Respect ignore lists from config: types
        try:
            class_name = getattr(type_hint, "name", None) or str(type_hint)
        except Exception:
            class_name = str(type_hint)
        if class_name in IGNORE_TYPES:
            log.message("Hcaptcha Scraper", f"Ignored sample of type {class_name} per config; removing capture.")
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception:
                pass
            return

        # Run OCR to determine prompt and apply question-based ignores
        ocr_text = _ocr_image(image_path)
        prompt = ocr_text or (prompt_hint or "no_prompt")
        prompt = prompt.replace('\n', ' ').strip()  # remove newlines

        # Check ignore_questions (case-insensitive substring match)
        lprompt = (prompt or "").lower()
        for q in IGNORE_QUESTIONS:
            if q and q in lprompt:
                log.message("Hcaptcha Scraper", f"Ignored sample matching question pattern '{q}'; removing capture.")
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception:
                    pass
                return

        # save image under detected type
        save_image(image_path, type_hint, prompt)
        log.message("Hcaptcha Scraper", f"New CAPTCHA sample added to dataset: {type_hint} with OCR result: '{prompt}'", start_time, time.time())
        try:
            # remove the temporary capture file after copying
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception:
            pass
        debug(f"Scheduled background processing saved: {image_path} -> {type_hint}/{prompt}")
    except Exception as e:
        log.failure(f"Background processing failed: {repr(e)}")


# Global thread pool for background processing (initialized at runtime from config)
_EXECUTOR = None

@debug
def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return s


@debug
def classify_prompt(prompt_text: str) -> str:
    """Heuristic classifier for French challenge prompts.

    Returns one of: IMAGE_LABEL_SINGLE_SELECT, IMAGE_LABEL_MULTI_SELECT,
    IMAGE_DRAG_SINGLE, IMAGE_DRAG_MULTI
    """
    t = _normalize_text(prompt_text)
    if not t:
        return "IMAGE_LABEL_SINGLE_SELECT"

    # French and English indicators for drag vs click style challenges
    drag_indicators = [
        # French
        'glisser', 'deplacer', 'glisser-deposer', 'faire glisser', 'faire glisser le', 'déplacer',
        # English
        'drag', 'please drag', 'drag and drop', 'drag-and-drop', 'slide', 'move', 'move the', 'drag the', 'drag the'
    ]
    click_indicators = [
        # French
        'cliquez', 'cliquer', 'appuyez', 'appuyez_sur', 'selectionnez', 'sélectionnez', 'sélectionner', 'appuyez sur',
        # English
        'click', 'tap', 'press', 'select', 'tap on', 'click on', 'press on'
    ]
    multi_indicators = [
        # French
        'tous', 'toutes', 'plusieurs', 'toutes les', 'tous les', 'sélectionnez toutes', 'sélectionnez tous', 'toutes les images',
        # English
        'all', 'all images', 'multiple', 'several', 'select all', 'select all images', 'more than one'
    ]
    single_indicators = [
        # French
        'un seul', 'une seule', "l'", 'le ', 'la ', 'une ', 'un ',
        # English
        'only', 'one', 'a single', 'single'
    ]

    is_drag = any(word in t for word in drag_indicators)
    is_click = any(word in t for word in click_indicators)
    is_multi = any(word in t for word in multi_indicators)
    # extra heuristics: phrases that imply dragging a piece to complete a shape
    drag_clues = ['half', 'right', 'left', 'piece', 'puzzle', 'complete', 'complete the', 'fit', 'insert', 'slide into', 'align']
    # if prompt mentions shape completion (e.g., "drag the shape half on the right to complete the shape")
    if any(clue in t for clue in drag_clues) and ('shape' in t or 'forme' in t or 'piece' in t or 'moitié' in t):
        is_drag = True
    # phrases like "drag the shape half" or "move the half" strongly indicate single drag
    if ('half' in t or 'moitié' in t) and ('right' in t or 'left' in t or 'droite' in t or 'gauche' in t):
        is_drag = True
    # explicit 'complete' often accompanies drag puzzles
    if 'complete' in t or 'compléter' in t or 'compléter la' in t:
        is_drag = True
    # detect explicit numeric >1 mentions
    if '2' in t or '3' in t or '4' in t or 'deux' in t or 'trois' in t:
        is_multi = True

    if is_drag:
        return 'IMAGE_DRAG_MULTI' if is_multi else 'IMAGE_DRAG_SINGLE'
    if is_click:
        return 'IMAGE_LABEL_MULTI_SELECT' if is_multi else 'IMAGE_LABEL_SINGLE_SELECT'

    # fallback: if multi words present, assume multi-select click
    if is_multi:
        return 'IMAGE_LABEL_MULTI_SELECT'
    return 'IMAGE_LABEL_SINGLE_SELECT'


@debug
async def async_worker(thread_id: int):
    log.info("Starting")

    # Load config
    dev = config.get('dev', {}) if isinstance(config, dict) else {}
    proxyless = bool(dev.get('Proxyless', True))

    # Load proxies
    proxies = load_proxies(os.path.join("input", "proxies.txt"))
    if proxyless and proxies:
        log.failure(f"Config requests proxyless mode but proxies were provided; refusing to run.")
        return
    if not proxyless and not proxies:
        log.failure(f"Config requests proxy mode but no proxies found; refusing to run.")
        return

    log.info(f"Proxyless={proxyless}")
    # process any existing captures left in OUTPUT_DIR
    process_existing_captures()

    proxies = load_proxies(os.path.join("input", "proxies.txt"))
    chosen_proxy = None
    if proxies:
        chosen_proxy = random.choice(proxies)
        log.info(f"Using proxy: {chosen_proxy.get('server')}")

    # no .env loader; use local OCR + heuristic classifier (no external Gemini required)

    try:
        async with async_playwright() as p:
            launch_kwargs = {}
            if chosen_proxy:
                launch_kwargs["proxy"] = chosen_proxy
            browser = await p.chromium.launch(headless=False, **launch_kwargs)
            # request English locale so hCaptcha UI shows English phrasing when available
            context = await browser.new_context(locale='en-US')
            page = await context.new_page()

            await page.goto(SITE_URL)

            log.info("Starting processing loop. Press Ctrl-C to stop.")
            log.info("=" * 50)
            try:
                while True:
                    # Capture with retries
                    MAX_ATTEMPTS = 4
                    attempt = 0
                    challenge_image_path = None

                    while attempt < MAX_ATTEMPTS:
                        attempt += 1
                        log.warning(f"Attempt {attempt}/{MAX_ATTEMPTS}")

                        try:
                            await page.wait_for_selector("iframe[src*='hcaptcha']", timeout=15000)
                        except Exception:
                            log.warning("hcaptcha iframes not found; attempting recovery")
                            try:
                                await smart_reload_or_recover(page)
                            except Exception:
                                try:
                                    await page.reload()
                                except Exception:
                                    await page.goto(SITE_URL)
                            await page.wait_for_timeout(1000)
                            continue

                        frames_locator = page.locator("iframe[src*='hcaptcha']")
                        count = await frames_locator.count()
                        debug(f"Found {count} hcaptcha iframes")

                        # Determine iframe sizes and try to pick checkbox iframe more reliably.
                        iframe_boxes = []
                        element_handle = None
                        checkbox_index = None
                        for i in range(count):
                            fh = frames_locator.nth(i)
                            title = await fh.get_attribute("title")
                            debug(f"iframe[{i}] title: {title}")
                            eh = await fh.element_handle()
                            box = None
                            try:
                                if eh:
                                    box = await eh.bounding_box()
                            except Exception:
                                box = None
                            w = (box.get("width") or 0) if box else 0
                            h = (box.get("height") or 0) if box else 0
                            area = w * h
                            iframe_boxes.append((i, area, eh, title))

                        # Prefer iframe whose title mentions checkbox
                        for i, area, eh, title in iframe_boxes:
                            if title and "checkbox" in title.lower():
                                checkbox_index = i
                                element_handle = eh
                                break

                        # Fallback: pick the smallest iframe as checkbox (often small checkbox)
                        if checkbox_index is None and iframe_boxes:
                            iframe_boxes.sort(key=lambda t: t[1])
                            checkbox_index, _, element_handle, _ = iframe_boxes[0]

                        if not element_handle:
                            log.warning("No iframe element found; attempting recovery")
                            try:
                                await smart_reload_or_recover(page)
                            except Exception:
                                try:
                                    await page.reload()
                                except Exception:
                                    await page.goto(SITE_URL)
                            await page.wait_for_timeout(800)
                            continue

                        # Try clicking the inner checkbox element inside the iframe for accuracy
                        try:
                            iframe = await element_handle.content_frame()
                            clicked = False
                            if iframe:
                                # common selectors for the checkbox element
                                selectors = [
                                    'div[role="checkbox"]',
                                    'input[type="checkbox"]',
                                    '.checkbox',
                                    '#checkbox',
                                ]
                                for sel in selectors:
                                    try:
                                        box_el = await iframe.query_selector(sel)
                                        if box_el:
                                            await box_el.click()
                                            clicked = True
                                            debug(f"Clicked inner checkbox via selector {sel}")
                                            break
                                    except Exception:
                                        continue

                            if not clicked:
                                # fallback: click center of iframe element
                                fb = await element_handle.bounding_box()
                                if not fb:
                                    try:
                                        await element_handle.evaluate("el => el.scrollIntoView({block: 'center'})")
                                    except Exception:
                                        pass
                                    fb = await element_handle.bounding_box()
                                if not fb:
                                    log.warning("Could not get iframe bounding box; attempting recovery")
                                    try:
                                        await smart_reload_or_recover(page, element_handle)
                                    except Exception:
                                        try:
                                            await page.reload()
                                        except Exception:
                                            await page.goto(SITE_URL)
                                    await page.wait_for_timeout(500)
                                    continue
                                x = fb["x"] + fb["width"] / 2
                                y = fb["y"] + fb["height"] / 2
                                await page.mouse.click(x, y)
                                debug("Clicked checkbox iframe center")
                        except Exception as e:
                            log.failure("Click failed:", repr(e))
                            try:
                                await page.reload()
                            except Exception:
                                await page.goto(SITE_URL)
                            await page.wait_for_timeout(600)
                            continue

                        await page.wait_for_timeout(1200)

                        # Pick the challenge iframe as the largest iframe that's not the checkbox iframe
                        challenge_index = None
                        if iframe_boxes:
                            # sort by area descending
                            sorted_by_area = sorted(iframe_boxes, key=lambda t: t[1], reverse=True)
                            for idx, area, eh, title in sorted_by_area:
                                if idx != checkbox_index:
                                    challenge_index = idx
                                    break
                        if challenge_index is None and count == 1:
                            challenge_index = 0

                        if challenge_index is None:
                            log.warning("Challenge iframe not found; attempting recovery")
                            try:
                                await smart_reload_or_recover(page)
                            except Exception:
                                try:
                                    await page.reload()
                                except Exception:
                                    await page.goto(SITE_URL)
                            await page.wait_for_timeout(500)
                            continue

                        try:
                            challenge_element = await frames_locator.nth(challenge_index).element_handle()
                            challenge_frame = await challenge_element.content_frame()

                            # Try to extract textual prompt from the frame DOM before relying on OCR
                            frame_prompt_text = None
                            try:
                                text = await challenge_frame.evaluate("() => document.body.innerText || ''")
                                if text:
                                    text = text.strip()
                                    # pick the longest non-empty line (likely the prompt)
                                    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                                    if lines:
                                        lines.sort(key=lambda s: len(s), reverse=True)
                                        frame_prompt_text = lines[0]
                                        log.info(f"Extracted frame prompt text: {frame_prompt_text}")
                                        # detect retry messages and attempt recovery without reloading
                                        lt = (frame_prompt_text or "").lower()
                                        if "please try again" in lt:
                                            # attempt click-around and iframe close/reopen instead of refresh
                                            recovered = False
                                            for r_try in range(3):
                                                try:
                                                    debug(f"handle_retry attempt {r_try+1}/3")
                                                    recovered = await handle_retry(page, challenge_element)
                                                    if recovered:
                                                        log.info("Retry recovery succeeded")
                                                        break
                                                except Exception:
                                                    recovered = False
                                                await page.wait_for_timeout(800)
                                            if not recovered:
                                                log.warning("Retry persisted after 3 attempts; refreshing page")
                                                try:
                                                    await page.reload()
                                                except Exception:
                                                    await page.goto(SITE_URL)
                                                await page.wait_for_timeout(1200)
                                            # retry the capture loop
                                            continue
                            except Exception:
                                frame_prompt_text = None

                            imgs = challenge_frame.locator("img")
                            img_count = await imgs.count()
                            largest_eh = None
                            largest_area = 0
                            if img_count > 0:
                                for j in range(img_count):
                                    eh = await imgs.nth(j).element_handle()
                                    if not eh:
                                        continue
                                    box = await eh.bounding_box()
                                    if not box:
                                        continue
                                    area = (box.get("width", 0) or 0) * (box.get("height", 0) or 0)
                                    if area > largest_area:
                                        largest_area = area
                                        largest_eh = eh

                            uid = uuid.uuid4().hex
                            if largest_eh:
                                fname = f"challenge_{uid}.png"
                                challenge_image_path = os.path.join(OUTPUT_DIR, fname)
                                await largest_eh.screenshot(path=challenge_image_path)
                            else:
                                fname = f"challenge_iframe_{uid}.png"
                                challenge_image_path = os.path.join(OUTPUT_DIR, fname)
                                await challenge_element.screenshot(path=challenge_image_path)

                            try:
                                sz = os.path.getsize(challenge_image_path) if os.path.exists(challenge_image_path) else 0
                                log.success(f"Saved {challenge_image_path} size={sz}")
                                if not sz or sz < 2000:
                                    log.warning("Captured image too small; attempting recovery")
                                    try:
                                        await smart_reload_or_recover(page, challenge_element)
                                    except Exception:
                                        try:
                                            await page.reload()
                                        except Exception:
                                            await page.goto(SITE_URL)
                                    await page.wait_for_timeout(500)
                                    continue

                                # check for visually blank/white captures and retry up to 3 times
                                blank_tries = 0
                                while blank_tries < 3 and is_blank_image(challenge_image_path):
                                    blank_tries += 1
                                    log.warning(f"Captured blank image; retrying ({blank_tries}/3)")
                                    try:
                                        os.remove(challenge_image_path)
                                    except Exception:
                                        pass
                                    await page.wait_for_timeout(1000)
                                    if largest_eh:
                                        await largest_eh.screenshot(path=challenge_image_path)
                                    else:
                                        await challenge_element.screenshot(path=challenge_image_path)
                                    sz = os.path.getsize(challenge_image_path) if os.path.exists(challenge_image_path) else 0
                                    log.info(f"Retake saved {challenge_image_path} size={sz}")

                                if not sz or sz < 2000 or is_blank_image(challenge_image_path):
                                    log.warning("Captured image invalid after retries; attempting recovery")
                                    try:
                                        await smart_reload_or_recover(page, challenge_element)
                                    except Exception:
                                        try:
                                            await page.reload()
                                        except Exception:
                                            await page.goto(SITE_URL)
                                    await page.wait_for_timeout(500)
                                    continue

                                debug("Captured valid image")
                                break
                            except Exception:
                                log.warning("Could not stat image file; retrying")
                                try:
                                    await page.reload()
                                except Exception:
                                    await page.goto(SITE_URL)
                                await page.wait_for_timeout(500)
                                continue
                        except Exception as e:
                            log.failure(f"Error capturing challenge image: {repr(e)}")
                            try:
                                await smart_reload_or_recover(page, challenge_element)
                            except Exception:
                                try:
                                    await page.reload()
                                except Exception:
                                    await page.goto(SITE_URL)
                            await page.wait_for_timeout(500)
                            continue

                    if not challenge_image_path:
                        log.warning("Failed to capture challenge after attempts; continuing")
                        continue

                    # Local processing: prefer frame-extracted prompt, fall back to OCR
                    try:
                        ocr_text = _ocr_image(challenge_image_path)
                        prompt_text = None
                        # if we managed to extract text from the frame, prefer it
                        if 'frame_prompt_text' in locals() and frame_prompt_text:
                            prompt_text = frame_prompt_text
                            lt2 = (prompt_text or "").lower()
                            if "please try again" in lt2:
                                try:
                                    await handle_retry(page, challenge_element)
                                except Exception:
                                    pass
                                continue
                        else:
                            prompt_text = ocr_text or "no_prompt"

                        classification = classify_prompt(prompt_text)
                        # schedule background save/processing so capture loop is non-blocking
                        start_time = time.time()
                        _EXECUTOR.submit(process_and_save_background, challenge_image_path, classification, prompt_text, start_time)
                        debug(f"Submitted background job for {challenge_image_path} -> {classification} / {prompt_text}")
                    except Exception as e:
                        log.failure(f"Failed to schedule background processing: {repr(e)}")
                        try:
                            if challenge_image_path and os.path.exists(challenge_image_path):
                                os.remove(challenge_image_path)
                        except Exception:
                            pass

                    await page.wait_for_timeout(800)
                    try:
                        await smart_reload_or_recover(page)
                    except Exception:
                        try:
                            await page.reload()
                        except Exception:
                            await page.goto(SITE_URL)
                    await page.wait_for_timeout(500)

            except KeyboardInterrupt:
                log.info("Processing loop interrupted by user")

            try:
                await browser.close()
            except Exception:
                pass
    except Exception as e:
        log.failure(f"Unhandled exception in async_worker: {repr(e)}")
        tb = traceback.format_exc()
        debug(tb)


def main():
    # Load config and initialize thread pool
    dev = config.get('dev', {}) if isinstance(config, dict) else {}
    threads = int(dev.get('Threads', 4) or 4)

    global _EXECUTOR
    try:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=threads)
    except Exception:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    log.info(f"Executor initialized with threads={threads}")

    # Start worker threads
    worker_threads = []
    for i in range(threads):
        t = threading.Thread(target=lambda i=i: asyncio.run(async_worker(i)))
        t.start()
        worker_threads.append(t)

    # Wait for all threads
    for t in worker_threads:
        t.join()

    log.info("All workers finished")


if __name__ == "__main__":
    main()