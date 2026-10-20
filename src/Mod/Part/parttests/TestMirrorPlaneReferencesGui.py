# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Part Mirror task references preserve admitted hierarchy placements.

Related reduced boundary for https://github.com/FreeCAD/FreeCAD/issues/32706.
The reporter's complete Body-as-source Assembly workflow is outside this matrix.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
try:
    import PartDesign
    import PartDesignGui
except ModuleNotFoundError as missing:
    if missing.name not in ("PartDesign", "PartDesignGui"):
        raise
    _has_part_design = False
else:
    _has_part_design = True
from PySide import QtCore, QtWidgets

class MirrorPlaneGuiFixture(unittest.TestCase):

    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench('PartWorkbench')
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        self.doc = App.newDocument('MirrorPlaneOccurrenceAudit')
        self._retained_task_wrappers = []
        self.modal_messages = []
        self.modal_closer = QtCore.QTimer(Gui.getMainWindow())

        def closeUnexpectedModal():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                self.modal_messages.append(modal.text())
                modal.reject()
        self.modal_closer.timeout.connect(closeUnexpectedModal)
        self.modal_closer.start(30)

    def tearDown(self):
        try:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)
            if self.previous_document in App.listDocuments():
                App.setActiveDocument(self.previous_document)
            self._retained_task_wrappers.clear()
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def _retain_task_ancestors(self, obj):
        while obj is not None:
            self._retained_task_wrappers.append(obj)
            obj = obj.parent()

    def _check(self, variant, gui):
        source, root, subname, base, normal, expected_center = self._fixture(variant)
        if gui:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(source)
            Gui.runCommand('Part_Mirror')
            dialog = Gui.Control.activeTaskDialog()
            self.assertIsNotNone(dialog)
            self._retained_task_wrappers.append(dialog)
            content = dialog.getDialogContent()
            for widget in content:
                self._retain_task_ancestors(widget)
            shapes = next((widget.findChild(QtWidgets.QTreeWidget, 'shapes') for widget in content if widget.findChild(QtWidgets.QTreeWidget, 'shapes') is not None), None)
            self.assertIsNotNone(shapes)
            self._retain_task_ancestors(shapes)
            shapes_parent = shapes.parentWidget()
            self._retained_task_wrappers.append(shapes_parent)
            combo = shapes_parent.findChild(QtWidgets.QComboBox, 'comboBox')
            self._retained_task_wrappers.append(combo)
            Gui.updateGui()
            self.assertEqual(len(shapes.selectedItems()), 1)
            self.assertEqual(shapes.selectedItems()[0].data(0, QtCore.Qt.UserRole), source.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self.doc.Name, root.Name, subname)
            Gui.updateGui()
            selection = Gui.Selection.getSelectionEx()
            raw_selection = Gui.Selection.getSelectionEx('', 0)
            self.assertEqual(len(selection), 1)
            self.assertIsNotNone(combo)
            self.assertEqual(combo.currentIndex(), 3)
            dialog.accept()
            Gui.updateGui()
            mirrors = [obj for obj in self.doc.Objects if obj.TypeId == 'Part::Mirroring']
            self.assertEqual(len(mirrors), 1)
            mirror = mirrors[0]
        else:
            mirror = self.doc.addObject('Part::Mirroring', 'ExplicitFullPathMirror')
            mirror.Source = source
            mirror.MirrorPlane = (root, [subname])
            self.doc.recompute()
        self.assertNotIn('Invalid', mirror.State)
        self.assertFalse(mirror.Shape.isNull())
        self.assertAlmostEqual(mirror.Shape.Volume, source.Shape.Volume, places=6)
        with self.subTest(check='plane normal'):
            self.assertAlmostEqual(abs(mirror.Normal.dot(normal)), 1, places=8)
        with self.subTest(check='plane offset'):
            self.assertAlmostEqual((mirror.Base - base).dot(normal), 0, places=8)
        with self.subTest(check='world mirrored center'):
            self.assertLess((mirror.Shape.CenterOfMass - expected_center).Length, 1e-07)

