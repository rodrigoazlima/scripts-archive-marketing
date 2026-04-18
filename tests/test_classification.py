"""
Unit tests for archive_marketing.py classification logic.

Run with:
  python -m pytest tests/ -v
  # or without pytest:
  python -m unittest tests.test_classification
"""

import re
import sys
import unittest
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))
from archive_marketing import classify


class TestSafeAllowlist(unittest.TestCase):
    """Emails from trusted senders must never be classified as marketing."""

    def test_google_security_alert(self):
        is_mkt, reason = classify(
            "Google <no-reply@accounts.google.com>",
            "Alerta de segurança"
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "safe-allowlist")

    def test_google_noreply(self):
        is_mkt, _ = classify("noreply@google.com", "Google Takeout ready")
        self.assertFalse(is_mkt)

    def test_github_device_verification(self):
        is_mkt, reason = classify(
            "GitHub <noreply@github.com>",
            "[GitHub] Please verify your device"
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "safe-allowlist")

    def test_apple_security(self):
        is_mkt, _ = classify(
            "Apple <no-reply@apple.com>",
            "Your Apple ID was used to sign in"
        )
        self.assertFalse(is_mkt)


class TestStrongSenderMarketing(unittest.TestCase):
    """Known marketing platforms should always be archived."""

    def test_aliexpress(self):
        is_mkt, reason = classify(
            "AliExpress <ae-best-message@newarrival.aliexpress.com>",
            "Rodrigo, olha isso incrível!"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_mailchimp(self):
        is_mkt, reason = classify(
            "Newsletter <news@mailchimp.com>",
            "Your weekly digest"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_sendgrid(self):
        is_mkt, reason = classify(
            "Acme <no-reply@sendgrid.net>",
            "Welcome to Acme"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_levels_fyi(self):
        is_mkt, reason = classify("hello@levels.fyi", "Talent Pool Now Live!")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_epicgames(self):
        is_mkt, reason = classify(
            "Epic Games <no-reply@acct.epicgames.com>",
            "Special offer for you"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_spotify(self):
        is_mkt, reason = classify("Spotify <no-reply@spotify.com>", "New music for you")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_decolar_travel(self):
        is_mkt, reason = classify(
            "Decolar <alertas@emails.decolar.com>",
            "Voos a partir de R$314"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_klaviyo(self):
        is_mkt, reason = classify("Store <email@klaviyo.com>", "Your cart is waiting")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_linkedin_jobs(self):
        is_mkt, reason = classify(
            "LinkedIn Jobs <jobs-noreply@linkedin.com>",
            "10 new jobs match your profile"
        )
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")


class TestSubjectMarketing(unittest.TestCase):
    """Marketing subjects from unknown senders should be archived."""

    def test_newsletter_subject(self):
        is_mkt, reason = classify("someone@unknown.com", "Our weekly newsletter")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_sale_subject(self):
        is_mkt, reason = classify("shop@unknown.com", "Big sale — 50% off everything")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_desconto_subject(self):
        is_mkt, reason = classify("loja@brasil.com", "Desconto exclusivo para você")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_giveaway_subject(self):
        # neutral sender that doesn't match strong sender patterns
        is_mkt, reason = classify("info@localservice.store", "Giveaway: Win a new laptop")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_unsubscribe_subject(self):
        is_mkt, reason = classify("info@saas.io", "Manage your subscription preferences")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_announcing_subject(self):
        # Use a sender not in any strong pattern
        is_mkt, reason = classify("contact@mylocalbrand.store", "Announcing our new feature")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_free_webinar(self):
        is_mkt, reason = classify("contact@localcompany.store", "Free webinar: grow your business")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_ptbr_oferta(self):
        is_mkt, reason = classify("loja@store.com.br", "Oferta imperdível, aproveite!")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_job_alert(self):
        is_mkt, reason = classify("alerts@jobboard.com", "New job alert: Python Developer")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")

    def test_talent_pool(self):
        is_mkt, reason = classify("hr@recruiter.com", "Talent Pool Now Live!")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "subject:match")


class TestWeakComboMarketing(unittest.TestCase):
    """noreply sender + weak engagement subject = marketing."""

    def test_noreply_reminder(self):
        # "reminder" is in WEAK_SUBJECT only — plus noreply → archive
        is_mkt, reason = classify("noreply@someservice.com", "Account reminder — action needed")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:noreply+subject:weak")

    def test_donotreply_trending(self):
        is_mkt, reason = classify("donotreply@app.io", "Trending content on the platform")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:noreply+subject:weak")

    def test_noreply_featured(self):
        # "featured" is in WEAK_SUBJECT only
        is_mkt, reason = classify("no-reply@tool.ai", "Featured tools for your workflow")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:noreply+subject:weak")


class TestLegitimateEmails(unittest.TestCase):
    """Legitimate emails must never be archived."""

    def test_personal_email(self):
        is_mkt, reason = classify("john.doe@gmail.com", "Meeting tomorrow at 10am")
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")

    def test_celesc_bill(self):
        is_mkt, reason = classify("celesc-fatura@celesc.com.br", "Fatura Celesc - 0051020847")
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")

    def test_anthropic_receipt(self):
        is_mkt, reason = classify(
            "Anthropic <invoice@mail.anthropic.com>",
            "Your receipt from Anthropic, PBC #1234"
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")

    def test_forge_receipt(self):
        is_mkt, reason = classify(
            "The Forge <invoice@forge-vtt.com>",
            "Your receipt from The Forge #2311"
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")

    def test_xai_login(self):
        is_mkt, reason = classify("xAI <noreply@x.ai>", "New login to your xAI account")
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")

    def test_calendar_invite(self):
        is_mkt, reason = classify(
            "Emilly Almeida <psi.emillyalmeida@gmail.com>",
            "Convite: Rodrigo Azevedo Lima"
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")


class TestUserExcludeList(unittest.TestCase):
    """User-defined exclude patterns must override all marketing signals."""

    def test_exclude_overrides_strong_sender(self):
        exclude = [re.compile(r"aliexpress", re.IGNORECASE)]
        is_mkt, reason = classify(
            "AliExpress <promo@aliexpress.com>",
            "Big sale today",
            exclude_patterns=exclude,
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "user-exclude")

    def test_exclude_by_subject(self):
        exclude = [re.compile(r"company newsletter", re.IGNORECASE)]
        is_mkt, reason = classify(
            "hr@mycompany.com",
            "Company Newsletter — Q1 Update",
            exclude_patterns=exclude,
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "user-exclude")

    def test_no_exclude_still_archives(self):
        is_mkt, _ = classify("promo@aliexpress.com", "Big sale today", exclude_patterns=[])
        self.assertTrue(is_mkt)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_empty_sender_and_subject(self):
        is_mkt, reason = classify("", "")
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "keep")

    def test_unicode_subject(self):
        is_mkt, _ = classify("loja@shop.com.br", "🔥 Oferta imperdível hoje!")
        self.assertTrue(is_mkt)

    def test_mixed_case_sender(self):
        is_mkt, reason = classify("News@MAILCHIMP.COM", "Weekly update")
        self.assertTrue(is_mkt)
        self.assertEqual(reason, "sender:strong")

    def test_percentage_discount(self):
        is_mkt, _ = classify("shop@store.com", "Get 70% off all items this weekend")
        self.assertTrue(is_mkt)

    def test_safe_sender_beats_marketing_subject(self):
        """Google security alerts must be kept even if subject looks promotional."""
        is_mkt, reason = classify(
            "Google <no-reply@accounts.google.com>",
            "Free security check — act now"
        )
        self.assertFalse(is_mkt)
        self.assertEqual(reason, "safe-allowlist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
