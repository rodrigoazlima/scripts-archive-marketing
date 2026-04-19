# Module: Classification Engine

## Table of Contents

- [Overview](#overview)
- [Regex Patterns](#regex-patterns)
  - [SAFE_SENDER](#safe_sender)
  - [MARKETING_SENDER_STRONG](#marketing_sender_strong)
  - [MARKETING_SUBJECT](#marketing_subject)
  - [NOREPLY_SENDER](#noreply_sender)
  - [WEAK_SUBJECT](#weak_subject)
- [classify() Function](#classify-function)
- [Date Helpers](#date-helpers)
- [Extending Patterns](#extending-patterns)
- [Testing Classification](#testing-classification)
- [Known Limitations](#known-limitations)

---

## Overview

The classification engine is the core intelligence of the application. It lives entirely in `archive_marketing.py` between lines ~89 and ~477.

**Design principle:** classification is a **pure function** with no side effects. It takes a sender string and a subject string, applies four compiled regex patterns in priority order, and returns a `(bool, str)` tuple. No I/O, no network, no global state.

All patterns are compiled **once at module load time** — not per email. This makes classification effectively instantaneous (microseconds per email).

---

## Regex Patterns

All patterns use `re.IGNORECASE | re.VERBOSE`. The `re.VERBOSE` flag allows multi-line patterns with comments and whitespace for readability.

### `SAFE_SENDER`

**Purpose:** Allowlist of trusted senders that must never be archived, regardless of subject.

**Covers:**
- `no-reply@accounts.google.com` — Google account security alerts
- `noreply@google.com` — Google service notifications
- `security@*.google.com` — Google security team
- `no-reply@*.apple.com` — Apple account alerts
- `security-noreply@*.amazon.com` — Amazon security
- `account-security-noreply@*` — Generic account security pattern
- `noreply@github.com` / `no-reply@github.com` — GitHub alerts

**Why these specifically?** These senders commonly use `noreply` prefixes and promotional-sounding language (e.g., "Your account was accessed from a new location") that could trigger the weak-combo rule. The safe allowlist ensures they are evaluated first.

---

### `MARKETING_SENDER_STRONG`

**Purpose:** Match known marketing platforms, e-commerce sites, and promotional services by sender domain. A single match here immediately archives the email.

**Categories covered:**

| Category | Examples |
|----------|---------|
| Email marketing platforms | Mailchimp, SendGrid, Klaviyo, ActiveCampaign, Brevo, Iterable, Customer.io |
| E-commerce (BR + global) | AliExpress, Mercado Livre, Shopee, Shein, Americanas, Kabum, eBay |
| Travel | Decolar, Booking.com, Airbnb, LATAM Airlines, Expedia |
| Food delivery | iFood, Rappi, Uber Eats, DoorDash |
| Finance marketing | Serasa Experian, 99Pay, PAN |
| Job boards | Indeed, Glassdoor, Catho, Vagas.com, LinkedIn jobs |
| Tech newsletters | Medium, Substack, Product Hunt, Morning Brew, TLDR.tech |
| AI/Dev newsletters | Ollama, email.claude.com, Perplexity, Kilo Code |
| Social media digests | Facebook Mail, Instagram notifications, Twitter mailer |
| Gaming | Epic Games, Steam, PlayStation, Xbox, Blizzard |
| Streaming | Netflix, Spotify, Disney+, HBO Max |
| Crypto | Binance, Coinbase, Bybit, Kraken |
| Events | Eventbrite, Sympla, Komoot |
| Generic patterns | `promotion@`, `marketing@`, `newsletter@`, `hello@*.io` |

**Pattern philosophy:** Match domain substrings (not exact domains) so that subdomains like `email.spotify.com` or `campaigns.mailchimp.com` are caught without enumerating every possible subdomain. The patterns are intentionally broad for sender matching — false positives at this tier are very rare because legitimate business email rarely comes from `mailchimp.com`.

---

### `MARKETING_SUBJECT`

**Purpose:** Match promotional keywords in the subject line. A match here archives the email regardless of sender.

**Categories covered:**

| Category | Keywords (sample) |
|----------|-----------------|
| Discount / price | `desconto`, `oferta`, `sale`, `% off`, `coupon`, `cashback`, `frete grátis` |
| Urgency | `última chance`, `hurry`, `act now`, `last chance`, `don't miss` |
| Newsletter | `newsletter`, `digest`, `weekly`, `roundup`, `top stories` |
| Announcements | `announcing`, `introducing`, `just launched`, `now live`, `changelog` |
| Re-engagement | `we miss you`, `come back`, `trial expired`, `upgrade your` |
| Giveaway | `giveaway`, `contest`, `raffle`, `win a free` |
| Content marketing | `free ebook`, `free guide`, `free webinar`, `download your` |
| Unsubscribe signals | `unsubscribe`, `email preferences`, `opt-out` |
| Job board spam | `jobs for you`, `recommended jobs`, `job alert`, `top vagas` |
| PT-BR promotional | `imperdível`, `aproveite`, `confira já`, `novidade`, `lançamento` |
| SaaS onboarding | `welcome to`, `complete your setup`, `create an instance` |

**Note on PT-BR:** Accent-insensitive matching is not built into Python's `re` module. Patterns include both accented and unaccented variants explicitly (e.g., `gr[áa]tis` matches both `grátis` and `gratis`).

---

### `NOREPLY_SENDER`

**Purpose:** Detect `noreply`-style sender addresses as a weak signal (insufficient alone).

**Matches:**
- `noreply`
- `no-reply`
- `do-not-reply`
- `donotreply`

Case-insensitive, word boundary anchored.

---

### `WEAK_SUBJECT`

**Purpose:** Engagement-sounding words that are too generic to archive alone but are strong signals when combined with a `noreply` sender.

**Matches:** `tips`, `guide`, `insights`, `update`, `reminder`, `announce`, `welcome`, `onboard`, `this week`, `this month`, `popular`, `trending`, `featured`, `discover`, `explore`, `fastest way`, `popular ways`, `next answer`

---

## `classify()` Function

```python
def classify(
    sender: str,
    subject: str,
    exclude_patterns: Optional[List[re.Pattern]] = None,
) -> Tuple[bool, str]:
```

**Evaluation order (first match wins):**

```
1. exclude_patterns   → (False, "user-exclude")
2. SAFE_SENDER        → (False, "safe-allowlist")
3. MARKETING_SENDER_STRONG → (True, "sender:strong")
4. MARKETING_SUBJECT  → (True, "subject:match")
5. NOREPLY + WEAK     → (True, "sender:noreply+subject:weak")
6. default            → (False, "keep")
```

The function uses short-circuit evaluation: as soon as a rule matches, it returns immediately without evaluating subsequent rules. This makes the safe allowlist an absolute override — a Google security alert cannot be archived even if its subject contains the word `newsletter`.

**Input handling:** The function is tolerant of empty strings. If `sender` or `subject` is empty, the regex patterns simply don't match and the email defaults to "keep".

---

## Date Helpers

### `_parse_email_date()`

```python
def _parse_email_date(msg: Dict) -> Optional[datetime]
```

Extracts a `datetime` from an MCP message dict. Tries these field names in order:

1. `date`
2. `dateReceived`
3. `receivedAt`
4. `Date`
5. `received`

Handles both Unix timestamps (seconds or milliseconds, distinguished by magnitude > 1e10) and ISO 8601 strings with or without milliseconds or `Z` suffix.

Returns `None` if no parseable date field is found. When `None` is returned, the email is treated as **within range** (not filtered out).

### `_date_arg()`

```python
def _date_arg(s: str) -> date_type
```

`argparse` type converter for `--date-from` and `--date-to`. Parses `YYYY-MM-DD` format and raises `argparse.ArgumentTypeError` on invalid input.

---

## Extending Patterns

All patterns use `re.VERBOSE` — add entries freely with standard Python regex syntax.

### Adding a new marketing platform (sender)

In `MARKETING_SENDER_STRONG`:

```python
    # ── Your new category ────────────────────────────────────────────
    yourplatform\.com   |
    mail\.yourplatform\.com |
```

### Adding a new keyword (subject)

In `MARKETING_SUBJECT`:

```python
    # ── New promotional term ──────────────────────────────────────────
    \byour_keyword\b   |
```

Use `\b` word boundaries for keywords that could appear as substrings of other words.

### Adding to the safe allowlist

In `SAFE_SENDER`:

```python
    noreply@yourbank\.com    |
```

### Adding an always-keep domain via config

Preferred over editing the source — use `exclude` in `config.json`:

```json
{
  "exclude": ["noreply@yourbank\\.com"]
}
```

Or via CLI: `--exclude "noreply@yourbank\.com"`

> **Important:** Add a test case in `tests/test_classification.py` whenever you add a new pattern. This ensures the pattern does what you expect and prevents regressions.

---

## Testing Classification

```bash
# Run all 40 tests
python -m unittest tests.test_classification -v

# Run a single test class
python -m unittest tests.test_classification.TestStrongSenderMarketing -v

# Run a single test method
python -m unittest tests.test_classification.TestSafeAllowlist.test_google_security_alert -v
```

### Test structure

Each test class maps to one classification tier:

| Class | Tier |
|-------|------|
| `TestSafeAllowlist` | SAFE_SENDER |
| `TestStrongSenderMarketing` | MARKETING_SENDER_STRONG |
| `TestSubjectMarketing` | MARKETING_SUBJECT |
| `TestWeakComboMarketing` | NOREPLY + WEAK_SUBJECT |
| `TestLegitimateEmails` | Default keep |
| `TestUserExcludeList` | User exclude patterns |

### Writing a new test

```python
class TestMyNewPattern(unittest.TestCase):
    def test_my_platform_archived(self):
        is_mkt, reason = classify(
            "My Platform <hello@myplatform.io>",
            "Your weekly report"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")
```

---

## Known Limitations

| Limitation | Impact |
|-----------|--------|
| No body reading | ~5% false-negative rate for marketing without platform branding |
| No ML / Bayesian scoring | Cannot learn from user corrections automatically |
| Regex only | Pattern maintenance is manual as new platforms emerge |
| No accent normalization | PT-BR patterns must enumerate both accented and unaccented variants |
| Subject language detection | Non-EN/PT-BR marketing emails may not match subject patterns |
| `noreply` + `weak` combo | Some transactional emails (e.g., bank statements) may be archived if sender uses `noreply` and subject contains `update` or `reminder` — use `exclude` list to correct |
