// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2024 Werner Mayer <wmayer[at]users.sourceforge.net>     *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it    *
 *   under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the  *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   FreeCAD is distributed in the hope that it will be useful, but        *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
 *   Lesser General Public License for more details.                       *
 *                                                                         *
 *   You should have received a copy of the GNU Lesser General Public      *
 *   License along with FreeCAD. If not, see                               *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 **************************************************************************/

#include <sstream>
#include <string>
#include <vector>

#include <App/GeoFeature.h>
#include <App/MaterialPy.h>
#include <App/PropertyStandard.h>

// generated out of ViewProviderGeometryObject.pyi
#include "ViewProviderGeometryObjectPy.h"
#include "ViewProviderGeometryObjectPy.cpp"

using namespace Gui;

// returns a string which represents the object e.g. when printed in python
std::string ViewProviderGeometryObjectPy::representation() const
{
    std::stringstream str;
    str << "<View provider geometry object at " << getViewProviderGeometryObjectPtr() << ">";

    return str.str();
}

PyObject* ViewProviderGeometryObjectPy::getCustomAttributes(const char* attr) const
{
    ViewProviderGeometryObject* vp = getViewProviderGeometryObjectPtr();
    if (strcmp(attr, "ShapeColor") == 0) {
        // Get material property of ViewProviderGeometryObject
        App::PropertyColor prop;
        prop.setValue(vp->ShapeAppearance.getDiffuseColor());
        return prop.getPyObject();
    }
    if (strcmp(attr, "ShapeMaterial") == 0) {
        // Get material property of ViewProviderGeometryObject
        auto geometry = vp->getObject<App::GeoFeature>();
        if (geometry) {
            auto material = geometry->getMaterialAppearance();
            App::PropertyMaterial prop;
            prop.setValue(material);
            return prop.getPyObject();
        }
    }
    return nullptr;
}

PyObject* ViewProviderGeometryObjectPy::getUserDefinedMaterial()
{
    App::Material mat = App::Material::getDefaultAppearance();
    return new App::MaterialPy(new App::Material(mat));
}

PyObject* ViewProviderGeometryObjectPy::beginTemporaryAppearance(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    getViewProviderGeometryObjectPtr()->beginTemporaryAppearance();
    Py_Return;
}

PyObject* ViewProviderGeometryObjectPy::endTemporaryAppearance(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    getViewProviderGeometryObjectPtr()->endTemporaryAppearance();
    Py_Return;
}

namespace
{
/// Reads a sequence of face names ("Face1" ...); sets a Python error and returns false if it is none
bool getFaceNames(PyObject* pyFaces, std::vector<std::string>& faces)
{
    if (!PySequence_Check(pyFaces) || PyUnicode_Check(pyFaces)) {
        PyErr_SetString(PyExc_TypeError, "Expect a list of face names");
        return false;
    }
    Py::Sequence sequence(pyFaces);
    for (Py_ssize_t i = 0; i < sequence.size(); ++i) {
        PyObject* item = sequence[i].ptr();
        const char* name = PyUnicode_Check(item) ? PyUnicode_AsUTF8(item) : nullptr;
        if (!name) {
            if (!PyErr_Occurred()) {
                PyErr_SetString(PyExc_TypeError, "Expect a list of face names");
            }
            return false;
        }
        faces.emplace_back(name);
    }
    return true;
}
}  // namespace

PyObject* ViewProviderGeometryObjectPy::isLookFromMaterial(PyObject* args) const
{
    const char* element = "";
    if (!PyArg_ParseTuple(args, "|s", &element)) {
        return nullptr;
    }
    bool fromMaterial = getViewProviderGeometryObjectPtr()->isLookFromMaterial(element);
    return Py::new_reference_to(Py::Boolean(fromMaterial));
}

PyObject* ViewProviderGeometryObjectPy::resetToMaterial(PyObject* args)
{
    PyObject* pyFaces = Py_None;
    if (!PyArg_ParseTuple(args, "|O", &pyFaces)) {
        return nullptr;
    }

    std::vector<std::string> faces;
    if (pyFaces != Py_None) {
        if (!getFaceNames(pyFaces, faces)) {
            return nullptr;
        }
        if (faces.empty()) {
            Py_Return;  // nothing to reset, unlike no argument at all
        }
    }

    PY_TRY
    {
        getViewProviderGeometryObjectPtr()->resetToMaterial(faces);
        Py_Return;
    }
    PY_CATCH
}

PyObject* ViewProviderGeometryObjectPy::setFaceAppearance(PyObject* args)
{
    PyObject* pyFaces = nullptr;
    PyObject* pyLook = nullptr;
    if (!PyArg_ParseTuple(args, "OO!", &pyFaces, &App::MaterialPy::Type, &pyLook)) {
        return nullptr;
    }
    std::vector<std::string> faces;
    if (!getFaceNames(pyFaces, faces)) {
        return nullptr;
    }

    PY_TRY
    {
        const App::Material& look = *static_cast<App::MaterialPy*>(pyLook)->getMaterialPtr();
        getViewProviderGeometryObjectPtr()->setFaceAppearance(faces, look);
        Py_Return;
    }
    PY_CATCH
}

int ViewProviderGeometryObjectPy::setCustomAttributes(const char* attr, PyObject* obj)
{
    ViewProviderGeometryObject* vp = getViewProviderGeometryObjectPtr();
    if (strcmp(attr, "ShapeColor") == 0) {
        // Get material property of ViewProviderGeometryObject
        App::PropertyColor prop;
        prop.setPyObject(obj);
        vp->ShapeAppearance.setDiffuseColor(prop.getValue());
        // Assign the value to the new property type
        // ...
        return 1;
    }
    if (strcmp(attr, "ShapeMaterial") == 0) {
        // Get material property of ViewProviderGeometryObject
        auto geometry = vp->getObject<App::GeoFeature>();
        if (geometry) {
            App::PropertyMaterial prop;
            prop.setPyObject(obj);
            geometry->setMaterialAppearance(prop.getValue());
        }
        return 1;
    }
    return 0;
}
