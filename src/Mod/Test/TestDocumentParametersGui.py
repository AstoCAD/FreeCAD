# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI coverage for the Parameters dialog (Std_Parameters) and its command group."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtTest, QtWidgets

COLUMN_NAME = 0
COLUMN_EXPRESSION = 2
COLUMN_VALUE = 3


class TestDocumentParametersGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TestDocumentParametersGui")
        self.doc.UndoMode = 1
        self.varset = self.doc.addObject("App::VarSet", "VarSet")
        self.varset.addProperty("App::PropertyLength", "width", "Base", "the width")
        self.varset.width = "10 mm"
        self.feature = self.doc.addObject("App::FeatureTest", "Feature")
        self.feature.addProperty("App::PropertyLength", "myVar", "UserParameters", "a user parameter")
        self.feature.myVar = "3 mm"
        self.feature.setExpression("Float", "VarSet.width / 1 mm")
        self.doc.recompute()
        Gui.Selection.clearSelection()
        self.dialog = None
        self.openDialog()

    def tearDown(self):
        try:
            if self.dialog is not None:
                self.dialog.close()
                self.dialog = None
                Gui.updateGui()
        finally:
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)

    # helpers

    def openDialog(self):
        Gui.runCommand("Std_Parameters", 0)
        Gui.updateGui()
        self.dialog = QtWidgets.QApplication.activeModalWidget()
        self.assertIsNotNone(self.dialog, "The Parameters dialog did not open")
        self.tree = self.widget(QtWidgets.QTreeWidget, "treeParameters")

    def widget(self, widget_type, name, parent=None):
        widget = (parent or self.dialog).findChild(widget_type, name)
        self.assertIsNotNone(widget, name)
        return widget

    def group(self, title):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.text(COLUMN_NAME) == title:
                return item
        return None

    def item(self, name):
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.text(COLUMN_NAME) == name:
                    return child
        return None

    def edit(self, name, column, text):
        item = self.item(name)
        self.assertIsNotNone(item, name)
        self.tree.setCurrentItem(item, column)
        self.tree.editItem(item, column)
        Gui.updateGui()
        editor = self.tree.findChild(QtWidgets.QWidget, "parameterEditor")
        self.assertIsNotNone(editor, "no editor for column {}".format(column))
        line = editor if isinstance(editor, QtWidgets.QLineEdit) else editor.findChild(QtWidgets.QLineEdit)
        self.assertIsNotNone(line)
        line.selectAll()
        line.insert(text)
        Gui.updateGui()
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return)
        editor.setObjectName("")  # the closed editor is deleted later
        Gui.updateGui()

    def withModal(self, trigger, handler):
        """Run trigger(), which opens a nested modal dialog, and handle it with handler(dialog)."""
        state = {"tries": 0, "handled": False, "error": None}
        timer = QtCore.QTimer(self.dialog)

        def poll():
            modal = QtWidgets.QApplication.activeModalWidget()
            state["tries"] += 1
            if modal is None or modal is self.dialog:
                if state["tries"] > 200:
                    timer.stop()
                return
            timer.stop()
            state["handled"] = True
            try:
                handler(modal)
            except BaseException as error:
                state["error"] = error
                modal.reject()

        timer.timeout.connect(poll)
        timer.start(20)
        trigger()
        timer.stop()
        Gui.updateGui()
        if state["error"] is not None:
            raise state["error"]
        self.assertTrue(state["handled"], "The nested dialog did not open")

    # tests

    def testListsUserParametersAndVarSets(self):
        user = self.group("User Parameters")
        self.assertIsNotNone(user)
        self.assertEqual([user.child(i).text(COLUMN_NAME) for i in range(user.childCount())], ["myVar"])
        varset = self.group(self.varset.Label)
        self.assertIsNotNone(varset)
        width = self.item("width")
        self.assertIs(width.parent(), varset)
        self.assertEqual(width.text(1), "Length")
        self.assertEqual(width.text(4), "the width")
        self.assertIsNone(self.group("Model Parameters"))

    def testModelParametersAreOptional(self):
        self.assertIsNone(self.item("Feature.Float"))
        self.widget(QtWidgets.QCheckBox, "checkBoxModel").setChecked(True)
        Gui.updateGui()
        model = self.item("Feature.Float")
        self.assertIsNotNone(model)
        self.assertEqual(model.text(COLUMN_EXPRESSION), "VarSet.width / 1 mm")

    def testFilter(self):
        self.widget(QtWidgets.QLineEdit, "lineEditFilter").setText("wid")
        Gui.updateGui()
        self.assertFalse(self.item("width").isHidden())
        self.assertTrue(self.item("myVar").isHidden())
        self.assertTrue(self.group("User Parameters").isHidden())

    def testEditExpressionIsOneUndoStep(self):
        self.edit("width", COLUMN_EXPRESSION, "4 mm * 2")
        self.assertEqual(dict(self.varset.ExpressionEngine).get("width"), "4 mm * 2")
        self.assertAlmostEqual(self.varset.width.Value, 8)
        self.assertAlmostEqual(self.feature.Float, 8)
        self.assertEqual(self.item("width").text(COLUMN_EXPRESSION), "4 mm * 2")
        self.assertEqual(self.doc.UndoNames[0], "Set parameter expression")
        self.doc.undo()
        self.assertNotIn("width", dict(self.varset.ExpressionEngine))

    def testExpressionWithBareUserParameter(self):
        # `myVar` (a user parameter of Feature) typed by its bare name, as the completer offers it
        other = self.doc.addObject("App::VarSet", "Other")
        other.addProperty("App::PropertyLength", "depth", "Base")
        self.doc.recompute()
        self.dialog.close()
        Gui.updateGui()
        self.openDialog()
        self.edit("depth", COLUMN_EXPRESSION, "myVar * 2")
        self.assertEqual(dict(other.ExpressionEngine).get("depth"), "Feature.myVar * 2")
        self.assertAlmostEqual(other.depth.Value, 6)

    def testAddParameterWithBareUserParameter(self):
        def fill(dialog):
            holder = self.widget(QtWidgets.QComboBox, "comboBoxHolder", dialog)
            holder.setCurrentIndex(0)  # a new variable set
            self.widget(QtWidgets.QLineEdit, "lineEditName", dialog).setText("depth")
            self.widget(QtWidgets.QLineEdit, "lineEditExpression", dialog).setText("myVar + 1 mm")
            Gui.updateGui()
            ok = self.widget(QtWidgets.QDialogButtonBox, "buttonBox", dialog).button(
                QtWidgets.QDialogButtonBox.Ok)
            self.assertTrue(ok.isEnabled())
            ok.click()

        before = [o.Name for o in self.doc.Objects]
        self.withModal(self.widget(QtWidgets.QPushButton, "pushButtonAdd").click, fill)
        added = [o for o in self.doc.Objects if o.Name not in before]
        self.assertEqual(len(added), 1)
        self.assertEqual(dict(added[0].ExpressionEngine).get("depth"), "Feature.myVar + 1 mm")
        self.assertAlmostEqual(added[0].depth.Value, 4)

    def testInvalidExpressionIsRefused(self):
        self.edit("width", COLUMN_EXPRESSION, "4 mm +")
        self.assertNotIn("width", dict(self.varset.ExpressionEngine))
        self.assertNotEqual(self.widget(QtWidgets.QLabel, "labelMessage").text(), "")

    def testExpressionWithWrongUnitIsRefused(self):
        self.edit("width", COLUMN_EXPRESSION, "30 deg")
        self.assertNotIn("width", dict(self.varset.ExpressionEngine))
        self.assertAlmostEqual(self.varset.width.Value, 10)

    def testEditValue(self):
        self.edit("myVar", COLUMN_VALUE, "7 mm")
        self.assertAlmostEqual(self.feature.myVar.Value, 7)
        self.assertEqual(self.doc.UndoNames[0], "Set parameter value")
        self.doc.undo()
        self.assertAlmostEqual(self.feature.myVar.Value, 3)

    def testRenameUpdatesExpressions(self):
        self.edit("width", COLUMN_NAME, "depth")
        self.assertIn("depth", self.varset.PropertiesList)
        self.assertNotIn("width", self.varset.PropertiesList)
        self.assertEqual(dict(self.feature.ExpressionEngine).get("Float"), "VarSet.depth / 1 mm")
        self.assertIsNotNone(self.item("depth"))
        self.doc.undo()
        self.assertIn("width", self.varset.PropertiesList)
        self.assertEqual(dict(self.feature.ExpressionEngine).get("Float"), "VarSet.width / 1 mm")

    def testRenameKeepsUserParameterNamesUnique(self):
        other = self.doc.addObject("App::FeatureTest", "Other")
        other.addProperty("App::PropertyLength", "taken", "UserParameters")
        QtCore.QMetaObject.invokeMethod(self.dialog, "refresh")
        Gui.updateGui()
        self.edit("myVar", COLUMN_NAME, "taken")
        self.assertIn("myVar", self.feature.PropertiesList)
        self.assertNotIn("taken", self.feature.PropertiesList)
        self.assertNotEqual(self.widget(QtWidgets.QLabel, "labelMessage").text(), "")

    def testDeleteWarnsWhenReferenced(self):
        self.tree.setCurrentItem(self.item("width"))
        delete = self.widget(QtWidgets.QPushButton, "pushButtonDelete")
        self.assertTrue(delete.isEnabled())
        seen = []

        def answer(button):
            def handler(box):
                seen.append(box.text())
                box.button(button).click()
            return handler

        self.withModal(delete.click, answer(QtWidgets.QMessageBox.No))
        self.assertIn("Feature.Float", seen[0])
        self.assertIn("width", self.varset.PropertiesList)

        self.withModal(delete.click, answer(QtWidgets.QMessageBox.Yes))
        self.assertNotIn("width", self.varset.PropertiesList)
        self.assertEqual(self.doc.UndoNames[0], "Delete parameter")
        self.doc.undo()
        self.assertIn("width", self.varset.PropertiesList)

    def testAddParameterToVarSet(self):
        self.tree.setCurrentItem(self.item("width"))

        def fill(dialog):
            holder = self.widget(QtWidgets.QComboBox, "comboBoxHolder", dialog)
            self.assertEqual(holder.currentData(), "VarSet")
            self.widget(QtWidgets.QLineEdit, "lineEditName", dialog).setText("height")
            self.widget(QtWidgets.QLineEdit, "lineEditExpression", dialog).setText("VarSet.width * 2")
            self.widget(QtWidgets.QLineEdit, "lineEditComment", dialog).setText("twice the width")
            Gui.updateGui()
            ok = self.widget(QtWidgets.QDialogButtonBox, "buttonBox", dialog).button(
                QtWidgets.QDialogButtonBox.Ok)
            self.assertTrue(ok.isEnabled())
            ok.click()

        self.withModal(self.widget(QtWidgets.QPushButton, "pushButtonAdd").click, fill)
        self.assertIn("height", self.varset.PropertiesList)
        # a reference to the own object is stored without the object name
        self.assertIn(dict(self.varset.ExpressionEngine).get("height"),
                      ("width * 2", "VarSet.width * 2"))
        self.assertAlmostEqual(self.varset.height.Value, 20)
        self.assertEqual(self.varset.getDocumentationOfProperty("height"), "twice the width")
        self.assertEqual(self.doc.UndoNames[0], "Add parameter")
        self.assertIsNotNone(self.item("height"))

    def testAddUserParameterToObject(self):
        self.tree.setCurrentItem(self.item("myVar"))

        def fill(dialog):
            holder = self.widget(QtWidgets.QComboBox, "comboBoxHolder", dialog)
            self.assertEqual(holder.currentData(), "Feature")
            name = self.widget(QtWidgets.QLineEdit, "lineEditName", dialog)
            expression = self.widget(QtWidgets.QLineEdit, "lineEditExpression", dialog)
            buttons = self.widget(QtWidgets.QDialogButtonBox, "buttonBox", dialog)
            name.setText("myVar")  # already used in the document
            expression.setText("5 mm")
            Gui.updateGui()
            self.assertFalse(buttons.button(QtWidgets.QDialogButtonBox.Ok).isEnabled())
            name.setText("thickness")
            Gui.updateGui()
            buttons.button(QtWidgets.QDialogButtonBox.Ok).click()

        self.withModal(self.widget(QtWidgets.QPushButton, "pushButtonAdd").click, fill)
        self.assertIn("thickness", self.feature.PropertiesList)
        self.assertEqual(self.feature.getGroupOfProperty("thickness"), "UserParameters")
        self.assertAlmostEqual(self.feature.thickness.Value, 5)
        self.assertNotIn("thickness", dict(self.feature.ExpressionEngine))

    def testAddToNewVarSet(self):
        def fill(dialog):
            holder = self.widget(QtWidgets.QComboBox, "comboBoxHolder", dialog)
            holder.setCurrentIndex(0)  # a new variable set
            self.assertEqual(holder.currentData(), "")
            self.widget(QtWidgets.QLineEdit, "lineEditName", dialog).setText("angle")
            self.widget(QtWidgets.QLineEdit, "lineEditExpression", dialog).setText("30 deg")
            Gui.updateGui()
            self.widget(QtWidgets.QDialogButtonBox, "buttonBox", dialog).button(
                QtWidgets.QDialogButtonBox.Ok).click()

        before = [o.Name for o in self.doc.Objects]
        self.withModal(self.widget(QtWidgets.QPushButton, "pushButtonAdd").click, fill)
        added = [o for o in self.doc.Objects if o.Name not in before]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].TypeId, "App::VarSet")
        self.assertEqual(added[0].getTypeIdOfProperty("angle"), "App::PropertyAngle")
        self.assertAlmostEqual(added[0].angle.Value, 30)
        # the new variable set and its parameter are one undo step
        self.doc.undo()
        self.assertEqual([o.Name for o in self.doc.Objects], before)

    def addDialogState(self, holder_name, name, expression):
        """Fill the Add dialog for @p holder_name; return (OK enabled, error text), cancelled,
        or add the parameter when OK is enabled and @p name ends with '!'."""
        state = {}

        def fill(dialog):
            holder = self.widget(QtWidgets.QComboBox, "comboBoxHolder", dialog)
            holder.setCurrentIndex(holder.findData(holder_name))
            self.widget(QtWidgets.QLineEdit, "lineEditName", dialog).setText(name.rstrip("!"))
            self.widget(QtWidgets.QLineEdit, "lineEditExpression", dialog).setText(expression)
            Gui.updateGui()
            buttons = self.widget(QtWidgets.QDialogButtonBox, "buttonBox", dialog)
            ok = buttons.button(QtWidgets.QDialogButtonBox.Ok)
            state["enabled"] = ok.isEnabled()
            if ok.isEnabled() and name.endswith("!"):
                ok.click()
            else:
                buttons.button(QtWidgets.QDialogButtonBox.Cancel).click()

        self.withModal(self.widget(QtWidgets.QPushButton, "pushButtonAdd").click, fill)
        return state["enabled"]

    def testUserParameterNamesFollowTheAppRules(self):
        # the same rules as `name = value` typed in an input (App::UserParameters::checkName)
        self.assertFalse(self.addDialogState("Feature", "VarSet", "5 mm"))  # an object name
        self.assertFalse(self.addDialogState("Feature", "_hidden", "5 mm"))  # reserved
        self.assertTrue(self.addDialogState("Feature", "fresh", "5 mm"))
        self.assertNotIn("fresh", self.feature.PropertiesList)  # cancelled

    def testUserParameterLengthIsSignedDistance(self):
        self.assertTrue(self.addDialogState("Feature", "offset!", "-5 mm"))
        self.assertEqual(self.feature.getTypeIdOfProperty("offset"), "App::PropertyDistance")
        self.assertEqual(self.feature.getGroupOfProperty("offset"), "UserParameters")
        self.assertAlmostEqual(self.feature.offset.Value, -5)

    def testUnitWithoutPropertyTypeIsRefused(self):
        # a plain App::PropertyQuantity would lose the unit on save
        self.assertFalse(self.addDialogState("VarSet", "odd", "2 mm * 1 N * 1 N"))
        self.assertFalse(self.addDialogState("Feature", "odd", "2 mm * 1 N * 1 N"))
        self.assertNotIn("odd", self.varset.PropertiesList)
        self.assertNotIn("odd", self.feature.PropertiesList)

    def testRenameUserParameterFollowsTheAppRules(self):
        self.edit("myVar", COLUMN_NAME, "VarSet")
        self.assertIn("myVar", self.feature.PropertiesList)
        self.assertNotEqual(self.widget(QtWidgets.QLabel, "labelMessage").text(), "")
        self.edit("myVar", COLUMN_NAME, "_myVar")
        self.assertIn("myVar", self.feature.PropertiesList)
        self.assertNotIn("_myVar", self.feature.PropertiesList)


