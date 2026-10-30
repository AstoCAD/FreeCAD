# SPDX-License-Identifier: LGPL-2.1-or-later

import re
from importlib import reload

import FreeCAD
import Path
import CAMTests.PathTestUtils as PathTestUtils
from Path.Post.scripts import uccnc_legacy_post as postprocessor


def _arc_words(gcode):
    """The words of the first G2 line of the output."""
    for line in gcode.splitlines():
        if re.match(r"^\s*(N\d+\s+)?G2\b", line):
            return line.split()
    return None


class TestUccncLegacyPost(PathTestUtils.PathTestBase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestUccncLegacyPost")
        self.docobj = self.doc.addObject("Path::Feature", "testpath")
        self.docobj.Path = Path.Path(
            [
                Path.Command("G0 X0 Y0 Z0"),
                Path.Command("G2 X20 Y0 Z0 I10 J0 K0 F600"),
            ]
        )
        reload(postprocessor)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def test_arc_offsets_metric(self):
        gcode = postprocessor.export([self.docobj], "-", "--no-header --no-show-editor")
        words = _arc_words(gcode)
        self.assertIsNotNone(words, gcode)
        self.assertIn("X20.000", words)
        self.assertIn("I10.000", words)
        self.assertIn("J0.000", words)
        self.assertIn("K0.000", words)

    def test_arc_offsets_inches(self):
        # Issue #30603: I, J and K were written in mm while X, Y and Z were
        # converted to inches, so every arc had the wrong center.
        gcode = postprocessor.export([self.docobj], "-", "--no-header --inches --no-show-editor")
        words = _arc_words(gcode)
        self.assertIsNotNone(words, gcode)
        self.assertIn("X0.787", words)
        self.assertIn("I0.394", words)
        self.assertIn("J0.000", words)
        self.assertIn("K0.000", words)