@unittest.skipUnless(_has_part_design, "PartDesign is not available")
class TestMirrorBodyPlaneBoundary(MirrorPlaneGuiFixture):

    def _body_fixture(self, variant):
        local_shape = Part.makeBox(10, 12, 15)
        body = self.doc.addObject('PartDesign::Body', 'ReferenceBody')
        leaf = body.newObject('PartDesign::Feature', 'ReferenceFeature')
        leaf.Shape = local_shape
        self.doc.recompute()
        face_name = 'Face' + str(max(range(1, len(local_shape.Faces) + 1), key=lambda index: local_shape.Faces[index - 1].CenterOfMass.z))
        placement = App.Placement()
        root = body
        subname = leaf.Name + '.' + face_name
        if variant == 'body':
            body.Placement = App.Placement(App.Vector(4, -3, 2), App.Rotation(App.Vector(1, 2, 0), 31))
            placement = App.Placement(body.Placement)
        located = local_shape.copy()
        located.Placement = placement
        source = self.doc.addObject('Part::Feature', 'IndependentWorldSource')
        source.Shape = located
        self.doc.recompute()
        base = placement.multVec(App.Vector(5, 6, 15))
        normal = placement.Rotation.multVec(App.Vector(0, 0, 1))
        center = placement.multVec(App.Vector(5, 6, 7.5))
        expected_center = center - normal * (2 * (center - base).dot(normal))
        return (source, root, subname, base, normal, expected_center)

    def _fixture(self, variant):
        self.assertIn(variant, ('identity', 'body'))
        values = self._body_fixture(variant)
        source, root, subname, base, normal, expected_center = values
        self.assertEqual(root.TypeId, 'PartDesign::Body')
        self.assertTrue(root.Shape.isValid())
        self.assertAlmostEqual(root.Shape.Volume, 1800)
        self.assertTrue(source.Shape.isValid())
        self.assertAlmostEqual(source.Shape.Volume, 1800)
        world_center = root.Placement.multVec(App.Vector(5, 6, 7.5))
        self.assertLess((source.Shape.CenterOfMass - world_center).Length, 1e-08, 'The independent source must already occupy the analytic world placement')
        self.assertAlmostEqual(normal.Length, 1)
        self.assertAlmostEqual((source.Shape.CenterOfMass - base).dot(normal), -7.5, places=8)
        return values

    def test_backend_identity_body_control(self):
        self._check('identity', gui=False)

    def test_backend_transformed_body_full_path(self):
        self._check('body', gui=False)

    def test_gui_identity_body_control(self):
        self._check('identity', gui=True)

    def test_gui_transformed_body(self):
        self._check('body', gui=True)

