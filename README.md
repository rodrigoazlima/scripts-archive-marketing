# 📬 Thunderbird Inbox Marketing Archiver

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GNU](https://img.shields.io/badge/License-GNUv3-blue.svg)](LICENSE)
[![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](archive_marketing.py)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](archive_marketing.py)

> **Automatically classify and archive marketing emails from your Thunderbird inbox — without opening a single email.**

Uses the [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) bridge to talk directly to your local Thunderbird installation over HTTP. No cloud services, no email credentials stored anywhere, no third-party access to your inbox.

---

## ✨ Features

- 🔍 **Classifies by sender + subject only** — email bodies are never read
- 🚀 **Bulk archiving** — moves hundreds of emails per minute
- 🔒 **100% local** — runs on your machine, talks to your Thunderbird
- ⏱️ **Rate-limit aware** — configurable delays to respect IMAP server limits
- 📄 **Dry-run mode** — preview what would be archived without touching anything
- 🔁 **Resume support** — `--start-offset` to continue interrupted runs
- 🌍 **Multilingual patterns** — English + Portuguese marketing keywords built-in
- 🛠️ **Fully configurable** — all settings via CLI flags

---

## 🧱 Prerequisites

### 1. Mozilla Thunderbird

Download from [thunderbird.net](https://www.thunderbird.net). Must be running when the script executes.

### 2. thunderbird-mcp Extension

This script communicates with Thunderbird via the **thunderbird-mcp** MCP bridge:

- GitHub: [joelpurra/thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp)

Follow the installation instructions in that repo. Once installed:
- The extension exposes a local HTTP server on `localhost:8765`
- A connection file is written to `%TEMP%\thunderbird-mcp\connection.json` (Windows) or `/tmp/thunderbird-mcp/connection.json` (macOS/Linux)
- The connection file contains the auth token and port — **never share this file**

### 3. Python 3.8+

```bash
python --version
```

No `pip install` needed — the script uses only the Python standard library.

---

## 🚀 Quick Start

### Step 1 — Clone the repo

```bash
git clone https://github.com/rodrigoazlima/scripts-archive-marketing.git
cd scripts-archive-marketing
```

### Step 2 — Find your inbox IMAP URI

Open Thunderbird → right-click your Inbox → **Properties** → copy the folder path.
It looks like:

```
imap://you%40gmail.com@imap.gmail.com/INBOX
```

### Step 3 — Find your archive folder URI

Same process for the destination folder (e.g. a "Marketing" or "🏬 Commerce" folder).
Create the folder in Thunderbird first if it doesn't exist.

### Step 4 — Dry run first

```bash
python archive_marketing.py \
  --inbox "imap://you%40gmail.com@imap.gmail.com/INBOX" \
  --archive-folder "imap://you%40gmail.com@imap.gmail.com/Marketing" \
  --dry-run \
  --verbose
```

This prints every classification decision without moving anything.

### Step 5 — Run for real

```bash
python archive_marketing.py \
  --inbox "imap://you%40gmail.com@imap.gmail.com/INBOX" \
  --archive-folder "imap://you%40gmail.com@imap.gmail.com/Marketing"
```

---

## ⚙️ All Options

```
usage: archive_marketing.py [options]

options:
  --inbox URI            IMAP folder URI of your inbox
  --archive-folder URI   IMAP folder URI to move marketing emails into
  --connection-file PATH Path to thunderbird-mcp connection.json
                         (default: auto-detected from %TEMP% / /tmp)
  --page-size N          Emails fetched per API call (default: 100)
  --fetch-delay SECS     Seconds between page fetches (default: 2.0)
  --move-delay SECS      Seconds between bulk-move calls (default: 1.5)
  --move-batch N         Max IDs per single move request (default: 50)
  --start-offset N       Skip first N emails — resume support (default: 0)
  --days-back N          How far back to scan in days (default: 3650)
  --dry-run              Classify only, do not move anything
  --verbose, -v          Print every classification decision
  -h, --help             Show this help message
```

---

## 🔍 How Classification Works

The script classifies each email using **two regex patterns** applied to the sender address and subject line. **The email body is never fetched or read.**

### Marketing sender pattern

Matches addresses from known marketing domains:

```
aliexpress, shopee, ebay, shein, indeed.com, glassdoor,
levels.fyi, medium.com, substack, mailchimp, sendgrid,
binance, coinbase, spotify, netflix, steam, epicgames ...
```

### Marketing subject pattern

Matches promotional keywords (English + Portuguese built-in):

```
desconto, oferta, promoção, liquidação, sale, deal,
X% off, free trial, newsletter, giveaway, cupom, coupon,
talent pool, frete grátis ...
```

### Safe-sender allowlist

Some senders are **always kept** regardless of subject:

```
no-reply@accounts.google.com  →  Google security alerts
noreply@google.com            →  Google notifications
```

### Extending the patterns

Edit the three pattern constants at the top of `archive_marketing.py`:

```python
MARKETING_SENDER_PATTERN = re.compile(r"...|your-domain\.com", re.IGNORECASE | re.VERBOSE)
MARKETING_SUBJECT_PATTERN = re.compile(r"...|your keyword", re.IGNORECASE | re.VERBOSE)
SAFE_SENDER_PATTERN = re.compile(r"...|trusted@domain\.com", re.IGNORECASE)
```

---

## 🔒 Security

| Concern | How it's handled |
|---------|-----------------|
| Email credentials | **Never used.** The script talks to Thunderbird locally — Thunderbird manages your IMAP credentials. |
| Auth token | Read at runtime from the thunderbird-mcp connection file. Never stored, never logged, never committed. |
| Email content | **Never fetched.** Classification uses only the `sender` and `subject` fields. |
| Network access | All communication is `localhost` only (`127.0.0.1:8765`). Nothing leaves your machine. |

> ⚠️ **Never commit `connection.json`** — it contains a live session token. It is excluded by `.gitignore`.

---

## 📁 Project Structure

```
scripts-archive-marketing/
├── archive_marketing.py   # Main script — all logic in one file
├── README.md              # This file
├── LICENSE                # GPL v3
└── .gitignore
```

---

## 💡 Scheduling (run daily automatically)

> **Important:** Thunderbird must be open and running when the script executes. The thunderbird-mcp bridge only works while Thunderbird is active.

### Windows — Task Scheduler

```powershell
$action = New-ScheduledTaskAction `
  -Execute "python.exe" `
  -Argument '"C:\path\to\archive_marketing.py" --inbox "imap://you%40gmail.com@imap.gmail.com/INBOX" --archive-folder "imap://you%40gmail.com@imap.gmail.com/Marketing"'

$trigger = New-ScheduledTaskTrigger -Daily -At "05:00AM"

Register-ScheduledTask `
  -TaskName "ArchiveMarketingEmails" `
  -TaskPath "\MyScripts\" `
  -Action $action `
  -Trigger $trigger `
  -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable)
```

### macOS / Linux — cron

```bash
crontab -e
```

Add:

```cron
0 5 * * * /usr/bin/python3 /path/to/archive_marketing.py \
  --inbox "imap://you%40gmail.com@imap.gmail.com/INBOX" \
  --archive-folder "imap://you%40gmail.com@imap.gmail.com/Marketing"
```

---

## 🧑‍💻 How It Works (Technical)

```
Your inbox
    │
    ▼
thunderbird-mcp (Thunderbird extension)
    │  exposes HTTP on localhost:8765
    │  auth token in %TEMP%/thunderbird-mcp/connection.json
    │
    ▼
archive_marketing.py
    │  reads connection.json at startup
    │  calls getRecentMessages (paginated, with offset)
    │  classifies sender + subject via regex
    │  calls updateMessage to bulk-move marketing emails
    │
    ▼
Archive folder (stays in Thunderbird / IMAP server)
```

The script speaks the **MCP JSON-RPC protocol** directly over HTTP — the same protocol used by Claude Code's MCP integration. No special library is needed.

---

## 🤝 Contributing

Contributions welcome! Ideas:

- 🌐 Add marketing patterns for more languages/regions
- 📊 Output a summary report (JSON / HTML)
- 📧 Support multiple inboxes in one run
- 🔧 Config file support (TOML / YAML) instead of CLI flags
- 🧪 Unit tests for classification patterns
- 🐧 Test on macOS / Linux and document connection file path differences

Please open an issue or pull request!

---

## 📄 License

[GPL v3](LICENSE) — free to use, modify, and distribute.

---

## 🙏 Acknowledgements

- [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) — the MCP bridge that makes local Thunderbird automation possible
- [Mozilla Thunderbird](https://www.thunderbird.net) — the open-source email client that respects your privacy
