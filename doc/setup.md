# Setup Guide

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Config File](#config-file)
  - [Environment Variables](#environment-variables)
  - [CLI Flags](#cli-flags)
  - [Priority Order](#priority-order)
- [Finding Your IMAP URIs](#finding-your-imap-uris)
- [First Run](#first-run)
- [Scheduling](#scheduling)
- [Windows-Specific Notes](#windows-specific-notes)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Mozilla Thunderbird

Download from [thunderbird.net](https://www.thunderbird.net). Thunderbird **must be running** every time the script executes — it is the IMAP client and the script is an automation layer on top of it.

### 2. thunderbird-mcp Extension

The script communicates with Thunderbird via the **thunderbird-mcp** bridge:

- **Repository:** [github.com/joelpurra/thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp)
- Install from that repo's instructions
- Once installed, the extension exposes an HTTP server on `localhost:8765`
- It writes a connection file to:
  - **Windows:** `%TEMP%\thunderbird-mcp\connection.json`
  - **macOS/Linux:** `/tmp/thunderbird-mcp/connection.json`

Verify the extension is working: Thunderbird → Add-ons Manager → thunderbird-mcp → status should show **Enabled** with a port number.

### 3. Python 3.8+

```bash
python --version
# Must be 3.8 or higher
```

No `pip install` is required. The script uses only Python's standard library.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/rodrigoazlima/scripts-archive-marketing.git
cd scripts-archive-marketing

# Verify the script is importable
python -c "import archive_marketing; print('OK')"

# Run tests to confirm environment
python -m unittest tests.test_classification -v
```

---

## Configuration

### Config File

The recommended approach for persistent settings. Copy the example and edit:

```bash
# Create the config directory
mkdir -p ~/.config/archive_marketing

# Copy the example
cp config.example.json ~/.config/archive_marketing/config.json

# Edit with your values
```

**Default config file location:** `~/.config/archive_marketing/config.json`

Override with `--config /path/to/other.json`.

#### Full config reference

```json
{
  "inbox":           "imap://you%40gmail.com@imap.gmail.com/INBOX",
  "archive_folder":  "imap://you%40gmail.com@imap.gmail.com/Marketing",

  "page_size":    100,
  "fetch_delay":  2.0,
  "move_delay":   1.5,
  "move_batch":   50,
  "days_back":    3650,
  "start_offset": 0,

  "exclude": [
    "boss@mycompany.com",
    "payroll@mycompany.com",
    "alerts@mybank.com"
  ],

  "send_report":         false,
  "report_to":           "you@gmail.com",
  "skip_report_if_empty": true,
  "cleanup_prev_reports": true,
  "reports_folder":       "imap://you%40gmail.com@imap.gmail.com/Reports"
}
```

#### Config key reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `inbox` | string | (Gmail example) | IMAP URI of the source inbox folder |
| `archive_folder` | string | (Gmail example) | IMAP URI of the destination archive folder |
| `page_size` | int | `100` | Emails fetched per MCP call |
| `fetch_delay` | float | `2.0` | Seconds to sleep between page fetches |
| `move_delay` | float | `1.5` | Seconds to sleep between batch move calls |
| `move_batch` | int | `50` | Max message IDs per single move request |
| `days_back` | int | `3650` | How many days back to scan (~10 years) |
| `start_offset` | int | `0` | Skip first N emails (resume interrupted runs) |
| `exclude` | array | `[]` | Regex patterns — matching emails always kept |
| `send_report` | bool | `false` | Send HTML summary email after each run |
| `report_to` | string | `null` | Report recipient (auto-detected from Thunderbird if empty) |
| `skip_report_if_empty` | bool | `true` | Skip report when zero emails were archived |
| `cleanup_prev_reports` | bool | `true` | Move old `[Archive Report]` emails out of inbox before new run |
| `reports_folder` | string | `null` | IMAP URI to move old report emails into |

---

### Environment Variables

All settings except `exclude`, `date_from`, and `date_to` can be set via environment variables. Env vars override the config file but are overridden by CLI flags.

| Variable | Config key equivalent |
|----------|----------------------|
| `ARCHIVE_INBOX` | `inbox` |
| `ARCHIVE_FOLDER` | `archive_folder` |
| `ARCHIVE_CONNECTION_FILE` | `connection_file` |
| `ARCHIVE_PAGE_SIZE` | `page_size` |
| `ARCHIVE_FETCH_DELAY` | `fetch_delay` |
| `ARCHIVE_MOVE_DELAY` | `move_delay` |
| `ARCHIVE_START_OFFSET` | `start_offset` |
| `ARCHIVE_DAYS_BACK` | `days_back` |
| `ARCHIVE_SEND_REPORT` | `send_report` (`true`/`false`) |
| `ARCHIVE_REPORT_TO` | `report_to` |
| `ARCHIVE_SKIP_REPORT_IF_EMPTY` | `skip_report_if_empty` (`true`/`false`) |
| `ARCHIVE_CLEANUP_PREV_REPORTS` | `cleanup_prev_reports` (`true`/`false`) |
| `ARCHIVE_REPORTS_FOLDER` | `reports_folder` |

Example for a Task Scheduler or cron environment:

```bash
export ARCHIVE_INBOX="imap://you%40gmail.com@imap.gmail.com/INBOX"
export ARCHIVE_FOLDER="imap://you%40gmail.com@imap.gmail.com/Marketing"
export ARCHIVE_SEND_REPORT=true
python archive_marketing.py
```

---

### CLI Flags

All flags from the complete reference:

```
--version                    Show version and exit
--config PATH                Path to JSON config file
--inbox URI                  IMAP URI of inbox
--archive-folder URI         IMAP URI of archive destination
--connection-file PATH       Path to thunderbird-mcp connection.json
--page-size N                Emails per MCP call (default: 100)
--fetch-delay SECS           Sleep between page fetches (default: 2.0)
--move-delay SECS            Sleep between move batches (default: 1.5)
--move-batch N               Max IDs per move request (default: 50)
--start-offset N             Skip first N emails — resume (default: 0)
--days-back N                Days back to scan (default: 3650)
--date-from YYYY-MM-DD       Only process emails on or after this date
--date-to   YYYY-MM-DD       Only process emails on or before this date
--exclude REGEX              Always-keep pattern (repeatable)
--export-csv PATH            Write all decisions to CSV
--dry-run                    Classify only — do not move any email
--dry-run-summary            Dry run, print final summary only (silent)
--send-report                Send HTML email report after run
--report-to EMAIL            Report recipient
--no-skip-report-if-empty    Send report even when nothing archived
--reports-folder URI         IMAP URI for old report cleanup destination
--no-cleanup-prev-reports    Skip moving old report emails
--verbose, -v                Print every classification decision
-h, --help                   Show help
```

---

### Priority Order

```
CLI flags
    ↓ (override)
Environment variables  (ARCHIVE_*)
    ↓ (override)
Config file  (~/.config/archive_marketing/config.json)
    ↓ (override)
Built-in defaults  (DEFAULTS dict in archive_marketing.py)
```

---

## Finding Your IMAP URIs

1. Open Thunderbird
2. Right-click any folder → **Properties**
3. The **Location** field shows the full IMAP URI

**Gmail inbox example:**
```
imap://you%40gmail.com@imap.gmail.com/INBOX
```

**Gmail custom folder:**
```
imap://you%40gmail.com@imap.gmail.com/Marketing
```

> **Note:** The `@` character in your email address must be URL-encoded as `%40`.

The archive folder (`Marketing` in the examples above) must exist in Thunderbird before running the script. Create it by right-clicking your inbox → **New Subfolder**.

---

## First Run

Always test with `--dry-run` before archiving for real:

```bash
# Preview what would be archived (verbose — shows every decision)
python archive_marketing.py --dry-run --verbose

# Preview for a specific year only
python archive_marketing.py --date-from 2025-01-01 --date-to 2025-12-31 --dry-run --verbose

# Silent dry run — just the summary count
python archive_marketing.py --dry-run-summary
```

Inspect the output. If you see legitimate emails in the `✗` (archive) list, add their sender to the `exclude` list in your config.

When satisfied:

```bash
python archive_marketing.py
```

---

## Scheduling

> **Important:** Thunderbird must be open and the thunderbird-mcp extension connected when the script runs.

### Windows — Task Scheduler

```powershell
$action = New-ScheduledTaskAction `
    -Execute "python.exe" `
    -Argument '"C:\path\to\archive_marketing.py"' `
    -WorkingDirectory "C:\path\to\scripts-archive-marketing"

$trigger = New-ScheduledTaskTrigger -Daily -At "06:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName "ArchiveMarketingEmails" `
    -TaskPath "\MyScripts\" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings
```

`-StartWhenAvailable` ensures the task runs the next time Thunderbird is open if it was closed at the scheduled time.

### macOS / Linux — cron

```cron
# Run at 06:00 every day
0 6 * * * cd /path/to/scripts-archive-marketing && python3 archive_marketing.py >> /var/log/archive_marketing.log 2>&1
```

---

## Windows-Specific Notes

- Python must be on the `PATH`, or use the full path to `python.exe` in Task Scheduler
- If you see emoji rendering errors in the terminal: `python -X utf8 archive_marketing.py`
- The script forces UTF-8 stdout/stderr on Windows automatically via `reconfigure()` — this covers most cases
- The default `connection_file` path uses `%TEMP%` which on Windows typically resolves to `C:\Users\<user>\AppData\Local\Temp\thunderbird-mcp\connection.json`

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `[ERROR] Connection file not found` | Thunderbird not running | Start Thunderbird, wait ~5s, retry |
| `[ERROR] Connection file not found` | Extension not installed | Install thunderbird-mcp, restart Thunderbird |
| `Authentication failed (403)` | Session token expired | Restart Thunderbird |
| `MCP error: Invalid parameters` | Wrong folder URI | Right-click folder → Properties → copy exact URI |
| Nothing archived, no errors | Folder URI mismatch | Run `--dry-run --verbose` and check sender/subject output |
| Too slow / Gmail rate limit | `fetch_delay` too short | Increase to `3.0` or higher |
| Legitimate email archived | Pattern too broad | Add sender regex to `exclude` list |
| `UnicodeEncodeError` on Windows | Terminal encoding | Use `python -X utf8 archive_marketing.py` |