class TestMirrorAdmittedPlanePaths(MirrorPlaneGuiFixture):

    def _fixture(self, variant):
        self.assertIn(variant, ('feature', 'link', 'nested_link', 'legacy_part'))
        local_shape = Part.makeBox(10, 12, 15)
        face_name = 'Face' + str(max(range(1, len(local_shape.Faces) + 1), key=lambda index: local_shape.Faces[index - 1].CenterOfMass.z))
        reference_placement = App.Placement(App.Vector(4, -3, 2), App.Rotation(App.Vector(1, 2, 0), 31))
        leaf = self.doc.addObject('Part::Feature', 'ReferenceFeature')
        leaf.Shape = local_shape
        root = leaf
        subname = face_name
        placement = reference_placement
        if variant == 'feature':
            leaf.Placement = reference_placement
        elif variant == 'link':
            root = self.doc.addObject('App::Link', 'ReferenceOccurrence')
            root.setLink(leaf)
            root.LinkTransform = False
            root.Placement = reference_placement
        elif variant == 'nested_link':
            body = self.doc.addObject('PartDesign::Body', 'ReferenceBody')
            body_leaf = body.newObject('PartDesign::Feature', 'NestedFeature')
            body_leaf.Shape = local_shape
            self.doc.removeObject(leaf.Name)
            body.Placement = reference_placement
            container = self.doc.addObject('App::Part', 'ReferenceContainer')
            container.addObject(body)
            self.assertTrue(container.Placement.isIdentity())
            root = self.doc.addObject('App::Link', 'NestedOccurrence')
            root.setLink(container)
            root.LinkTransform = False
            root.Placement = App.Placement(App.Vector(11, 7, -5), App.Rotation(App.Vector(0, 1, 2), 19))
            placement = root.Placement * body.Placement
            subname = body.Name + '.' + body_leaf.Name + '.' + face_name
        else:
            leaf.Placement = reference_placement
            root = self.doc.addObject('App::Part', 'IdentityContainer')
            root.addObject(leaf)
            self.assertTrue(root.Placement.isIdentity())
            subname = leaf.Name + '.' + face_name
        located = local_shape.copy()
        located.Placement = placement
        source = self.doc.addObject('Part::Feature', 'IndependentWorldSource')
        source.Shape = located
        self.doc.recompute()
        self.assertTrue(source.Shape.isValid())
        self.assertAlmostEqual(source.Shape.Volume, 1800)
        center = placement.multVec(App.Vector(5, 6, 7.5))
        self.assertLess((source.Shape.CenterOfMass - center).Length, 1e-08)
        if variant != 'legacy_part':
            self.assertIn(root.TypeId, ('Part::Feature', 'App::Link'))
            self.assertTrue(root.Shape.isValid())
            self.assertAlmostEqual(root.Shape.Volume, 1800)
            solids = root.Shape.Solids
            self.assertEqual(len(solids), 1, 'The reference occurrence must contain exactly one solid')
            self.assertLess((solids[0].CenterOfMass - center).Length, 1e-08)
        else:
            self.assertEqual(root.TypeId, 'App::Part')
            self.assertLess((leaf.Shape.CenterOfMass - center).Length, 1e-08)
        base = placement.multVec(App.Vector(5, 6, 15))
        normal = placement.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(normal.Length, 1)
        self.assertAlmostEqual((center - base).dot(normal), -7.5, places=8)
        expected_center = center - normal * (2 * (center - base).dot(normal))
        return (source, root, subname, base, normal, expected_center)

    def test_backend_direct_placed_feature_control(self):
        self._check('feature', gui=False)

    def test_gui_direct_placed_feature_control(self):
        self._check('feature', gui=True)

    def test_backend_placed_link_full_path(self):
        self._check('link', gui=False)

    def test_gui_placed_link(self):
        self._check('link', gui=True)

    @unittest.skipUnless(_has_part_design, "PartDesign is not available")
    def test_backend_link_to_nested_part_body_full_path(self):
        self._check('nested_link', gui=False)

    @unittest.skipUnless(_has_part_design, "PartDesign is not available")
    def test_gui_link_to_nested_part_body(self):
        self._check('nested_link', gui=True)

    def test_gui_identity_part_parent_legacy_resolution_control(self):
        self._check('legacy_part', gui=True)

