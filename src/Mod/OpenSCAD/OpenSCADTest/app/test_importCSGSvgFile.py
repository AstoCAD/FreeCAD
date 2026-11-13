# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG import() of an SVG file.

The importer reads the SVG file into a temporary document and closes it
again. The document that was active before must be active again afterwards,
and the imported shape must go into the document being imported into.
"""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG

SVG = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0 0 20 10">\n'
    '<path d="M 0,0 L 20,0 L 20,10 L 0,10 Z"/>\n'
    "</svg>\n"
)


class TestCsgImportSvgFile(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-svg-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _csg(self, svg=SVG):
        folder = Path(self.temp.name)
        (folder / "shape.svg").write_text(svg, encoding="utf-8")
        path = folder / "SvgFile.csg"
        path.write_text('import(file = "shape.svg", layer = "");\n', encoding="utf-8")
        return str(path)

    def _active(self):
        """The active document as the application and as App.ActiveDocument name it."""
        active = App.activeDocument()
        try:
            attribute = App.ActiveDocument.Name if App.ActiveDocument else None
        except ReferenceError:
            attribute = "<closed document>"
        return (active.Name if active else None, attribute)

    def _new_documents(self):
        return set(App.listDocuments()) - self.before

    def _assert_rectangle(self, obj):
        self.assertIsNotNone(obj)
        self.assertAlmostEqual(obj.Shape.BoundBox.XLength, 20.0, places=6)
        self.assertAlmostEqual(obj.Shape.BoundBox.YLength, 10.0, places=6)

    def test_open_leaves_the_new_document_active(self):
        doc = importCSG.open(self._csg())
        self._assert_rectangle(doc.getObject("shape"))
        self.assertEqual(self._new_documents(), {doc.Name})
        self.assertEqual(self._active(), (doc.Name, doc.Name))
        App.closeDocument(doc.Name)
        self.assertEqual(self._active(), (None, None))

    def test_insert_into_a_document_that_is_not_active(self):
        target = App.newDocument("SvgFileTarget")
        active = App.newDocument("SvgFileActive")
        App.setActiveDocument(active.Name)
        importCSG.insert(self._csg(), target.Name)
        self._assert_rectangle(target.getObject("shape"))
        self.assertEqual(active.Objects, [])
        self.assertEqual(self._new_documents(), {target.Name, active.Name})
        self.assertEqual(self._active(), (active.Name, active.Name))

    def test_unreadable_svg_file(self):
        target = App.newDocument("SvgFileTarget")
        App.setActiveDocument(target.Name)
        with self.assertRaises(Exception):
            importCSG.insert(self._csg(SVG[: SVG.index("<path")]), target.Name)
        self.assertEqual(self._new_documents(), {target.Name})
        self.assertEqual(self._active(), (target.Name, target.Name))


if __name__ == "__main__":
    unittest.main()
