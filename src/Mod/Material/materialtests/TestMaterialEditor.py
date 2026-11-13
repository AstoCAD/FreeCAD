# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Tests for the Python material editor (MaterialEditor.py) that need no dialog
"""

import os
import tempfile
import unittest

import MaterialEditor


class _PreviewStub:
    """Records what the editor loads into a preview widget"""

    def __init__(self):
        self.svg = None

    def load(self, data):
        self.svg = bytes(data).decode("utf8")


class _WidgetStub:
    def __init__(self):
        self.PreviewRender = _PreviewStub()
        self.PreviewVector = _PreviewStub()


class MaterialEditorPreviewTestCases(unittest.TestCase):
    """
    MaterialEditor.updatePreviews colours the preview images from the material
    """

    def setUp(self):
        icons = tempfile.TemporaryDirectory()
        self.addCleanup(icons.cleanup)
        for name in ("preview-rendered.svg", "preview-vector.svg"):
            with open(os.path.join(icons.name, name), "w", encoding="utf8") as svg:
                svg.write('<svg fill="#d3d7cf" stroke="#555753"/>')

        # bypass __init__, which builds the dialog
        self.editor = MaterialEditor.MaterialEditor.__new__(MaterialEditor.MaterialEditor)
        self.editor.iconPath = icons.name + os.sep
        self.editor.widget = _WidgetStub()

    def testViewColorWithoutDiffuseColor(self):
        self.editor.updatePreviews(mat={"ViewColor": "(1.0, 0.0, 0.0, 1.0)"})
        expected = '<svg fill="#ff0000" stroke="#7d0000"/>'
        self.assertEqual(self.editor.widget.PreviewRender.svg, expected)
        self.assertEqual(self.editor.widget.PreviewVector.svg, expected)

    def testDiffuseColorBeforeViewColor(self):
        self.editor.updatePreviews(
            mat={"DiffuseColor": "(0.0, 1.0, 0.0, 1.0)", "ViewColor": "(1.0, 0.0, 0.0, 1.0)"}
        )
        expected = '<svg fill="#00ff00" stroke="#007d00"/>'
        self.assertEqual(self.editor.widget.PreviewRender.svg, expected)
        self.assertEqual(self.editor.widget.PreviewVector.svg, expected)
