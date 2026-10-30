# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI tests for the Robot workbench."""

import os
import tempfile
import unittest

import FreeCAD
import FreeCADGui
from pivy import coin

import Robot  # noqa: F401  registers Robot::RobotObject
import RobotGui  # noqa: F401  registers its view provider


def _root_translation(view_object):
    """Return the translation of the view provider's root transform node."""
    search = coin.SoSearchAction()
    search.setType(coin.SoTransform.getClassTypeId())
    search.setInterest(coin.SoSearchAction.FIRST)
    search.setSearchingAll(True)
    search.apply(view_object.RootNode)
    path = search.getPath()
    if path is None:
        return None
    node = coin.cast(path.getTail(), "SoTransform")
    return FreeCAD.Vector(node.translation.getValue().getValue())


class TestRobotPlacement(unittest.TestCase):
    """The robot must be drawn at its Placement (issue #15014)."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestRobotPlacement")
        self.files = []

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            if name.startswith("TestRobotPlacement"):
                FreeCAD.closeDocument(name)
        for path in self.files:
            if os.path.exists(path):
                os.remove(path)

    def _assertDrawnAt(self, robot, expected):
        translation = _root_translation(robot.ViewObject)
        self.assertIsNotNone(translation)
        self.assertTrue(
            translation.isEqual(expected, 1e-6),
            "robot drawn at {} instead of {}".format(translation, expected),
        )

    def testPlacementChangeMovesRobot(self):
        robot = self.doc.addObject("Robot::RobotObject", "Robot")
        self.doc.recompute()
        robot.Placement = FreeCAD.Placement(FreeCAD.Vector(1000, 200, 0), FreeCAD.Rotation())
        self.doc.recompute()
        self._assertDrawnAt(robot, FreeCAD.Vector(1000, 200, 0))

    def testPlacementKeptAfterReload(self):
        first = self.doc.addObject("Robot::RobotObject", "Robot")
        second = self.doc.addObject("Robot::RobotObject", "Robot001")
        second.Placement = FreeCAD.Placement(FreeCAD.Vector(1500, -300, 0), FreeCAD.Rotation())
        self.doc.recompute()

        fd, path = tempfile.mkstemp(suffix=".FCStd", prefix="TestRobotPlacement")
        os.close(fd)
        self.files.append(path)
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)

        self.doc = FreeCAD.openDocument(path)
        self._assertDrawnAt(self.doc.getObject("Robot"), FreeCAD.Vector(0, 0, 0))
        self._assertDrawnAt(self.doc.getObject("Robot001"), FreeCAD.Vector(1500, -300, 0))
