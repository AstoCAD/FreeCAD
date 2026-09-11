// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include <vector>
#include <Geom_BSplineSurface.hxx>
#include <TopoDS_Edge.hxx>

namespace Surface
{
// Interpolate an open rectangular network. Curves may be unordered and reversed;
// each profile/guide pair must have one distinct intersection.
Handle(Geom_BSplineSurface) buildGordonSurface(
    const std::vector<TopoDS_Edge>& profiles,
    const std::vector<TopoDS_Edge>& guides,
    double tolerance,
    int maxSamples,
    double& approximationError
);
}  // namespace Surface
