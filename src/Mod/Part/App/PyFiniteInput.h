// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <cmath>
#include <string>

#include <gp_Pnt.hxx>

#include <CXX/Objects.hxx>
#include <Base/Matrix.h>
#include <Base/Tools2D.h>
#include <Base/Vector3D.h>

/** Validation of the numbers that Part's Python bindings receive.
 *
 * OpenCASCADE does not check for NaN or infinity: a gp_Pnt, gp_Dir or a radius built from them is
 * accepted silently and only breaks later, in whatever algorithm consumes the geometry. The
 * bindings therefore check their input where the Python value is turned into OCC geometry.
 *
 * These helpers are meant for Python entry points only (constructors, attribute setters and the
 * Part.makeXXX() factories): they throw Py::ValueError("<what> must be finite"), which sets the
 * Python exception. Do not use them in C++ internals or in restore paths. Base::Vector3d itself
 * must keep accepting NaN (e.g. Points uses it to mark invalid points).
 */
namespace Part
{

/// Returns @p value, or throws Py::ValueError("<what> must be finite") if it is NaN or infinite.
inline double checkFinite(double value, const char* what)
{
    if (!std::isfinite(value)) {
        throw Py::ValueError(std::string(what) + " must be finite");
    }
    return value;
}

/// Returns @p vec, or throws Py::ValueError("<what> must be finite") for a non-finite coordinate.
inline const Base::Vector3d& checkFinite(const Base::Vector3d& vec, const char* what)
{
    if (!std::isfinite(vec.x) || !std::isfinite(vec.y) || !std::isfinite(vec.z)) {
        throw Py::ValueError(std::string(what) + " must be finite");
    }
    return vec;
}

/// Returns @p vec, or throws Py::ValueError("<what> must be finite") for a non-finite coordinate.
inline const Base::Vector2d& checkFinite(const Base::Vector2d& vec, const char* what)
{
    if (!std::isfinite(vec.x) || !std::isfinite(vec.y)) {
        throw Py::ValueError(std::string(what) + " must be finite");
    }
    return vec;
}

/// Returns @p mat, or throws Py::ValueError("<what> must be finite") for a non-finite element.
inline const Base::Matrix4D& checkFinite(const Base::Matrix4D& mat, const char* what)
{
    for (unsigned int row = 0; row < 4; ++row) {
        for (double element : mat[row]) {
            if (!std::isfinite(element)) {
                throw Py::ValueError(std::string(what) + " must be finite");
            }
        }
    }
    return mat;
}

/** Converts a checked vector to a point.
 *
 * Directions are deliberately checked with checkFinite() and then built by the caller as before,
 * so that a null direction keeps raising the caller's existing error.
 */
inline gp_Pnt toFinitePnt(const Base::Vector3d& vec, const char* what)
{
    checkFinite(vec, what);
    return gp_Pnt(vec.x, vec.y, vec.z);
}

}  // namespace Part
