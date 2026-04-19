# Module: Reporting

## Table of Contents

- [Overview](#overview)
- [HTML Email Report](#html-email-report)
  - [Report Trigger Logic](#report-trigger-logic)
  - [Sender Detection](#sender-detection)
  - [Report Content](#report-content)
  - [Subject Format](#subject-format)
- [Previous Report Cleanup](#previous-report-cleanup)
  - [How Cleanup Works](#how-cleanup-works)
  - [Reports Folder Auto-Creation](#reports-folder-auto-creation)
- [CSV Export](#csv-export)
- [Terminal Output](#terminal-output)
- [Configuration Reference](#configuration-reference)

---

## Overview

The reporting module provides two forms of output after each archiving run:

1. **HTML email report** — a styled summary sent via Thunderbird to the user's own inbox
2. **CSV export** — a per-email classification log written to a local file

Additionally, the **previous report cleanup** feature automatically moves old `[Archive Report]` emails out of the inbox before sending a new one, preventing report accumulation.

All reporting code lives in `archive_marketing.py` from line ~765 to ~1030.

---

## HTML Email Report

### Report Trigger Logic

The report is sent at the end of `run()` only when all of these conditions are true:

1. `args.send_report` is `True` (set via `--send-report`, env var, or config file)
2. Either `args.skip_report_if_empty` is `False`, OR `total_archived > 0`

```python
if getattr(args, "send_report", False):
    if total_archived == 0 and getattr(args, "skip_report_if_empty", True):
        print("[report] No emails archived — skipping report.", flush=True)
    else:
        send_report_email(token, port, args, total_archived, total_kept,
                          reason_counts, run_duration)
```

The default behavior (`skip_report_if_empty: true`) means a report is only sent when at least one email was archived. This prevents daily "0 archived" noise reports.

### Sender Detection

`send_report_email()` calls `_tb_identity()` to find the sender's email address:

```python
def _tb_identity(token: str, port: int) -> Tuple[str, str]:
    accounts = _mcp_call(token, port, "listAccounts", {})
    for acct in accounts:
        ids = acct.get("identities", [])
        if ids:
            return ids[0].get("email", ""), ids[0].get("name", "")
    return "", ""
```

The first identity from the first account is used. If `args.report_to` is explicitly configured, it overrides the auto-detected recipient. If neither is available, the report is skipped with a warning.

### Report Content

The HTML report is a self-contained responsive email with:

| Section | Content |
|---------|---------|
| **Header** | Run date, time, recipient |
| **Stats cards** | Archived count, Kept count, Total scanned, Duration |
| **Run settings table** | Inbox URI, Archive URI, Days scanned, Mode (live/dry) |
| **Classification breakdown** | All `reason → count` pairs sorted by frequency |
| **Footer** | Script version + GitHub link |

The HTML is inline-styled for maximum email client compatibility (no external CSS, no `<link>` tags).

**Duration formatting:**
- Under 60 seconds → `"42s"`
- 60 seconds or more → `"1.7m"`

### Subject Format

```
[Archive Report] {N} archived{dry_label} — {Day}, {Month} {DD}, {YYYY}
```

Example: `[Archive Report] 147 archived — Saturday, April 19, 2025`

The `[Archive Report]` prefix is a constant (`_REPORT_SUBJECT_PREFIX`) used by the cleanup feature to identify previous reports.

---

## Previous Report Cleanup

Because the report email is sent to the user's own inbox (via `sendMail`), it would accumulate with each run. The cleanup feature moves these old report emails to a designated folder before sending a new one.

### How Cleanup Works

`cleanup_prev_reports()` runs unconditionally when `cleanup_prev_reports` is `True` and `reports_folder` is configured — even if no new report will be sent (e.g., `skip_report_if_empty` and zero archived emails). This ensures old reports are always moved, not just when a new one is being sent.

**Process:**

```mermaid
flowchart TD
    A[cleanup_prev_reports called] --> B[ensure_reports_folder]
    B --> C{Folder exists?}
    C -->|No| D[createFolder via MCP]
    D --> E[Scan inbox, all pages]
    C -->|Yes| E
    E --> F{Subject starts with\n'[Archive Report]'?}
    F -->|Yes| G[Collect message ID]
    F -->|No| H[Skip]
    G --> I{More pages?}
    I -->|Yes| E
    I -->|No| J[move_emails in batches to reports_folder]
    J --> K[Print count moved]
```

Cleanup scans the **entire inbox** (up to 3650 days back), not just recent messages. This handles the case where a report was not cleaned up from a previous run.

### Reports Folder Auto-Creation

`ensure_reports_folder()` checks whether `reports_folder` exists in Thunderbird by calling `listFolders` on its parent URI. If not found, it calls `createFolder`.

URI parsing: the function splits on the last `/` to separate `parent_uri` from `folder_name`. If the URI has no `/` separating a folder name, cleanup is skipped with a warning.

Example:
```
reports_folder = "imap://you%40gmail.com@imap.gmail.com/Reports"
parent_uri     = "imap://you%40gmail.com@imap.gmail.com"
folder_name    = "Reports"
```

---

## CSV Export

When `--export-csv PATH` is specified, every classification decision is appended to a CSV file:

```csv
timestamp,sender,subject,is_marketing,reason
2025-04-19T06:00:01,Newsletter <news@mailchimp.com>,Your weekly digest,True,sender:strong
2025-04-19T06:00:01,GitHub <noreply@github.com>,[GitHub] Security alert,False,safe-allowlist
```

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | ISO 8601 | Classification batch time (same for all emails on one page) |
| `sender` | string | Full From address as returned by MCP |
| `subject` | string | Subject line as returned by MCP |
| `is_marketing` | bool | `True` or `False` |
| `reason` | string | Classification reason label |

The CSV file is opened at the start of `run()` and closed in the `finally` block, ensuring the file is flushed even if an exception occurs mid-run.

> **Note:** Date-filtered emails (skipped due to `--date-from`/`--date-to`) are not written to the CSV — only emails that went through `classify()`.

---

## Terminal Output

The main loop prints structured progress to stdout:

```
==============================================================
  Thunderbird Inbox Marketing Archiver  v1.3.0
  https://github.com/rodrigoazlima/scripts-archive-marketing
==============================================================
  Inbox  : imap://you%40gmail.com@imap.gmail.com/INBOX
  Archive: imap://you%40gmail.com@imap.gmail.com/Marketing
  Offset : 0  |  Page: 100  |  Delay: 2.0s
  Range  : 2025-01-01 → 2025-12-31
==============================================================

[Page   1] offset=0      ... fetched 100   (inbox total: ~1247)
           Marketing: 73    Keeping: 24  Skipped(date): 3
           Archived 73 (batch 1)
           Running total: 73 archived / 24 kept  — sleeping 2.0s...

[Page   2] offset=100    ... fetched 100   ...
...

==============================================================
  COMPLETE
  Archived : 892
  Kept     : 355

  Classification breakdown:
    sender:strong                           712
    subject:match                           134
    sender:noreply+subject:weak              46

  Exported : /path/to/output.csv
==============================================================
```

**`--dry-run-summary` mode** suppresses all per-page output and prints only the final summary block. Useful for cron jobs where you want just the count.

**`--verbose` / `-v`** adds per-email lines showing the classification decision:
```
    ✗ [sender:strong               ] Shopee <noreply@shopee.com.br>    Super Sale this weekend!
    ✓ [keep                        ] Bank <alerts@mybank.com>           Your statement is ready
```

---

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `send_report` | `false` | Enable HTML email reporting |
| `report_to` | `null` | Explicit recipient; auto-detected if empty |
| `skip_report_if_empty` | `true` | Skip report when zero emails archived |
| `cleanup_prev_reports` | `true` | Move old `[Archive Report]` emails before new run |
| `reports_folder` | `null` | IMAP URI for report email storage |
| `export_csv` | `null` | Path to CSV output file |