class TestMirrorLabelPathSerialization(MirrorPlaneGuiFixture):

    def _fixture(self, variant):
        self.assertIn(variant, ('identifier', 'special_label'))
        local_shape = Part.makeBox(10, 12, 15)
        face_name = 'Face' + str(max(range(1, len(local_shape.Faces) + 1), key=lambda index: local_shape.Faces[index - 1].CenterOfMass.z))
        placement = App.Placement(App.Vector(4, -3, 2), App.Rotation(App.Vector(1, 2, 0), 31))
        leaf = self.doc.addObject('Part::Feature', 'ReferenceFeature')
        leaf.Shape = local_shape
        leaf.Placement = placement
        root = self.doc.addObject('Part::Compound', 'ReferenceCompound')
        root.Links = [leaf]
        self.assertTrue(root.Placement.isIdentity())
        if variant == 'special_label':
            leaf.Label = "Child's \\ branch"
            subname = '$' + leaf.Label + '.' + face_name
        else:
            subname = leaf.Name + '.' + face_name
        located = local_shape.copy()
        located.Placement = placement
        source = self.doc.addObject('Part::Feature', 'IndependentWorldSource')
        source.Shape = located
        self.doc.recompute()
        self.assertEqual(root.getSubObject(subname, 1), leaf, 'The native root must resolve the exact selected face path')
        self.assertTrue(root.Shape.isValid())
        self.assertAlmostEqual(root.Shape.Volume, 1800)
        solids = root.Shape.Solids
        self.assertEqual(len(solids), 1)
        center = placement.multVec(App.Vector(5, 6, 7.5))
        self.assertLess((solids[0].CenterOfMass - center).Length, 1e-08)
        self.assertTrue(source.Shape.isValid())
        self.assertAlmostEqual(source.Shape.Volume, 1800)
        self.assertLess((source.Shape.CenterOfMass - center).Length, 1e-08)
        base = placement.multVec(App.Vector(5, 6, 15))
        normal = placement.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(normal.Length, 1)
        self.assertAlmostEqual((center - base).dot(normal), -7.5, places=8)
        expected_center = center - normal * (2 * (center - base).dot(normal))
        return (source, root, subname, base, normal, expected_center)

    def _check(self, variant, gui):
        source, root, subname, base, normal, expected_center = self._fixture(variant)
        if gui:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(source)
            Gui.runCommand('Part_Mirror')
            dialog = Gui.Control.activeTaskDialog()
            self.assertIsNotNone(dialog)
            self._retained_task_wrappers.append(dialog)
            content = dialog.getDialogContent()
            for widget in content:
                self._retain_task_ancestors(widget)
            shapes = next((widget.findChild(QtWidgets.QTreeWidget, 'shapes') for widget in content if widget.findChild(QtWidgets.QTreeWidget, 'shapes') is not None), None)
            self.assertIsNotNone(shapes)
            self._retain_task_ancestors(shapes)
            shapes_parent = shapes.parentWidget()
            self._retained_task_wrappers.append(shapes_parent)
            combo = shapes_parent.findChild(QtWidgets.QComboBox, 'comboBox')
            self._retained_task_wrappers.append(combo)
            Gui.updateGui()
            self.assertEqual(len(shapes.selectedItems()), 1)
            self.assertEqual(shapes.selectedItems()[0].data(0, QtCore.Qt.UserRole), source.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self.doc.Name, root.Name, subname)
            Gui.updateGui()
            selection = Gui.Selection.getSelectionEx()
            raw_selection = Gui.Selection.getSelectionEx('', 0)
            self.assertEqual(len(raw_selection), 1)
            self.assertEqual(raw_selection[0].ObjectName, root.Name)
            self.assertEqual(len(raw_selection[0].SubElementNames), 1)
            self.assertTrue(raw_selection[0].SubElementNames[0].startswith(subname.rsplit('.', 1)[0] + '.'))
            self.assertEqual(len(selection), 1)
            self.assertIsNotNone(combo)
            self.assertEqual(combo.currentIndex(), 3)
            dialog.accept()
            Gui.updateGui()
            mirrors = [obj for obj in self.doc.Objects if obj.TypeId == 'Part::Mirroring']
            self.assertEqual(len(mirrors), 1)
            mirror = mirrors[0]
        else:
            mirror = self.doc.addObject('Part::Mirroring', 'ExplicitFullPathMirror')
            mirror.Source = source
            mirror.MirrorPlane = (root, [subname])
            self.doc.recompute()
        self.assertNotIn('Invalid', mirror.State)
        self.assertFalse(mirror.Shape.isNull())
        self.assertAlmostEqual(mirror.Shape.Volume, source.Shape.Volume, places=6)
        with self.subTest(check='plane normal'):
            self.assertAlmostEqual(abs(mirror.Normal.dot(normal)), 1, places=8)
        with self.subTest(check='plane offset'):
            self.assertAlmostEqual((mirror.Base - base).dot(normal), 0, places=8)
        with self.subTest(check='world mirrored center'):
            self.assertLess((mirror.Shape.CenterOfMass - expected_center).Length, 1e-07)

    def test_backend_identifier_path_control(self):
        self._check('identifier', gui=False)

    def test_gui_identifier_path_control(self):
        self._check('identifier', gui=True)

    def test_backend_special_label_path_control(self):
        self._check('special_label', gui=False)

    def test_gui_special_label_path_control(self):
        self._check('special_label', gui=True)
