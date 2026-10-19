# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
import os
import unittest


class DrawHatchTest(unittest.TestCase):
    def setUp(self):
        """Creates a page and view"""
        self.path = os.path.dirname(os.path.abspath(__file__))
        print("TDHatch path: " + self.path)
        templateFileSpec = self.path + "/TestTemplate.svg"

        FreeCAD.newDocument("TDHatch")
        FreeCAD.setActiveDocument("TDHatch")
        FreeCAD.ActiveDocument = FreeCAD.getDocument("TDHatch")

        # make source feature
        box = FreeCAD.ActiveDocument.addObject("Part::Box", "Box")

        # make a page
        self.page = FreeCAD.ActiveDocument.addObject("TechDraw::DrawPage", "Page")
        FreeCAD.ActiveDocument.addObject("TechDraw::DrawSVGTemplate", "Template")
        FreeCAD.ActiveDocument.Template.Template = templateFileSpec
        FreeCAD.ActiveDocument.Page.Template = FreeCAD.ActiveDocument.Template
        self.page.Scale = 5.0
        # page.ViewObject.show()  #unit tests run in console mode

        # make Views
        self.view = FreeCAD.ActiveDocument.addObject("TechDraw::DrawViewPart", "View")
        FreeCAD.ActiveDocument.View.Source = [box]
        self.page.addView(self.view)
        FreeCAD.ActiveDocument.recompute()

    def tearDown(self):
        FreeCAD.closeDocument("TDHatch")

    def testMakeHatchCase(self):
        """Tests if hatch area can be added to view"""
        # make hatch
        print("making hatch")
        hatch = FreeCAD.ActiveDocument.addObject("TechDraw::DrawHatch", "Hatch")
        hatch.Source = (self.view, ["Face0"])
        hatchFileSpec = self.path + "/TestHatch.svg"
        # comment out to use default from preferences
        hatch.HatchPattern = (
            hatchFileSpec
        )
        print("finished hatch")
        FreeCAD.ActiveDocument.recompute()

        self.assertTrue("Up-to-date" in hatch.State)

    def testBitmapHatchWithoutTextureWarnings(self):
        """A bitmap hatch exports its texture without invalid brush warnings."""
        if not FreeCAD.GuiUp:
            self.skipTest("Bitmap rendering requires the GUI")
        import base64
        import tempfile
        import time
        import xml.etree.ElementTree as ET
        from pathlib import Path
        import FreeCADGui
        import TechDrawGui
        from PySide import QtCore, QtGui

        def process_events(milliseconds=100):
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(milliseconds, loop.quit)
            loop.exec_()

        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 2
        self.view.X = 50
        self.view.Y = 50
        FreeCAD.ActiveDocument.recompute()
        deadline = time.monotonic() + 10
        while not self.view.getVisibleEdges() and time.monotonic() < deadline:
            process_events()
        self.assertTrue(self.view.getVisibleEdges())
        FreeCADGui.activeDocument().getObject(self.page.Name).show()
        process_events()

        messages = []

        def handler(message_type, context, message):
            messages.append(str(message))

        with tempfile.TemporaryDirectory() as directory:
            tile_path = Path(directory) / "red_tile.png"
            tile = QtGui.QImage(16, 16, QtGui.QImage.Format_RGB32)
            tile.fill(QtGui.QColor("red"))
            self.assertTrue(tile.save(str(tile_path)))
            old_handler = QtCore.qInstallMessageHandler(handler)
            try:
                hatch = FreeCAD.ActiveDocument.addObject("TechDraw::DrawHatch", "BitmapHatch")
                hatch.Source = (self.view, ["Face0"])
                hatch.HatchPattern = str(tile_path)
                FreeCAD.ActiveDocument.recompute()
                self.view.requestPaint()
                process_events(300)
                svg_path = Path(directory) / "bitmap_hatch.svg"
                TechDrawGui.exportPageAsSvg(self.page, str(svg_path))
                process_events()
            finally:
                QtCore.qInstallMessageHandler(old_handler)

            red_textures = 0
            for element in ET.parse(svg_path).getroot().iter():
                if element.tag.rsplit("}", 1)[-1] != "image":
                    continue
                href = element.get("{http://www.w3.org/1999/xlink}href", element.get("href", ""))
                if ";base64," not in href:
                    continue
                texture = QtGui.QImage.fromData(base64.b64decode(href.split(",", 1)[1]))
                if not texture.isNull():
                    color = texture.pixelColor(texture.width() // 2, texture.height() // 2)
                    if color.red() > 240 and color.green() < 15 and color.blue() < 15:
                        red_textures += 1
            self.assertGreater(red_textures, 0, "Requested hatch texture missing from SVG")
            self.assertFalse([
                message for message in messages if "Incorrect use of TexturePattern" in message
            ])


if __name__ == "__main__":
    unittest.main()
