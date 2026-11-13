# SPDX-License-Identifier: LGPL-2.1-or-later
"""Non-ASCII text in the files exchanged with OpenSCAD.

OpenSCAD reads its .scad files and writes its CSG output as UTF-8, and an SVG
file states its own encoding. Text such as a text() string or an SVG title
must reach the other side unchanged, whatever the locale encoding of the
system is (cp1252 on most Windows systems).
"""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import FreeCAD as App
import importCSG
import OpenSCADUtils

# "Á" is C3 81 in UTF-8, and 0x81 is not a character of cp1252; "Ω" and "日"
# are not in cp1252 at all.
TEXT = "Ávila Pièce Ωμέγα 日本"


class TestCsgTextEncoding(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-encoding-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            # The SVG import sets App.ActiveDocument back to the imported
            # document without making it active: activate it so that closing
            # it also resets App.ActiveDocument.
            App.setActiveDocument(name)
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _call_openscad_with_pipes(self, scad, csg):
        """Run the pipes transfer mechanism on the bytes of a .scad file.

        Instead of OpenSCAD, a stand-in process answers with the given CSG
        bytes. Returns the bytes it was sent and the path of the CSG file.
        """
        received = []

        class OpenSCADProcess:
            returncode = 0

            def __init__(self, args, **kwargs):
                pass

            def communicate(self, input=None, timeout=None):
                received.append(input)
                return csg, b""

        source = Path(self.temp.name) / "source.scad"
        source.write_bytes(scad)
        target = Path(self.temp.name) / "result.csg"
        with mock.patch.object(OpenSCADUtils, "getopenscadexe", return_value="openscad"):
            with mock.patch.object(OpenSCADUtils.subprocess, "Popen", OpenSCADProcess):
                result = OpenSCADUtils.call_openscad_with_pipes(
                    str(source), str(target), "csg", False
                )
        self.assertEqual(result, str(target))
        self.assertEqual(len(received), 1)
        return received[0], target

    def test_pipes_send_the_scad_file_as_it_is(self):
        scad = ('text("%s", size = 10);\n' % TEXT).encode("utf-8")
        received, _target = self._call_openscad_with_pipes(scad, b"group();\n")
        self.assertEqual(received, scad)

    def test_pipes_keep_the_text_of_the_csg_output(self):
        csg = 'group() {\n\ttext(text = "%s", size = 10);\n}\n' % TEXT
        _received, target = self._call_openscad_with_pipes(b"cube();\n", csg.encode("utf-8"))
        # the CSG importer reads the file as UTF-8
        self.assertEqual(target.read_text(encoding="utf-8"), csg)

    def test_import_of_an_svg_file_with_non_ascii_text(self):
        folder = Path(self.temp.name)
        (folder / "shape.svg").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" '
            'viewBox="0 0 20 10">\n'
            "<title>%s</title>\n"
            '<path d="M 0,0 L 20,0 L 20,10 L 0,10 Z"/>\n'
            "</svg>\n" % TEXT,
            encoding="utf-8",
        )
        csg = folder / "SvgFile.csg"
        csg.write_text('import(file = "shape.svg", layer = "");\n', encoding="utf-8")
        doc = importCSG.open(str(csg))
        shape = doc.getObject("shape")
        self.assertIsNotNone(shape)
        self.assertAlmostEqual(shape.Shape.BoundBox.XLength, 20.0, places=6)
        self.assertAlmostEqual(shape.Shape.BoundBox.YLength, 10.0, places=6)


if __name__ == "__main__":
    unittest.main()
