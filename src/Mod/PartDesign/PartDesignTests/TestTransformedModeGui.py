# SPDX-License-Identifier: LGPL-2.1-or-later
"""Transform mode switching in the pattern task panel."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestTransformedModeGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TransformedModeGui")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.box = self.body.newObject("PartDesign::AdditiveBox", "Box")
        self.box.Length = 4
        self.box.Width = 4
        self.box.Height = 4
        self.doc.recompute()

    def tearDown(self):
        Gui.Selection.clearSelection()
        if self.gui_doc.getInEdit():
            self.gui_doc.resetEdit()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        App.closeDocument(self.doc.Name)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def featureGroup(self):
        groups = [
            group
            for group in Gui.getMainWindow().findChildren(QtWidgets.QGroupBox, "groupFeatureList")
            if group.isVisible()
        ]
        self.assertEqual(len(groups), 1)
        return groups[0]

    def checkedItems(self, group):
        widget = group.findChild(QtWidgets.QListWidget, "listWidgetFeatures")
        self.assertIsNotNone(widget)
        return [
            widget.item(row).text()
            for row in range(widget.count())
            if widget.item(row).checkState() == QtCore.Qt.Checked
        ]

    def testToolShapesSurviveSwitchToBodyAndBack(self):
        # https://github.com/FreeCAD/FreeCAD/issues/32951
        pattern = self.body.newObject("PartDesign::LinearPattern", "LinearPattern")
        pattern.Originals = [self.box]
        x_axis = [f for f in self.body.Origin.OriginFeatures if f.Role == "X_Axis"][0]
        pattern.Direction = (x_axis, [""])
        pattern.Length = 10
        pattern.Occurrences = 2
        self.doc.recompute()
        self.assertEqual(pattern.TransformMode, "Features")

        self.gui_doc.setEdit(pattern.Name)
        self.pump()
        group = self.featureGroup()
        self.assertTrue(group.isChecked())
        self.assertEqual(self.checkedItems(group), [self.box.Label])

        # Switching to "Transform body" and back must not drop the selected features.
        group.setChecked(False)
        self.pump()
        self.assertEqual(pattern.TransformMode, "Whole shape")

        group.setChecked(True)
        self.pump()
        self.assertEqual(pattern.TransformMode, "Features")
        self.assertEqual(self.checkedItems(group), [self.box.Label])
        self.assertEqual(pattern.Originals, [self.box])
