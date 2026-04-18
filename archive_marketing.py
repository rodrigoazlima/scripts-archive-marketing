#!/usr/bin/env python3
"""
archive_marketing.py — Thunderbird Inbox Marketing Archiver

Reads emails from your IMAP inbox via the Thunderbird MCP HTTP bridge,
classifies them as marketing or legitimate using sender/subject pattern
matching (no email body is ever opened), and bulk-moves marketing emails
to a designated archive folder.

Requirements:
  - Mozilla Thunderbird with the thunderbird-mcp extension installed and running
    https://github.com/joelpurra/thunderbird-mcp
  - Python 3.8+  (stdlib only — no pip installs needed)

Usage:
  python archive_marketing.py [options]

See README.md for full setup instructions.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


# ---------------------------------------------------------------------------
# Default configuration — override via CLI flags or environment variables
# ---------------------------------------------------------------------------

DEFAULT_CONNECTION_FILE = str(
    Path(os.environ.get("TEMP", "/tmp")) / "thunderbird-mcp" / "connection.json"
)

DEFAULT_INBOX = "imap://you%40gmail.com@imap.gmail.com/INBOX"
DEFAULT_ARCHIVE_FOLDER = "imap://you%40gmail.com@imap.gmail.com/Marketing"

DEFAULT_PAGE_SIZE = 100     # emails fetched per API call
DEFAULT_FETCH_DELAY = 2.0   # seconds between page fetches  (IMAP rate limit)
DEFAULT_MOVE_DELAY = 1.5    # seconds between bulk-move calls
DEFAULT_MOVE_BATCH = 50     # max IDs per single move call
DEFAULT_START_OFFSET = 0    # resume from a specific page offset
DEFAULT_DAYS_BACK = 3650    # look back ~10 years


# ---------------------------------------------------------------------------
# Marketing sender patterns
# Extend this list to catch senders specific to your region/subscriptions.
# ---------------------------------------------------------------------------

MARKETING_SENDER_PATTERN = re.compile(
    r"""
    aliexpress | mercadolivre | shopee | ebay | shein |
    noreply.*promo | promo.*noreply |
    linkedin.*jobs | jobalert | indeed\.com | glassdoor | ziprecruiter |
    levels\.fyi | medium\.com | substack |
    producthunt |
    spotify | netflix | steam | epicgames |
    mailchimp | sendgrid | klaviyo |
    binance | coinbase |
    ae-best | newarrival\.aliexpress | promotion@ |
    komoot |
    emails\.decolar\.com |
    mail\.perplexity\.ai |
    signalrgb\.com |
    comunicacao\.serasaexperian |
    99pay@99app | 99app\.com |
    updates\.thundercompute |
    mail\.supernova\.io |
    engage\.affinity |
    mailgun\.patreon\.com
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Marketing subject patterns
# ---------------------------------------------------------------------------

