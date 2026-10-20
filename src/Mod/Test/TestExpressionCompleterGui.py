# SPDX-License-Identifier: LGPL-2.1-or-later
"""Expression completion through the actual bound quantity editor."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class TestExpressionCompleterGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ExpressionCompleterRegression")
        self.doc.Label = "Completion document with spaces"
        self.dialog = None
        self.spin = None
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.addCleanup(self.close_editor)
        self.varset = self.doc.addObject("App::VarSet", "VarSet")
        self.varset.Label = "Variables with spaces"
        self.varset.addProperty("App::PropertyLength", "xLength")
        self.varset.addProperty("App::PropertyLength", "yWidth")
        self.varset.addProperty("App::PropertyPlacement", "Placement")
        self.varset.xLength = 20
        self.varset.yWidth = 5
        self.varset.Placement = App.Placement(App.Vector(3, 4, 5), App.Rotation())
        self.other = self.doc.addObject("App::FeaturePython", "Other")
        self.other.addProperty("App::PropertyLength", "Length")
        self.doc.recompute()

    def close_editor(self):
        if self.dialog is not None:
            self.dialog.reject()
            self.dialog = None
        if self.spin is not None:
            self.spin.close()
            self.spin.deleteLater()
            self.spin = None
        Gui.updateGui()

    def check_completions(self, owner, cases):
        """Open the real expression dialog, complete, insert, and evaluate each case."""
        self.spin = Gui.UiLoader().createWidget("Gui::QuantitySpinBox")
        self.spin.setProperty("unit", "mm")
        prop = "yWidth" if owner == self.varset else "Length"
        self.spin.setProperty("binding", self.doc.Name + "#" + owner.Name + "." + prop)
        self.spin.show()
        self.spin.setFocus()
        QtTest.QTest.keyClicks(self.spin, "=")
        Gui.updateGui()
        dialogs = [widget for widget in QtWidgets.QApplication.allWidgets()
                   if widget.objectName() == "DlgExpressionInput" and widget.isVisible()]
        self.assertEqual(len(dialogs), 1)
        self.dialog = dialogs[0]
        expression = self.dialog.findChild(QtWidgets.QPlainTextEdit, "expression")
        self.assertIsNotNone(expression)
        completers = expression.findChildren(QtWidgets.QCompleter)
        self.assertEqual(len(completers), 1)
        completer = completers[0]

        for prefix, leaf, value, expected_path in cases:
            with self.subTest(owner=owner.Name, prefix=prefix):
                expression.setPlainText(prefix)
                cursor = expression.textCursor()
                cursor.movePosition(QtGui.QTextCursor.End)
                expression.setTextCursor(cursor)
                completer.slotUpdate(prefix, len(prefix))
                self.assertEqual(completer.splitPath(prefix), expected_path)
                model = completer.completionModel()
                candidates = [(model.index(row, 0), model.index(row, 0).data())
                              for row in range(model.rowCount())]
                matches = [index for index, label in candidates if label == leaf]
                self.assertTrue(matches, candidates)
                self.assertIsInstance(model, QtCore.QAbstractProxyModel)
                source_index = model.mapToSource(matches[0])
                self.assertEqual(source_index.model(), completer.model())
                completion = completer.pathFromIndex(source_index)
                self.assertTrue(completion.endswith(leaf), completion)
                # Exercise the editor's real completion insertion connection.
                completer.activated[str].emit(completion)
                inserted = expression.toPlainText()
                self.assertEqual(inserted, completion)
                result = owner.evalExpression(inserted)
                if hasattr(result, "Value"):
                    result = result.Value
                self.assertAlmostEqual(result, value)
        return completer

    def testSameOwnerQualifiedName(self):
        self.check_completions(self.varset, [
            ("VarSet.x", "xLength", 20, ["VarSet", "x"]),
            ("VarSet.xL", "xLength", 20, ["VarSet", "xL"]),
        ])

    def testSameOwnerQuotedLabel(self):
        for text in (self.varset.Label, "Variables α.with # punctuation"):
            with self.subTest(label=text):
                self.varset.Label = text
                label = "<<" + text + ">>"
                try:
                    self.check_completions(self.varset, [
                        (label + ".xL", "xLength", 20, [label, "xL"]),
                    ])
                finally:
                    self.close_editor()

    def testSameOwnerDocumentQualifiedName(self):
        self.check_completions(self.varset, [
            (self.doc.Name + "#VarSet.xL", "xLength", 20,
             [self.doc.Name, "VarSet", "xL"]),
        ])

    def testSameOwnerDocumentQualifiedLabels(self):
        document = "<<" + self.doc.Label + ">>"
        label = "<<" + self.varset.Label + ">>"
        self.check_completions(self.varset, [
            (document + "#" + label + ".xL", "xLength", 20,
             [document, label, "xL"]),
        ])

    def testSameOwnerExactProperty(self):
        self.check_completions(self.varset, [
            ("VarSet.xLength", "xLength", 20, ["VarSet", "xLength"]),
        ])

    def testUnqualifiedAndLeadingDotProperties(self):
        self.check_completions(self.varset, [
            ("xL", "xLength", 20, ["xL"]),
            (".xL", "xLength", 20, ["VarSet", "xL"]),
        ])

    def testOtherOwnerQualifiedProperties(self):
        label = "<<" + self.varset.Label + ">>"
        self.check_completions(self.other, [
            ("VarSet.xL", "xLength", 20, ["VarSet", "xL"]),
            (label + ".xL", "xLength", 20, [label, "xL"]),
        ])

    def testNestedPlacementPaths(self):
        self.check_completions(self.varset, [
            ("Placement.Base.", "Base.x", 3, ["Placement", "Base."]),
            (".Placement.Base.", "Base.x", 3, ["VarSet", "Placement", "Base."]),
            ("VarSet.Placement.Base.", "Base.x", 3,
             ["VarSet", "Placement", "Base."]),
            ("VarSet.Placement.Base.x", "Base.x", 3,
             ["VarSet", "Placement", "Base.x"]),
        ])

    def testLocalCompoundPropertyWithOwnerName(self):
        self.varset.addProperty("App::PropertyPlacement", self.varset.Name)
        self.varset.VarSet = App.Placement(App.Vector(91, 92, 93), App.Rotation())
        self.doc.recompute()
        completer = self.check_completions(self.varset, [
            (".VarSet.Base.", "Base.x", 91, ["VarSet", "VarSet", "Base."]),
            (".VarSet.Base.x", "Base.x", 91, ["VarSet", "VarSet", "Base.x"]),
        ])
        # The ambiguous bare form already lacks candidates, but its local-property
        # interpretation must not gain an object qualifier.
        self.assertEqual(completer.splitPath("VarSet.Base."), ["VarSet", "Base."])
        self.assertEqual(completer.splitPath("VarSet.Base.x"), ["VarSet", "Base.x"])
        self.assertEqual(self.varset.evalExpression("VarSet.Base.x"), 91)
