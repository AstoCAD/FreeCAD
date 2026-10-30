# SPDX-License-Identifier: LGPL-2.1-or-later

"""App-level regression tests for the Robot Python API."""

import unittest

import FreeCAD as App
import Robot


def _waypoint(x, **kw):
    return Robot.Waypoint(App.Placement(App.Vector(x, 0, 0), App.Rotation()), **kw)


class TestRobotTrajectory(unittest.TestCase):
    def test_single_waypoint_position_and_velocity(self):
        """A trajectory without any motion segment must not crash position()/velocity()."""
        trac = Robot.Trajectory([_waypoint(10)])
        for time in (-1.0, 0.0, 5.0):
            self.assertEqual(trac.position(time).Base, App.Vector(10, 0, 0))
            self.assertEqual(trac.velocity(time), 0.0)

    def test_two_waypoints_position(self):
        trac = Robot.Trajectory([_waypoint(0), _waypoint(100)])
        self.assertGreater(trac.Duration, 0.0)
        self.assertEqual(trac.position(0.0).Base, App.Vector(0, 0, 0))
        self.assertTrue(trac.position(trac.Duration).Base.isEqual(App.Vector(100, 0, 0), 1e-7))

    def test_delete_last_out_of_range(self):
        """deleteLast() must not crash when it removes more waypoints than there are."""
        self.assertEqual(len(Robot.Trajectory().deleteLast().Waypoints), 0)
        self.assertEqual(len(Robot.Trajectory([_waypoint(0)]).deleteLast().Waypoints), 0)
        self.assertEqual(len(Robot.Trajectory([_waypoint(0), _waypoint(1)]).deleteLast(5).Waypoints), 0)
        with self.assertRaises(ValueError):
            Robot.Trajectory([_waypoint(0), _waypoint(1)]).deleteLast(-1)

    def test_infeasible_trajectory_constructor_raises(self):
        """A KDL failure in Trajectory() must become a Python exception, not escape as C++."""
        waypoints = [_waypoint(0, cont=True) for _ in range(3)]
        with self.assertRaises(RuntimeError):
            Robot.Trajectory(waypoints)
        # the same failure through a regular method was already converted
        trac = Robot.Trajectory(waypoints[:2])
        with self.assertRaises(RuntimeError):
            trac.insertWaypoints(waypoints[2])

    def test_edge2trac_non_positive_segvalue(self):
        """Edge2TracObject looped forever on a circle edge with SegValue <= 0."""
        import Part

        doc = App.newDocument("TestRobotEdge2Trac")
        try:
            circle = doc.addObject("Part::Feature", "Circle")
            circle.Shape = Part.makeCircle(10)
            trac = doc.addObject("Robot::Edge2TracObject", "Edge2Trac")
            trac.Source = (circle, ["Edge1"])
            doc.recompute()
            self.assertTrue(trac.isValid())
            self.assertGreater(len(trac.Trajectory.Waypoints), 2)
            for value in (0.0, -1.0):
                trac.SegValue = value
                doc.recompute()
                self.assertFalse(trac.isValid())
            trac.SegValue = 1.0
            doc.recompute()
            self.assertTrue(trac.isValid())
        finally:
            App.closeDocument(doc.Name)

    def test_delete_last_unchanged(self):
        trac = Robot.Trajectory([_waypoint(i) for i in range(5)])
        self.assertEqual(len(trac.deleteLast(0).Waypoints), 4)
