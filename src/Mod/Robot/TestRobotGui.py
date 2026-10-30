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

    def _assertDrawnAt(self, obj, expected, tolerance=1e-6):
        translation = _root_translation(obj.ViewObject)
        self.assertIsNotNone(translation)
        self.assertTrue(
            translation.isEqual(expected, tolerance),
            "drawn at {} instead of {}".format(translation, expected),
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

    def _assertToolAtTcp(self, robot, tool):
        expected = robot.Placement.multiply(robot.Tcp).multiply(robot.ToolBase.inverse()).Base
        # Coin stores the transformation in single precision
        self._assertDrawnAt(tool, expected, 1e-2)

    def testToolFollowsRobotPlacement(self):
        """The tool must be drawn at the Tcp of a placed robot (issue #5562)."""
        robot = self.doc.addObject("Robot::RobotObject", "Robot")
        robot.Placement = FreeCAD.Placement(FreeCAD.Vector(1000, 200, 0), FreeCAD.Rotation())
        robot.Axis2 = -60  # moves the Tcp away from the robot origin
        tool = self.doc.addObject("Part::Box", "Tool")
        self.doc.recompute()

        # tool attached to an already placed robot
        robot.ToolShape = tool
        self.doc.recompute()
        self.assertFalse(robot.Tcp.Base.isEqual(FreeCAD.Vector(), 1e-6))
        self._assertToolAtTcp(robot, tool)

        # robot moved after the tool was attached
        robot.Placement = FreeCAD.Placement(
            FreeCAD.Vector(-500, 300, 50), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90)
        )
        self.doc.recompute()
        self._assertToolAtTcp(robot, tool)
