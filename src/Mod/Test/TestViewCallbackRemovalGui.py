# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD contributors
# SPDX-FileNotice: Part of the FreeCAD project.

"""GUI regression tests for removing 3D view callbacks from Python.

See https://github.com/FreeCAD/FreeCAD/issues/19379

To run tests:
    FreeCAD -t TestViewCallbackRemovalGui
"""

import sys
import unittest

import FreeCAD
import FreeCADGui
from pivy import coin

# Extra references to the callables given to remove*(): a wrong release of a reference the
# view does not own then makes the test fail instead of crashing the interpreter.
_KEEP_ALIVE = []


class Holder:
    def callback(self, *args):
        pass


class TestViewCallbackRemovalGui(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestViewCallbackRemoval")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.view = FreeCADGui.ActiveDocument.ActiveView

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def check_bound_method_removal(self, add, remove):
        holder = Holder()
        # 'holder.callback' creates a new bound method object on every access, so the
        # object given to remove() is not the one given to add().
        removed = holder.callback
        _KEEP_ALIVE.extend((removed, removed))
        holder_refs = sys.getrefcount(holder)
        removed_refs = sys.getrefcount(removed)

        add(holder.callback)
        self.assertEqual(sys.getrefcount(holder), holder_refs + 1)
        remove(removed)

        # the registered callback must be released, and the argument left alone
        self.assertEqual(sys.getrefcount(holder), holder_refs)
        self.assertEqual(sys.getrefcount(removed), removed_refs)

    def test_remove_dragger_callback_with_bound_method(self):
        dragger = coin.SoTranslate2Dragger()
        self.check_bound_method_removal(
            lambda cb: self.view.addDraggerCallback(dragger, "addFinishCallback", cb),
            lambda cb: self.view.removeDraggerCallback(dragger, "addFinishCallback", cb),
        )

    def test_remove_event_callback_with_bound_method(self):
        self.check_bound_method_removal(
            lambda cb: self.view.addEventCallback("SoMouseButtonEvent", cb),
            lambda cb: self.view.removeEventCallback("SoMouseButtonEvent", cb),
        )

    def test_remove_event_callback_pivy_with_bound_method(self):
        event_type = coin.SoMouseButtonEvent.getClassTypeId()
        self.check_bound_method_removal(
            lambda cb: self.view.addEventCallbackPivy(event_type, cb),
            lambda cb: self.view.removeEventCallbackPivy(event_type, cb),
        )

    def test_remove_unregistered_callback_keeps_reference(self):
        def callback(*args):
            pass

        _KEEP_ALIVE.extend((callback, callback))
        refs = sys.getrefcount(callback)
        self.view.addEventCallback("SoMouseButtonEvent", callback)
        self.view.removeEventCallback("SoMouseButtonEvent", callback)
        self.assertEqual(sys.getrefcount(callback), refs)

        # removing it a second time must not release a reference it does not own
        self.view.removeEventCallback("SoMouseButtonEvent", callback)
        self.assertEqual(sys.getrefcount(callback), refs)
