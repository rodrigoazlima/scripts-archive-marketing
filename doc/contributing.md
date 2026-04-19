# Contributing

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Adding Classification Patterns](#adding-classification-patterns)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)

---

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a feature branch: `git checkout -b feat/your-feature-name`
4. Make changes, add tests, verify CI passes
5. Submit a pull request

---

## Development Setup

```bash
git clone https://github.com/your-fork/scripts-archive-marketing.git
cd scripts-archive-marketing

# Verify setup
python -c "import archive_marketing; print('OK')"
python -m unittest tests.test_classification -v

# Install linter
pip install ruff
ruff check archive_marketing.py tests/
```

No virtual environment is required — the project has no pip dependencies.

---

## Coding Standards

- **Single file:** all application code stays in `archive_marketing.py`
- **No external dependencies:** stdlib only — no `pip install` requirements
- **Python 3.8 compatible:** do not use syntax or stdlib features introduced after 3.8
- **Type hints:** use `typing` module annotations on all function signatures
- **No comments for obvious code:** only add a comment when the *why* is non-obvious
- **`re.VERBOSE`:** all new regex patterns must use verbose mode with category comments

Run linting before submitting:

```bash
ruff check archive_marketing.py tests/
```

---

## Adding Classification Patterns

### New marketing sender domain

Edit `MARKETING_SENDER_STRONG` in `archive_marketing.py`. Add to the appropriate category section using `re.VERBOSE` style:

```python
    # ── Your category ─────────────────────────────────────────────────
    newplatform\.com    |
    mail\.newplatform\.com |
```

**Rules:**
- Escape dots: `\.` not `.`
- Use `|` alternation, not separate patterns
- End each line with `|` except the last entry in the pattern
- Add to an existing category or create a new one with a comment header
- The pattern should match substrings of sender addresses (no anchors needed)

### New subject keyword

Edit `MARKETING_SUBJECT`:

```python
    # ── New category ──────────────────────────────────────────────────
    \byour_keyword\b    |
```

Use `\b` word boundaries for words that might appear as substrings.

For PT-BR keywords with accents, include both forms:
```python
    promo[çc][ãa]o      |   # matches both promoção and promocao
```

### New safe allowlist entry

Edit `SAFE_SENDER`:

```python
    noreply@yourtrustedsender\.com  |
```

### Test requirement

**Every new pattern must have a corresponding test case.** Add it to `tests/test_classification.py` in the appropriate test class:

```python
def test_newplatform_archived(self):
    is_mkt, reason = classify(
        "New Platform <hello@newplatform.com>",
        "Your monthly digest"
    )
    self.assertTrue(is_mkt)
    self.assertEqual(reason, "sender:strong")
```

---

## Testing Guidelines

```bash
# Run all tests
python -m unittest tests.test_classification -v

# Run a specific class
python -m unittest tests.test_classification.TestStrongSenderMarketing -v

# Run a specific test
python -m unittest tests.test_classification.TestSafeAllowlist.test_google_security_alert -v
```

### Test structure rules

- One test class per classification tier
- Test both positive cases (email IS classified correctly) and negative cases (email is NOT misclassified)
- Use `self.assertTrue(is_mkt)` / `self.assertFalse(is_mkt)` + `self.assertEqual(reason, "...")` for precision
- Test inputs should be realistic — use actual sender formats like `"Brand Name <email@domain.com>"`
- Do not test against the raw regex patterns directly — always test through `classify()`

### CI matrix

Tests run automatically on GitHub Actions across:
- **Python versions:** 3.8, 3.9, 3.10, 3.11, 3.12
- **Operating systems:** Ubuntu, Windows, macOS

A pull request must pass all 15 combinations before merging.

---

## Pull Request Process

1. **Branch naming:** `feat/`, `fix/`, `docs/`, `chore/` prefix
2. **One concern per PR:** keep pattern additions, bug fixes, and refactors in separate PRs
3. **Update version:** bump `__version__` in `archive_marketing.py` following semver:
   - `patch` (x.x.N) — bug fixes, pattern corrections
   - `minor` (x.N.0) — new patterns, new features, new config options
   - `major` (N.0.0) — breaking changes to CLI, config format, or behavior
4. **Update changelog:** add an entry to `doc/changelog.md`
5. **Tests must pass:** all 40+ tests + new tests for added patterns
6. **Linting must pass:** `ruff check archive_marketing.py tests/`

### PR description template

```markdown
## What
[Short description of the change]

## Why
[Motivation — what problem does this solve?]

## Testing
- [ ] Added test cases for new patterns
- [ ] All existing tests pass
- [ ] Tested with a real Thunderbird inbox (if behavior change)

## Checklist
- [ ] Version bumped
- [ ] Changelog updated
- [ ] No new pip dependencies introduced
```

---

## Issue Reporting

Use the GitHub issue templates:

- **Bug report:** unexpected archiving behavior, crashes, MCP errors
- **Feature request:** new classification patterns, config options, CLI flags

When reporting a false positive (legitimate email archived):
- Include the sender address (redact if needed) and subject line
- State which rule triggered: run with `--dry-run --verbose` and copy the line

When reporting a false negative (marketing email not archived):
- Include sender and subject
- We will add it to the appropriate pattern tier
