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
  - Weak signals   (noreply sender, engagement words) combined → archive
  - Safe allowlist (security/account alerts)         → always keep

Requirements:
  - Mozilla Thunderbird with thunderbird-mcp extension installed and running
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

# Force UTF-8 stdout/stderr on Windows (handles emoji in folder paths/subjects)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Default configuration — override via CLI flags
# ---------------------------------------------------------------------------

DEFAULT_CONNECTION_FILE = str(
    Path(os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp")))
    / "thunderbird-mcp" / "connection.json"
)

DEFAULT_INBOX = "imap://you%40gmail.com@imap.gmail.com/INBOX"
DEFAULT_ARCHIVE_FOLDER = "imap://you%40gmail.com@imap.gmail.com/Marketing"

DEFAULT_PAGE_SIZE    = 100
DEFAULT_FETCH_DELAY  = 2.0
DEFAULT_MOVE_DELAY   = 1.5
DEFAULT_MOVE_BATCH   = 50
DEFAULT_START_OFFSET = 0
DEFAULT_DAYS_BACK    = 3650


# ---------------------------------------------------------------------------
# SAFE SENDERS — always kept regardless of subject
# Security alerts, account notifications from trusted providers.
# ---------------------------------------------------------------------------

SAFE_SENDER = re.compile(r"""
    no-reply@accounts\.google\.com      |   # Google account security
    noreply@google\.com                 |   # Google notifications
    security@.*\.google\.com            |   # Google security
    no-reply@.*\.apple\.com             |   # Apple security
    security-noreply@.*\.amazon\.com    |   # Amazon security
    account-security-noreply@.*         |   # Generic account security
    noreply@github\.com                 |   # GitHub device/security alerts
    no-reply@github\.com
""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# STRONG SENDER SIGNALS — definite marketing platforms & domains
# Match on any part of the From address.
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
    mailer-daemon@          |
    em\..*amazonses\.com    |
    xt\.local               |   # Twilio SendGrid

    # ── E-commerce (BR + Global) ───────────────────────────────────────────
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

    # ── Travel & Hospitality ───────────────────────────────────────────────
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

    # ── Finance marketing (promotional, not transactional) ─────────────────
    promotion@pan\.com\.vc | pan\.com\.vc |
    comunicacao\.serasaexperian |
    99pay@99app | 99app\.com |
    nubank\.com\.br.*marketing |
    c6bank\.com\.br.*promo |

    # ── Job boards (mass mailings) ─────────────────────────────────────────
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

    # ── Social media notifications / digests ───────────────────────────────
    facebookmail\.com |
    notification.*instagram |
    mailer\.twitter\.com | twitteremail\.com |
    tiktok.*email   |
    notify\..*reddit\.com |
    email\.linkedin\.com | news\.linkedin\.com |

    # ── Gaming ────────────────────────────────────────────────────────────
    epicgames\.com  | email\.epicgames\.com | acct\.epicgames\.com |
    steampowered\.com | store\.steampowered |
    playstation\.com |
    xbox\.com        |
    blizzard\.com   |
    ubisoft\.com    |
    ea\.com         |

    # ── Streaming ─────────────────────────────────────────────────────────
    netflix\.com    |
    spotify\.com    | sptfy\.com |
    disneyplus\.com |
    hbomax\.com     | max\.com |
    primevideo\.amazon |

    # ── Crypto ────────────────────────────────────────────────────────────
    binance\.com    |
    coinbase\.com   |
    bybit\.com      |
    kraken\.com     |
    coinmarketcap\. |
    crypto\.com     |

    # ── Travel & Experiences ──────────────────────────────────────────────
    komoot\.         |
    eventbrite\.    |
    sympla\.com\.br |

    # ── Miscellaneous known senders ───────────────────────────────────────
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
    alerts@.*shop   |
    digest@         |
    email@.*shop    |
    hello@.*\.(io|ai|co|app)   # Generic SaaS "hello@" senders

""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# MARKETING SUBJECT KEYWORDS
# Matches promotional language in any supported language.
# ---------------------------------------------------------------------------

MARKETING_SUBJECT = re.compile(r"""

    # ── Promotional / discount ────────────────────────────────────────────
    \bdesconto\b    | \bdescontos\b |
    \boferta\b      | \bofertas\b   |
    promo[çc][ãa]   | promoc        |
    liquida[çc][ãa] | \bliqui\b     |
    \bsale\b        | \bsales\b     |
    \bdeal\b        | \bdeals\b     |
    \d+\s*%\s*off   |
    \boff\b.*\bprice |
    \bcupom\b       | \bcoupon\b    | \bvoucher\b   | \bpromo\s*code\b |
    \bcashback\b    |
    \bbon[uú]s\b    |
    frete\s*gr[áa]tis | free\s+shipping | envio\s+gr[áa]tis |
    \bgratuito\b    | \bgratis\b    | \bfor\s+free\b |
    \bsem\s+juros\b | \bparcelado\b | sem\s+acr[eé]scimo |
    \bcr[eé]dito\b.*\bexclusivo\b   |
    \bblack\s+friday\b | \bcyber\s+monday\b | \bprime\s+day\b |
    \bmega\s+sale\b | \bflash\s+sale\b | \bflash\s+deal\b |
    \bsummer\s+sale\b | \bwinter\s+sale\b |
    \blimited\s+time\b | \btime.sensitive\b |
    \bexpires?\s+(today|soon|tonight|in \d+)\b |
    \bhurry\b       | \bact\s+now\b | \blast\s+chance\b |
    [úu]ltima\s+chance | n[ãa]o\s+perca | imperd[íi]vel |
    \bdon.t\s+miss\b | \bmissing\s+out\b | \bfomo\b |
    \bexclusive\s+(offer|deal|access|discount)\b |
    \bmembers?\s+only\b | \bvip\s+(offer|access|deal)\b |
    aproveite\b     | economize\b   | \bganhe\b     |
    super\s+oferta  | queima\s+(de\s+)?estoque |
    at[eé]\s+\d+.*\boff\b |

    # ── Newsletter / content marketing ────────────────────────────────────
    \bnewsletter\b  |
    \bdigest\b      |
    \bweekly\b      | \bmonthly\b   | \bdaily\s+update\b |
    \broundup\b     | \brecap\b     | \bhighlights\b |
    \btop\s+stories\b | \bthis\s+week\s+in\b | \bthis\s+month\s+in\b |
    what.?s\s+(new|happening|hot) |
    \bcurious\b.*\bweek\b | \binside\s+the\b |

    # ── Product announcements ─────────────────────────────────────────────
    \bannouncing\b  | \bannouncement\b |
    \bintroducing\b | \bwe.re\s+(launching|releasing|shipping)\b |
    \bwe.re\s+excited\s+to\b | \bexcited\s+to\s+(share|announce|introduce)\b |
    \bjust\s+launched\b | \bnow\s+live\b | \bnow\s+available\b |
    \bcoming\s+soon\b   | \bsneek\s+peek\b | \bpreview\b |
    \bchangelog\b   | \brelease\s+notes\b | \bproduct\s+update\b |
    \bnew\s+feature\b | \bnew\s+in\b.*\d{4} | \bwhat.?s\s+new\s+in\b |

    # ── Engagement / re-engagement ────────────────────────────────────────
    \bwe\s+miss\s+you\b | \bcome\s+back\b | \bwe.ve\s+been\s+thinking\b |
    \bstill\s+interested\b | \bare\s+you\s+still\b |
    \btrial\s*(has\s*)?(ended|expired)\b | \byour\s+trial\b |
    \bjoin\s+(the\s+)?(community|waitlist|beta)\b |
    \bget\s+started\b | \bget\s+access\b | \bget\s+early\s+access\b |
    \bstart\s+your\b.*\bfree\b |
    \bupgrade\s+(your|to)\b | \bunlock\b.*\bfeature\b |

    # ── Giveaway / contest ────────────────────────────────────────────────
    \bgiveaway\b    | \bcontest\b   | \braffle\b    | \bwin\s+(a|an|free)\b |
    \byou.ve\s+(won|been\s+selected|been\s+chosen)\b |
    feeling\s+lucky | \blucky\s+draw\b |

    # ── Educational content marketing ─────────────────────────────────────
    \bfree\s+(ebook|guide|webinar|workshop|course|template|checklist|toolkit|whitepaper)\b |
    \bdownload\s+(your|our|the|free)\b |
    \blearn\s+how\s+to\b | \btips\s+(to|for|on)\b | \btricks\s+(to|for)\b |
    \bhow\s+to\s+(boost|improve|grow|scale|double|triple)\b |
    \bcase\s+study\b | \bsuccess\s+story\b |

    # ── Unsubscribe / email management language ───────────────────────────
    \bunsubscribe\b | \bemail\s+preferences\b | \bmanage\s+(your\s+)?subscription\b |
    \bview\s+(in|this)\s+(browser|email)\b | \bopt.out\b |

    # ── Job board spam ────────────────────────────────────────────────────
    \bjobs?\s+for\s+you\b | \brecommended\s+jobs?\b | \bnew\s+jobs?\s+(near|for|match)\b |
    \bjob\s+alert\b | \bcareer\s+opportunit\b |
    top\s+vagas | vagas\s+para\s+voc[eê] | \bvaga\s+em\b |
    talent\s+pool | \bwe.re\s+hiring\b | \bjoin\s+our\s+team\b |

    # ── PT-BR promotional language ────────────────────────────────────────
    incrível        | imperd[íi]vel | olha\s+(isso|s[oó]) |
    n[ãa]o\s+perca  | n[ãa]o\s+perd[ao] | confira\s+(já|agora|isso) |
    melhore\s+sua\s+vida | organize\s+suas\s+finan[çc]as |
    sem\s+complicar | sua\s+vida\s+financeira |
    novidade\b      | lan[çc]amento | aproveite | conquiste |
    assine\s+(j[aá]|agora|nosso) | assine\s+e\s+(ganhe|economize) |
    mega\s+promo    | app\s+days   | madrugol  | fds\s+azul |
    voos\s+a\s+partir | pacotes\s+com | hot[eé]is\s+e\s+pacotes |
    kit\s+de\s+ferramentas | kit.*criativo |
    cart[ãa]o.*esperando | esperando.*por\s+voc[eê] |
    [úu]ltima\s+oportunidade |

    # ── Travel promotional ────────────────────────────────────────────────
    \bvoos?\b.*\boff\b | \bpassagens?\b.*\bdesconto |
    \bhotel\b.*\boff\b | \bpacote\b.*\bdesconto |
    fim\s+de\s+semana.*oferta |

    # ── SaaS / product onboarding (automated sequences) ───────────────────
    welcome\s+to\s+(the\s+)?\w+  |   # "Welcome to Acme"
    create\s+an?\s+instance       |
    get\s+started\s+with          |
    your\s+account\s+is\s+ready   |
    complete\s+your\s+(setup|profile|registration) |
    \d+\s+(tip|trick|step)s?\s+(to|for|that) |   # "5 tips to..."
    import\s+figma                |
    desktop\s+redesign            | routines.*ultrareview |
    hermes.*agent | support.*hermes

""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# WEAK SIGNALS — individually insufficient, but combined they tip the scale.
# A noreply sender + any weak subject = marketing.
# ---------------------------------------------------------------------------

NOREPLY_SENDER = re.compile(
    r"\bnoreply\b | \bno.reply\b | \bdo.not.reply\b | \bdonotreply\b",
    re.IGNORECASE | re.VERBOSE,
)

WEAK_SUBJECT = re.compile(r"""
    \btips?\b       | \bguide\b    | \binsights?\b |
    \bupdate[sd]?\b | \breminder\b | \binvitation\b |
    \bannounce\b    | \bannounced\b | \bannouncing\b |
    \bwelcome\b     | \bonboard\b  |
    \bthis\s+week\b | \bthis\s+month\b |
    \bpopular\b     | \btrending\b | \bfeatured\b |
    \bexclusive\b   | \bspecial\b.*\bfor\s+you\b |
    \bdiscover\b    | \bexplore\b  |
    fastest\s+way   | popular\s+ways | next\s+answer
""", re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# Classification engine
# ---------------------------------------------------------------------------

def classify(sender: str, subject: str) -> tuple[bool, str]:
    """
    Returns (is_marketing, reason).
    Reason is a short string for verbose logging.
    """
    # 1. Safe allowlist always wins
    if SAFE_SENDER.search(sender):
        return False, "safe-allowlist"

    # 2. Strong sender match → definite marketing
    if MARKETING_SENDER_STRONG.search(sender):
        return True, "sender:strong"

    # 3. Marketing subject → definite marketing
    if MARKETING_SUBJECT.search(subject):
        return True, "subject:match"

    # 4. Weak combo: noreply sender + weak engagement subject
    if NOREPLY_SENDER.search(sender) and WEAK_SUBJECT.search(subject):
        return True, "sender:noreply+subject:weak"

    return False, "keep"


# ---------------------------------------------------------------------------
# Thunderbird MCP HTTP client
# ---------------------------------------------------------------------------

_req_id = 0

def _mcp_call(token: str, port: int, tool_name: str, arguments: dict) -> object:
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

    content = raw.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        return json.loads(content[0]["text"])

    raise RuntimeError(f"Unexpected MCP response: {raw}")


def load_connection(connection_file: str) -> tuple[str, int]:
    try:
        with open(connection_file, encoding="utf-8") as f:
            data = json.load(f)
        return data["token"], data["port"]
    except FileNotFoundError:
        sys.exit(
            f"\n[ERROR] Connection file not found:\n  {connection_file}\n\n"
            "Make sure Thunderbird is running and the thunderbird-mcp extension is active.\n"
            "See: https://github.com/rodrigoazlima/scripts-archive-marketing\n"
        )
    except KeyError as e:
        sys.exit(f"\n[ERROR] Malformed connection file — missing key: {e}\n")


def fetch_page(token, port, inbox, offset, page_size, days_back) -> tuple[list, int]:
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


def move_emails(token, port, inbox, message_ids: list, destination: str) -> int:
    result = _mcp_call(token, port, "updateMessage", {
        "folderPath": inbox,
        "messageIds": message_ids,
        "moveTo": destination,
    })
    return result.get("updated", len(message_ids))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(args):
    token, port = load_connection(args.connection_file)

    total_archived = 0
    total_kept = 0
    reason_counts: dict[str, int] = {}
    offset = args.start_offset
    page_num = 0

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{'='*62}")
    print(f"  {mode}Thunderbird Inbox Marketing Archiver")
    print(f"  https://github.com/rodrigoazlima/scripts-archive-marketing")
    print(f"{'='*62}")
    print(f"  Inbox  : {args.inbox}")
    print(f"  Archive: {args.archive_folder}")
    print(f"  Offset : {offset}  |  Page: {args.page_size}  |  Delay: {args.fetch_delay}s")
    print(f"{'='*62}\n")

    while True:
        page_num += 1
        print(f"[Page {page_num:>3}] offset={offset:<6}", end=" ... ", flush=True)

        emails, total = [], 0
        for attempt in range(3):
            try:
                emails, total = fetch_page(
                    token, port, args.inbox, offset, args.page_size, args.days_back
                )
                break
            except Exception as exc:
                if attempt == 2:
                    print(f"\n[ERROR] Failed after 3 attempts: {exc}\nStopping.")
                    _print_summary(total_archived, total_kept, reason_counts, args.dry_run)
                    return
                wait = 10 * (attempt + 1)
                print(f"\n  Retry {attempt+1}/3 in {wait}s ({exc}) ...", end=" ", flush=True)
                time.sleep(wait)

        print(f"fetched {len(emails):<4}  (inbox total: ~{total})", flush=True)

        if not emails:
            print("  No more emails. Done!\n")
            break

        marketing_ids = []
        for email in emails:
            sender  = email.get("author", "")
            subject = email.get("subject", "")
            mid     = email.get("id", "")

            is_mkt, reason = classify(sender, subject)
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

            if is_mkt:
                marketing_ids.append(mid)
                if args.verbose:
                    print(f"    ✗ [{reason:<30}] {sender[:40]:<40}  {subject[:45]}")
            else:
                if args.verbose:
                    print(f"    ✓ [{reason:<30}] {sender[:40]:<40}  {subject[:45]}")

        kept = len(emails) - len(marketing_ids)
        print(f"         Marketing: {len(marketing_ids):<4}  Keeping: {kept}", flush=True)

        if marketing_ids and not args.dry_run:
            for i in range(0, len(marketing_ids), args.move_batch):
                batch = marketing_ids[i : i + args.move_batch]
                try:
                    moved = move_emails(token, port, args.inbox, batch, args.archive_folder)
                    print(f"         Archived {moved} (batch {i // args.move_batch + 1})", flush=True)
                except Exception as exc:
                    print(f"         [ERROR] Move failed: {exc}", flush=True)
                if i + args.move_batch < len(marketing_ids):
                    time.sleep(args.move_delay)

        total_archived += len(marketing_ids)
        total_kept += kept

        if len(emails) < args.page_size:
            print("  Last page. Done!\n")
            break

        offset += args.page_size
        print(
            f"         Total so far: {total_archived} archived / {total_kept} kept"
            f"  — sleeping {args.fetch_delay}s...\n",
            flush=True,
        )
        time.sleep(args.fetch_delay)

    _print_summary(total_archived, total_kept, reason_counts, args.dry_run)


def _print_summary(archived, kept, reason_counts, dry_run):
    print(f"\n{'='*62}")
    if dry_run:
        print(f"  DRY RUN — no emails moved.  Would have archived: {archived}")
    else:
        print(f"  COMPLETE")
        print(f"  Archived : {archived}")
    print(f"  Kept     : {kept}")
    if reason_counts:
        print(f"\n  Breakdown by classification reason:")
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"    {reason:<35} {count:>6}")
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
    p.add_argument("--inbox",            default=DEFAULT_INBOX,
                   help="IMAP folder URI of your inbox.")
    p.add_argument("--archive-folder",   default=DEFAULT_ARCHIVE_FOLDER,
                   help="IMAP folder URI to move marketing emails into.")
    p.add_argument("--connection-file",  default=DEFAULT_CONNECTION_FILE,
                   help="Path to thunderbird-mcp connection.json.")
    p.add_argument("--page-size",        type=int,   default=DEFAULT_PAGE_SIZE)
    p.add_argument("--fetch-delay",      type=float, default=DEFAULT_FETCH_DELAY,
                   help="Seconds between page fetches (IMAP rate limit).")
    p.add_argument("--move-delay",       type=float, default=DEFAULT_MOVE_DELAY,
                   help="Seconds between bulk-move calls.")
    p.add_argument("--move-batch",       type=int,   default=DEFAULT_MOVE_BATCH,
                   help="Max message IDs per move request.")
    p.add_argument("--start-offset",     type=int,   default=DEFAULT_START_OFFSET,
                   help="Skip first N emails (resume support).")
    p.add_argument("--days-back",        type=int,   default=DEFAULT_DAYS_BACK,
                   help="How many days back to scan.")
    p.add_argument("--dry-run",          action="store_true",
                   help="Classify only — do not move any email.")
    p.add_argument("--verbose", "-v",    action="store_true",
                   help="Print every classification decision.")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    run(args)
