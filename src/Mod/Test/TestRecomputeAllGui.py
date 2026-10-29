# SPDX-License-Identifier: LGPL-2.1-or-later
"""Std_RecomputeAll recomputes every object of the active document (#17589)."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui


class CountingFeature:
    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyInteger", "Executions")

    def execute(self, obj):
        obj.Executions = obj.Executions + 1


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestRecomputeAllGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("RecomputeAll17589")
        Gui.getDocument(self.doc.Name).activeView()
        self.objects = []
        for name in ("First", "Second"):
            obj = self.doc.addObject("App::FeaturePython", name)
            CountingFeature(obj)
            self.objects.append(obj)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def testRecomputesUpToDateObjects(self):
        self.assertEqual([obj.Executions for obj in self.objects], [1, 1])
        self.assertFalse(self.doc.mustExecute())

        command = Gui.Command.get("Std_RecomputeAll")
        self.assertIsNotNone(command)
        self.assertEqual(command.getShortcut(), "Shift+F5")

        App.setActiveDocument(self.doc.Name)
        Gui.runCommand("Std_RecomputeAll")
        self.assertEqual([obj.Executions for obj in self.objects], [2, 2])
        self.assertFalse(self.doc.mustExecute())
