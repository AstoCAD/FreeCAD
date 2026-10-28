# SPDX-License-Identifier: LGPL-2.1-or-later
"""Opening embedded text documents must preserve their saved clean state.

These tests use the public ViewObject.doubleClicked API used by
Std_TextDocument, followed by actual native editor input. They do not depend on
tree visibility. Saves and the save/reopen test use ordinary owned FCStd files
inside an explicitly selected disposable profile; modified flags are never reset.
"""

import os
from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestTextDocumentOpenGui(unittest.TestCase):
    def setUp(self):
        self.profile = self._owned_profile()
        self.assertEqual(App.listDocuments(), {}, "Requires an isolated GUI process")
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.owned = []
        self.temporary = tempfile.TemporaryDirectory(
            prefix="text_document_open_", dir=str(self.profile)
        )
        self.directory = Path(self.temporary.name)
        self.assertTrue(self.directory.resolve().is_relative_to(self.profile))
        self.addCleanup(self._cleanup)
        self.main = Gui.getMainWindow()
        areas = self.main.findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]

    def _owned_profile(self):
        selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
        if not selected:
            self.skipTest("Requires an explicitly selected disposable test profile")
        import stat

        def plain(path):
            for part in (path, *path.parents):
                try:
                    if part.is_symlink():
                        return False
                    junction = getattr(part, "is_junction", None)
                    if junction is not None and junction():
                        return False
                    attributes = getattr(part.lstat(), "st_file_attributes", 0)
                    if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                        return False
                except FileNotFoundError:
                    continue
                except OSError:
                    return False
            return True

        raw = Path(selected)
        if not raw.is_absolute() or not plain(raw):
            self.skipTest("The disposable profile must be an absolute plain directory")
        try:
            profile = raw.resolve(strict=True)
        except OSError:
            self.skipTest("The disposable profile must already exist")
        if not profile.is_dir():
            self.skipTest("The disposable profile must be a directory")
        home_text = os.environ.get("FREECAD_USER_HOME")
        if not home_text:
            self.skipTest("FREECAD_USER_HOME must explicitly select the disposable profile")
        home = Path(home_text)
        if not home.is_absolute() or not plain(home):
            self.skipTest("FREECAD_USER_HOME must be an absolute plain directory")
        try:
            matching_home = home.resolve(strict=True) == profile
        except OSError:
            matching_home = False
        if not matching_home:
            self.skipTest("FREECAD_USER_HOME does not match the disposable profile")
        config = Path(App.ConfigGet("UserParameter"))
        data = Path(App.getUserAppDataDir())
        if not all(path.is_absolute() and plain(path) for path in (config, data)):
            self.skipTest("Active profile paths must be absolute and free of links")
        if config.resolve() != profile / "user.cfg":
            self.skipTest("The active user configuration is outside the selected profile")
        if not all(path.resolve().is_relative_to(profile) for path in (config, data)):
            self.skipTest("Active configuration and data must stay in the selected profile")
        return profile

    def _events(self):
        QtTest.QTest.qWait(20)

    def _wait(self, predicate, message):
        deadline = time.monotonic() + 6
        while not predicate():
            self.assertLess(time.monotonic(), deadline, message)
            self._events()

    def _cleanup(self):
        try:
            Gui.Selection.clearSelection()
            for name, uid in reversed(self.owned):
                if name in App.listDocuments():
                    self.assertEqual(str(App.getDocument(name).Uid), uid)
                    App.closeDocument(name)
            self._events()
            self.assertEqual(App.listDocuments(), {})
        finally:
            self.temporary.cleanup()

    def _state(self, document, note):
        return {
            "name": document.Name,
            "uid": str(document.Uid),
            "label": document.Label,
            "comment": document.Comment,
            "note_name": note.Name,
            "note_label": note.Label,
            "text": note.Text,
            "gui_modified": bool(Gui.getDocument(document.Name).Modified),
            "font_name": note.ViewObject.FontName,
            "font_size": float(note.ViewObject.FontSize),
            "syntax": str(note.ViewObject.SyntaxHighlighter),
            "read_only": bool(note.ViewObject.ReadOnly),
            "status": {
                name: list(note.ViewObject.getPropertyStatus(name))
                for name in ("FontName", "SyntaxHighlighter")
            },
        }

    def _assert_presentation(self, note, editor):
        self.assertEqual(editor.toPlainText(), note.Text)
        self.assertEqual(editor.isReadOnly(), note.ViewObject.ReadOnly)
        expected_font = QtGui.QFont(note.ViewObject.FontName, int(note.ViewObject.FontSize))
        self.assertEqual(editor.font().family(), expected_font.family())
        self.assertEqual(editor.font().pointSize(), expected_font.pointSize())
        highlighters = editor.findChildren(QtGui.QSyntaxHighlighter)
        self.assertEqual(len(highlighters), int(str(note.ViewObject.SyntaxHighlighter) == "Python"))
        for highlighter in highlighters:
            self.assertIs(highlighter.document(), editor.document())

    def _save_clean(self, document, note, editor=None):
        self.assertTrue(Gui.getDocument(document.Name).save())
        self._events()
        self.assertTrue(Path(document.FileName).is_file())
        self.assertFalse(Gui.getDocument(document.Name).Modified)
        if editor is not None:
            self._assert_presentation(note, editor)

    def _create(self, syntax="None", read_only=False):
        document = App.newDocument("TextDocumentOpenTest")
        self.owned.append((document.Name, str(document.Uid)))
        note = document.addObject("App::TextDocument", "Note")
        note.Label = "AuditTextNote"
        note.Text = "ordinary ASCII note"
        note.ViewObject.SyntaxHighlighter = syntax
        note.ViewObject.ReadOnly = read_only
        document.recompute()
        path = self.directory / "note.FCStd"
        self.assertTrue(path.resolve().is_relative_to(self.directory.resolve()))
        document.saveAs(str(path))
        self._save_clean(document, note)
        self.assertEqual(len(document.Objects), 1)
        return document, note

    def _open(self, document, note, existing=None):
        before = self._state(document, note)
        App.setActiveDocument(document.Name)
        Gui.Selection.clearSelection()
        self._events()
        self.assertIn((document.Name, str(document.Uid)), self.owned)
        self.assertEqual(str(document.Uid), before["uid"])
        self.assertEqual(App.getDocument(document.Name), document)
        self.assertEqual(note.Document, document)
        self.assertEqual(document.getObject(note.Name), note)
        self.assertEqual(note.ViewObject.Object, note)
        self.main.raise_()
        self.main.activateWindow()
        self._wait(
            lambda: QtWidgets.QApplication.applicationState() == QtCore.Qt.ApplicationActive
            and QtWidgets.QApplication.activeWindow() is self.main,
            "The main window did not become ready for editor input",
        )
        self.assertEqual(bool(Gui.getDocument(document.Name).Modified), before["gui_modified"])
        old_windows = list(self.area.subWindowList())
        self.assertIs(note.ViewObject.doubleClicked(), True)
        if existing is None:
            def created():
                return [
                    window for window in self.area.subWindowList()
                    if window not in old_windows
                    and window.widget().inherits("Gui::TextDocumentEditorView")
                ]

            self._wait(lambda: len(created()) == 1, "The native embedded text editor did not open")
            window = created()[0]
        else:
            window = existing
            self._wait(lambda: self.area.activeSubWindow() is window, "Existing editor did not activate")
            self.assertEqual(list(self.area.subWindowList()), old_windows)
        self.assertTrue(window.widget().inherits("Gui::TextDocumentEditorView"))
        editors = window.widget().findChildren(QtWidgets.QPlainTextEdit)
        self.assertEqual(len(editors), 1)
        editor = editors[0]
        self.assertTrue(editor.isVisibleTo(self.main))
        self.assertIs(self.area.activeSubWindow(), window)
        after = self._state(document, note)
        self.assertEqual(
            {key: value for key, value in after.items() if key != "gui_modified"},
            {key: value for key, value in before.items() if key != "gui_modified"},
        )
        self._assert_presentation(note, editor)
        return window, editor

    def _editable(self):
        document, note = self._create()
        window, editor = self._open(document, note)
        # Observe opening before an ordinary save establishes the edit control baseline.
        self._save_clean(document, note, editor)
        return document, note, window, editor

    def test_open_clean_default_note_stays_clean(self):
        document, note = self._create()
        self._open(document, note)
        self.assertFalse(Gui.getDocument(document.Name).Modified)

    def test_open_clean_python_note_stays_clean(self):
        document, note = self._create("Python")
        self._open(document, note)
        self.assertFalse(Gui.getDocument(document.Name).Modified)

    def test_open_read_only_note_stays_clean(self):
        document, note = self._create(read_only=True)
        self._open(document, note)
        self.assertFalse(Gui.getDocument(document.Name).Modified)

    def test_open_preserves_existing_dirty_state(self):
        document, note = self._create()
        document.Comment = "ordinary pending ASCII comment"
        self.assertTrue(Gui.getDocument(document.Name).Modified)
        self._open(document, note)
        self.assertEqual(document.Comment, "ordinary pending ASCII comment")
        self.assertTrue(Gui.getDocument(document.Name).Modified)

    def test_real_editor_typing_marks_document_dirty(self):
        document, note, window, editor = self._editable()
        editor.setFocus(QtCore.Qt.OtherFocusReason)
        self._wait(lambda: editor.hasFocus(), "The real note editor did not receive focus")
        editor.selectAll()
        QtTest.QTest.keyClicks(editor, "edited ASCII note")
        self._wait(lambda: note.Text == "edited ASCII note", "Real keystrokes did not update the note")
        self._assert_presentation(note, editor)
        self.assertTrue(Gui.getDocument(document.Name).Modified)

    def test_later_font_change_marks_document_dirty(self):
        document, note, window, editor = self._editable()
        families = list(QtGui.QFontDatabase.families())
        candidates = [
            name for name in ("Courier New", "Consolas", "Arial", "DejaVu Sans Mono")
            if name in families and name != note.ViewObject.FontName
        ]
        if not candidates:
            candidates = sorted(
                name for name in families if name.isascii() and name != note.ViewObject.FontName
            )
        self.assertTrue(candidates, "Requires a distinct ordinary installed ASCII font")
        before = note.Text
        note.ViewObject.FontName = candidates[0]
        self._events()
        self._assert_presentation(note, editor)
        self.assertEqual(note.Text, before)
        self.assertTrue(Gui.getDocument(document.Name).Modified)

    def test_later_syntax_change_marks_document_dirty(self):
        document, note, window, editor = self._editable()
        before = note.Text
        note.ViewObject.SyntaxHighlighter = "Python"
        self._events()
        self._assert_presentation(note, editor)
        self.assertEqual(note.Text, before)
        self.assertTrue(Gui.getDocument(document.Name).Modified)

    def test_activate_existing_editor_keeps_clean_state_and_window_count(self):
        document, note, window, editor = self._editable()
        reused_window, reused_editor = self._open(document, note, existing=window)
        self.assertIs(reused_window, window)
        self.assertIs(reused_editor, editor)
        self.assertFalse(Gui.getDocument(document.Name).Modified)

    def test_open_note_after_ordinary_saved_file_reopen_stays_clean(self):
        document, note = self._create("Python")
        name, uid, note_name = document.Name, str(document.Uid), note.Name
        path, text, label = document.FileName, note.Text, note.Label
        self.assertEqual((name, uid), self.owned[-1])
        # This is a normal save/close/open workflow. Reacquire every wrapper after close.
        App.closeDocument(name)
        self.owned.pop()
        del note, document
        self._events()
        self.assertEqual(App.listDocuments(), {})
        reopened = App.openDocument(path)
        self.owned.append((reopened.Name, str(reopened.Uid)))
        restored = reopened.getObject(note_name)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.Text, text)
        self.assertEqual(restored.Label, label)
        self.assertEqual(str(restored.ViewObject.SyntaxHighlighter), "Python")
        self.assertFalse(Gui.getDocument(reopened.Name).Modified)
        self._open(reopened, restored)
        self.assertFalse(Gui.getDocument(reopened.Name).Modified)
