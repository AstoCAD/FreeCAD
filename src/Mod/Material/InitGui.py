# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2013 Juergen Riegel
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

"""Initialization of the Material module graphical interface.

There is no Material workbench anymore: its only tool, the material setter, is part of
Std_SetAppearance ("Material and appearance"), and the material editor is in the Tools menu.
"""

# Load the GUI at startup, like Measure, so that "Material and appearance" (View menu, context
# menus, Ctrl+D) and the material editor (Tools menu) exist in every workbench
import MatGui

FreeCAD.__unit_test__ += [ "TestMaterialsGui" ]
