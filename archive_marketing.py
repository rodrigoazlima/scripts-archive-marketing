#!/usr/bin/env python3
"""
archive_marketing.py — Thunderbird Inbox Marketing Archiver
https://github.com/rodrigoazlima/scripts-archive-marketing

Reads emails from your IMAP inbox via the Thunderbird MCP HTTP bridge,
classifies them as marketing or legitimate using sender/subject pattern
matching (no email body is ever opened), and bulk-moves marketing emails
to a designated archive folder.

Classification uses a weighted scoring system:
  - Strong signal  (known marketing platform/domain) → always archive
  - Subject match  (promotional keyword)             → always archive
  - Weak signals   (noreply sender + engagement subject combined) → archive
  - Exclude list   (user-defined allowlist patterns) → always keep
  - Safe allowlist (security/account alerts)         → always keep

Requirements:
  - Mozilla Thunderbird with thunderbird-mcp extension installed and running
    https://github.com/joelpurra/thunderbird-mcp
  - Python 3.8+  (stdlib only — no pip installs needed)

Configuration priority (highest → lowest):
  1. CLI flags
  2. Environment variables  (ARCHIVE_INBOX, ARCHIVE_FOLDER, …)
  3. Config file            (--config path, or ~/.config/archive_marketing/config.json)
  4. Built-in defaults

Usage:
  python archive_marketing.py [options]

See README.md for full setup and troubleshooting instructions.
"""

import argparse
import csv
import json
import os
import re
import stat
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Force UTF-8 stdout/stderr on Windows (handles emoji in folder paths/subjects)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

__version__ = "1.2.0"

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_TEMP = os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp"))

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
    "send_report":          False,
    "report_to":            None,
    "skip_report_if_empty":    True,
    "cleanup_prev_reports":    True,
    "reports_folder":          None,
}

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "archive_marketing" / "config.json"

# ---------------------------------------------------------------------------
# SAFE SENDERS — always kept regardless of subject
# ---------------------------------------------------------------------------

