---
name: Bug Report
about: Something isn't working as expected
labels: bug
---

## Description
<!-- Clear description of the bug -->

## Steps to Reproduce
1. Run `python archive_marketing.py --dry-run ...`
2. ...

## Expected Behavior
<!-- What should happen -->

## Actual Behavior
<!-- What actually happens — paste the exact error/output -->

```
paste output here
```

## Environment

| Field | Value |
|-------|-------|
| OS | <!-- Windows 11 / macOS 14 / Ubuntu 22.04 --> |
| Python version | <!-- python --version --> |
| Script version | <!-- python archive_marketing.py --version --> |
| Thunderbird version | <!-- Help → About Thunderbird --> |
| thunderbird-mcp version | <!-- from extension manager --> |

## Config (redact sensitive values)
<!-- Share your CLI flags or config.json, removing real IMAP URIs/tokens -->

```json
{
  "inbox": "imap://REDACTED@imap.gmail.com/INBOX",
  "archive_folder": "imap://REDACTED@imap.gmail.com/Marketing"
}
```
