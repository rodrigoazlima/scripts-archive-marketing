# 📬 Thunderbird Inbox Marketing Archiver

[![Version](https://img.shields.io/badge/version-1.2.0-blue)](archive_marketing.py)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GNU](https://img.shields.io/badge/License-GNUv3-blue.svg)](LICENSE)
[![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](archive_marketing.py)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](archive_marketing.py)
[![CI](https://github.com/rodrigoazlima/scripts-archive-marketing/actions/workflows/ci.yml/badge.svg)](https://github.com/rodrigoazlima/scripts-archive-marketing/actions)

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
- 🛠️ **Config file** — persist settings in `~/.config/archive_marketing/config.json`
- 🌿 **Env var support** — override any setting via environment variables
- 🚫 **Exclude list** — `--exclude` flag to always keep specific senders/patterns
- 📊 **CSV export** — log every classification decision to a file
- 📨 **Email report** — auto-send yourself an HTML summary after each run
- 🧪 **Tested** — 40 unit tests covering all classification rules

---

## 🧱 Prerequisites

### 1. Mozilla Thunderbird

Download from [thunderbird.net](https://www.thunderbird.net). **Must be running** when the script executes.

### 2. thunderbird-mcp Extension

This script communicates with Thunderbird via the **thunderbird-mcp** MCP bridge:

- GitHub: [joelpurra/thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp)

Follow the installation instructions in that repo. Once installed:
- The extension exposes a local HTTP server on `localhost:8765`
- A connection file is written to:
  - **Windows:** `%TEMP%\thunderbird-mcp\connection.json`
  - **macOS/Linux:** `/tmp/thunderbird-mcp/connection.json`
- The connection file contains the auth token and port — **never share or commit this file**

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

### Step 2 — Find your IMAP folder URIs

Open Thunderbird → right-click a folder → **Properties** → copy the path.

Inbox example:
```
imap://you%40gmail.com@imap.gmail.com/INBOX
```

Archive folder example (create it in Thunderbird first):
```
imap://you%40gmail.com@imap.gmail.com/Marketing
```

### Step 3 — Create a config file (recommended)

```bash
cp config.example.json ~/.config/archive_marketing/config.json
# then edit with your actual IMAP URIs
```

### Step 4 — Dry run first

```bash
python archive_marketing.py --dry-run --verbose
```

### Step 5 — Run for real

```bash
python archive_marketing.py
```

---

## ⚙️ Configuration

Settings are resolved in this priority order: **CLI flags > env vars > config file > defaults**

### Config file

Copy `config.example.json` to `~/.config/archive_marketing/config.json`:

```json
{
  "inbox":          "imap://you%40gmail.com@imap.gmail.com/INBOX",
  "archive_folder": "imap://you%40gmail.com@imap.gmail.com/Marketing",
  "page_size":      100,
  "fetch_delay":    2.0,
  "exclude": [
    "payroll@mycompany.com",
    "boss@mycompany.com"
  ],
  "send_report": true,
  "report_to":   "you@gmail.com"
}
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `ARCHIVE_INBOX` | IMAP URI of inbox |
| `ARCHIVE_FOLDER` | IMAP URI of archive destination |
| `ARCHIVE_CONNECTION_FILE` | Path to thunderbird-mcp connection.json |
| `ARCHIVE_PAGE_SIZE` | Emails per API call |
| `ARCHIVE_FETCH_DELAY` | Seconds between page fetches |
| `ARCHIVE_MOVE_DELAY` | Seconds between move calls |
| `ARCHIVE_START_OFFSET` | Resume from offset |
| `ARCHIVE_DAYS_BACK` | How many days back to scan |
| `ARCHIVE_SEND_REPORT` | `true`/`false` — send email report after run |
| `ARCHIVE_REPORT_TO` | Recipient email for the report (default: auto from Thunderbird) |

### All CLI flags

```
options:
  --version              Show version and exit
  --config PATH          Path to JSON config file
  --inbox URI            IMAP folder URI of your inbox
  --archive-folder URI   IMAP folder URI for archived emails
  --connection-file PATH Path to thunderbird-mcp connection.json
  --page-size N          Emails per API call (default: 100)
  --fetch-delay SECS     Delay between page fetches (default: 2.0)
  --move-delay SECS      Delay between move calls (default: 1.5)
  --move-batch N         Max IDs per move request (default: 50)
  --start-offset N       Skip first N emails — resume (default: 0)
  --days-back N          Days back to scan (default: 3650)
  --exclude REGEX        Keep emails matching this pattern (repeatable)
  --export-csv PATH      Write all decisions to a CSV file
  --dry-run              Classify only — do not move emails
  --dry-run-summary      Dry run, print only final summary
  --send-report          Send HTML email report after each run
  --report-to EMAIL      Report recipient (default: auto-detect from Thunderbird)
  --verbose, -v          Print every classification decision
  -h, --help             Show help
```

---

## 🔍 How Classification Works

The script classifies each email using a **weighted scoring system** applied only to the sender address and subject line. **The email body is never fetched or read.**

```
┌─────────────────────────────────────────────────┐
│  For each email (sender + subject)              │
│                                                 │
│  1. User --exclude list?  → KEEP               │
│  2. Safe allowlist?       → KEEP               │
│  3. Strong sender match?  → ARCHIVE            │
│  4. Marketing subject?    → ARCHIVE            │
│  5. noreply + weak word?  → ARCHIVE            │
│  6. Default               → KEEP               │
└─────────────────────────────────────────────────┘
```

### Tier 1 — Safe allowlist (always kept)
```
no-reply@accounts.google.com   Google security alerts
noreply@google.com             Google notifications
noreply@github.com             GitHub security alerts
no-reply@*.apple.com           Apple account alerts
```

### Tier 2 — Strong sender (always archived)
100+ known marketing platforms and domains including:
- Email platforms: Mailchimp, SendGrid, Klaviyo, ActiveCampaign, Brevo, Iterable…
- E-commerce: AliExpress, Shopee, Mercado Livre, Shein, Kabum…
- Job boards: Indeed, Glassdoor, Catho, Vagas.com…
- Travel: Decolar, Booking.com, Airbnb, LATAM…
- Gaming: Epic Games, Steam, PlayStation…
- Streaming: Netflix, Spotify, Disney+…
- Crypto: Binance, Coinbase, Bybit…

### Tier 3 — Marketing subject (always archived)
Promotional keywords in English + Portuguese:
```
desconto, oferta, sale, deal, % off, giveaway, newsletter, digest,
announcing, introducing, unsubscribe, talent pool, frete grátis,
imperdível, aproveite, black friday, free trial, job alert…
```

### Tier 4 — Weak combo (archived when combined)
`noreply` sender + weak engagement word (tips, reminder, trending, featured…) → archived

### Extending the patterns

Edit the pattern constants at the top of `archive_marketing.py`. They are standard Python regex with `re.VERBOSE` for readability — add your domains and keywords freely.

---

## 🔒 Security

| Concern | How it's handled |
|---------|-----------------|
| Email credentials | **Never used.** Thunderbird manages your IMAP credentials. |
| Auth token | Read at runtime from the thunderbird-mcp connection file. Never stored, logged, or committed. |
| Email content | **Never fetched.** Only `sender` and `subject` fields are used. |
| Network access | All communication is `localhost` only. Nothing leaves your machine. |
| Connection file perms | Script warns if the file has world-readable permissions (POSIX). |

> ⚠️ **Never commit `connection.json`** — it contains a live session token. Excluded by `.gitignore`.

---

## 📁 Project Structure

```
scripts-archive-marketing/
├── archive_marketing.py       # Main script
├── config.example.json        # Example config file
├── tests/
│   └── test_classification.py # 40 unit tests
├── .github/
│   ├── workflows/ci.yml       # GitHub Actions CI
│   └── ISSUE_TEMPLATE/        # Bug report & feature request templates
├── README.md
├── LICENSE                    # GNU v3
└── .gitignore
```

---

## 🧪 Running Tests

```bash
# Standard unittest (no dependencies)
python -m unittest tests.test_classification -v

# With pytest (optional)
pip install pytest
pytest tests/ -v
```

---

## 💡 Scheduling (run daily automatically)

> **Important:** Thunderbird must be open and running when the script executes.

### Windows — Task Scheduler

```powershell
$action = New-ScheduledTaskAction `
  -Execute "python.exe" `
  -Argument '"C:\path\to\archive_marketing.py"' `
  -WorkingDirectory "C:\path\to\scripts-archive-marketing"

$trigger = New-ScheduledTaskTrigger -Daily -At "05:00AM"

Register-ScheduledTask `
  -TaskName "ArchiveMarketingEmails" `
  -TaskPath "\MyScripts\" `
  -Action $action `
  -Trigger $trigger `
  -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable)
```

### macOS / Linux — cron

```cron
0 5 * * * cd /path/to/scripts-archive-marketing && python3 archive_marketing.py
```

---

## 🧑‍💻 How It Works (Technical)

```
Your inbox
    │
    ▼
thunderbird-mcp (Thunderbird extension)
    │  HTTP server on localhost:8765
    │  auth token in connection.json
    │
    ▼
archive_marketing.py
    │  1. load_connection()  — read token + port
    │  2. fetch_page()       — getRecentMessages (paginated)
    │  3. classify()         — 4-tier regex scoring
    │  4. move_emails()      — updateMessage (bulk move)
    │
    ▼
Archive folder (IMAP server, stays private)
```

The script speaks **MCP JSON-RPC over HTTP** — no special libraries needed.

---

## 🐛 Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `Connection file not found` | Thunderbird not running | Start Thunderbird, wait 5s, retry |
| `Connection file not found` | Extension not installed | Install thunderbird-mcp, restart Thunderbird |
| `Authentication failed (403)` | Token expired | Restart Thunderbird to refresh the token |
| `MCP error: Invalid parameters` | Wrong folder URI | Right-click folder → Properties → copy the exact URI |
| Emoji in folder path crashes | Windows cp1252 terminal | Use `python -X utf8 archive_marketing.py` |
| Script runs but archives nothing | Folder URI wrong | Run with `--dry-run --verbose` to inspect |
| Too many emails per run | Gmail rate limit | Increase `--fetch-delay` to 3.0 or more |
| False positives (legit email archived) | Pattern too broad | Add sender to `--exclude` or config `exclude` list |

### Enable debug output

```bash
python archive_marketing.py --dry-run --verbose
```

### Check Thunderbird MCP status

Open Thunderbird → Add-ons → find thunderbird-mcp → status should show "Enabled" and a port number.

---

## ❓ FAQ

**Q: Does this work with non-Gmail IMAP accounts?**  
A: Yes. Any IMAP account configured in Thunderbird works — just use the correct folder URI from Thunderbird's folder properties.

**Q: How do I find my folder URI?**  
A: Right-click any folder in Thunderbird → **Properties** → the path shown is the URI. URL-encode the `@` as `%40`.

**Q: Can I run multiple inboxes?**  
A: Run the script once per inbox with different `--inbox` and `--archive-folder` arguments.

**Q: Will it re-archive already-archived emails?**  
A: No. It only reads from `--inbox`. Emails already moved are not re-processed.

**Q: Is the connection token safe?**  
A: The token is a local session secret generated by Thunderbird. It never leaves your machine. The script reads it at runtime and never logs it.

**Q: What if Thunderbird is closed when the scheduled task runs?**  
A: The script exits immediately with a clear error message. Set `StartWhenAvailable` in Task Scheduler so it retries when Thunderbird is next open.

---

## 🤝 Contributing

Contributions welcome! See [ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/) for how to report bugs or suggest new marketing patterns.

Ideas:
- 🌐 Marketing patterns for more languages/regions (Spanish, French, German…)
- 📧 Support multiple inboxes in one run
- 🔄 Rollback support (move back from archive to inbox)

---

## 📄 License

[GNU v3](LICENSE) — free to use, modify, and distribute.

---

## 🙏 Acknowledgements

- [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) — the MCP bridge that makes local Thunderbird automation possible
- [Mozilla Thunderbird](https://www.thunderbird.net) — the open-source email client that respects your privacy
