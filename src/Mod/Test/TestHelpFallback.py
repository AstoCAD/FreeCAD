# SPDX-License-Identifier: LGPL-2.1-or-later
"""Localized help lookup falls back on network errors without hiding other faults."""

import socket
import ssl
import threading
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

    def _call_with_stalled_server(self, func):
        """Run func(url) against a local server that accepts but never answers.

        Help.show() runs in the GUI thread, so a lookup that never returns
        freezes FreeCAD (#32052). Returns the list of results, which is empty
        when the call is still blocked.
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = []
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(4)
            url = "http://127.0.0.1:%d/Manual/fr" % server.getsockname()[1]

            def run():
                try:
                    result.append(func(url))
                except Exception as error:
                    result.append(error)

            with patch.object(Help, "NETWORK_TIMEOUT", 1, create=True):
                worker = threading.Thread(target=run, daemon=True)
                worker.start()
                worker.join(20)
                blocked = worker.is_alive()
        finally:
            server.close()
        self.assertFalse(blocked, "Help request still blocked after 20 s on a stalled server")
        return result

    def test_stalled_server_localized_lookup_uses_english_url(self):
        result = self._call_with_stalled_server(lambda url: Help.location_url(url, self.english))
        self.assertEqual(result, [(self.english, "")])

    def test_stalled_server_contents_returns_error_text(self):
        result = self._call_with_stalled_server(Help.get_contents)
        self.assertEqual(result, [Help.ERRORTXT])
