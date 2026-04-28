<!-- SPONSOR-START -->
---

<div align="center">

### 🌐 Need Proxies? Check out my services

<a href="https://vaultproxies.com" target="_blank" rel="noopener noreferrer">
  <img src="https://i.imgur.com/TF165pP.gif" alt="VaultProxies">
</a>
<p></p>

<table>
  <tr>
    <th>Service</th>
    <th>Pricing</th>
    <th>Features</th>
  </tr>
  <tr>
    <td><b><a href="https://vaultproxies.com" target="_blank" rel="noopener noreferrer">🔮 VaultProxies</a></b></td>
    <td><code>$1.00/GB</code> residential</td>
    <td>Residential · IPv6 · Residential Unlimited · Datacenter</td>
  </tr>
  <tr>
    <td><b><a href="https://nullproxies.com" target="_blank" rel="noopener noreferrer">🌑 NullProxies</a></b></td>
    <td><code>$0.75/GB</code> residential</td>
    <td>Residential · Residential Unlimited · DC Unlimited · Mobile Proxies</td>
  </tr>
  <tr>
    <td><b><a href="https://strikeproxy.net" target="_blank" rel="noopener noreferrer">⚡ StrikeProxy</a></b></td>
    <td><code>$0.75/GB</code> residential</td>
    <td>Residential · Residential Unlimited · DC Unlimited · Mobile Proxies</td>
  </tr>
</table>
</div>

<!-- SPONSOR-END -->

<div align="center">
  <h2 align="center">hCaptcha Challenger</h2>
  <p align="center">
    An automated tool for scraping and classifying hCaptcha challenges using Playwright/Patchright.
    <br />
    <br />
    <a href="https://discord.cyberious.xyz">💬 Discord</a>
    ·
    <a href="#-changelog">📜 ChangeLog</a>
    ·
    <a href="https://github.com/sexfrance/hcaptcha-scraper/issues">⚠️ Report Bug</a>
    ·
    <a href="https://github.com/sexfrance/hcaptcha-scraper/issues">💡 Request Feature</a>
  </p>
</div>

---

### ⚙️ Installation

- Requires: `Python 3.8+`
- Create a virtual environment:
  ```bash
  python -m venv venv
  ```
- Activate the environment:
  - Windows: `venv\Scripts\activate`
  - macOS/Linux: `source venv/bin/activate`
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  playwright install chromium
  ```

---

### 🔥 Features

- **Automated Scraping**: Uses Patchright to interact with hCaptcha demos and capture challenge images.
- **Smart Classification**: Heuristic-based classification of challenge types (Single Select, Multi Select, Drag & Drop).
- **Multi-threaded**: Supports multiple workers for high-speed data collection.
- **Proxy Support**: Robust proxy handling with support for various formats (IP:Port, User:Pass@IP:Port, etc.).
- **Dataset Management**: Automated organization of captured images into structured folders based on challenge type and prompt.
- **Utility Scripts**: Built-in scripts for dataset statistics and post-capture image organization.
- **Configurable**: Easily adjust settings through `input/config.toml`.

---

### 📁 Directory Structure

- `main.py`: The core automation engine that runs the scraper.
- `input/`:
  - `config.toml`: Main configuration file.
  - `proxies.txt`: File containing proxies to use (one per line).
- `scripts/`:
  - `classify_images.py`: Re-scans the output folder to organize images using OCR and prompt heuristics.
  - `stats.py`: Provides a detailed report on the current dataset (types, questions, image counts).
- `output/`: Automatic directory where captured and classified images are stored.

---

### 📝 Usage

1. **Configuration**:
   Edit `input/config.toml` to set your desired thread count, logging level, and ignore lists:
   ```toml
   [dev]
   Proxyless = true   # Set to false to use proxies from input/proxies.txt
   Debug = false      # Enable for detailed execution logs
   Threads = 5        # Number of concurrent workers
   minimal = true     # Only show core log messages
   ignore_types = []  # List of challenge types to skip
   ```

2. **Run the Scraper**:
   ```bash
   python main.py
   ```

3. **Get Dataset Stats**:
   ```bash
   python scripts/stats.py
   ```

4. **Re-classify Images**:
   ```bash
   python scripts/classify_images.py --folder output/ --move
   ```

---

### ❗ Disclaimers

- This project is for educational purposes only.
- The author is not responsible for any misuse.
- Ensure your use complies with the terms of service of any sites accessed.

---

### 📜 ChangeLog

```diff
v1.0.0 ⋮ 12/30/2024
+ Initial release of the comprehensive hCaptcha Challenger
+ Integrated multi-threading and proxy support
+ Added dataset management scripts
```

<p align="center">
  <img src="https://img.shields.io/github/license/sexfrance/hcaptcha-scraper.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/stars/sexfrance/hcaptcha-scraper.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/languages/top/sexfrance/hcaptcha-scraper.svg?style=for-the-badge&labelColor=black&color=python"/>
</p>
