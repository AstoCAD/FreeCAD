// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: 2026 The FreeCAD Project Association AISBL
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1            *
 *   of the License, or (at your option) any later version.                   *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful,               *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty              *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                  *
 *   See the GNU Lesser General Public License for more details.              *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD. If not, see https://www.gnu.org/licenses     *
 *                                                                            *
 ******************************************************************************/

// inclusion of the generated files (generated out of LocalCoordinateSystem.pyi)
#include "LocalCoordinateSystemPy.h"
#include "LocalCoordinateSystemPy.cpp"

using namespace App;

// The element getters of LocalCoordinateSystem throw a Base::RuntimeError when the element of the
// requested role is missing. The generated method wrappers turn it into a Python RuntimeError.

// returns a string which represents the object e.g. when printed in python
std::string LocalCoordinateSystemPy::representation() const
{
    return {"<LocalCoordinateSystem object>"};
}

PyObject* LocalCoordinateSystemPy::getOrigin(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getOrigin()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getX(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getX()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getY(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getY()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getZ(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getZ()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getXY(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getXY()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getXZ(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getXZ()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getYZ(PyObject* args) const
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    return getLocalCoordinateSystemPtr()->getYZ()->getPyObject();
}

PyObject* LocalCoordinateSystemPy::getCustomAttributes(const char* /*attr*/) const
{
    return nullptr;
}

int LocalCoordinateSystemPy::setCustomAttributes(const char* /*attr*/, PyObject* /*obj*/)
{
    return 0;
}