class TestParametersCommandGroupGui(unittest.TestCase):
    def testCommandsExist(self):
        for name in ("Std_Parameters", "Std_VarSet", "Std_ParametersGroup"):
            self.assertIsNotNone(Gui.Command.get(name), name)
        self.assertEqual(Gui.Command.get("Std_Parameters").getInfo()["pixmap"], "VarSet")
        self.assertEqual(Gui.Command.get("Std_ParametersGroup").getInfo()["pixmap"], "VarSet")

    def testGroupReplacesVarSetInFileToolbar(self):
        toolbars = Gui.activeWorkbench().getToolbarItems()
        if "File" not in toolbars:
            self.skipTest("the active workbench has no File toolbar")
        self.assertIn("Std_ParametersGroup", toolbars["File"])
        self.assertNotIn("Std_VarSet", toolbars["File"])

    def testGroupDefaultIsParameters(self):
        actions = Gui.Command.get("Std_ParametersGroup").getAction()
        if not actions:
            self.skipTest("the command group is not in the current toolbars or menus")
        texts = [action.text().replace("&", "") for action in actions]
        self.assertEqual(len(texts), 2, texts)
        self.assertTrue(texts[0].startswith("Parameters"), texts)
        self.assertEqual(texts[1], "Variable Set")


class _TaskPanel:
    def __init__(self):
        self.form = QtWidgets.QWidget()

    def accept(self):
        return True

    def reject(self):
        return True


