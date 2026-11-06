# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: preference widgets show the default the code uses.

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


# Workbench preference pages: (Gui module registering the page, page class, widget,
# parameter group, parameter type, parameter, value the code uses while it is unset)
MODULE_DEFAULTS = (
    # ViewProviderPartExt::loadParameter(), ViewProviderCurveNet, CAM PathSegmentWalker
    ("PartGui", "PartGui::DlgSettings3DViewPart", "maxDeviation",
     "Mod/Part", "Float", "MeshDeviation", 0.2),
)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestModulePreferenceDefaultsGui(unittest.TestCase):
    """Workbench preference pages show the value their code uses for an unset parameter."""

    def setUp(self):
        import importlib

        self.rows = []
        for row in MODULE_DEFAULTS:
            try:
                importlib.import_module(row[0])  # registers the module's preference pages
            except ImportError:
                continue
            self.rows.append(row)
        if not self.rows:
            self.skipTest("No workbench with a checked preference page is available")
        self.results = {}
        self.errors = []
        saved = []
        for _module, _page, _widget, group, typ, name, _value in self.rows:
            handle = App.ParamGet("User parameter:BaseApp/Preferences/" + group)
            had = name in getattr(handle, "Get" + typ + "s")()
            saved.append((handle, typ, name, had, getattr(handle, "Get" + typ)(name) if had else None))
            getattr(handle, "Rem" + typ)(name)

        def restore():
            for handle, typ, name, had, value in saved:
                if had:
                    getattr(handle, "Set" + typ)(name, value)
                else:
                    getattr(handle, "Rem" + typ)(name)

        self.addCleanup(restore)

    def inspect(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            pages = {}
            for widget in dialog.findChildren(QtWidgets.QWidget):
                pages.setdefault(widget.metaObject().className(), widget)
            for _module, page_class, widget_name, _group, _typ, name, _value in self.rows:
                page = pages.get(page_class)
                if page is None:
                    self.errors.append("page not found: " + page_class)
                    continue
                widget = page.findChild(QtWidgets.QWidget, widget_name)
                if widget is None:
                    self.errors.append("widget not found: " + widget_name)
                    continue
                # OK/Apply stores this value (Pref*::savePreferences)
                if isinstance(widget, QtWidgets.QAbstractButton):
                    self.results[name] = widget.isChecked()
                else:
                    self.results[name] = widget.value()
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testUnsetParametersShowCodeDefault(self):
        QtCore.QTimer.singleShot(500, self.inspect)
        Gui.showPreferences("General")
        self.assertEqual(self.errors, [])
        for _module, _page, _widget, _group, _typ, name, value in self.rows:
            with self.subTest(parameter=name):
                self.assertIn(name, self.results)
                if isinstance(value, float):
                    self.assertAlmostEqual(self.results[name], value, places=6)
                else:
                    self.assertEqual(self.results[name], value)
