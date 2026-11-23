// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2018 Werner Mayer <wmayer[at]users.sourceforge.net>     *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/

#include <sstream>


#include <Mod/Mesh/App/MeshFeature.h>

#include "ViewProvider.h"
// inclusion of the generated files (generated out of ViewProviderMeshPy.xml)
#include "ViewProviderMeshPy.h"
#include "ViewProviderMeshPy.cpp"


using namespace MeshGui;

namespace
{
// Converts a sequence of facet indices of the mesh shown by the view provider.
// An index outside the mesh raises IndexError, as the selection flags are set without a check.
std::vector<Mesh::FacetIndex> facetIndicesFromPy(PyObject* obj, ViewProviderMesh* vp)
{
    auto feature = freecad_cast<Mesh::Feature*>(vp->getObject());
    const unsigned long numFacets = feature ? feature->Mesh.getValue().countFacets() : 0;

    Py::Sequence list(obj);
    std::vector<Mesh::FacetIndex> selection;
    selection.reserve(list.size());
    for (Py::Sequence::iterator it = list.begin(); it != list.end(); ++it) {
        Py::Long index(*it);
        unsigned long value = PyLong_AsUnsignedLong(index.ptr());
        if ((value == static_cast<unsigned long>(-1) && PyErr_Occurred()) || value >= numFacets) {
            PyErr_Clear();
            throw Py::IndexError("Facet index out of range");
        }
        selection.push_back(value);
    }
    return selection;
}
}  // namespace

// returns a string which represents the object e.g. when printed in python
std::string ViewProviderMeshPy::representation() const
{
    std::stringstream str;
    str << "<View provider object at " << getViewProviderDocumentObjectPtr() << ">";

    return str.str();
}

PyObject* ViewProviderMeshPy::setSelection(PyObject* args)
{
    PyObject* obj {};
    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return nullptr;
    }

    ViewProviderMesh* vp = getViewProviderMeshPtr();
    std::vector<Mesh::FacetIndex> selection = facetIndicesFromPy(obj, vp);
    vp->setSelection(selection);
    Py_Return;
}

PyObject* ViewProviderMeshPy::addSelection(PyObject* args)
{
    PyObject* obj {};
    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return nullptr;
    }

    ViewProviderMesh* vp = getViewProviderMeshPtr();
    std::vector<Mesh::FacetIndex> selection = facetIndicesFromPy(obj, vp);
    vp->addSelection(selection);
    Py_Return;
}

PyObject* ViewProviderMeshPy::removeSelection(PyObject* args)
{
    PyObject* obj {};
    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return nullptr;
    }

    ViewProviderMesh* vp = getViewProviderMeshPtr();
    std::vector<Mesh::FacetIndex> selection = facetIndicesFromPy(obj, vp);
    vp->removeSelection(selection);
    Py_Return;
}

PyObject* ViewProviderMeshPy::invertSelection(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    ViewProviderMesh* vp = getViewProviderMeshPtr();
    vp->invertSelection();
    Py_Return;
}

PyObject* ViewProviderMeshPy::clearSelection(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    ViewProviderMesh* vp = getViewProviderMeshPtr();
    vp->clearSelection();
    Py_Return;
}

PyObject* ViewProviderMeshPy::highlightSegments(PyObject* args)
{
    PyObject* list {};
    if (!PyArg_ParseTuple(args, "O", &list)) {
        return nullptr;
    }

    App::PropertyColorList colors;
    colors.setPyObject(list);

    ViewProviderMesh* vp = getViewProviderMeshPtr();
    vp->highlightSegments(colors.getValues());
    Py_Return;
}

PyObject* ViewProviderMeshPy::getCustomAttributes(const char* /*attr*/) const
{
    return nullptr;
}

int ViewProviderMeshPy::setCustomAttributes(const char* /*attr*/, PyObject* /*obj*/)
{
    return 0;
}
