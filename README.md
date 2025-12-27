<div align="center">
  <h2 align="center">Title e.g: Crunchyroll Account Creator</h2>
  <p align="center">
    Description e.g: An automated tool for creating Crunchyroll accounts with email verification support, proxy handling, and multi-threading capabilities.
    <br />
    <br />
    <a href="https://discord.cyberious.xyz">💬 Discord</a>
    ·
    <a href="#-changelog">📜 ChangeLog</a>
    ·
    <a href="https://github.com/sexfrance/Crunchyroll-Account-Creator/issues">⚠️ Report Bug</a>
    ·
    <a href="https://github.com/sexfrance/Crunchyroll-Account-Creator/issues">💡 Request Feature</a>
  </p>
</div>

---

### ⚙️ Installation

- Requires: `Python 3.7+`
- Make a python virtual environment: `python3 -m venv venv`
- Source the environment: `venv\Scriptsctivate` (Windows) / `source venv/bin/activate` (macOS, Linux)
- Install the requirements: `pip install -r requirements.txt`

---

### 🔥 Features

- Feature E.g: Email verification support using bune.pw email service
- Feature E.g: Proxy support for avoiding rate limits
- Feature E.g: Multi-threaded account generation
- Feature E.g: Real-time creation tracking with console title updates
- Feature E.g: Configurable thread count
- Feature E.g: Debug mode for troubleshooting
- Feature E.g: Proxy/Proxyless mode support
- Feature E.g: Automatic token handling
- Feature E.g: Custom password support
- Feature E.g: Detailed logging system
- Feature E.g: Account data saving (email:password format)
- Feature E.g: Full account capture with account_id and external_id

---

### 📝 Usage

1. **Configuration**:
   Edit `input/config.toml`:

   ```toml
   [dev]
   Debug = false
   Proxyless = false
   Threads = 1

   [data]
   password = "optional_custom_password"
   email_verified = true
   ```

2. **Proxy Setup** (Optional):
   - Add proxies to `input/proxies.txt` (one per line)
   - Format: `ip:port` or `user:pass@ip:port`

3. **Running the script**:
   ```bash
   python main.py
   ```

4. **Output**:
   - Created accounts are saved to `output/accounts.txt` (email:password)
   - Detailed account info saved to `output/full_account_capture.txt` (email:password:account_id:external_id)

---

### 📹 Preview

![Preview](https://i.imgur.com/c7yeYrQ.gif)

---

### ❗ Disclaimers

- This project is for educational purposes only
- The author is not responsible for any misuse of this tool
- Use responsibly and in accordance with Crunchyroll's terms of service

---

### 📜 ChangeLog

```diff
v0.0.1 ⋮ 12/26/2024
! Initial release with email verification and proxy support
```

<p align="center">
  <img src="https://img.shields.io/github/license/sexfrance/Crunchyroll-Account-Creator.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/stars/sexfrance/Crunchyroll-Account-Creator.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/languages/top/sexfrance/Crunchyroll-Account-Creator.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=python"/>
</p>