# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2021 Chris Hennes
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

# Gui Unit tests for the FEM module
from OpenSCADTest.gui.test_commandUndo import TestCommandUndo as OpenSCADGuiTestCommandUndo
from OpenSCADTest.gui.test_dummy import TestDummy as OpenSCADGuiTestDummy
from OpenSCADTest.gui.test_importCSGVisibility import TestImportCSGVisibility as OpenSCADGuiTestImportCSGVisibility
from OpenSCADTest.gui.test_replaceObject import TestReplaceObjectUndo as OpenSCADGuiTestReplaceObjectUndo


# dummy usage to get flake8 and lgtm quiet
False if OpenSCADGuiTestCommandUndo.__name__ else True
False if OpenSCADGuiTestDummy.__name__ else True
False if OpenSCADGuiTestImportCSGVisibility.__name__ else True
False if OpenSCADGuiTestReplaceObjectUndo.__name__ else True
