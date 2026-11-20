# SPDX-License-Identifier: LGPL-2.1-or-later
"""The bundled templates match the folder the New Page panel picks them from.

The panel takes the first SVG in <standard>/<size>/<landscape|portrait>, so a
template must have the orientation of its folder. The Chinese A0, A1 and A2
NO_CLIP templates were landscape sheets in the portrait folders, and the
ISO5457-NoTitleBlock A2 portrait template was a copy of the minimal one with
its title block.
"""

import os
import unittest

import FreeCAD


ORIENTATIONS = {"landscape": "Landscape", "portrait": "Portrait"}


def templateDir():
    return os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw", "Templates")


def layoutTemplates(baseDir):
    """Yield (standard, orientation, path) for every SVG in the panel layout."""
    for standard in sorted(os.listdir(baseDir)):
        standardDir = os.path.join(baseDir, standard)
        if not os.path.isdir(standardDir):
            continue
        for size in sorted(os.listdir(standardDir)):
            for orientation in ORIENTATIONS:
                folder = os.path.join(standardDir, size, orientation)
                if not os.path.isdir(folder):
                    continue
                for name in sorted(os.listdir(folder)):
                    if name.lower().endswith(".svg"):
                        yield standard, orientation, os.path.join(folder, name)


class TemplateFolderLayoutTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TemplateFolderLayoutTest")
        self.template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        self.templates = list(layoutTemplates(templateDir()))
        self.assertTrue(self.templates, templateDir())

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def load(self, path):
        # Setting Template reads the size, orientation and fields of the file
        self.template.Template = path
        return self.template

    def testOrientationMatchesFolder(self):
        for _standard, orientation, path in self.templates:
            with self.subTest(template=os.path.relpath(path, templateDir())):
                template = self.load(path)
                self.assertEqual(
                    template.Orientation,
                    ORIENTATIONS[orientation],
                    "%s x %s" % (template.Width, template.Height),
                )

    def testNoTitleBlockTemplatesHaveNoFields(self):
        checked = 0
        for standard, _orientation, path in self.templates:
            if "notitleblock" not in standard.lower():
                continue
            checked += 1
            with self.subTest(template=os.path.relpath(path, templateDir())):
                self.assertEqual(self.load(path).EditableTexts, {})
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
