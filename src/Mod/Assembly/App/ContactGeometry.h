// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                         *
 *                                                                          *
 *   This file is part of FreeCAD.                                          *
 *                                                                          *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, either version 2.1 of the   *
 *   License, or (at your option) any later version.                        *
 *                                                                          *
 *   FreeCAD is distributed in the hope that it will be useful, but         *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of             *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
 *   Lesser General Public License for more details.                        *
 *                                                                          *
 *   You should have received a copy of the GNU Lesser General Public       *
 *   License along with FreeCAD. If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                       *
 *                                                                          *
 ***************************************************************************/

#pragma once

#include <memory>
#include <vector>
#include <Base/Placement.h>
#include <TopoDS_Shape.hxx>
#include <Mod/Assembly/AssemblyGlobal.h>

namespace Assembly
{
struct ContactPoint
{
    Base::Vector3d point;
    Base::Vector3d normal;  // Outward force direction on the first body.
    double penetration;
    double weight = 1; // Reference surface quadrature weight.
};

// Immutable reference geometry; all queries use rigid transforms from this pose.
// Boxes only reject distant pairs. Witness points and normals come from BRep
// boundaries, with an analytic radius offset for spherical components.
// Classifier scratch state is reused; query one instance on one thread at a time.
class AssemblyExport ContactGeometry
{
public:
    ContactGeometry(const TopoDS_Shape& first, const TopoDS_Shape& second,
                    bool prepareManifold = true);
    std::vector<ContactPoint> points(
        const Base::Placement& firstDelta, const Base::Placement& secondDelta
    ) const;
    // Conservative advancement along a rigid, linearly translated/slerped sweep.
    // Returns 1 for a clear sweep, otherwise a safe fraction before first touch.
    double sweep(const Base::Placement& firstStart, const Base::Placement& firstEnd,
                 const Base::Placement& secondStart, const Base::Placement& secondEnd,
                 bool allowSeparatingTouch = false) const;
    bool acceptStep(const Base::Placement& firstStart, const Base::Placement& firstEnd,
                    const Base::Placement& secondStart, const Base::Placement& secondEnd) const;

private:
    std::vector<ContactPoint> computePoints(
        const Base::Placement& firstDelta, const Base::Placement& secondDelta
    ) const;
    struct Shape;
    double travel(const Shape& shape, const Base::Placement& start,
                  const Base::Placement& end) const;
    std::shared_ptr<const Shape> first;
    std::shared_ptr<const Shape> second;
    // Geometry depends only on pose, not velocity. Exact matches can be reused
    // across residual/result evaluations, including rejected integrator steps.
    mutable bool hasCachedPoints = false;
    mutable Base::Placement cachedFirstDelta;
    mutable Base::Placement cachedSecondDelta;
    mutable std::vector<ContactPoint> cachedPoints;
};
}
