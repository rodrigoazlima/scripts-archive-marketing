# Glossary

Terms and acronyms used throughout this project and its documentation.

---

## A

**Archive folder**  
An IMAP folder designated as the destination for classified marketing emails. Typically named `Marketing` or similar. Must exist in Thunderbird before the script runs. Configured via `archive_folder` in `config.json` or `--archive-folder` CLI flag.

**Author field**  
The MCP field name for the email sender. Equivalent to the IMAP/RFC 5322 `From:` header. The script reads `email.get("author", "")` from the MCP response.

---

## B

**Bearer token**  
An authentication credential in the format `Authorization: Bearer <token>`. The thunderbird-mcp extension generates a bearer token when Thunderbird starts, writes it to `connection.json`, and requires it on every HTTP request to the MCP bridge.

**Bulk move**  
Sending multiple message IDs in a single `updateMessage` MCP call instead of one call per email. Controlled by `move_batch` (default: 50 IDs per call). Dramatically reduces run time for large inboxes.

---

## C

**Classification**  
The process of determining whether an email is marketing or legitimate based on its sender address and subject line only. Implemented in the `classify()` function using a 4-tier regex pipeline.

**`connection.json`**  
File written by the thunderbird-mcp extension containing the current session's bearer token and port number. Located in `%TEMP%\thunderbird-mcp\` (Windows) or `/tmp/thunderbird-mcp/` (macOS/Linux). Rotated each time Thunderbird restarts.

---

## D

**`days_back`**  
Configuration parameter controlling how far back in time the MCP `getRecentMessages` call looks. Default: 3650 (~10 years). Auto-adjusted when `--date-from` is specified to ensure the requested date range is covered.

**Date range filtering**  
Client-side filtering of emails by their received date. Enabled by `--date-from` and/or `--date-to` CLI flags. Emails outside the range are skipped (not classified or archived). The MCP server still returns them; filtering happens in Python after fetching.

**Dry run**  
An execution mode (`--dry-run`) in which emails are classified but not moved. Useful for previewing what would be archived before committing to a live run.

---

## E

**Exclude list**  
A user-defined list of regex patterns. Any email whose sender OR subject matches any pattern in the exclude list is always kept, regardless of all other classification rules. Configured via `exclude` in `config.json` or repeated `--exclude` CLI flags.

---

## F

**False negative**  
A marketing email that the script fails to archive — it is classified as "keep" when it should be "archive". Caused by marketing senders/subjects that don't match any pattern. Reduce by extending `MARKETING_SENDER_STRONG` or `MARKETING_SUBJECT`.

**False positive**  
A legitimate email that is incorrectly archived. Caused by sender domains or subject keywords that match marketing patterns but shouldn't. Fix by adding the sender to the `exclude` list.

---

## I

**IMAP**  
Internet Message Access Protocol. The standard protocol for reading and managing email on a remote server. Thunderbird uses IMAP to communicate with Gmail, Office 365, and other email providers. The script never speaks IMAP directly — it delegates all IMAP communication to Thunderbird via the MCP bridge.

**IMAP URI**  
A URI identifying a specific IMAP folder, in the format:  
`imap://user%40domain.com@imap.server.com/FolderName`  
The `@` in the email address must be URL-encoded as `%40`. Find it by right-clicking a folder in Thunderbird → Properties.

---

## J

**JSON-RPC 2.0**  
A remote procedure call protocol encoded in JSON. The thunderbird-mcp extension exposes a JSON-RPC 2.0 over HTTP interface. All MCP tool calls use `"method": "tools/call"` with a `name` and `arguments` payload.

---

## M

**MCP (Model Context Protocol)**  
An open protocol for connecting AI tools to external systems. The thunderbird-mcp extension implements MCP to expose Thunderbird's email capabilities. In this project, MCP is used as a local automation API — not specifically for AI purposes.

**MCP bridge**  
The HTTP server component of the thunderbird-mcp extension. Listens on `localhost:8765` (or another configured port). Translates incoming MCP JSON-RPC calls into Thunderbird's internal API calls.

**Marketing email**  
For the purposes of this script: any email identified by the classification engine as coming from a marketing platform, containing promotional content, or exhibiting a combination of noreply sender and engagement-oriented subject. The definition is intentionally conservative — when in doubt, the script defaults to "keep".

---

## N

**noreply sender**  
An email address containing `noreply`, `no-reply`, `donotreply`, or `do-not-reply`. Used as a weak signal in tier 5 of the classification pipeline — insufficient to archive alone, but combined with a weak engagement subject, triggers archiving.

---

## O

**Offset**  
Pagination parameter for `getRecentMessages`. Specifies how many messages to skip. Incremented by `page_size` after each page. Configurable via `--start-offset` to resume an interrupted run.

---

## P

**Page size**  
Number of emails fetched per MCP call (default: 100). Higher values reduce the number of API calls but increase memory usage and the duration of individual calls.

**Pattern tier**  
One of the five classification rules applied in priority order. See [classification.md](modules/classification.md) for the full tier description.

**PT-BR**  
Brazilian Portuguese. `MARKETING_SUBJECT` contains promotional keywords in both English and Portuguese (Brazil) to match marketing emails from Brazilian e-commerce and service providers.

---

## R

**Rate limiting**  
Intentional sleep delays (`fetch_delay`, `move_delay`) inserted between MCP calls to prevent overwhelming the IMAP server or triggering provider-side throttling (e.g., Gmail's connection limits).

**Reason code**  
A short label returned by `classify()` identifying which rule triggered the classification decision. Values: `"user-exclude"`, `"safe-allowlist"`, `"sender:strong"`, `"subject:match"`, `"sender:noreply+subject:weak"`, `"keep"`.

**`re.VERBOSE`**  
A Python `re` flag (`re.X`) that allows regex patterns to span multiple lines with comments and arbitrary whitespace. Used for all classification patterns to make them readable and maintainable.

---

## S

**Safe allowlist**  
Tier 2 of the classification pipeline. A set of trusted sender address patterns (Google, GitHub, Apple security addresses) that always result in "keep" regardless of the subject line.

**Strong sender signal**  
Tier 3 of the classification pipeline. A match in `MARKETING_SENDER_STRONG` — known marketing platform domains that definitively identify an email as marketing regardless of subject.

---

## T

**Thunderbird**  
[Mozilla Thunderbird](https://www.thunderbird.net) — an open-source desktop email client. Used as the IMAP client and authentication layer. Must be running while the script executes.

**thunderbird-mcp**  
The Thunderbird extension ([joelpurra/thunderbird-mcp](https://github.com/joelpurra/thunderbird-mcp)) that exposes Thunderbird's functionality over a local HTTP/MCP interface.

---

## W

**Weak combo**  
Tier 5 of the classification pipeline. An email with a `noreply`-style sender address AND a weak engagement word in the subject (e.g., "tips", "reminder", "trending") is archived even though neither signal is strong enough individually.

---

## Z

**Zero-dependency**  
The design principle that `archive_marketing.py` requires no third-party packages (`pip install`). All imports are from the Python standard library. This allows the script to run in any Python 3.8+ environment without package management.