MARKETING_SUBJECT_PATTERN = re.compile(
    r"""
    desconto | oferta | promo[çc] | liquida[çc] | \bsale\b | \bdeals?\b |
    \d+\%\s*off | free\s+trial | assine | cupom | coupon | frete\s*gr[áa]tis |
    newsletter | incr[íi]vel | imperd[íi]vel | n[ãa]o\s+perca |
    top\s+vagas | vagas\s+para\s+voc[eê] | jobs\s+for\s+you |
    talent\s+pool |
    trial.*ended | join.*community |
    cart[ãa]o.*esperando | esperando.*por\s+voc[eê] |
    melhore\s+sua\s+vida | organize\s+suas\s+finan[çc]as |
    sem\s+complicar | [úu]ltima\s+chance |
    fastest\s+way.*answer | popular.*ways.*use |
    next\s+answer.*search | giveaway | feeling\s+lucky |
    product\s+updates.*new\s+features | import\s+figma |
    create\s+an\s+instance | welcome\s+to\s+thunder |
    mega\s+promo | app\s+days | madrugol | fds\s+azul |
    voos\s+a\s+partir | pacotes\s+com | hot[eé]is\s+e\s+pacotes
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Safe-sender allowlist — these are NEVER classified as marketing
# regardless of subject line.
# ---------------------------------------------------------------------------

SAFE_SENDER_PATTERN = re.compile(
    r"no-reply@accounts\.google\.com|noreply@google\.com",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Thunderbird MCP HTTP client
# ---------------------------------------------------------------------------

_request_counter = 0


def _mcp_call(token: str, port: int, tool_name: str, arguments: dict) -> object:
    """Send a single MCP tools/call request to the Thunderbird HTTP bridge."""
    global _request_counter
    _request_counter += 1

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": _request_counter,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read())

    # Unwrap MCP result envelope:
    # { "result": { "content": [{ "type": "text", "text": "<json string>" }] } }
    content = raw.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        return json.loads(content[0]["text"])

    raise RuntimeError(f"Unexpected MCP response: {raw}")


def load_connection(connection_file: str) -> tuple[str, int]:
    """Read the Thunderbird MCP auth token and port from the connection file."""
    try:
        with open(connection_file, encoding="utf-8") as f:
            data = json.load(f)
        return data["token"], data["port"]
    except FileNotFoundError:
        sys.exit(
            f"\n[ERROR] Connection file not found: {connection_file}\n"
            "Make sure Thunderbird is running and the thunderbird-mcp extension is active.\n"
        )
    except KeyError as e:
        sys.exit(f"\n[ERROR] Malformed connection file — missing key: {e}\n")


def fetch_page(token, port, inbox, offset, page_size, days_back) -> tuple[list, int]:
    """Fetch one page of inbox messages. Returns (emails, total_count)."""
    result = _mcp_call(token, port, "getRecentMessages", {
        "folderPath": inbox,
        "maxResults": page_size,
        "offset": offset,
        "daysBack": days_back,
    })

    if isinstance(result, dict) and "messages" in result:
        return result["messages"], result.get("totalMatches", 0)
    if isinstance(result, list):
        return result, 0

    return [], 0


def move_emails(token, port, inbox, message_ids: list[str], destination: str) -> int:
    """Move a list of message IDs to the destination folder. Returns count moved."""
    result = _mcp_call(token, port, "updateMessage", {
        "folderPath": inbox,
        "messageIds": message_ids,
        "moveTo": destination,
    })
    return result.get("updated", len(message_ids))


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def is_marketing(sender: str, subject: str) -> bool:
    if SAFE_SENDER_PATTERN.search(sender):
        return False
    return bool(
        MARKETING_SENDER_PATTERN.search(sender)
        or MARKETING_SUBJECT_PATTERN.search(subject)
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(args):
    token, port = load_connection(args.connection_file)

    total_archived = 0
    total_kept = 0
    offset = args.start_offset
    page_num = 0

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{'='*60}")
    print(f"  {mode}Thunderbird Inbox Marketing Archiver")
    print(f"{'='*60}")
    print(f"  Inbox:   {args.inbox}")
    print(f"  Archive: {args.archive_folder}")
    print(f"  Start offset: {offset} | Page size: {args.page_size}")
    print(f"  Fetch delay: {args.fetch_delay}s | Move delay: {args.move_delay}s")
    print(f"{'='*60}\n")

    while True:
        page_num += 1
        print(f"[Page {page_num:>3}] offset={offset:<6}", end=" ... ", flush=True)

        # Fetch with retry
        for attempt in range(3):
            try:
                emails, total = fetch_page(
                    token, port, args.inbox, offset, args.page_size, args.days_back
                )
                break
            except Exception as exc:
                if attempt == 2:
                    print(f"\n[ERROR] Failed after 3 attempts: {exc}")
                    print("Stopping.")
                    break
                wait = 10 * (attempt + 1)
                print(f"\n  Retry {attempt+1}/3 in {wait}s ({exc})", end=" ", flush=True)
                time.sleep(wait)
        else:
            break

        print(f"fetched {len(emails):<4}  (inbox total: {total})", flush=True)

        if not emails:
            print("  No more emails. Done!\n")
            break

        # Classify
        marketing_ids = []
        for email in emails:
            sender  = email.get("author", "")
            subject = email.get("subject", "")
            mid     = email.get("id", "")
            if is_marketing(sender, subject):
                marketing_ids.append(mid)
                if args.verbose:
                    print(f"    ARCHIVE  {sender[:45]:<45}  {subject[:50]}")
            else:
                if args.verbose:
                    print(f"    keep     {sender[:45]:<45}  {subject[:50]}")

        kept = len(emails) - len(marketing_ids)
        print(f"         Marketing: {len(marketing_ids):<4}  Keeping: {kept}", flush=True)

        # Archive in sub-batches
        if marketing_ids and not args.dry_run:
            for i in range(0, len(marketing_ids), args.move_batch):
                batch = marketing_ids[i : i + args.move_batch]
                try:
                    moved = move_emails(token, port, args.inbox, batch, args.archive_folder)
                    print(f"         Archived {moved} emails (batch {i//args.move_batch + 1})", flush=True)
                except Exception as exc:
                    print(f"         [ERROR] Move failed: {exc}", flush=True)
                if i + args.move_batch < len(marketing_ids):
                    time.sleep(args.move_delay)

        total_archived += len(marketing_ids)
        total_kept += kept

        if len(emails) < args.page_size:
            print("  Last page reached. Done!\n")
            break

        offset += args.page_size
        print(
            f"         Running total: {total_archived} archived, {total_kept} kept"
            f"  — sleeping {args.fetch_delay}s...\n",
            flush=True,
        )
        time.sleep(args.fetch_delay)

    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"  DRY RUN complete — no emails were moved.")
        print(f"  Would have archived: {total_archived}")
    else:
        print(f"  COMPLETE")
        print(f"  Archived : {total_archived}")
    print(f"  Kept     : {total_kept}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="archive_marketing.py",
        description="Archive marketing emails from Thunderbird inbox via the thunderbird-mcp bridge.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--inbox",            default=DEFAULT_INBOX,
                   help="IMAP folder URI of your inbox.")
    p.add_argument("--archive-folder",   default=DEFAULT_ARCHIVE_FOLDER,
                   help="IMAP folder URI to move marketing emails into.")
    p.add_argument("--connection-file",  default=DEFAULT_CONNECTION_FILE,
                   help="Path to thunderbird-mcp connection.json.")
    p.add_argument("--page-size",        type=int,   default=DEFAULT_PAGE_SIZE,
                   help="Emails fetched per API call.")
    p.add_argument("--fetch-delay",      type=float, default=DEFAULT_FETCH_DELAY,
                   help="Seconds to wait between page fetches.")
    p.add_argument("--move-delay",       type=float, default=DEFAULT_MOVE_DELAY,
                   help="Seconds to wait between bulk-move calls.")
    p.add_argument("--move-batch",       type=int,   default=DEFAULT_MOVE_BATCH,
                   help="Max message IDs per single move request.")
    p.add_argument("--start-offset",     type=int,   default=DEFAULT_START_OFFSET,
                   help="Skip the first N emails (resume support).")
    p.add_argument("--days-back",        type=int,   default=DEFAULT_DAYS_BACK,
                   help="How many days back to scan.")
    p.add_argument("--dry-run",          action="store_true",
                   help="Classify emails but do not move them.")
    p.add_argument("--verbose", "-v",    action="store_true",
                   help="Print every email classification decision.")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    run(args)
