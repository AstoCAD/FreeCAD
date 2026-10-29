# SPDX-License-Identifier: LGPL-2.1-or-later
"""Double-clicking a geometry object must honour the user edit mode."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui


class EditModeRecorder:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.modes = []

    def attach(self, vobj):
        pass

    def setEdit(self, vobj, mode):
        self.modes.append(mode)
        return True

    def unsetEdit(self, vobj, mode):
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestUserEditModeGui(unittest.TestCase):
    def setUp(self):
        self.previous_mode = Gui.getUserEditMode()
        self.doc = App.newDocument("UserEditMode12124")
        self.obj = self.doc.addObject("App::GeometryPython", "Geometry")
        self.recorder = EditModeRecorder(self.obj.ViewObject)

    def tearDown(self):
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc.getInEdit():
            gui_doc.resetEdit()
        Gui.setUserEditMode(self.previous_mode)
        App.closeDocument(self.doc.Name)

    def testDoubleClickUsesUserEditMode(self):
        # https://github.com/FreeCAD/FreeCAD/issues/12124
        modes = Gui.listUserEditModes()
        cutting = 2
        Gui.setUserEditMode(modes[cutting])
        self.assertEqual(Gui.getUserEditMode(), modes[cutting])

        self.assertTrue(self.obj.ViewObject.doubleClicked())
        self.assertEqual(self.recorder.modes, [cutting])

    def testDoubleClickUsesDefaultEditModeByDefault(self):
        modes = Gui.listUserEditModes()
        Gui.setUserEditMode(modes[0])

        self.assertTrue(self.obj.ViewObject.doubleClicked())
        self.assertEqual(self.recorder.modes, [0])
