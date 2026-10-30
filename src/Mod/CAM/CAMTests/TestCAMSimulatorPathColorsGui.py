# SPDX-License-Identifier: LGPL-2.1-or-later

"""The new CAM simulator draws the tool path with the CAM path preferences.

Rapid moves use DefaultRapidPathColor, feed moves DefaultNormalPathColor and
the line width follows DefaultPathLineWidth (#22186).
"""

import unittest

import FreeCAD
import FreeCADGui
import Part
import Path
from PySide import QtCore, QtGui, QtWidgets

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/CAM"

BLUE = 0x0000FFFF  # 0xRRGGBBAA
GREEN = 0x00FF00FF


def _events(count=10):
    for _ in range(count):
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)


class TestCAMSimulatorPathColors(unittest.TestCase):
    def setUp(self):
        import CAMSimulator

        self.param = FreeCAD.ParamGet(PARAM_PATH)
        self.saved = {}
        for name in ("DefaultNormalPathColor", "DefaultRapidPathColor"):
            if name in self.param.GetUnsigneds():
                self.saved[name] = ("unsigned", self.param.GetUnsigned(name))
        if "DefaultPathLineWidth" in self.param.GetInts():
            self.saved["DefaultPathLineWidth"] = ("int", self.param.GetInt("DefaultPathLineWidth"))
        self.addCleanup(self._restorePreferences)

        self.param.SetUnsigned("DefaultNormalPathColor", GREEN)
        self.param.SetUnsigned("DefaultRapidPathColor", BLUE)
        self.param.SetInt("DefaultPathLineWidth", 1)

        self.doc = FreeCAD.newDocument("TestCAMSimulatorPathColors")
        self.addCleanup(self._closeDocument)

        self.sim = CAMSimulator.PathSim()
        self.sim.ResetSimulation(FreeCADGui.getDocument(self.doc.Name))
        # flat end mill, radius 1 and length 10, as a (radius, z) profile
        self.sim.AddTool([1.0, 10.0, 1.0, 0.0, 0.0, 0.0], 1, 2.0, 1)
        commands = [
            Path.Command("M6", {"T": 1}),
            Path.Command("G0", {"X": 5, "Y": 5, "Z": 8}),
            Path.Command("G0", {"X": 35, "Y": 5, "Z": 8}),
            Path.Command("G1", {"X": 35, "Y": 35, "Z": 8}),
            Path.Command("G1", {"X": 5, "Y": 35, "Z": 8}),
        ]
        for cmd in commands:
            self.sim.AddCommand(cmd)
        self.sim.BeginSimulation(Part.makeBox(40, 40, 5), 5)
        _events(20)

        self.view = self._simulatorWidget()
        path_buttons = [
            b
            for b in self.view.window().findChildren(QtWidgets.QToolButton, "pathButton")
            if b.isVisible()
        ]
        self.assertTrue(path_buttons, "the simulator path button was not found")
        self.path_button = path_buttons[0]
        self.path_button.setChecked(True)
        _events()

    def _restorePreferences(self):
        for name in ("DefaultNormalPathColor", "DefaultRapidPathColor"):
            if name in self.saved:
                self.param.SetUnsigned(name, self.saved[name][1])
            else:
                self.param.RemUnsigned(name)
        if "DefaultPathLineWidth" in self.saved:
            self.param.SetInt("DefaultPathLineWidth", self.saved["DefaultPathLineWidth"][1])
        else:
            self.param.RemInt("DefaultPathLineWidth")

    def _closeDocument(self):
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)
        _events()

    def _simulatorWidget(self):
        for _ in range(100):
            for widget in QtWidgets.QApplication.allWidgets():
                if (
                    widget.metaObject().className() == "CAMSimulator::DlgCAMSimulator"
                    and widget.isVisible()
                ):
                    return widget
            _events(1)
        self.fail("the CAM simulator view was not opened")

    def _countPixels(self):
        """Return the number of (blue, green) path pixels in the simulator view."""
        _events()
        image = self.view.grab().toImage()
        if image.isNull():
            self.skipTest("the CAM simulator view could not be grabbed")
        image = image.convertToFormat(QtGui.QImage.Format_RGB32)
        # Format_RGB32 is stored as B, G, R, A bytes on little endian machines
        data = bytes(image.constBits())[: image.width() * image.height() * 4]
        blue = green = 0
        for i in range(0, len(data), 4):
            b, g, r = data[i], data[i + 1], data[i + 2]
            # the simulator does not output the exact preference color (pure green
            # comes out as about 0,200,0), so look for the dominant channel
            if b > 120 and r < 60 and g < 60:
                blue += 1
            elif g > 120 and r < 60 and b < 60:
                green += 1
        return blue, green

    def testRapidAndFeedColors(self):
        blue, green = self._countPixels()
        self.assertGreater(green, 0, "feed moves are not drawn in the normal path color")
        self.assertGreater(blue, 0, "rapid moves are not drawn in the rapid path color")

    def testLineWidth(self):
        _, thin = self._countPixels()
        self.param.SetInt("DefaultPathLineWidth", 3)
        _, thick = self._countPixels()
        self.assertGreater(thin, 0)
        self.assertGreater(thick, 1.5 * thin, "the path line width preference is ignored")


if __name__ == "__main__":
    unittest.main()
