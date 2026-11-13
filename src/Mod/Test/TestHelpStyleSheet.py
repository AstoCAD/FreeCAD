# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Help stylesheet is decoded as UTF-8, the charset of the page it goes into."""

import codecs
import os
import tempfile
import unittest

import FreeCAD as App

try:
    import Help
except ModuleNotFoundError as error:
    if error.name != "Help":
        raise
    Help = None

# "Á" is C3 81 in UTF-8; 0x81 has no meaning in Windows-1252, so reading the file
# in that locale encoding fails, and the other characters turn into mojibake.
RULE = 'li::before { content: "• Ávila Ω"; }'


@unittest.skipIf(Help is None, "Requires the Help module")
class TestHelpStyleSheet(unittest.TestCase):
    def setUp(self):
        self.prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Help")
        had = "StyleSheet" in self.prefs.GetStrings()
        old = self.prefs.GetString("StyleSheet")

        def restore():
            if had:
                self.prefs.SetString("StyleSheet", old)
            else:
                self.prefs.RemString("StyleSheet")

        self.addCleanup(restore)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "help.css")

    def _convert_with(self, data):
        with open(self.path, "wb") as stream:
            stream.write(data)
        self.prefs.SetString("StyleSheet", self.path)
        return Help.convert("# Title\n", "raw")

    def test_utf8_stylesheet_is_inserted_unchanged(self):
        html = self._convert_with(RULE.encode("utf-8"))
        self.assertIn("<style>\n" + RULE + "\n</style>", html)

    def test_byte_order_mark_is_not_part_of_the_stylesheet(self):
        html = self._convert_with(codecs.BOM_UTF8 + RULE.encode("utf-8"))
        self.assertIn("<style>\n" + RULE + "\n</style>", html)

    def test_invalid_utf8_byte_does_not_prevent_the_page(self):
        html = self._convert_with(b"/* caf\xe9 */\n" + RULE.encode("utf-8"))
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("/* caf� */\n" + RULE, html)
