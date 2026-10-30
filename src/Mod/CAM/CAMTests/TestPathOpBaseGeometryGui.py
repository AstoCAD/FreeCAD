# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import unittest

import FreeCAD
import FreeCADGui
import Path.Main.Gui.Job as PathJobGui
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore, QtGui


class TestPathOpBaseGeometryDeleteKey(unittest.TestCase):
    """The Delete key in the Base Geometry list removes the selected entries
    instead of deleting the model object through Std_Delete (#13877)."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestPathOpBaseGeometryGui")
        FreeCAD.setActiveDocument(self.doc.Name)
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = 20
        box.Width = 20
        box.Height = 10
        cyl = self.doc.addObject("Part::Cylinder", "Cylinder")
        cyl.Radius = 2
        cyl.Height = 10
        cyl.Placement.Base = FreeCAD.Vector(10, 10, 0)
        cut = self.doc.addObject("Part::Cut", "Cut")
        cut.Base = box
        cut.Tool = cyl
        self.doc.recompute()
        self.job = PathJobGui.Create([cut], openTaskPanel=False)
        self.doc.recompute()
        self.model = self.job.Model.Group[0]

    def tearDown(self):
        dialog = FreeCADGui.Control.activeTaskDialog()
        if dialog:
            dialog.reject()
        FreeCADGui.Control.closeDialog()
        FreeCAD.closeDocument(self.doc.Name)

    def _open(self, command):
        op = command.setJob(self.job)
        self.assertIsNotNone(op)
        panel = op.ViewObject.Proxy.panel
        self.assertIsNotNone(panel)
        pages = [p for p in panel.featurePages if isinstance(p, PathOpGui.TaskPanelBaseGeometryPage)]
        self.assertEqual(len(pages), 1)
        return op, pages[0]

    def _pressDelete(self, widget):
        override = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_Delete, QtCore.Qt.NoModifier
        )
        QtGui.QApplication.sendEvent(widget, override)
        # an accepted override keeps the global Delete shortcut from firing
        self.assertTrue(override.isAccepted())
        press = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Delete, QtCore.Qt.NoModifier)
        QtGui.QApplication.sendEvent(widget, press)

    def _baseSubs(self, op):
        return [sub for _, subs in op.Base for sub in subs]

    def test00_profile_delete_key(self):
        import Path.Op.Gui.Profile as PathProfileGui

        op, page = self._open(PathProfileGui.Command)
        op.Base = [(self.model, ("Face1", "Face2"))]
        page.setFields(op)
        baseList = page.form.baseList
        self.assertEqual(baseList.count(), 2)

        baseList.setCurrentRow(0)
        self._pressDelete(baseList)

        self.assertEqual(baseList.count(), 1)
        self.assertEqual(self._baseSubs(op), ["Face2"])
        self.assertIsNotNone(self.doc.getObject(self.model.Name))

    def test01_drilling_delete_key(self):
        import Path.Op.Gui.Drilling as PathDrillingGui

        op, page = self._open(PathDrillingGui.Command)
        if not self._baseSubs(op):
            # make sure there is a hole feature to remove
            cylFaces = [
                f"Face{i + 1}"
                for i, f in enumerate(self.model.Shape.Faces)
                if f.Surface.TypeId == "Part::GeomCylinder"
            ]
            op.Proxy.addBase(op, self.model, cylFaces[0])
            page.setFields(op)
        baseList = page.form.baseList
        self.assertEqual(baseList.rowCount(), 1)

        baseList.selectRow(0)
        self._pressDelete(baseList)

        self.assertEqual(baseList.rowCount(), 0)
        self.assertEqual(self._baseSubs(op), [])
        self.assertIsNotNone(self.doc.getObject(self.model.Name))
