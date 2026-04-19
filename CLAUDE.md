# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run tests (no dependencies needed)
python -m unittest tests.test_classification -v

# Run single test class
python -m unittest tests.test_classification.TestSafeAllowlist -v

# Lint
pip install ruff
ruff check archive_marketing.py tests/

# Dry run (no emails moved)
python archive_marketing.py --dry-run --verbose

# Syntax check
python -c "import archive_marketing; print('OK')"
```

## Architecture

Single-file script (`archive_marketing.py`) — no dependencies beyond Python stdlib. Talks to a locally running Thunderbird via the [thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp) HTTP bridge.

**Data flow:**
```
Thunderbird (running) → thunderbird-mcp HTTP bridge (localhost)
  → fetch_page() [getRecentMessages MCP call]
  → classify() [regex only — no body fetch]
  → move_emails() [updateMessage MCP call]
```

**Classification pipeline** (`classify()`, line 392) — first match wins:
1. User `--exclude` patterns → always keep
2. `SAFE_SENDER` allowlist (Google/GitHub/Apple security) → always keep
3. `MARKETING_SENDER_STRONG` (100+ platforms/domains) → always archive
4. `MARKETING_SUBJECT` (promo keywords, EN + PT-BR) → always archive
5. `NOREPLY_SENDER` + `WEAK_SUBJECT` combined → archive
6. Default → keep

**Config priority:** CLI flags > env vars (`ARCHIVE_*`) > `~/.config/archive_marketing/config.json` > built-in defaults (`DEFAULTS` dict, line 63). `merge_config()` applies this layering after argparse.

**MCP communication:** `_mcp_call()` (line 559) sends JSON-RPC 2.0 over HTTP with a bearer token from `connection.json`. Token + port are read at runtime from `%TEMP%\thunderbird-mcp\connection.json` (Windows) or `/tmp/thunderbird-mcp/connection.json`.

**Report flow:** After archiving, if `cleanup_prev_reports` is set, previous `[Archive Report]` emails are moved from inbox to `reports_folder` before a new HTML report is sent via `sendMail` MCP call.

## Extending patterns

The four classification regexes (`SAFE_SENDER`, `MARKETING_SENDER_STRONG`, `MARKETING_SUBJECT`, `NOREPLY_SENDER`, `WEAK_SUBJECT`) all use `re.VERBOSE` — add entries freely. Tests in `tests/test_classification.py` cover all tiers; add a test case when adding a new pattern.

## Version

`__version__` at line 55 — bump when releasing. Use semver: patch for bugfixes, minor for new patterns/features.
