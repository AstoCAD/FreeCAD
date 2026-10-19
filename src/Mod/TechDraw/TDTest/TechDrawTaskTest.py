#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import FreeCAD
import FreeCADGui
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate


class TechDrawTaskTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testDrawProjGroup(self):
        obj = self.doc.addObject("TechDraw::DrawProjGroup")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawProjGroupInvalidAnchor(self):
        """Invalid anchor links must be rejected before constructing the task panel."""
        group = self.doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        page = createPageWithSVGTemplate(self.doc)
        page.addView(group)
        template = page.Template
        part = self.doc.addObject("App::Part", "Part")
        for anchor in (page, template, part, None):
            with self.subTest(anchor=anchor):
                group.Anchor = anchor
                self.assertFalse(group.ViewObject.doubleClicked())

    def testMoveViewUndoRedo(self):
        """Moving a view between pages is recorded by the task's transaction."""
        from TechDrawTools.TaskMoveView import TaskMoveView

        self.doc.UndoMode = 1
        source_page = createPageWithSVGTemplate(self.doc)
        target_page = self.doc.addObject("TechDraw::DrawPage", "TargetPage")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "TargetTemplate")
        template.Template = source_page.Template.Template
        target_page.Template = template
        view = self.doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        view.Text = ["Move me"]
        source_page.addView(view)
        self.doc.recompute()
        self.doc.clearUndos()

        task = TaskMoveView()
        try:
            task.setValues(view.Name, source_page.Name, target_page.Name)
            self.assertTrue(task.accept())
            self.assertNotIn(view, source_page.Views)
            self.assertIn(view, target_page.Views)
            self.doc.undo()
            self.assertIn(view, source_page.Views)
            self.assertNotIn(view, target_page.Views)
            self.doc.redo()
            self.assertNotIn(view, source_page.Views)
            self.assertIn(view, target_page.Views)
        finally:
            task.form.deleteLater()

    def testLockDraftAndArchViews(self):
        """The view lock command works for SVG-based views and records undo."""
        FreeCADGui.activateWorkbench("TechDrawWorkbench")
        self.doc.UndoMode = 1
        page = createPageWithSVGTemplate(self.doc)
        arch = self.doc.addObject("TechDraw::DrawViewArch", "ArchView")
        draft = self.doc.addObject("TechDraw::DrawViewDraft", "DraftView")
        for view in (arch, draft):
            page.addView(view)
        command = "TechDraw_ExtensionLockUnlockView"
        self.assertTrue(FreeCADGui.isCommandActive(command))
        part_view = self.doc.addObject("TechDraw::DrawViewPart", "PartView")
        page.addView(part_view)
        unrelated = self.doc.addObject("App::Part", "Unrelated")
        self.addCleanup(FreeCADGui.Selection.clearSelection)
        for view in (arch, draft, part_view):
            with self.subTest(view=view.TypeId):
                FreeCADGui.Selection.clearSelection()
                FreeCADGui.Selection.addSelection(self.doc.Name, view.Name)
                FreeCADGui.Selection.addSelection(self.doc.Name, unrelated.Name)
                view.LockPosition = False
                self.doc.clearUndos()
                FreeCADGui.runCommand(command)
                self.assertTrue(view.LockPosition)
                self.doc.undo()
                self.assertFalse(view.LockPosition)
                self.doc.redo()
                self.assertTrue(view.LockPosition)
                FreeCADGui.runCommand(command)
                self.assertFalse(view.LockPosition)

    def testTemplateFieldMouseButtons(self):
        """Navigation buttons do not open the template field editor."""
        import TechDrawGui
        from PySide import QtCore, QtWidgets

        page = createPageWithSVGTemplate(self.doc)
        previous_texts = dict(page.Template.EditableTexts)
        self.doc.recompute()
        FreeCADGui.activeDocument().getObject(page.Name).show()

        def process_events():
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(100, loop.quit)
            loop.exec_()

        process_events()
        scene = TechDrawGui.getSceneForPage(page)
        # TemplateTextField is UserType + 48 in QGIUserTypes.h.
        fields = [item for item in scene.items() if item.type() == 65536 + 48]
        self.assertTrue(fields)
        field = fields[0]
        rectangle = next(child for child in field.childItems() if child.type() == 3)
        position = rectangle.mapToParent(rectangle.rect().center())
        for button, expected_dialogs in (
            (QtCore.Qt.MiddleButton, 0),
            (QtCore.Qt.RightButton, 0),
            (QtCore.Qt.LeftButton, 1),
        ):
            with self.subTest(button=button):
                dialogs = []

                def close_field_dialog():
                    dialog = QtWidgets.QApplication.activeModalWidget()
                    if isinstance(dialog, QtWidgets.QDialog):
                        dialogs.append(dialog.metaObject().className())
                        dialog.reject()

                timer = QtCore.QTimer()
                timer.timeout.connect(close_field_dialog)
                timer.start(20)
                try:
                    for kind in (QtCore.QEvent.GraphicsSceneMousePress,
                                 QtCore.QEvent.GraphicsSceneMouseRelease):
                        event = QtWidgets.QGraphicsSceneMouseEvent(kind)
                        event.setButton(button)
                        event.setButtons(button if kind == QtCore.QEvent.GraphicsSceneMousePress
                                         else QtCore.Qt.NoButton)
                        event.setPos(position)
                        event.setScenePos(field.mapToScene(position))
                        scene.sendEvent(field, event)
                    process_events()
                finally:
                    timer.stop()
                self.assertEqual(len(dialogs), expected_dialogs)
                if expected_dialogs:
                    self.assertTrue(dialogs[0].endswith("DlgTemplateField"))
        self.assertEqual(dict(page.Template.EditableTexts), previous_texts)

    def testAxoLengthZeroDecimalFormatting(self):
        """A zero-decimal axonometric dimension preserves integer zero digits."""
        import time
        import Part
        from PySide import QtCore
        from TechDrawTools.CommandAxoLengthDimension import CommandAxoLengthDimension

        prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
        missing = "__missing_before_axo_format_test__"
        previous_format = prefs.GetString("formatSpec", missing)

        def restore_format():
            if previous_format == missing:
                prefs.RemString("formatSpec")
            else:
                prefs.SetString("formatSpec", previous_format)

        self.addCleanup(restore_format)
        self.addCleanup(FreeCADGui.Selection.clearSelection)

        def process_events():
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()

        page = createPageWithSVGTemplate(self.doc)
        page.ViewObject.show()
        command = CommandAxoLengthDimension()
        projection_factor = (2.0 / 3.0) ** 0.5
        for length in (10.0, 100.0, 0.4):
            source = self.doc.addObject("Part::Feature", "AxoSource")
            source.Shape = Part.makeCompound([
                Part.makeLine(FreeCAD.Vector(), FreeCAD.Vector(length, 0, 0)),
                Part.makeLine(FreeCAD.Vector(), FreeCAD.Vector(0, 20, 0)),
            ])
            view = self.doc.addObject("TechDraw::DrawViewPart", "AxoView")
            view.Source = [source]
            view.Direction = FreeCAD.Vector(1, 1, 1)
            view.XDirection = FreeCAD.Vector(1, -1, 0)
            view.ScaleType = "Custom"
            view.Scale = 1
            page.addView(view)
            self.doc.recompute()
            deadline = time.monotonic() + 15
            while not view.getVisibleEdges() or "Up-to-date" not in view.State:
                self.assertLess(time.monotonic(), deadline, view.State)
                process_events()
            self.assertEqual(len(view.getVisibleEdges()), 2)
            names = {}
            for index in range(2):
                name = "Edge%d" % index
                edge = view.getEdgeBySelection(name)
                for role, expected in (("measure", length), ("extension", 20.0)):
                    if abs(edge.Length - expected * projection_factor) < 1e-7:
                        names[role] = name
            self.assertEqual(set(names), {"measure", "extension"})

            for format_spec, decimals in (("%.2w", 2), ("%.0f", 0), ("%.0w", 0)):
                with self.subTest(length=length, format=format_spec):
                    prefs.SetString("formatSpec", format_spec)
                    previous_objects = {obj.Name for obj in self.doc.Objects}
                    FreeCADGui.Selection.clearSelection()
                    for role in ("measure", "extension"):
                        FreeCADGui.Selection.addSelection(self.doc.Name, view.Name, names[role])
                    command.Activated()
                    dimensions = [obj for obj in self.doc.Objects
                                  if obj.Name not in previous_objects
                                  and obj.isDerivedFrom("TechDraw::DrawViewDimension")]
                    self.assertEqual(len(dimensions), 1)
                    dimension = dimensions[0]
                    self.assertTrue(dimension.Arbitrary)
                    self.assertAlmostEqual(float(dimension.FormatSpec), round(length, decimals))

        # Lengths are nonnegative, but the numeric formatter also accepts signs.
        for value in (-10.0, -100.0, 0.0):
            self.assertEqual(command._formatValueToSpec(value, "%.0w"), str(int(value)))

    def testDrawViewSection(self):
        obj = self.doc.addObject("TechDraw::DrawViewSection")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawComplexSection(self):
        obj = self.doc.addObject("TechDraw::DrawComplexSection")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawRichAnno(self):
        obj = self.doc.addObject("TechDraw::DrawRichAnno")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawLeaderLine(self):
        obj = self.doc.addObject("TechDraw::DrawLeaderLine")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawViewDetail(self):
        obj = self.doc.addObject("TechDraw::DrawViewDetail")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

