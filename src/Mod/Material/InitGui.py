# SPDX-License-Identifier: LGPL-2.1-or-later

#***************************************************************************
#*   Copyright (c) 2013 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************
"""Initialization of the Material module graphical interface.

There is no Material workbench anymore: its only tool, the material setter, is part of
Std_SetAppearance ("Material and appearance"), and the material editor is in the Tools menu.
"""

# Load the GUI at startup, like Measure, so that "Material and appearance" (View menu, context
# menus, Ctrl+D) and the material editor (Tools menu) exist in every workbench
import MatGui

FreeCAD.__unit_test__ += [ "TestMaterialsGui" ]
