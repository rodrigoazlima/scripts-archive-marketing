# Module: Configuration System

## Table of Contents

- [Overview](#overview)
- [DEFAULTS Dict](#defaults-dict)
- [Configuration Sources](#configuration-sources)
- [load_config()](#load_config)
- [merge_config()](#merge_config)
- [Date Range Configuration](#date-range-configuration)
- [Exclude Patterns](#exclude-patterns)
- [Effective days_back Computation](#effective-days_back-computation)

---

## Overview

The configuration system lives in `archive_marketing.py` from line ~60 to ~562. It implements a **four-layer priority stack** that merges settings from CLI flags, environment variables, a JSON config file, and built-in defaults — in that order.

The result is an `argparse.Namespace` object passed to `run()`. Every configurable behavior of the script is controlled through this object.

---

## DEFAULTS Dict

`DEFAULTS` (line ~63) is the single source of truth for all built-in defaults. It serves two purposes:

1. Provides fallback values when no other source specifies a setting
2. Is used by `merge_config()` to detect whether a CLI argument was explicitly set by the user (by comparing the current value to the default)

```python
DEFAULTS: Dict = {
    "inbox":           "imap://you%40gmail.com@imap.gmail.com/INBOX",
    "archive_folder":  "imap://you%40gmail.com@imap.gmail.com/Marketing",
    "connection_file": str(Path(_TEMP) / "thunderbird-mcp" / "connection.json"),
    "page_size":       100,
    "fetch_delay":     2.0,
    "move_delay":      1.5,
    "move_batch":      50,
    "start_offset":    0,
    "days_back":       3650,
    "dry_run":         False,
    "verbose":         False,
    "dry_run_summary": False,
    "export_csv":      None,
    "exclude":         [],
    "date_from":       None,
    "date_to":         None,
    "send_report":          False,
    "report_to":            None,
    "skip_report_if_empty":    True,
    "cleanup_prev_reports":    True,
    "reports_folder":          None,
}
```

---

## Configuration Sources

```mermaid
flowchart TB
    A[build_parser().parse_args()\nCLI flags]
    B[Environment variables\nARCHIVE_*]
    C[JSON config file\n~/.config/archive_marketing/config.json]
    D[DEFAULTS dict\nBuilt-in values]

    D -->|filled by| C
    C -->|overridden by| B
    B -->|overridden by| A
    A -->|final| NS[argparse.Namespace\npassed to run()]
```

### Source 1: CLI flags (highest priority)

Defined in `build_parser()`. argparse sets each attribute on the `Namespace` to its default from `DEFAULTS` if the user does not provide the flag. `merge_config()` detects this by comparing the value to `DEFAULTS[attr]`.

### Source 2: Environment variables

Mapped in `merge_config()` via `ENV_MAP`:

```python
ENV_MAP = {
    "inbox":           "ARCHIVE_INBOX",
    "archive_folder":  "ARCHIVE_FOLDER",
    "connection_file": "ARCHIVE_CONNECTION_FILE",
    "page_size":       "ARCHIVE_PAGE_SIZE",
    "fetch_delay":     "ARCHIVE_FETCH_DELAY",
    "move_delay":      "ARCHIVE_MOVE_DELAY",
    "start_offset":    "ARCHIVE_START_OFFSET",
    "days_back":       "ARCHIVE_DAYS_BACK",
    "send_report":          "ARCHIVE_SEND_REPORT",
    "report_to":            "ARCHIVE_REPORT_TO",
    "skip_report_if_empty":    "ARCHIVE_SKIP_REPORT_IF_EMPTY",
    "cleanup_prev_reports":    "ARCHIVE_CLEANUP_PREV_REPORTS",
    "reports_folder":          "ARCHIVE_REPORTS_FOLDER",
}
```

Type coercion is automatic:
- `bool` settings: `"1"`, `"true"`, `"yes"` → `True` (case-insensitive); anything else → `False`
- `int` settings: `int(raw)`
- `float` settings: `float(raw)`
- `str` settings: used as-is

### Source 3: JSON config file

Loaded by `load_config()`. The default path is `~/.config/archive_marketing/config.json`. Override with `--config`.

The file is optional — if it does not exist, `load_config()` returns `{}` silently.

### Source 4: Built-in defaults (lowest priority)

The `DEFAULTS` dict. Applied by argparse for CLI flags and as the final fallback in `merge_config()`.

---

## `load_config()`

```python
def load_config(path: Optional[str]) -> Dict
```

Reads and JSON-parses the config file. Returns an empty dict if the file does not exist. Calls `sys.exit()` if the file exists but is not valid JSON (this is always a user error and should not be silently ignored).

```python
file_cfg = load_config(cli.config)  # cli.config = --config value or None
```

---

## `merge_config()`

```python
def merge_config(cli_args: argparse.Namespace, file_cfg: Dict) -> argparse.Namespace
```

The core of the priority system. For each configurable attribute:

1. If the current CLI value equals `DEFAULTS[attr]` (user did not explicitly set it):
   - If the corresponding env var exists → use env var value (type-coerced)
   - Else if the config file contains the key → use config file value
2. Otherwise → keep the CLI value (user explicitly set it)

**Special case — `exclude` list:** Unlike scalar settings, `exclude` is merged (CLI list + config file list), not overridden. Duplicates are removed via `set()`.

```python
file_excl = file_cfg.get("exclude", [])
cli_excl  = getattr(cli_args, "exclude", []) or []
combined  = list(set(file_excl + cli_excl))
cli_args.exclude = combined
```

---

## Date Range Configuration

`--date-from` and `--date-to` are CLI-only settings (no env var or config file equivalent). They take `YYYY-MM-DD` strings and are parsed by `_date_arg()` into `datetime.date` objects.

These settings are not in `ENV_MAP` — they are designed as run-specific overrides, not persistent configuration.

In `run()`, before the main loop:

```python
date_from_dt = datetime.combine(args.date_from, datetime.min.time()) if args.date_from else None
date_to_dt   = datetime.combine(args.date_to,   datetime.max.time()) if args.date_to   else None
```

`datetime.min.time()` → `00:00:00` — emails on the from-date are included  
`datetime.max.time()` → `23:59:59.999999` — emails on the to-date are included

---

## Exclude Patterns

The `exclude` setting accepts a list of regex strings. They are compiled in `run()`:

```python
exclude_patterns: List[re.Pattern] = []
for pat in (args.exclude or []):
    try:
        exclude_patterns.append(re.compile(pat, re.IGNORECASE))
    except re.error as e:
        print(f"[WARN] Invalid exclude pattern '{pat}': {e}", flush=True)
```

Invalid patterns emit a warning and are skipped — they do not cause the script to abort.

Each compiled pattern is tested against both sender AND subject. A match on either causes the email to be kept.

---

## Effective `days_back` Computation

When `--date-from` is specified, `days_back` is automatically adjusted in `run()` to cover the required historical range:

```python
if date_from_dt:
    days_needed = (datetime.now().date() - args.date_from).days + 1
    if days_needed > args.days_back:
        args.days_back = days_needed
```

This ensures the MCP `getRecentMessages` call fetches far enough back to reach `date_from`. The `+1` accounts for partial-day boundary alignment.

**Example:** Running on 2026-04-19 with `--date-from 2025-01-01`:
- `days_needed = (2026-04-19 − 2025-01-01).days + 1 = 474`
- If default `days_back = 3650`, no change (3650 > 474)
- If user had set `--days-back 30`, it would be overridden to 474

The `date_to` filter does not need to adjust `days_back` — emails newer than `date_to` are filtered client-side after fetching.
