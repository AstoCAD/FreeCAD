# SPDX-License-Identifier: LGPL-2.1-or-later
"""File pickers preserve surviving menu actions and tolerate deleted actions."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
try:
    from shiboken6 import isValid
except ImportError:
    from shiboken2 import isValid


class _MessageBoxShows(QtCore.QObject):
    def __init__(self, record):
        super().__init__()
        self.record = record

    def eventFilter(self, target, event):
        if event.type() == QtCore.QEvent.Show and target.inherits("QMessageBox"):
            self.record({
                "meta": target.metaObject().className(),
                "title": str(target.property("windowTitle") or ""),
                "text": str(target.property("text") or ""),
                "informative_text": str(target.property("informativeText") or ""),
                "detailed_text": str(target.property("detailedText") or ""),
            })
        return False


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
class TestFileDialogMenuLifetime(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        self.window = Gui.getMainWindow()
        self.bar = self.window.menuBar()
        self.menus = []
        self.callback_errors = []
        self.watchdog_fired = False
        self.modal_seen = False
        self.dialog = None
        self.settings = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        self.old_native_setting = next((value for kind, name, value in (self.settings.GetContents() or [])
                                        if name == "DontUseNativeDialog"), None)
        self.settings.SetBool("DontUseNativeDialog", True)
        self.addCleanup(self._cleanup)
        self.message_boxes = []
        self.message_box_observer = _MessageBoxShows(self.message_boxes.append)
        self.app.installEventFilter(self.message_box_observer)

    def _cleanup(self):
        if hasattr(self, "message_box_observer"):
            self.app.removeEventFilter(self.message_box_observer)
        if hasattr(self, "poll"):
            self.poll.stop()
        if hasattr(self, "watchdog"):
            self.watchdog.stop()
        if self.dialog is not None and isValid(self.dialog) and self.dialog.isVisible():
            self.dialog.reject()
        for menu in self.menus:
            if isValid(menu):
                menu.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(menu, QtCore.QEvent.DeferredDelete)
        if self.old_native_setting is None:
            self.settings.RemBool("DontUseNativeDialog")
        else:
            self.settings.SetBool("DontUseNativeDialog", self.old_native_setting)

    def _watchdog(self):
        self.watchdog_fired = True
        modal = self.app.activeModalWidget()
        if modal is not None:
            modal.reject()

    def _open_and_cancel(self, enabled, delete_menu):
        self.menu = QtWidgets.QMenu("FileDialog lifetime fixture", self.bar)
        self.menu.setObjectName("FileDialogLifetimeFixtureOwnedMenu")
        self.menus.append(self.menu)
        self.action = self.bar.addMenu(self.menu)
        self.action.setEnabled(enabled)
        self.assertIn(self.action, self.bar.actions())
        self.assertEqual(self.action.isEnabled(), enabled)
        self.menu_destroyed = False
        self.action_destroyed = False
        self.menu.destroyed.connect(lambda: setattr(self, "menu_destroyed", True))
        self.action.destroyed.connect(lambda: setattr(self, "action_destroyed", True))

        def handle_picker():
            modal = self.app.activeModalWidget()
            if modal is None or not modal.inherits("QFileDialog"):
                return
            self.poll.stop()
            self.dialog = modal
            self.modal_seen = True
            try:
                self.assertTrue(modal.isVisible())
                self.assertTrue(modal.isModal())
                # Verify FreeCAD's ActionDisabler, beyond ordinary Qt modality.
                self.assertFalse(self.action.isEnabled())
                if delete_menu:
                    self.menu.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(self.menu, QtCore.QEvent.DeferredDelete)
                    self.assertTrue(self.menu_destroyed)
                    self.assertTrue(self.action_destroyed)
                    self.assertFalse(isValid(self.action))
                    self.assertFalse(isValid(self.menu))
            except Exception as error:
                self.callback_errors.append(type(error).__name__ + ": " + str(error))
            finally:
                modal.reject()

        self.poll = QtCore.QTimer()
        self.poll.timeout.connect(handle_picker)
        self.poll.start(20)
        self.watchdog = QtCore.QTimer()
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self._watchdog)
        self.watchdog.start(5000)
        Gui.runCommand("Std_Open")
        self.poll.stop()
        self.watchdog.stop()
        self.assertTrue(self.modal_seen, "The actual Std_Open picker was not observed")
        self.assertFalse(self.watchdog_fired, "Native picker handling reached its watchdog")
        self.assertEqual(self.callback_errors, [])
        self.assertEqual(self.message_boxes, [], "Std_Open raised an actual native error dialog")
        if delete_menu:
            self.assertTrue(self.menu_destroyed)
            self.assertTrue(self.action_destroyed)
        else:
            self.assertTrue(isValid(self.menu))
            self.assertTrue(isValid(self.action))
            self.assertEqual(self.action.isEnabled(), enabled)

    def test_enabled_menu_survives_control(self):
        self._open_and_cancel(enabled=True, delete_menu=False)

    def test_disabled_menu_survives_control(self):
        self._open_and_cancel(enabled=False, delete_menu=False)

    def test_owned_enabled_menu_deleted_during_picker(self):
        self._open_and_cancel(enabled=True, delete_menu=True)
