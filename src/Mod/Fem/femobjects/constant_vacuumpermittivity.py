# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2020 Bernd Hahnebach <bernd@bimstatik.org>              *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
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

__title__ = "FreeCAD FEM constant vacuum permittivity object"
__author__ = "Bernd Hahnebach"
__url__ = "https://www.freecad.org"

## @package constant_vacuumpermittivity
#  \ingroup FEM
#  \brief FreeCAD FEM constant vacuum permittivity object

from FreeCAD import Units

from femtools import constants
from . import base_fempythonobject


class ConstantVacuumPermittivity(base_fempythonobject.BaseFemPythonObject):

    Type = "Fem::ConstantVacuumPermittivity"

    def __init__(self, obj):
        super().__init__(obj)
        obj.addProperty(
            "App::PropertyVacuumPermittivity",
            "VacuumPermittivity",
            "Constants",
            "Overwrites default permittivity of vacuum",
        )
        obj.setPropertyStatus("VacuumPermittivity", "LockDynamic")
        # we must set an expression so that the small value can actually be entered
        obj.setExpression("VacuumPermittivity", constants.vacuum_permittivity())

    def onDocumentRestored(self, obj):
        # Older versions bound a unitless expression (e.g. "8.85419e-12"), which stores the SI
        # number in the internal units (mm based) of the property, and the solver writer
        # scaled it back. Give such an expression the unit F/m it was meant in.
        for path, expression in obj.ExpressionEngine:
            if path != "VacuumPermittivity":
                continue
            try:
                value = obj.evalExpression(expression)
            except Exception:
                # an expression that cannot be evaluated now is left as it is
                return
            if isinstance(value, Units.Quantity) and value.Unit != Units.Unit():
                return
            try:
                float(expression)
                new_expression = f"{expression} F/m"
            except ValueError:
                new_expression = f"({expression}) * 1 F/m"
            obj.setExpression("VacuumPermittivity", new_expression)
            # a restored object is not recomputed, so set the value the expression gives now
            obj.VacuumPermittivity = obj.evalExpression(new_expression)
