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

    def test_delete_last_updates_the_motion(self):
        """deleteLast() changes the trajectory in place: its duration and path must follow."""
        trac = Robot.Trajectory([_waypoint(x) for x in (0, 100, 200, 300)])
        trac.deleteLast(1)
        remaining = trac.Waypoints
        self.assertGreaterEqual(len(remaining), 2)
        self.assertLess(len(remaining), 4)
        shorter = Robot.Trajectory(remaining)
        self.assertAlmostEqual(trac.Length, shorter.Length)
        self.assertAlmostEqual(trac.Duration, shorter.Duration)
        self.assertTrue(trac.position(trac.Duration).Base.isEqual(remaining[-1].Pos.Base, 1e-7))
        trac.deleteLast(5)
        self.assertEqual(len(trac.Waypoints), 0)
        self.assertEqual(trac.Length, 0.0)
        self.assertEqual(trac.Duration, 0.0)


class TestRobotAttributeErrors(unittest.TestCase):
    """Errors raised by attribute setters used to surface as 'Unknown exception'."""

    def test_unreachable_tcp_raises_runtime_error(self):
        nan = float("nan")
        for placement in (
            App.Placement(App.Vector(nan, 0, 0), App.Rotation()),
            App.Placement(App.Vector(1e9, 0, 0), App.Rotation()),
        ):
            with self.subTest(placement=placement):
                robot = Robot.Robot6Axis()
                tcp = robot.Tcp
                with self.assertRaisesRegex(RuntimeError, "Can not reach Point"):
                    robot.Tcp = placement
                self.assertTrue(robot.Tcp.isSame(tcp, 1e-9))

    def test_reachable_tcp_unchanged(self):
        robot = Robot.Robot6Axis()
        target = robot.Tcp
        target.Base = target.Base + App.Vector(-100, 0, 0)
        robot.Tcp = target
        self.assertTrue(robot.Tcp.isSame(target, 1e-3))

    def test_unknown_waypoint_type_raises_type_error(self):
        waypoint = _waypoint(0)
        with self.assertRaisesRegex(TypeError, "Unknown waypoint type"):
            waypoint.Type = "Bogus"
        waypoint.Type = "PTP"
        self.assertEqual(waypoint.Type, "PTP")
