# Public API Reference

All public functions in `archive_marketing.py`. Internal helpers prefixed with `_` are documented in the relevant module files under `modules/`.

## Table of Contents

- [classify()](#classify)
- [load_config()](#load_config)
- [merge_config()](#merge_config)
- [validate_connection_file()](#validate_connection_file)
- [load_connection()](#load_connection)
- [fetch_page()](#fetch_page)
- [move_emails()](#move_emails)
- [open_csv_writer()](#open_csv_writer)
- [ensure_reports_folder()](#ensure_reports_folder)
- [cleanup_prev_reports()](#cleanup_prev_reports)
- [send_report_email()](#send_report_email)
- [run()](#run)
- [build_parser()](#build_parser)

---

## `classify()`

```python
def classify(
    sender: str,
    subject: str,
    exclude_patterns: Optional[List[re.Pattern]] = None,
) -> Tuple[bool, str]
```

Classify a single email as marketing or legitimate using the 4-tier regex pipeline.

**This is a pure function** — no side effects, no I/O, no global state mutation. Safe to call from any context.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `sender` | `str` | Full From address string, e.g. `"Acme <news@acme.com>"` |
| `subject` | `str` | Subject line of the email |
| `exclude_patterns` | `Optional[List[re.Pattern]]` | User-compiled regex patterns; matching emails are always kept |

### Returns

`Tuple[bool, str]` — `(is_marketing, reason)`

| `is_marketing` | `reason` value | Tier |
|----------------|----------------|------|
| `False` | `"user-exclude"` | 1 — user exclude list matched |
| `False` | `"safe-allowlist"` | 2 — safe sender allowlist matched |
| `True` | `"sender:strong"` | 3 — strong marketing sender matched |
| `True` | `"subject:match"` | 4 — marketing subject keyword matched |
| `True` | `"sender:noreply+subject:weak"` | 5 — weak combo matched |
| `False` | `"keep"` | 6 — default, no rule matched |

### Example

```python
from archive_marketing import classify
import re

# Basic usage
is_mkt, reason = classify(
    "Mailchimp <campaigns@mc.us12.list-manage.com>",
    "Your weekly digest is ready"
)
# → (True, "sender:strong")

# With user exclude patterns
patterns = [re.compile(r"payroll@mycompany\.com", re.IGNORECASE)]
is_mkt, reason = classify(
    "Payroll <payroll@mycompany.com>",
    "Your salary slip for March",
    exclude_patterns=patterns,
)
# → (False, "user-exclude")

# Safe allowlist
is_mkt, reason = classify(
    "GitHub <noreply@github.com>",
    "[GitHub] Please verify your device"
)
# → (False, "safe-allowlist")
```

---

## `load_config()`

```python
def load_config(path: Optional[str]) -> Dict
```

Load settings from a JSON config file.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `Optional[str]` | Explicit path to config file, or `None` to use default location |

### Returns

`Dict` — key/value settings from the file. Missing keys are not filled in — that happens in `merge_config()`.

### Raises

- `SystemExit` — if the file exists but is not valid JSON

### Behavior

- If `path` is `None`, tries `~/.config/archive_marketing/config.json`
- If the file does not exist, returns an empty dict (not an error)
- Prints `[config] Loaded from <path>` on success

---

## `merge_config()`

```python
def merge_config(cli_args: argparse.Namespace, file_cfg: Dict) -> argparse.Namespace
```

Apply config file and environment variable values for any CLI option that was not explicitly set.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cli_args` | `argparse.Namespace` | Parsed CLI arguments (from `build_parser().parse_args()`) |
| `file_cfg` | `Dict` | Dict from `load_config()` |

### Returns

`argparse.Namespace` — the same object with env/file values merged in.

### Priority

`CLI > environment variable > config file > built-in default`

A setting is only overridden from env/file if its current value equals the argparse default (i.e., the user did not explicitly set it on the command line).

---

## `validate_connection_file()`

```python
def validate_connection_file(path: str) -> None
```

Warn if the thunderbird-mcp connection file has world-readable permissions.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Filesystem path to `connection.json` |

### Behavior

- On POSIX systems: warns if group-read or world-read bits are set; prints `chmod 600` suggestion
- On Windows: best-effort only (permission model is different)
- Non-critical: `OSError` is silently ignored

---

## `load_connection()`

```python
def load_connection(connection_file: str) -> Tuple[str, int]
```

Read the Thunderbird MCP auth token and port from the connection file.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `connection_file` | `str` | Path to the thunderbird-mcp `connection.json` |

### Returns

`Tuple[str, int]` — `(token, port)`

### Raises

- `SystemExit` — with a user-friendly checklist message if the file is missing, malformed, or not valid JSON

---

## `fetch_page()`

```python
def fetch_page(
    token: str,
    port: int,
    inbox: str,
    offset: int,
    page_size: int,
    days_back: int,
) -> Tuple[List[Dict], int]
```

Fetch one page of inbox messages via the MCP `getRecentMessages` tool.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | Bearer auth token from `connection.json` |
| `port` | `int` | TCP port the thunderbird-mcp extension listens on |
| `inbox` | `str` | IMAP folder URI of the source folder |
| `offset` | `int` | Number of messages to skip (pagination) |
| `page_size` | `int` | Maximum messages to return |
| `days_back` | `int` | Only return messages newer than this many days |

### Returns

`Tuple[List[Dict], int]` — `(messages, total_count)`

Each message dict contains at minimum: `id`, `author`, `subject`. May also contain `date` or similar timestamp fields depending on the thunderbird-mcp version.

---

## `move_emails()`

```python
def move_emails(
    token: str,
    port: int,
    inbox: str,
    message_ids: List[str],
    destination: str,
) -> int
```

Move a batch of messages to the destination folder via the MCP `updateMessage` tool.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | Bearer auth token |
| `port` | `int` | MCP bridge port |
| `inbox` | `str` | Source IMAP folder URI |
| `message_ids` | `List[str]` | List of message IDs to move |
| `destination` | `str` | Destination IMAP folder URI |

### Returns

`int` — number of messages successfully moved (from `result["updated"]`, falls back to `len(message_ids)`)

---

## `open_csv_writer()`

```python
def open_csv_writer(path: str) -> Tuple[IO, csv.DictWriter]
```

Open a CSV file for writing classification results.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Output file path |

### Returns

`Tuple[IO, csv.DictWriter]` — `(file_handle, writer)`

### CSV columns

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 timestamp of the classification batch |
| `sender` | Full From address string |
| `subject` | Subject line |
| `is_marketing` | `True` or `False` |
| `reason` | Classification reason label |

---

## `ensure_reports_folder()`

```python
def ensure_reports_folder(token: str, port: int, reports_folder: str) -> bool
```

Ensure the reports folder exists in Thunderbird; create it if not found.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | MCP auth token |
| `port` | `int` | MCP bridge port |
| `reports_folder` | `str` | Full IMAP URI of the desired reports folder |

### Returns

`bool` — `True` if the folder exists or was successfully created, `False` on failure.

---

## `cleanup_prev_reports()`

```python
def cleanup_prev_reports(
    token: str,
    port: int,
    inbox: str,
    reports_folder: str,
    move_batch: int = 50,
) -> int
```

Move previous archive-run report emails (identified by subject prefix `[Archive Report]`) from inbox to `reports_folder`.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | MCP auth token |
| `port` | `int` | MCP bridge port |
| `inbox` | `str` | Source IMAP folder URI |
| `reports_folder` | `str` | Destination IMAP folder URI |
| `move_batch` | `int` | Max message IDs per move request (default: `50`) |

### Returns

`int` — number of report emails moved.

### Behavior

- Scans the entire inbox (up to 3650 days back) looking for subjects starting with `[Archive Report]`
- Moves all matches regardless of whether a new report will be sent
- Called after the main archiving loop, before `send_report_email()`

---

## `send_report_email()`

```python
def send_report_email(
    token: str,
    port: int,
    args: argparse.Namespace,
    archived: int,
    kept: int,
    reason_counts: Dict[str, int],
    run_duration: float,
) -> None
```

Send an HTML email summary report via Thunderbird's `sendMail` MCP tool.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | MCP auth token |
| `port` | `int` | MCP bridge port |
| `args` | `argparse.Namespace` | Merged config (for inbox URI, dry_run flag, etc.) |
| `archived` | `int` | Total emails archived in this run |
| `kept` | `int` | Total emails kept in this run |
| `reason_counts` | `Dict[str, int]` | Classification reason → count breakdown |
| `run_duration` | `float` | Wall-clock seconds the run took |

### Behavior

- Auto-detects sender address from Thunderbird's first IMAP account via `listAccounts`
- Falls back to `args.report_to` if auto-detection fails
- Exits with a warning (no exception) if no recipient can be determined
- Subject format: `[Archive Report] N archived — Day, Month DD, YYYY`

---

## `run()`

```python
def run(args: argparse.Namespace) -> None
```

Main orchestration entry point. Paginate inbox, classify, and archive marketing emails.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `args` | `argparse.Namespace` | Fully merged configuration (output of `merge_config()`) |

### Behavior

1. Load connection (token + port)
2. Compute effective `days_back` if `date_from` is set
3. Compile user exclude patterns
4. Open CSV writer if `--export-csv` specified
5. Paginated loop: fetch → date-filter → classify → archive
6. Move previous report emails (`cleanup_prev_reports`)
7. Send HTML report (`send_report_email`) if configured
8. Print final summary

---

## `build_parser()`

```python
def build_parser() -> argparse.ArgumentParser
```

Build and return the CLI argument parser.

### Returns

`argparse.ArgumentParser` — configured with all flags and their defaults from `DEFAULTS`.

### Usage

```python
parser = build_parser()
args = parser.parse_args()
# or for testing:
args = parser.parse_args(["--dry-run", "--date-from", "2025-01-01"])
```
