# Changelog

All notable changes to this project are documented here.

Format: `## [version] — YYYY-MM-DD` with sections `### Added`, `### Changed`, `### Fixed`, `### Removed`.

---

## [1.3.0] — 2026-04-19

### Added

- `--date-from YYYY-MM-DD` — only process emails on or after this date
- `--date-to YYYY-MM-DD` — only process emails on or before this date
- Auto-computation of `days_back` when `--date-from` is specified (no manual override needed)
- `_parse_email_date()` — parses email date from multiple MCP field names and formats (Unix ms/s timestamps and ISO strings)
- `_date_arg()` — argparse type converter for date flags with clear error messages
- Per-page `Skipped(date): N` counter in terminal output when date filtering is active
- Date range shown in run header: `Range  : 2025-01-01 → 2025-12-31`

### Changed

- `datetime` import extended with `date as date_type` for type annotations

---

## [1.2.1] — 2026-04-18

### Fixed

- Corrected version label from 1.3.0 → 1.2.1 (the `cleanup_prev_reports`/`reports_folder` feature was a bugfix patch, not a minor release)

---

## [1.2.0] — 2026-04-18 *(corrected to 1.2.1)*

### Added

- `cleanup_prev_reports` — automatically moves previous `[Archive Report]` emails from inbox to `reports_folder` before each run
- `ensure_reports_folder()` — creates the reports IMAP folder if it does not exist
- `reports_folder` configuration option (config file, env var `ARCHIVE_REPORTS_FOLDER`, CLI `--reports-folder`)
- `--no-cleanup-prev-reports` flag to disable cleanup
- Reports folder auto-creation using `createFolder` MCP tool

### Changed

- Cleanup now runs unconditionally (regardless of whether a new report will be sent), ensuring old reports are always moved even on zero-archive runs

### Fixed

- Previous reports accumulated in inbox when `skip_report_if_empty` prevented a new report from being sent

---

## [1.1.0] — 2026-04-17

### Added

- `send_report` — HTML email summary report sent via Thunderbird after each run
- `report_to` — explicit report recipient (auto-detected from Thunderbird if not set)
- `skip_report_if_empty` — suppress report when no emails were archived (default: `true`)
- `_tb_identity()` — detects the user's email address from Thunderbird's `listAccounts`
- `send_report_email()` — inline-styled responsive HTML report with stats, breakdown, and run settings
- `--send-report`, `--report-to`, `--no-skip-report-if-empty` CLI flags
- Env vars: `ARCHIVE_SEND_REPORT`, `ARCHIVE_REPORT_TO`, `ARCHIVE_SKIP_REPORT_IF_EMPTY`

---

## [1.0.0] — 2026-04-16

### Added

- Initial release
- 4-tier regex classification engine (`classify()`)
- `SAFE_SENDER` allowlist (Google, GitHub, Apple security)
- `MARKETING_SENDER_STRONG` — 100+ marketing platform domains
- `MARKETING_SUBJECT` — promotional keywords in English and Portuguese (BR)
- `NOREPLY_SENDER` + `WEAK_SUBJECT` weak-combo tier
- Paginated inbox fetch via thunderbird-mcp `getRecentMessages`
- Bulk IMAP move via thunderbird-mcp `updateMessage`
- Configuration layering: CLI > env vars > JSON config file > defaults
- `--dry-run` and `--dry-run-summary` modes
- `--verbose` per-email classification output
- `--export-csv` — classification log export
- `--exclude` — user-defined always-keep patterns
- `--start-offset` — resume interrupted runs
- `--days-back` — historical scan range
- `validate_connection_file()` — POSIX permission warning for connection.json
- UTF-8 stdout/stderr reconfiguration for Windows
- 40 unit tests covering all classification tiers
- GitHub Actions CI: Python 3.8–3.12 × Ubuntu/Windows/macOS

---

## Template for Future Entries

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Added
- New feature or capability

### Changed
- Modification to existing behavior (note if this is a breaking change)

### Fixed
- Bug that was corrected

### Removed
- Feature or option that was removed
```