class TestParametersCommandInTaskGui(unittest.TestCase):
    """The Parameters dialog commits its own transactions: it must not be opened while a task
    dialog holds a transaction of the document (Cancel of the task would no longer revert)."""

    def setUp(self):
        self.doc = App.newDocument("TestParametersCommandInTaskGui")
        self.doc.UndoMode = 1
        self.feature = self.doc.addObject("App::FeatureTest", "Feature")
        self.doc.recompute()
        Gui.updateGui()

    def tearDown(self):
        try:
            Gui.Control.closeDialog()
            Gui.updateGui()
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
        finally:
            App.closeDocument(self.doc.Name)

    def command(self):
        return Gui.Command.get("Std_Parameters")

    def testDisabledWhileTaskHoldsTransaction(self):
        self.assertTrue(self.command().isActive())
        self.doc.openTransaction("Task edit")
        self.feature.Integer = 5
        Gui.Control.showDialog(_TaskPanel())
        Gui.updateGui()
        self.assertFalse(self.command().isActive())

        # running it anyway opens nothing and keeps the task's transaction
        Gui.runCommand("Std_Parameters", 0)
        Gui.updateGui()
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.assertTrue(self.doc.HasPendingTransaction)
        self.doc.abortTransaction()
        self.assertNotEqual(self.feature.Integer, 5)

    def testEnabledInTaskWithoutTransaction(self):
        # e.g. sketch edit between two tools
        Gui.Control.showDialog(_TaskPanel())
        Gui.updateGui()
        self.assertTrue(self.command().isActive())


if __name__ == "__main__":
    unittest.main()
