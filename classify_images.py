import os
import argparse
from logmagix import Logger

from main import OUTPUT_DIR, _ocr_image, classify_prompt, sanitize_folder_name
import shutil

log = Logger()

def process_folder(folder: str, move: bool = False, recursive: bool = False):
    if not os.path.isdir(folder):
        log.failure(f"Folder not found: {folder}")
        return

    exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
    files = []
    if recursive:
        for root, dirs, filenames in os.walk(folder):
            for fn in filenames:
                if fn.lower().endswith(exts):
                    files.append(os.path.join(root, fn))
    else:
        for fn in os.listdir(folder):
            if fn.lower().endswith(exts):
                files.append(os.path.join(folder, fn))

    if not files:
        log.info(f"No image files found in {folder}")
        return

    log.info(f"Found {len(files)} image(s) in {folder}")

    for path in files:
        try:
            ocr_text = _ocr_image(path) or ''
            classification = classify_prompt(ocr_text or '')
            log.info(f"{os.path.basename(path)} -> {classification} / '{ocr_text}'")
            if move:
                class_sanitized = sanitize_folder_name(classification if isinstance(classification, str) else str(classification))
                prompt_sanitized = sanitize_folder_name(ocr_text or 'no_prompt')
                dest_dir = os.path.join(OUTPUT_DIR, class_sanitized, prompt_sanitized)
                dest_path = os.path.join(dest_dir, os.path.basename(path))
                # if source already is the destination, skip
                if os.path.abspath(dest_path) == os.path.abspath(path):
                    log.info(f"Already organized: {path}")
                    continue
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.copy2(path, dest_path)
                    if os.path.exists(dest_path) and os.path.abspath(dest_path) != os.path.abspath(path):
                        os.remove(path)
                        log.info(f"Moved {path} -> {dest_path}")
                except Exception as e:
                    log.failure(f"Failed to move {path} -> {dest_path}: {e}")
        except Exception as e:
            log.failure(f"Failed to classify {path}: {e}")

def main():
    parser = argparse.ArgumentParser(description='Classify images in a folder using OCR and prompt heuristics')
    parser.add_argument('--folder', '-f', default=OUTPUT_DIR, help='Folder to scan for images')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--move', '-m', dest='move', action='store_true', default=True, help='Move (organize) images into classification folders (default)')
    group.add_argument('--no-move', dest='move', action='store_false', help='Do not move files; leave originals in place')
    parser.add_argument('--recursive', '-r', dest='recursive', action='store_true', help='Scan folders recursively')
    args = parser.parse_args()

    process_folder(args.folder, args.move, args.recursive)

if __name__ == '__main__':
    main()
