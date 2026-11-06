# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: preference check boxes show the default the code uses.

A preference check box shows its .ui state when the parameter is not set yet,
and OK/Apply writes what it shows. These boxes were unchecked in the .ui file
while the code defaults to True, so on a fresh profile the page showed the
wrong state, and pressing OK on any page turned the features off.

To run tests:
    FreeCAD -t TestPreferenceDefaultsGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

# (page class, check box, parameter group, parameter): the code reads them with default True
CHECKED_BY_DEFAULT = (
    ("Gui::Dialog::DlgSettingsSelection", "checkBoxAutoSwitch", "TreeView", "SyncView"),
    ("Gui::Dialog::DlgSettingsSelection", "checkBoxAutoExpand", "TreeView", "SyncSelection"),
    ("Gui::Dialog::DlgSettingsSelection", "checkBoxRecord", "TreeView", "RecordSelection"),
    ("Gui::Dialog::DlgSettingsDocumentImp", "prefCanAbortRecompute", "Document", "CanAbortRecompute"),
)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestPreferenceDefaultsGui(unittest.TestCase):
    def setUp(self):
        self.results = {}
        self.errors = []
        self.saved = []
        for _page, _box, group, name in CHECKED_BY_DEFAULT:
            handle = App.ParamGet("User parameter:BaseApp/Preferences/" + group)
            had = name in handle.GetBools()
            self.saved.append((handle, name, had, handle.GetBool(name) if had else None))
            handle.RemBool(name)
        self.addCleanup(self._restore)

    def _restore(self):
        for handle, name, had, value in self.saved:
            if had:
                handle.SetBool(name, value)
            else:
                handle.RemBool(name)

    def inspect(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            pages = {}
            for widget in dialog.findChildren(QtWidgets.QWidget):
                pages.setdefault(widget.metaObject().className(), widget)
            for page_class, box_name, _group, name in CHECKED_BY_DEFAULT:
                page = pages.get(page_class)
                if page is None:
                    self.errors.append("page not found: " + page_class)
                    continue
                box = page.findChild(QtWidgets.QCheckBox, box_name)
                if box is None:
                    self.errors.append("check box not found: " + box_name)
                    continue
                # OK/Apply stores this state (PrefCheckBox::savePreferences)
                self.results[name] = box.isChecked()
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testUnsetParametersShowCodeDefault(self):
        QtCore.QTimer.singleShot(500, self.inspect)
        Gui.showPreferences("General")
        self.assertEqual(self.errors, [])
        for _page, _box, _group, name in CHECKED_BY_DEFAULT:
            with self.subTest(parameter=name):
                self.assertTrue(self.results.get(name), name + " shown unchecked")
