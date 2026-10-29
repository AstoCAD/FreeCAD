# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cached cosmetic-edge wrappers remain safe when their view clears its edges.

Exercise only normal TechDraw creation, read, clear and reuse operations with an
explicitly selected disposable profile. Console mode is supported.
"""

import os
from pathlib import Path
import time
import unittest
import uuid

import FreeCAD as App


def owned_profile():
    selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
    if not selected:
        raise unittest.SkipTest("Requires an explicitly selected disposable test profile")
    import stat

    def plain_path(path):
        for component in (path, *path.parents):
            try:
                if component.is_symlink():
                    return False
                is_junction = getattr(component, "is_junction", None)
                if is_junction is not None and is_junction():
                    return False
                attributes = getattr(component.lstat(), "st_file_attributes", 0)
                if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    return False
            except FileNotFoundError:
                continue
            except OSError:
                return False
        return True

    raw = Path(selected)
    if not raw.is_absolute() or not plain_path(raw):
        raise unittest.SkipTest("Disposable profile must be an absolute directory without links")
    try:
        profile = raw.resolve(strict=True)
    except OSError:
        raise unittest.SkipTest("Disposable test profile must already exist")
    if not profile.is_dir():
        raise unittest.SkipTest("Disposable test profile must be a directory")
    configured_home = os.environ.get("FREECAD_USER_HOME")
    if not configured_home:
        raise unittest.SkipTest("FREECAD_USER_HOME must select the disposable profile")
    home = Path(configured_home)
    if not home.is_absolute() or not plain_path(home):
        raise unittest.SkipTest("FREECAD_USER_HOME must be absolute and free of links")
    try:
        matching_home = home.resolve(strict=True) == profile
    except OSError:
        matching_home = False
    if not matching_home:
        raise unittest.SkipTest("FREECAD_USER_HOME does not match the selected profile")
    parameter_file = Path(App.ConfigGet("UserParameter"))
    data_directory = Path(App.getUserAppDataDir())
    paths = (parameter_file, data_directory)
    if not all(path.is_absolute() and plain_path(path) for path in paths):
        raise unittest.SkipTest("Active profile paths must be absolute and free of links")
    if parameter_file.resolve() != profile / "user.cfg":
        raise unittest.SkipTest("Active user configuration is outside the selected profile")
    if not all(path.resolve().is_relative_to(profile) for path in paths):
        raise unittest.SkipTest("Active configuration and data must stay in the test profile")
    return profile


def point(value):
    return (float(value.x), float(value.y), float(value.z))


def shape_data(shape):
    box = shape.BoundBox
    return {
        "null": bool(shape.isNull()),
        "valid": bool(shape.isValid()),
        "volume": float(shape.Volume),
        "bounds": (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "vertices": len(shape.Vertexes),
    }


class TestCosmeticEdgeLifetime(unittest.TestCase):
    def setUp(self):
        self.profile = owned_profile()
        self.assertFalse(App.listDocuments(), "Requires a disposable process without documents")
        self.document_name = None
        self.document_uid = None
        self.addCleanup(self._close_owned_document)
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        from TDTest import TechDrawTestUtilities

        self.doc = App.newDocument("CosmeticEdgeLifetime" + uuid.uuid4().hex[:8])
        self.document_name, self.document_uid = self.doc.Name, str(self.doc.Uid)
        # This fixture does not exercise Undo of the existing shallow cosmetic lists.
        self.doc.UndoMode = 0
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 10, 12, 4
        self.page = TechDrawTestUtilities.createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.Rotation = 0
        self._recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)
        self.assertFalse(self.source.Shape.isNull())
        self.assertTrue(self.source.Shape.isValid())
        self.assertAlmostEqual(self.source.Shape.Volume, 480)
        self.original = self._model_snapshot()

    def _close_owned_document(self):
        if self.document_name and self.document_name in App.listDocuments():
            doc = App.getDocument(self.document_name)
            self.assertEqual(str(doc.Uid), self.document_uid, "Owned document identity changed")
            if doc.HasPendingTransaction:
                doc.abortTransaction()
            App.closeDocument(self.document_name)

    def _recompute(self):
        self.doc.recompute()
        deadline = time.monotonic() + 10
        while not self.view.getVisibleEdges() or "Up-to-date" not in self.view.State:
            self.assertLess(time.monotonic(), deadline, "Ordinary box-view projection did not finish")
            if not App.GuiUp:
                self.fail("Console-mode projection did not finish synchronously")
            import FreeCADGui as Gui
            from PySide import QtCore

            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            loop.exec_()
            Gui.updateGui()

    def _model_snapshot(self):
        return {
            "document_name": self.doc.Name,
            "document_uid": str(self.doc.Uid),
            "document_label": self.doc.Label,
            "objects": [(obj.Name, obj.TypeId, obj.Label) for obj in self.doc.Objects],
            "source_dimensions": (self.source.Length.Value, self.source.Width.Value,
                                  self.source.Height.Value),
            "source_placement": tuple(self.source.Placement.toMatrix().A),
            "source_shape": shape_data(self.source.Shape),
            "page_views": [obj.Name for obj in self.page.Views],
            "template": self.page.Template.Name,
            "view_source": [obj.Name for obj in self.view.Source],
            "view_direction": point(self.view.Direction),
            "view_xdirection": point(self.view.XDirection),
            "view_scale": self.view.Scale,
            "view_rotation": float(self.view.Rotation),
            "pending": bool(self.doc.HasPendingTransaction),
            "booked": self.doc.getBookedTransactionID(),
            "undo": list(self.doc.UndoNames),
            "redo": list(self.doc.RedoNames),
        }

    def _assert_unrelated_state(self):
        self.assertEqual(self._model_snapshot(), self.original)

    def _make_line(self):
        tag = self.view.makeCosmeticLine(App.Vector(-5, 10, 0), App.Vector(5, 10, 0))
        self.assertIsInstance(tag, str)
        self.assertTrue(tag)
        self._recompute()
        return tag

    def _assert_live_line(self, edge, tag):
        self.assertEqual(edge.Tag, tag)
        self.assertEqual(point(edge.Start), (-5.0, 10.0, 0.0))
        self.assertEqual(point(edge.End), (5.0, 10.0, 0.0))

    def test_control_clear_without_reading_edge_wrappers(self):
        self._make_line()
        # No getCosmeticEdge/CosmeticEdges access has created a Python twin.
        self.view.clearCosmeticEdges()
        self._recompute()
        self.assertEqual(self.view.CosmeticEdges, [])
        self._assert_unrelated_state()

    def test_control_live_getter_and_list_share_usable_edge(self):
        tag = self._make_line()
        edges = self.view.CosmeticEdges
        self.assertEqual(len(edges), 1)
        edge = self.view.getCosmeticEdge(tag)
        self.assertIs(edge, edges[0])
        self._assert_live_line(edge, tag)
        self._recompute()
        self._assert_live_line(edges[0], tag)
        self._assert_unrelated_state()

    def test_discarded_arc_wrapper_list_can_be_cleared(self):
        tag = self.view.makeCosmeticCircleArc(App.Vector(0, 15, 0), 2, 0, 180)
        self.assertIsInstance(tag, str)
        self.assertTrue(tag)
        self._recompute()
        self.assertEqual(len(self.view.CosmeticEdges), 1)
        print("Cosmetic edge list read and discarded; clearing its ordinary arc", flush=True)
        self.view.clearCosmeticEdges()
        self._recompute()
        self.assertEqual(self.view.CosmeticEdges, [])
        self._assert_unrelated_state()

    def test_retained_edge_is_invalidated_when_its_view_clears(self):
        tag = self._make_line()
        retained = self.view.CosmeticEdges
        self.assertEqual(len(retained), 1)
        edge = self.view.getCosmeticEdge(tag)
        self.assertIs(edge, retained[0])
        self._assert_live_line(edge, tag)
        print("Live cosmetic edge retained; clearing its view-owned list", flush=True)
        self.view.clearCosmeticEdges()
        self._recompute()
        self.assertEqual(self.view.CosmeticEdges, [])
        self._assert_unrelated_state()
        with self.assertRaises(ReferenceError):
            _ = edge.Tag
        with self.assertRaises(ReferenceError):
            _ = retained[0].Start
        fresh_tag = self._make_line()
        self.assertNotEqual(fresh_tag, tag)
        fresh = self.view.getCosmeticEdge(fresh_tag)
        self._assert_live_line(fresh, fresh_tag)
        with self.assertRaises(ReferenceError):
            _ = edge.Tag
        self._assert_unrelated_state()
