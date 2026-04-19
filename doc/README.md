# Thunderbird Inbox Marketing Archiver — Documentation

> **Version:** 1.3.0 | **Language:** Python 3.8+ | **Dependencies:** None (stdlib only)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Documentation Index](#documentation-index)

---

## Overview

`archive_marketing.py` is a zero-dependency Python script that automatically classifies and bulk-archives marketing emails from a Thunderbird inbox — **without opening or reading a single email body**.

It connects to a locally running Thunderbird instance through the [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) HTTP bridge, fetches emails in paginated batches, applies a multi-tier regex classification engine against sender address and subject line only, and moves identified marketing emails to a designated archive folder via IMAP.

Everything runs locally. No cloud services, no email credentials stored by the script, no network traffic leaving the machine.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Privacy-first classification** | Only sender and subject are read — email bodies are never fetched |
| **Multi-tier regex engine** | Weighted scoring: safe allowlist → strong sender → subject keywords → weak combos |
| **Bulk archiving** | Moves up to 50 messages per API call; handles thousands of emails per run |
| **Date range filtering** | `--date-from` / `--date-to` to target a specific year or period |
| **Dry-run mode** | Preview what would be archived without touching any email |
| **Multilingual patterns** | English and Portuguese (BR) promotional keywords built-in |
| **HTML email report** | Sends an HTML summary via Thunderbird after each run |
| **Config layering** | CLI flags → env vars → JSON config file → built-in defaults |
| **Resume support** | `--start-offset` to continue interrupted runs |
| **CSV export** | Every classification decision logged to a CSV file |
| **Zero dependencies** | Python stdlib only — no `pip install` required |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.8+ |
| Email client | Mozilla Thunderbird (local, must be running) |
| IMAP bridge | [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) extension |
| Protocol | MCP JSON-RPC 2.0 over HTTP (`localhost` only) |
| Classification | Python `re` module (compiled regex, `re.VERBOSE`) |
| HTTP client | `urllib.request` (stdlib) |
| Config | `argparse` + `json` + `os.environ` |
| Testing | `unittest` (stdlib) |
| CI | GitHub Actions (Python 3.8–3.12, Ubuntu/Windows/macOS) |

---

## How It Works

```
Thunderbird (running locally)
        │
        │  thunderbird-mcp extension
        │  HTTP server: localhost:8765
        │  Auth token: %TEMP%\thunderbird-mcp\connection.json
        ▼
archive_marketing.py
        │
        ├── 1. load_connection()   — read token + port
        ├── 2. fetch_page()        — getRecentMessages (paginated)
        ├── 3. classify()          — 4-tier regex scoring (sender + subject)
        ├── 4. move_emails()       — updateMessage (bulk IMAP move)
        ├── 5. cleanup_prev_reports() — move old report emails out of inbox
        └── 6. send_report_email() — HTML summary via sendMail
```

Classification is a pure function with no side effects. It never touches the network or filesystem — only the four compiled regex patterns.

---

## Quick Start

### Prerequisites

1. [Mozilla Thunderbird](https://www.thunderbird.net) installed and **running**
2. [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) extension installed and showing **Connected**
3. Python 3.8+

### Install

```bash
git clone https://github.com/rodrigoazlima/scripts-archive-marketing.git
cd scripts-archive-marketing
```

No `pip install` needed.

### Configure

```bash
cp config.example.json ~/.config/archive_marketing/config.json
# Edit with your actual IMAP folder URIs
```

Minimum required settings:

```json
{
  "inbox":          "imap://you%40gmail.com@imap.gmail.com/INBOX",
  "archive_folder": "imap://you%40gmail.com@imap.gmail.com/Marketing"
}
```

> **Tip:** Find your IMAP URI by right-clicking a folder in Thunderbird → Properties.

### Dry run first

```bash
python archive_marketing.py --dry-run --verbose
```

### Run for real

```bash
python archive_marketing.py
```

### Run for a specific year

```bash
python archive_marketing.py --date-from 2025-01-01 --date-to 2025-12-31 --dry-run
```

---

## Project Structure

```
scripts-archive-marketing/
├── archive_marketing.py       # Entire application — single file
├── config.example.json        # Example configuration (copy to ~/.config/…)
├── tests/
│   ├── __init__.py
│   └── test_classification.py # 40 unit tests for classify()
├── doc/                       # This documentation
├── logs/                      # Runtime log files (gitignored)
├── .github/
│   ├── workflows/ci.yml       # GitHub Actions: test + lint (5 Python versions × 3 OS)
│   └── ISSUE_TEMPLATE/        # Bug report and feature request templates
├── README.md                  # User-facing readme
├── LICENSE                    # GNU GPL v3
└── .gitignore
```

---

## Documentation Index

| File | Description |
|------|-------------|
| [architecture.md](architecture.md) | System architecture, component diagram, design decisions |
| [file-structure.md](file-structure.md) | Full directory tree with file-level explanations |
| [setup.md](setup.md) | Installation, configuration, env vars, scheduling |
| [api.md](api.md) | All public functions — parameters, return types, examples |
| [modules/classification.md](modules/classification.md) | Classification engine — regex tiers, logic, extending patterns |
| [modules/mcp-client.md](modules/mcp-client.md) | Thunderbird MCP HTTP client — protocol, error handling |
| [modules/config.md](modules/config.md) | Configuration system — layering, env vars, CLI flags |
| [modules/reporting.md](modules/reporting.md) | Email reporting and previous-report cleanup |
| [dependencies.md](dependencies.md) | External dependencies, licenses, security notes |
| [glossary.md](glossary.md) | Domain-specific terms and acronyms |
| [contributing.md](contributing.md) | Contribution guide, coding standards, testing |
| [changelog.md](changelog.md) | Version history and change log |
