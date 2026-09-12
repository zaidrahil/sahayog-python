"""
tests/test_multilingual.py
--------------------------
Unit and integration tests for Sahayog's 11-language Indian multilingual support.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from translations import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_LANGUAGE_CODES,
    TRANSLATIONS,
    CATEGORY_TRANSLATIONS,
    translate,
    translate_category,
    get_language_info,
)
from app import app


class TestMultilingualSupport(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def test_all_supported_languages_configured(self):
        self.assertEqual(len(SUPPORTED_LANGUAGES), 11)
        expected_codes = {"en", "hi", "te", "mr", "ta", "bn", "kn", "gu", "ml", "pa", "or"}
        self.assertEqual(SUPPORTED_LANGUAGE_CODES, expected_codes)

    def test_required_translation_keys_present_in_all_languages(self):
        reference_keys = set(TRANSLATIONS["en"].keys())
        for code, native, english, flag in SUPPORTED_LANGUAGES:
            self.assertIn(code, TRANSLATIONS, f"Missing translations for language code: {code}")
            lang_keys = set(TRANSLATIONS[code].keys())
            missing = reference_keys - lang_keys
            self.assertEqual(missing, set(), f"Language '{code}' is missing keys: {missing}")

    def test_category_translations_present_in_all_languages(self):
        expected_categories = {
            "electrician", "plumber", "carpenter", "painter", "domestic_help",
            "caregiver", "driver", "gardener", "cleaner", "technician"
        }
        for code, native, english, flag in SUPPORTED_LANGUAGES:
            self.assertIn(code, CATEGORY_TRANSLATIONS, f"Missing category translations for {code}")
            cat_keys = set(CATEGORY_TRANSLATIONS[code].keys())
            self.assertEqual(cat_keys, expected_categories, f"Language '{code}' missing categories: {expected_categories - cat_keys}")

    def test_translate_function_fallback(self):
        # Existing key
        self.assertEqual(translate("app_name", "hi"), "सहयोग")
        self.assertEqual(translate("app_name", "te"), "సహాయోగ్")
        self.assertEqual(translate("app_name", "ta"), "சகயோக்")
        # Non-existent language fallback to english
        self.assertEqual(translate("app_name", "xyz"), "Sahayog")
        # Non-existent key fallback to key itself
        self.assertEqual(translate("non_existent_key_123", "hi"), "non_existent_key_123")

    def test_translate_category_function(self):
        self.assertEqual(translate_category("electrician", "hi"), "इलेक्ट्रीशियन")
        self.assertEqual(translate_category("electrician", "te"), "ఎలక్ట్రీషియన్")
        self.assertEqual(translate_category("plumber", "mr"), "प्लंबर")
        self.assertEqual(translate_category("carpenter", "ta"), "தச்சர்")

    def test_get_language_info(self):
        info_te = get_language_info("te")
        self.assertEqual(info_te["code"], "te")
        self.assertEqual(info_te["native_name"], "తెలుగు")
        self.assertEqual(info_te["flag"], "🇮🇳")

    def test_http_set_language_routes(self):
        """Test setting each of the 11 languages via HTTP and verifying rendered HTML."""
        for code, native, english, flag in SUPPORTED_LANGUAGES:
            with self.subTest(code=code):
                res = self.client.get(f"/lang/{code}", follow_redirects=True)
                self.assertEqual(res.status_code, 200)
                html = res.data.decode("utf-8")
                # Verify language attribute in <html> tag
                self.assertIn(f'<html lang="{code}">', html)
                # Verify native script appears in the rendered navbar
                self.assertIn(native, html)
                # Verify translated trade names appear on the landing page
                translated_electrician = translate_category("electrician", code)
                self.assertIn(translated_electrician, html)


if __name__ == "__main__":
    unittest.main()