SAFE_SENDER = re.compile(r"""
    no-reply@accounts\.google\.com      |
    noreply@google\.com                 |
    security@.*\.google\.com            |
    no-reply@.*\.apple\.com             |
    security-noreply@.*\.amazon\.com    |
    account-security-noreply@.*         |
    noreply@github\.com                 |
    no-reply@github\.com
""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# STRONG SENDER SIGNALS — definite marketing platforms & domains
# ---------------------------------------------------------------------------

MARKETING_SENDER_STRONG = re.compile(r"""

    # ── Email marketing platforms ──────────────────────────────────────────
    mailchimp\.com          | mc\.us\d+\. | mcsv\.net | mcdlv\.net |
    sendgrid\.(com|net)     | sendgrid-.*\. |
    klaviyo\.com            |
    constantcontact\.com    |
    activecampaign\.com     |
    hubspot(email)?\.com    |
    marketo\.com            |
    brevo\.com              | sendinblue\.com |
    mailerlite\.com         |
    campaignmonitor\.com    |
    drip\.com               |
    convertkit\.com         |
    aweber\.com             |
    getresponse\.(com|pl)   |
    omnisend\.com           |
    dotdigital\.com         |
    salesforcemarketingcloud\.com |
    exacttarget\.com        |
    responsys\.com          |
    emarsys\.com            |
    iterable\.com           |
    customer\.io            |
    postmarkapp\.com        |
    sparkpostmail\.com      |
    createsend\.com         |
    emailoctopus\.com       |
    em\..*amazonses\.com    |
    xt\.local               |

    # ── E-commerce ────────────────────────────────────────────────────────
    aliexpress      | ae-best | newarrival\.aliexpress | deals\.aliexpress |
    mercadolivre    | mercadolibre |
    shopee          |
    ebay\.          |
    shein           |
    wish\.com       |
    casasbahia      | magazineluiza | magazinevoce | americanas | netshoes |
    centauro        | nike\.com | adidas\. | puma\. |
    zara\.          | hm\.com |
    carrefour       | kabum | pichau |

    # ── Travel ────────────────────────────────────────────────────────────
    emails\.decolar\.com | decolar\. |
    booking\.com    |
    airbnb\.com     |
    trivago\.        |
    expedia\.        |
    skyscanner\.     |
    latamairlines\. | voegol\. | voeazul\. |
    tripadvisor\.   |

    # ── Food & Delivery ────────────────────────────────────────────────────
    ifood\.com\.br  |
    rappi\.          |
    ubereats\.       |
    doordash\.       |
    deliverymuch\.  |

    # ── Finance marketing ──────────────────────────────────────────────────
    promotion@pan\.com\.vc | pan\.com\.vc |
    comunicacao\.serasaexperian |
    99pay@99app | 99app\.com |

    # ── Job boards ────────────────────────────────────────────────────────
    jobalert        | jobnotification |
    indeed\.com     |
    glassdoor\.      |
    ziprecruiter\.  |
    monster\.        |
    careerbuilder\. |
    catho\.com\.br  |
    vagas\.com      |
    empregare\.     |
    trampos\.co     |
    infojobs\.      |
    linkedin.*jobs  | jobs.*linkedin |

    # ── Tech newsletters ───────────────────────────────────────────────────
    levels\.fyi     |
    medium\.com     | .*\.medium\.com |
    substack\.com   | .*\.substack\.com |
    producthunt\.com |
    hackernewsletter |
    tldr\.tech      |
    bensbites\.      |
    therundown\.ai  |
    superhuman\.com |
    morning.*brew   |
    thehustle\.co   |

    # ── AI/Dev tools newsletters ───────────────────────────────────────────
    ollama\.com     | hello@ollama |
    email\.claude\.com |
    kilocode\.ai    |
    mail\.supernova\.io |
    engage\.affinity |
    updates\.thundercompute |
    mail\.perplexity\.ai |
    signalrgb\.com  |

    # ── Social media digests ───────────────────────────────────────────────
    facebookmail\.com |
    notification.*instagram |
    mailer\.twitter\.com | twitteremail\.com |
    tiktok.*email   |
    notify\..*reddit\.com |
    email\.linkedin\.com | news\.linkedin\.com |

    # ── Gaming ────────────────────────────────────────────────────────────
    epicgames\.com  | email\.epicgames\.com | acct\.epicgames\.com |
    steampowered\.com |
    playstation\.com |
    xbox\.com        |
    blizzard\.com   |
    ubisoft\.com    |
    ea\.com         |

    # ── Streaming ─────────────────────────────────────────────────────────
    netflix\.com    |
    spotify\.com    | sptfy\.com |
    disneyplus\.com |
    hbomax\.com     |
    primevideo\.amazon |

    # ── Crypto ────────────────────────────────────────────────────────────
    binance\.com    |
    coinbase\.com   |
    bybit\.com      |
    kraken\.com     |
    coinmarketcap\. |
    crypto\.com     |

    # ── Events ────────────────────────────────────────────────────────────
    komoot\.         |
    eventbrite\.    |
    sympla\.com\.br |

    # ── Generic marketing patterns ─────────────────────────────────────────
    mailgun\.patreon\.com |
    promotion@      |
    promo@          |
    noreply.*promo  |
    marketing@      |
    newsletter@     |
    news@           |
    announce@       |
    updates@        |
    offers@         |
    deals@          |
    digest@         |
    hello@.*\.(io|ai|co|app)

""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# MARKETING SUBJECT KEYWORDS
# ---------------------------------------------------------------------------

MARKETING_SUBJECT = re.compile(r"""

    # ── Promotional / discount ────────────────────────────────────────────
    \bdesconto\b    | \bdescontos\b |
    \boferta\b      | \bofertas\b   |
    promo[çc][ãa]   | promoc        |
    liquida[çc][ãa] |
    \bsale\b        | \bsales\b     |
    \bdeal\b        | \bdeals\b     |
    \d+\s*%\s*off   |
    \bcupom\b       | \bcoupon\b    | \bvoucher\b   | \bpromo\s*code\b |
    \bcashback\b    |
    \bbon[uú]s\b    |
    frete\s*gr[áa]tis | free\s+shipping | envio\s+gr[áa]tis |
    \bgratuito\b    | \bgratis\b    | \bfor\s+free\b |
    \bsem\s+juros\b | \bparcelado\b |
    \bblack\s+friday\b | \bcyber\s+monday\b | \bprime\s+day\b |
    \bmega\s+sale\b | \bflash\s+sale\b |
    \blimited\s+time\b |
    \bhurry\b       | \bact\s+now\b | \blast\s+chance\b |
    [úu]ltima\s+chance | n[ãa]o\s+perca | imperd[íi]vel |
    \bdon.t\s+miss\b |
    \bexclusive\s+(offer|deal|access|discount)\b |
    \bmembers?\s+only\b |
    aproveite\b     | economize\b   | \bganhe\b     |
    super\s+oferta  | queima\s+(de\s+)?estoque |
    at[eé]\s+\d+.*\boff\b |

    # ── Newsletter / content ──────────────────────────────────────────────
    \bnewsletter\b  |
    \bdigest\b      |
    \bweekly\b      | \bmonthly\b   |
    \broundup\b     | \brecap\b     | \bhighlights\b |
    \btop\s+stories\b |
    what.?s\s+(new|happening|hot) |

    # ── Announcements ─────────────────────────────────────────────────────
    \bannouncing\b  | \bannouncement\b |
    \bintroducing\b |
    \bwe.re\s+(launching|releasing|shipping)\b |
    \bwe.re\s+excited\s+to\b |
    \bjust\s+launched\b | \bnow\s+live\b | \bnow\s+available\b |
    \bcoming\s+soon\b   |
    \bchangelog\b   | \brelease\s+notes\b | \bproduct\s+update\b |
    \bnew\s+feature\b |

    # ── Engagement / re-engagement ────────────────────────────────────────
    \bwe\s+miss\s+you\b | \bcome\s+back\b |
    \btrial\s*(has\s*)?(ended|expired)\b | \byour\s+trial\b |
    \bjoin\s+(the\s+)?(community|waitlist|beta)\b |
    \bget\s+started\b | \bget\s+early\s+access\b |
    \bupgrade\s+(your|to)\b |

    # ── Giveaway / contest ────────────────────────────────────────────────
    \bgiveaway\b    | \bcontest\b   | \braffle\b    |
    \bwin\s+(a|an|free)\b |
    feeling\s+lucky |

    # ── Content marketing ─────────────────────────────────────────────────
    \bfree\s+(ebook|guide|webinar|workshop|course|template|checklist|toolkit|whitepaper)\b |
    \bdownload\s+(your|our|the|free)\b |
    \btips\s+(to|for|on)\b |
    \bhow\s+to\s+(boost|improve|grow|scale|double|triple)\b |

    # ── Unsubscribe signals ───────────────────────────────────────────────
    \bunsubscribe\b | \bemail\s+preferences\b |
    \bmanage\s+(your\s+)?subscription\b |
    \bopt.out\b     |

    # ── Job board spam ────────────────────────────────────────────────────
    \bjobs?\s+for\s+you\b | \brecommended\s+jobs?\b |
    \bjob\s+alert\b |
    top\s+vagas | vagas\s+para\s+voc[eê] |
    talent\s+pool | \bwe.re\s+hiring\b |

    # ── PT-BR promotional ─────────────────────────────────────────────────
    incrível        | imperd[íi]vel | olha\s+(isso|s[oó]) |
    n[ãa]o\s+perca  | confira\s+(já|agora|isso) |
    melhore\s+sua\s+vida | organize\s+suas\s+finan[çc]as |
    sem\s+complicar |
    novidade\b      | lan[çc]amento | aproveite | conquiste |
    assine\s+(j[aá]|agora|nosso) |
    mega\s+promo    | app\s+days   | madrugol  | fds\s+azul |
    voos\s+a\s+partir | pacotes\s+com | hot[eé]is\s+e\s+pacotes |
    cart[ãa]o.*esperando | esperando.*por\s+voc[eê] |

    # ── Travel promotional ────────────────────────────────────────────────
    \bvoos?\b.*\boff\b | \bpassagens?\b.*\bdesconto |
    fim\s+de\s+semana.*oferta |

    # ── SaaS onboarding sequences ──────────────────────────────────────────
    welcome\s+to\s+(the\s+)?\w+  |
    create\s+an?\s+instance       |
    complete\s+your\s+(setup|profile|registration) |
    import\s+figma                |
    desktop\s+redesign            |
    hermes.*agent

""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# WEAK SIGNALS — individually insufficient; noreply + weak subject → archive
# ---------------------------------------------------------------------------

NOREPLY_SENDER = re.compile(
    r"\bnoreply\b | \bno.reply\b | \bdo.not.reply\b | \bdonotreply\b",
    re.IGNORECASE | re.VERBOSE,
)

WEAK_SUBJECT = re.compile(r"""
    \btips?\b       | \bguide\b    | \binsights?\b |
    \bupdate[sd]?\b | \breminder\b |
    \bannounce\b    | \bannounced\b | \bannouncing\b |
    \bwelcome\b     | \bonboard\b  |
    \bthis\s+week\b | \bthis\s+month\b |
    \bpopular\b     | \btrending\b | \bfeatured\b |
    \bdiscover\b    | \bexplore\b  |
    fastest\s+way   | popular\s+ways | next\s+answer
""", re.IGNORECASE | re.VERBOSE)


# ---------------------------------------------------------------------------
# Classification engine
# ---------------------------------------------------------------------------

def classify(
    sender: str,
    subject: str,
    exclude_patterns: Optional[List[re.Pattern]] = None,
) -> Tuple[bool, str]:
    """
    Classify an email as marketing or legitimate.

    Evaluation order (first match wins):
      1. User exclude list   → always keep
      2. Safe-sender allowlist → always keep
      3. Strong sender match → always archive
      4. Marketing subject   → always archive
      5. noreply + weak subject → archive
      6. Default → keep

    Args:
        sender:           Full From address string (e.g. "Acme <news@acme.com>").
        subject:          Subject line of the email.
        exclude_patterns: Optional list of compiled regex patterns; matching
                          emails are always kept regardless of other signals.

    Returns:
        Tuple of (is_marketing: bool, reason: str).
        ``reason`` is a short label useful for logging and CSV export.
    """
    # 1. User-defined exclude list (explicit keep)
    if exclude_patterns:
        for pat in exclude_patterns:
            if pat.search(sender) or pat.search(subject):
                return False, "user-exclude"

    # 2. Safe allowlist
    if SAFE_SENDER.search(sender):
        return False, "safe-allowlist"

    # 3. Strong sender → definite marketing
    if MARKETING_SENDER_STRONG.search(sender):
        return True, "sender:strong"

    # 4. Marketing subject
    if MARKETING_SUBJECT.search(subject):
        return True, "subject:match"

    # 5. Weak combo: noreply + engagement subject
    if NOREPLY_SENDER.search(sender) and WEAK_SUBJECT.search(subject):
        return True, "sender:noreply+subject:weak"

    return False, "keep"


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

def load_config(path: Optional[str]) -> Dict:
    """
    Load settings from a JSON config file.

    Args:
        path: Explicit path to config file, or None to try the default location.

    Returns:
        Dict of settings (only keys present in the file; missing keys are
        filled later from env vars and CLI defaults).
    """
    search = [path] if path else [str(DEFAULT_CONFIG_PATH)]
    for p in search:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            print(f"[config] Loaded from {p}", flush=True)
            return data
        except FileNotFoundError:
            pass
        except json.JSONDecodeError as e:
            sys.exit(f"[ERROR] Config file is not valid JSON: {p}\n  {e}")
    return {}


def merge_config(cli_args: argparse.Namespace, file_cfg: Dict) -> argparse.Namespace:
    """
    Apply config file and environment variable values for any CLI option that
    was not explicitly set by the user (i.e. still at its argparse default).

    Priority: CLI > env var > config file > built-in default.

    Args:
        cli_args: Parsed argparse namespace.
        file_cfg: Dict loaded from the JSON config file.

    Returns:
        Updated argparse namespace.
    """
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

    for attr, env_key in ENV_MAP.items():
        default_val = DEFAULTS.get(attr)
        if getattr(cli_args, attr, None) == default_val:
            if env_key in os.environ:
                raw = os.environ[env_key]
                # Cast to correct type (bool must come before int — bool is subclass of int)
                if isinstance(default_val, bool):
                    raw = raw.lower() in ("1", "true", "yes")
                elif isinstance(default_val, int):
                    raw = int(raw)
                elif isinstance(default_val, float):
                    raw = float(raw)
                setattr(cli_args, attr, raw)
            elif attr in file_cfg:
                setattr(cli_args, attr, file_cfg[attr])

    # exclude list: merge CLI + file
    file_excl = file_cfg.get("exclude", [])
    cli_excl  = getattr(cli_args, "exclude", []) or []
    combined  = list(set(file_excl + cli_excl))
    cli_args.exclude = combined

    return cli_args


# ---------------------------------------------------------------------------
# Security: connection file validation
# ---------------------------------------------------------------------------

def validate_connection_file(path: str) -> None:
    """
    Warn if the thunderbird-mcp connection file has world-readable permissions.
    On Windows, permission checks are best-effort only.

    Args:
        path: Filesystem path to the connection.json file.
    """
    try:
        mode = os.stat(path).st_mode
        # On POSIX: warn if group or other can read (should be 600)
        if os.name != "nt" and (mode & (stat.S_IRGRP | stat.S_IROTH)):
            print(
                f"[WARN] Connection file has permissive permissions: {oct(mode & 0o777)}\n"
                f"       Run: chmod 600 {path}",
                flush=True,
            )
    except OSError:
        pass  # Non-critical check


# ---------------------------------------------------------------------------
# Thunderbird MCP HTTP client
# ---------------------------------------------------------------------------

_req_id = 0


def _mcp_call(token: str, port: int, tool_name: str, arguments: Dict) -> object:
    """
    Send a single MCP tools/call request to the Thunderbird HTTP bridge.

    Args:
        token:      Bearer auth token from connection.json.
        port:       TCP port the Thunderbird extension is listening on.
        tool_name:  MCP tool name (e.g. "getRecentMessages").
        arguments:  Tool arguments dict.

    Returns:
        Parsed JSON result from the MCP response envelope.

    Raises:
        RuntimeError: If the response has an unexpected shape.
        urllib.error.URLError: On network errors (caller handles retries).
    """
    global _req_id
    _req_id += 1

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": _req_id,
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

    if raw.get("error"):
        code = raw["error"].get("code", "?")
        msg  = raw["error"].get("message", "unknown error")
        raise RuntimeError(f"MCP error {code}: {msg}")

    content = raw.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        return json.loads(content[0]["text"])

    raise RuntimeError("Unexpected MCP response shape")


def load_connection(connection_file: str) -> Tuple[str, int]:
    """
    Read the Thunderbird MCP auth token and port from the connection file.

    Args:
        connection_file: Path to the thunderbird-mcp connection.json.

    Returns:
        Tuple of (token, port).  Exits with an informative message on failure.
    """
    try:
        with open(connection_file, encoding="utf-8") as f:
            data = json.load(f)
        token = data["token"]
        port  = data["port"]
    except FileNotFoundError:
        sys.exit(
            f"\n[ERROR] Connection file not found:\n  {connection_file}\n\n"
            "Checklist:\n"
            "  1. Is Thunderbird running?\n"
            "  2. Is the thunderbird-mcp extension installed and enabled?\n"
            "  3. Does the extension show 'Connected' in Thunderbird add-ons?\n\n"
            "See: https://github.com/rodrigoazlima/scripts-archive-marketing#prerequisites\n"
        )
    except KeyError as e:
        sys.exit(f"\n[ERROR] Malformed connection file — missing key: {e}\n")
    except json.JSONDecodeError:
        sys.exit(f"\n[ERROR] Connection file is not valid JSON: {connection_file}\n")

    validate_connection_file(connection_file)
    return token, port


def fetch_page(
    token: str,
    port: int,
    inbox: str,
    offset: int,
    page_size: int,
    days_back: int,
) -> Tuple[List[Dict], int]:
    """
    Fetch one page of inbox messages.

    Args:
        token:     Auth token.
        port:      MCP bridge port.
        inbox:     IMAP folder URI.
        offset:    Number of messages to skip (for pagination).
        page_size: Max messages to return.
        days_back: Only return messages newer than this many days.

    Returns:
        Tuple of (emails list, total_count).
    """
    result = _mcp_call(token, port, "getRecentMessages", {
        "folderPath": inbox,
        "maxResults":  page_size,
        "offset":      offset,
        "daysBack":    days_back,
    })
    if isinstance(result, dict) and "messages" in result:
        return result["messages"], result.get("totalMatches", 0)
    if isinstance(result, list):
        return result, 0
    return [], 0


def move_emails(
    token: str,
    port: int,
    inbox: str,
    message_ids: List[str],
    destination: str,
) -> int:
    """
    Move a list of messages to the destination folder.

    Args:
        token:       Auth token.
        port:        MCP bridge port.
        inbox:       Source IMAP folder URI.
        message_ids: List of message IDs to move.
        destination: Destination IMAP folder URI.

    Returns:
        Number of messages successfully moved.
    """
    result = _mcp_call(token, port, "updateMessage", {
        "folderPath": inbox,
        "messageIds": message_ids,
        "moveTo":     destination,
    })
    return result.get("updated", len(message_ids))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def open_csv_writer(path: str):
    """
    Open a CSV file for writing classification results.

    Args:
        path: Output file path.

    Returns:
        Tuple of (file handle, csv.DictWriter).
    """
    fh = open(path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=["timestamp", "sender", "subject", "is_marketing", "reason"])
    writer.writeheader()
    return fh, writer


# ---------------------------------------------------------------------------
# Previous report cleanup
# ---------------------------------------------------------------------------

_REPORT_SUBJECT_PREFIX = "[Archive Report]"


def ensure_reports_folder(token: str, port: int, reports_folder: str) -> bool:
    """
    Ensure reports_folder exists in Thunderbird. Lists subfolders of the parent
    and creates the folder if not found.

    Args:
        token:          MCP auth token.
        port:           MCP bridge port.
        reports_folder: Full IMAP URI of the desired reports folder.

    Returns:
        True if folder exists or was created, False on failure.
    """
    parts = reports_folder.rsplit("/", 1)
    if len(parts) != 2 or not parts[1]:
        print(f"[cleanup] Cannot parse reports_folder URI: {reports_folder}", flush=True)
        return False

    parent_uri, folder_name = parts

    try:
        result = _mcp_call(token, port, "listFolders", {"folderPath": parent_uri})
        folders = result if isinstance(result, list) else result.get("folders", [])
        existing = {f.get("name", "") for f in folders}
        if folder_name in existing:
            return True
    except Exception as exc:
        print(f"[cleanup] listFolders failed: {exc}", flush=True)

    try:
        _mcp_call(token, port, "createFolder", {
            "parentFolderPath": parent_uri,
            "name": folder_name,
        })
        print(f"[cleanup] Created reports folder: {reports_folder}", flush=True)
        return True
    except Exception as exc:
        print(f"[cleanup] Failed to create reports folder: {exc}", flush=True)
        return False


def cleanup_prev_reports(
    token: str,
    port: int,
    inbox: str,
    reports_folder: str,
    move_batch: int = 50,
) -> int:
    """
    Move any previous archive-run report emails (unread, still in inbox) to
    reports_folder.  Matches only on subject prefix — email bodies are never
    fetched or read.

    Args:
        token:          MCP auth token.
        port:           MCP bridge port.
        inbox:          Source IMAP folder URI.
        reports_folder: Destination IMAP folder URI for old reports.
        move_batch:     Max IDs per move request.

    Returns:
        Number of report emails moved.
    """
    offset = 0
    page_size = 100
    matched_ids: List[str] = []

    while True:
        try:
            emails, _ = fetch_page(token, port, inbox, offset, page_size, days_back=3650)
        except Exception as exc:
            print(f"[cleanup] Failed to fetch inbox page: {exc}", flush=True)
            break

        if not emails:
            break

        for msg in emails:
            subject = msg.get("subject", "")
            if subject.startswith(_REPORT_SUBJECT_PREFIX):
                matched_ids.append(msg.get("id", ""))

        if len(emails) < page_size:
            break
        offset += page_size

    if not matched_ids:
        return 0

    moved = 0
    for i in range(0, len(matched_ids), move_batch):
        batch = matched_ids[i: i + move_batch]
        try:
            moved += move_emails(token, port, inbox, batch, reports_folder)
        except Exception as exc:
            print(f"[cleanup] Move failed: {exc}", flush=True)

    print(f"[cleanup] Moved {moved} previous report(s) to reports folder.", flush=True)
    return moved


# ---------------------------------------------------------------------------
# Email report
# ---------------------------------------------------------------------------

def _tb_identity(token: str, port: int) -> Tuple[str, str]:
    """
    Return (email, display_name) of the first Thunderbird IMAP identity.

    Falls back to ("", "") if listAccounts fails or returns no identities.
    """
    try:
        accounts = _mcp_call(token, port, "listAccounts", {})
        for acct in accounts:
            ids = acct.get("identities", [])
            if ids:
                return ids[0].get("email", ""), ids[0].get("name", "")
    except Exception:
        pass
    return "", ""


def send_report_email(
    token: str,
    port: int,
    args: argparse.Namespace,
    archived: int,
    kept: int,
    reason_counts: Dict[str, int],
    run_duration: float,
) -> None:
    """
    Send an HTML email summary report via Thunderbird after an archiving run.

    Sender and recipient identity are resolved from Thunderbird's account list
    unless ``args.report_to`` is set explicitly in config/CLI.

    Args:
        token:         MCP auth token.
        port:          MCP bridge port.
        args:          Merged config namespace (inbox, archive_folder, dry_run…).
        archived:      Number of emails archived in this run.
        kept:          Number of emails kept in this run.
        reason_counts: Classification reason breakdown dict.
        run_duration:  Wall-clock seconds the run took.
    """
    sender_email, sender_name = _tb_identity(token, port)
    report_to = getattr(args, "report_to", None) or sender_email

    if not report_to:
        print(
            "[report] Cannot determine report recipient. "
            "Set 'report_to' in config.json or use --report-to.",
            flush=True,
        )
        return

    now       = datetime.now()
    date_str  = now.strftime("%A, %B %d, %Y")
    time_str  = now.strftime("%H:%M")
    dry_label = " (DRY RUN)" if args.dry_run else ""

    if run_duration < 60:
        dur_str = f"{run_duration:.0f}s"
    else:
        dur_str = f"{run_duration / 60:.1f}m"

    # Classification breakdown table rows
    breakdown_rows = "\n".join(
        f"<tr><td>{r}</td><td style='text-align:right'><strong>{c}</strong></td></tr>"
        for r, c in sorted(reason_counts.items(), key=lambda x: -x[1])
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;
        color:#1a1a1a;margin:0;padding:20px;background:#f5f5f5}}
  .card{{background:#fff;border-radius:8px;padding:24px;max-width:620px;margin:0 auto;
         box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  h1{{font-size:20px;margin:0 0 4px}}
  .sub{{color:#666;font-size:13px;margin:0 0 20px}}
  .stats{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
  .stat{{flex:1;min-width:110px;background:#f9f9f9;border-radius:6px;padding:14px;text-align:center}}
  .stat .num{{font-size:28px;font-weight:700;line-height:1}}
  .stat .lbl{{font-size:11px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:.05em}}
  .sec-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
              color:#888;margin:20px 0 8px;border-bottom:1px solid #eee;padding-bottom:5px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  td{{padding:6px 4px;border-bottom:1px solid #f0f0f0;vertical-align:top}}
  td:first-child{{color:#555;padding-right:16px}}
  .footer{{font-size:11px;color:#aaa;margin-top:20px;text-align:center}}
</style>
</head>
<body>
<div class="card">
  <h1>&#128235; Archive Run Report{dry_label}</h1>
  <p class="sub">{date_str} &nbsp;&middot;&nbsp; {time_str} &nbsp;&middot;&nbsp; {report_to}</p>

  <div class="stats">
    <div class="stat">
      <div class="num" style="color:#c0392b">{archived}</div>
      <div class="lbl">Archived</div>
    </div>
    <div class="stat">
      <div class="num" style="color:#2e7d32">{kept}</div>
      <div class="lbl">Kept</div>
    </div>
    <div class="stat">
      <div class="num">{archived + kept}</div>
      <div class="lbl">Scanned</div>
    </div>
    <div class="stat">
      <div class="num">{dur_str}</div>
      <div class="lbl">Duration</div>
    </div>
  </div>

  <div class="sec-title">Run settings</div>
  <table>
    <tr><td>Inbox</td><td><code style="font-size:12px">{args.inbox}</code></td></tr>
    <tr><td>Archive</td><td><code style="font-size:12px">{args.archive_folder}</code></td></tr>
    <tr><td>Days scanned</td><td>{args.days_back}</td></tr>
    <tr><td>Mode</td><td>{'DRY RUN — no emails moved' if args.dry_run else 'Live — emails moved'}</td></tr>
  </table>

  <div class="sec-title">Classification breakdown</div>
  <table>
    <tr style="color:#888;font-size:11px">
      <td><strong>Reason</strong></td>
      <td style="text-align:right"><strong>Count</strong></td>
    </tr>
    {breakdown_rows}
  </table>

  <div class="footer">
    archive_marketing.py v{__version__} &nbsp;&middot;&nbsp;
    <a href="https://github.com/rodrigoazlima/scripts-archive-marketing">github.com/rodrigoazlima/scripts-archive-marketing</a>
  </div>
</div>
</body>
</html>"""

    subject = f"[Archive Report] {archived} archived{dry_label} — {date_str}"
    try:
        _mcp_call(token, port, "sendMail", {
            "to":         report_to,
            "from":       sender_email,
            "subject":    subject,
            "body":       html,
            "isHtml":     True,
            "skipReview": True,
        })
        print(f"[report] Report sent to {report_to}", flush=True)
    except Exception as exc:
        print(f"[report] Failed to send email report: {exc}", flush=True)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    """
    Main entry point: paginate inbox, classify, and archive marketing emails.

    Args:
        args: Merged configuration namespace (CLI + env + config file).
    """
    token, port = load_connection(args.connection_file)
    run_start = time.time()

    # Compile user exclude patterns
    exclude_patterns: List[re.Pattern] = []
    for pat in (args.exclude or []):
        try:
            exclude_patterns.append(re.compile(pat, re.IGNORECASE))
        except re.error as e:
            print(f"[WARN] Invalid exclude pattern '{pat}': {e}", flush=True)

    # CSV export setup
    csv_fh, csv_writer = None, None
    if args.export_csv:
        try:
            csv_fh, csv_writer = open_csv_writer(args.export_csv)
            print(f"[export] Writing classifications to: {args.export_csv}", flush=True)
        except OSError as e:
            print(f"[WARN] Cannot open CSV export file: {e}", flush=True)

    total_archived = 0
    total_kept     = 0
    reason_counts: Dict[str, int] = {}
    offset   = args.start_offset
    page_num = 0

    mode = "[DRY RUN] " if args.dry_run else ""
    if not args.dry_run_summary:
        print(f"\n{'='*62}")
        print(f"  {mode}Thunderbird Inbox Marketing Archiver  v{__version__}")
        print(f"  https://github.com/rodrigoazlima/scripts-archive-marketing")
        print(f"{'='*62}")
        print(f"  Inbox  : {args.inbox}")
        print(f"  Archive: {args.archive_folder}")
        print(f"  Offset : {offset}  |  Page: {args.page_size}  |  Delay: {args.fetch_delay}s")
        if exclude_patterns:
            print(f"  Exclude: {len(exclude_patterns)} pattern(s)")
        print(f"{'='*62}\n")

    try:
        while True:
            page_num += 1
            if not args.dry_run_summary:
                print(f"[Page {page_num:>3}] offset={offset:<6}", end=" ... ", flush=True)

            # Fetch with retry
            emails: List[Dict] = []
            total: int = 0
            for attempt in range(3):
                try:
                    emails, total = fetch_page(
                        token, port, args.inbox, offset, args.page_size, args.days_back
                    )
                    break
                except Exception as exc:
                    if attempt == 2:
                        if not args.dry_run_summary:
                            print(f"\n[ERROR] Failed after 3 attempts: {exc}\nStopping.")
                        break
                    wait = 10 * (attempt + 1)
                    if not args.dry_run_summary:
                        print(f"\n  Retry {attempt+1}/3 in {wait}s ...", end=" ", flush=True)
                    time.sleep(wait)

            if not args.dry_run_summary:
                print(f"fetched {len(emails):<4}  (inbox total: ~{total})", flush=True)

            if not emails:
                if not args.dry_run_summary:
                    print("  No more emails. Done!\n")
                break

            # Classify
            marketing_ids: List[str] = []
            ts = datetime.now().isoformat(timespec="seconds")

            for email in emails:
                sender  = email.get("author", "")
                subject = email.get("subject", "")
                mid     = email.get("id", "")

                is_mkt, reason = classify(sender, subject, exclude_patterns)
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

                if csv_writer:
                    csv_writer.writerow({
                        "timestamp":    ts,
                        "sender":       sender,
                        "subject":      subject,
                        "is_marketing": is_mkt,
                        "reason":       reason,
                    })

                if is_mkt:
                    marketing_ids.append(mid)
                    if args.verbose and not args.dry_run_summary:
                        print(f"    ✗ [{reason:<30}] {sender[:40]:<40}  {subject[:45]}")
                else:
                    if args.verbose and not args.dry_run_summary:
                        print(f"    ✓ [{reason:<30}] {sender[:40]:<40}  {subject[:45]}")

            kept = len(emails) - len(marketing_ids)
            if not args.dry_run_summary:
                print(f"         Marketing: {len(marketing_ids):<4}  Keeping: {kept}", flush=True)

            # Archive
            if marketing_ids and not args.dry_run:
                for i in range(0, len(marketing_ids), args.move_batch):
                    batch = marketing_ids[i : i + args.move_batch]
                    try:
                        moved = move_emails(token, port, args.inbox, batch, args.archive_folder)
                        if not args.dry_run_summary:
                            print(f"         Archived {moved} (batch {i // args.move_batch + 1})", flush=True)
                    except Exception as exc:
                        print(f"         [ERROR] Move failed: {exc}", flush=True)
                    if i + args.move_batch < len(marketing_ids):
                        time.sleep(args.move_delay)

            total_archived += len(marketing_ids)
            total_kept     += kept

            if len(emails) < args.page_size:
                if not args.dry_run_summary:
                    print("  Last page. Done!\n")
                break

            offset += args.page_size
            if not args.dry_run_summary:
                print(
                    f"         Running total: {total_archived} archived / {total_kept} kept"
                    f"  — sleeping {args.fetch_delay}s...\n",
                    flush=True,
                )
            time.sleep(args.fetch_delay)

    finally:
        if csv_fh:
            csv_fh.close()

    run_duration = time.time() - run_start
    _print_summary(total_archived, total_kept, reason_counts, args.dry_run, args.export_csv)

    # Always clean up previous reports regardless of whether a new one will be sent.
    # A leftover report in the inbox must be moved even on runs with nothing archived.
    if getattr(args, "cleanup_prev_reports", True):
        rf = getattr(args, "reports_folder", None)
        if rf:
            if ensure_reports_folder(token, port, rf):
                cleanup_prev_reports(token, port, args.inbox, rf, args.move_batch)
        else:
            print(
                "[cleanup] cleanup_prev_reports enabled but reports_folder not set — skipping.",
                flush=True,
            )

    if getattr(args, "send_report", False):
        if total_archived == 0 and getattr(args, "skip_report_if_empty", True):
            print("[report] No emails archived — skipping report.", flush=True)
        else:
            send_report_email(token, port, args, total_archived, total_kept, reason_counts, run_duration)


def _print_summary(
    archived: int,
    kept: int,
    reason_counts: Dict[str, int],
    dry_run: bool,
    export_csv: Optional[str],
) -> None:
    print(f"\n{'='*62}")
    if dry_run:
        print(f"  DRY RUN — no emails moved.")
        print(f"  Would archive: {archived}")
    else:
        print(f"  COMPLETE")
        print(f"  Archived : {archived}")
    print(f"  Kept     : {kept}")
    if reason_counts:
        print(f"\n  Classification breakdown:")
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"    {reason:<38} {count:>6}")
    if export_csv:
        print(f"\n  Exported : {export_csv}")
    print(f"{'='*62}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="archive_marketing.py",
        description=(
            "Archive marketing emails from Thunderbird inbox via the thunderbird-mcp bridge.\n"
            "https://github.com/rodrigoazlima/scripts-archive-marketing"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    p.add_argument("--config",          metavar="PATH",
                   help="Path to JSON config file (default: ~/.config/archive_marketing/config.json).")
    p.add_argument("--inbox",           default=DEFAULTS["inbox"],
                   help="IMAP folder URI of your inbox.")
    p.add_argument("--archive-folder",  default=DEFAULTS["archive_folder"],
                   help="IMAP folder URI for archived marketing emails.")
    p.add_argument("--connection-file", default=DEFAULTS["connection_file"],
                   help="Path to thunderbird-mcp connection.json.")
    p.add_argument("--page-size",       type=int,   default=DEFAULTS["page_size"],
                   help="Emails fetched per API call.")
    p.add_argument("--fetch-delay",     type=float, default=DEFAULTS["fetch_delay"],
                   help="Seconds between page fetches (IMAP rate limit).")
    p.add_argument("--move-delay",      type=float, default=DEFAULTS["move_delay"],
                   help="Seconds between bulk-move calls.")
    p.add_argument("--move-batch",      type=int,   default=DEFAULTS["move_batch"],
                   help="Max message IDs per move request.")
    p.add_argument("--start-offset",    type=int,   default=DEFAULTS["start_offset"],
                   help="Skip first N emails (resume support).")
    p.add_argument("--days-back",       type=int,   default=DEFAULTS["days_back"],
                   help="How many days back to scan.")
    p.add_argument("--exclude",         metavar="REGEX", action="append", default=[],
                   help="Regex pattern: matching sender/subject always kept. Repeatable.")
    p.add_argument("--export-csv",      metavar="PATH",
                   help="Write every classification decision to a CSV file.")
    p.add_argument("--dry-run",         action="store_true",
                   help="Classify only — do not move any email.")
    p.add_argument("--dry-run-summary", action="store_true",
                   help="Dry run with only the final summary printed (quiet mode).")
    p.add_argument("--verbose", "-v",   action="store_true",
                   help="Print every classification decision.")
    p.add_argument("--send-report",          action="store_true", default=DEFAULTS["send_report"],
                   help="Send an HTML email summary report after each run.")
    p.add_argument("--report-to",            metavar="EMAIL", default=DEFAULTS["report_to"],
                   help="Recipient for the report email (default: auto-detect from Thunderbird).")
    p.add_argument("--no-skip-report-if-empty", dest="skip_report_if_empty",
                   action="store_false", default=DEFAULTS["skip_report_if_empty"],
                   help="Send report even when no emails were archived (default: skip if empty).")
    p.add_argument("--reports-folder",       metavar="URI", default=DEFAULTS["reports_folder"],
                   help="IMAP folder URI where previous open reports are moved before sending a new one.")
    p.add_argument("--no-cleanup-prev-reports", dest="cleanup_prev_reports",
                   action="store_false", default=DEFAULTS["cleanup_prev_reports"],
                   help="Skip moving previous open reports before sending new report (default: move them).")
    return p


if __name__ == "__main__":
    parser = build_parser()
    cli    = parser.parse_args()

    # --dry-run-summary implies --dry-run
    if cli.dry_run_summary:
        cli.dry_run = True

    file_cfg = load_config(cli.config)
    args     = merge_config(cli, file_cfg)

    run(args)
