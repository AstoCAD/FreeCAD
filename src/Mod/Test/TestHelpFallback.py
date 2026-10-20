# SPDX-License-Identifier: LGPL-2.1-or-later
"""Localized help lookup falls back on network errors without hiding other faults."""

import ssl
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

try:
    import Help
except ModuleNotFoundError as error:
    if error.name != "Help":
        raise
    Help = None


@unittest.skipIf(Help is None, "Requires the Help module")
class TestHelpFallback(unittest.TestCase):
    localized = "https://example.invalid/Manual/fr"
    english = "https://example.invalid/Manual"

    def _assert_fallback(self, error):
        with patch.object(Help.urllib.request, "urlopen", side_effect=error):
            try:
                actual = Help.location_url(self.localized, self.english)
            except urllib.error.URLError as failure:
                self.fail("Network error escaped the English fallback: " + str(failure))
        self.assertEqual(actual, (self.english, ""))

    def _response(self, data):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = data
        return response

    def test_certificate_verification_error_uses_english_url(self):
        reason = ssl.SSLCertVerificationError("certificate verify failed")
        self._assert_fallback(urllib.error.URLError(reason))

    def test_other_url_error_uses_english_url(self):
        self._assert_fallback(urllib.error.URLError(ConnectionRefusedError("connection refused")))

    def test_http_error_uses_english_url_control(self):
        error = urllib.error.HTTPError(self.localized, 404, "Not Found", None, None)
        self._assert_fallback(error)

    def test_success_retains_localized_url_and_title_control(self):
        response = self._response(b"<html><title>Localized page - FreeCAD</title></html>")
        with patch.object(Help.urllib.request, "urlopen", return_value=response):
            self.assertEqual(
                Help.location_url(self.localized, self.english),
                (self.localized, "Localized page"),
            )

    def test_invalid_content_error_propagates(self):
        response = self._response(b"\xff")
        with patch.object(Help.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(UnicodeDecodeError):
                Help.location_url(self.localized, self.english)

    def test_programming_error_propagates(self):
        error = ValueError("unexpected request implementation failure")
        with patch.object(Help.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(ValueError) as failure:
                Help.location_url(self.localized, self.english)
        self.assertIs(failure.exception, error)
