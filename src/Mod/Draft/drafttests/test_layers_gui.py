# SPDX-License-Identifier: LGPL-2.1-or-later

"""Unit tests for the Draft Layers manager, GUI only."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

import Draft
from draftguitools import gui_layers
from draftutils import params
from drafttests import test_base

USE_PRINT_COLOR_COLUMN = 8


class DraftGuiLayersManager(test_base.DraftTestCaseDoc):
    """The Layers manager shows and edits the UsePrintColor property (#17953)."""

    def setUp(self):
        super().setUp()
        # the manager stores its size when it closes
        for name in ("LayersManagerWidth", "LayersManagerHeight"):
            self.addCleanup(params.set_param, name, params.get_param(name))
        self.layer_a = Draft.make_layer("A_layer")
        self.layer_b = Draft.make_layer("B_layer")
        self.layer_b.ViewObject.UsePrintColor = True
        self.doc.recompute()

    def run_manager(self, callback):
        """Open the Layers manager and run callback(cmd) inside its event loop."""
        cmd = gui_layers.LayerManager()
        errors = []

        def inside():
            try:
                callback(cmd)
            except Exception as err:  # reported after the dialog has closed
                errors.append(err)
            finally:
                if cmd.dialog.isVisible():
                    cmd.dialog.reject()

        QtCore.QTimer.singleShot(0, inside)
        cmd.Activated()
        Gui.updateGui()
        self.assertFalse(cmd.dialog.isVisible())
        if errors:
            raise errors[0]
        return cmd

    @staticmethod
    def rows(cmd):
        model = cmd.model
        return {model.item(row, 1).toolTip(): row for row in range(model.rowCount())}

    def test_column_shows_use_print_color(self):
        def check(cmd):
            model = cmd.model
            self.assertEqual(model.columnCount(), USE_PRINT_COLOR_COLUMN + 1)
            self.assertEqual(
                model.headerData(USE_PRINT_COLOR_COLUMN, QtCore.Qt.Horizontal),
                gui_layers.translate("Draft", "Use Print Color"),
            )
            rows = self.rows(cmd)
            item_a = model.item(rows[self.layer_a.Name], USE_PRINT_COLOR_COLUMN)
            item_b = model.item(rows[self.layer_b.Name], USE_PRINT_COLOR_COLUMN)
            for item in (item_a, item_b):
                self.assertTrue(item.isCheckable())
                self.assertFalse(item.isEditable())
                self.assertTrue(item.isEnabled())
            self.assertEqual(item_a.checkState(), QtCore.Qt.Unchecked)
            self.assertEqual(item_b.checkState(), QtCore.Qt.Checked)

        self.run_manager(check)

    def test_ok_writes_use_print_color(self):
        def toggle(cmd):
            rows = self.rows(cmd)
            cmd.model.item(rows[self.layer_a.Name], USE_PRINT_COLOR_COLUMN).setCheckState(
                QtCore.Qt.Checked
            )
            cmd.model.item(rows[self.layer_b.Name], USE_PRINT_COLOR_COLUMN).setCheckState(
                QtCore.Qt.Unchecked
            )
            cmd.accept()

        self.run_manager(toggle)
        self.assertTrue(self.layer_a.ViewObject.UsePrintColor)
        self.assertFalse(self.layer_b.ViewObject.UsePrintColor)

    def test_unchanged_dialog_does_not_open_transaction(self):
        undo_count = self.doc.UndoCount
        self.run_manager(lambda cmd: cmd.accept())
        self.assertEqual(self.doc.UndoCount, undo_count)
        self.assertFalse(self.layer_a.ViewObject.UsePrintColor)
        self.assertTrue(self.layer_b.ViewObject.UsePrintColor)

    def test_cancel_keeps_use_print_color(self):
        def toggle(cmd):
            rows = self.rows(cmd)
            cmd.model.item(rows[self.layer_a.Name], USE_PRINT_COLOR_COLUMN).setCheckState(
                QtCore.Qt.Checked
            )
            cmd.dialog.reject()

        self.run_manager(toggle)
        self.assertFalse(self.layer_a.ViewObject.UsePrintColor)

    def test_new_layer_row(self):
        def add(cmd):
            cmd.addItem()
            row = cmd.model.rowCount() - 1
            item = cmd.model.item(row, USE_PRINT_COLOR_COLUMN)
            self.assertEqual(item.checkState(), QtCore.Qt.Unchecked)
            item.setCheckState(QtCore.Qt.Checked)
            cmd.accept()

        before = {obj.Name for obj in self.doc.Objects}
        self.run_manager(add)
        new = [obj for obj in self.doc.Objects if obj.Name not in before]
        self.assertEqual(len(new), 1)
        self.assertTrue(new[0].ViewObject.UsePrintColor)


## @}
