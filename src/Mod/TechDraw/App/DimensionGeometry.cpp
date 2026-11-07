// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2022 WandererFan <wandererfan@gmail.com>                *
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

# include <gp_Ax3.hxx>
# include <gp_Trsf.hxx>
# include <gp_Vec.hxx>


#include <Base/Console.h>
#include <Base/Converter.h>
#include <Base/Tools.h>

#include "DimensionGeometry.h"
#include "DrawUtil.h"
#include "DrawViewPart.h"
#include "DrawViewDetail.h"


using namespace TechDraw;
using DU = DrawUtil;

namespace
{
//! project a 3d point (relative to the view's centroid) onto the dvp's paper plane, in the
//! coordinates of the view's 2d geometry: scaled, rotated by the view's Rotation and with Y
//! inverted.
Base::Vector3d projectToView(const DrawViewPart* dvp, const Base::Vector3d& point)
{
    auto detailView = dynamic_cast<const DrawViewDetail*>(dvp);
    if (detailView) {
        return detailView->mapPoint3dToDetail(point) * detailView->getScale();
    }
    Base::Vector3d result = dvp->projectPoint(point, false) * dvp->getScale();
    result.RotateZ(Base::toRadians(dvp->Rotation.getValue()));
    return DU::invertY(result);
}
}  // namespace

pointPair::pointPair(const pointPair& pp)
{
    first(pp.first());
    second(pp.second());
    overrideFirst(pp.extensionLineFirst());
    overrideSecond(pp.extensionLineSecond());
}

// set extension line points from argument base points
void pointPair::setExtensionLine(const pointPair& pp){
    overrideFirst(pp.first());
    overrideSecond(pp.second());
}

//move the points by offset
void pointPair::move(const Base::Vector3d& offset)
{
    m_first = m_first - offset;
    m_second = m_second - offset;
    m_overrideFirst = m_overrideFirst - offset;
    m_overrideSecond = m_overrideSecond - offset;
}

//move the points by factor
void pointPair::scale(double factor)
{
    m_first = m_first * factor;
    m_second = m_second * factor;
    m_overrideFirst = m_overrideFirst * factor;
    m_overrideSecond = m_overrideSecond * factor;
}

// project the points onto the dvp's paper plane.
void pointPair::project(const DrawViewPart* dvp)
{
    m_first = projectToView(dvp, m_first);
    m_second = projectToView(dvp, m_second);
    m_overrideFirst = projectToView(dvp, m_overrideFirst);
    m_overrideSecond = projectToView(dvp, m_overrideSecond);
}

// map the points onto the dvp's XY coordinate system
// this routine is no longer needed since we now use the hlr projector instead
// of "projectToPlane" from Vector3d
void pointPair::mapToPage(const DrawViewPart* dvp)
{
    gp_Trsf xOXYZ;
    gp_Ax3 OXYZ;
    xOXYZ.SetTransformation(OXYZ, gp_Ax3(dvp->getRotatedCS()));

    gp_Vec gvFirst = Base::convertTo<gp_Vec>(m_first).Transformed(xOXYZ);
    m_first = Base::convertTo<Base::Vector3d>(gvFirst);
    gp_Vec gvSecond = Base::convertTo<gp_Vec>(m_second).Transformed(xOXYZ);
    m_second = Base::convertTo<Base::Vector3d>(gvSecond);
}

// this routine is no longer needed since we now use the dvp's projectPoint
// which performs Y inversion by default
void pointPair::invertY()
{
    m_first = DU::invertY(m_first);
    m_second = DU::invertY(m_second);
}

void pointPair::dump(const std::string& text) const
{
    Base::Console().message("pointPair - {}\n", text);
    Base::Console().message("pointPair - first: {}  second: {}\n",
                            DU::formatVector(first()), DU::formatVector(second()));
}

//! return unscaled, unrotated version of this pointPair.  caller is responsible for
//! for ensuring this pointPair is in scaled, rotated form before calling this method.
pointPair pointPair::toCanonicalForm(DrawViewPart* dvp) const
{
    pointPair result;
    // invert points?
    result.m_first = CosmeticVertex::makeCanonicalPoint(dvp, m_first);
    result.m_second = CosmeticVertex::makeCanonicalPoint(dvp, m_second);
    result.m_overrideFirst = CosmeticVertex::makeCanonicalPoint(dvp, m_overrideFirst);
    result.m_overrideSecond = CosmeticVertex::makeCanonicalPoint(dvp, m_overrideSecond);
    return result;
}

//! return scaled and rotated version of this pointPair.  caller is responsible for
//! for ensuring this pointPair is in canonical form before calling this method.
pointPair pointPair::toDisplayForm(DrawViewPart* dvp) const
{
    pointPair result;

    // invert points?
    result.m_first = m_first * dvp->getScale();
    result.m_second = m_second * dvp->getScale();
    result.m_overrideFirst = m_overrideFirst * dvp->getScale();
    result.m_overrideSecond = m_overrideSecond * dvp->getScale();
    auto rotationDeg = dvp->Rotation.getValue();
    if (rotationDeg != 0.0) {
        auto rotationRad = Base::toRadians(rotationDeg);
        result.m_first.RotateZ(rotationRad);
        result.m_second.RotateZ(rotationRad);
        result.m_overrideFirst.RotateZ(rotationRad);
        result.m_overrideSecond.RotateZ(rotationRad);
    }
    return result;
}



anglePoints::anglePoints()
{
    m_ends.first(Base::Vector3d(0.0, 0.0, 0.0));
    m_ends.second(Base::Vector3d(0.0, 0.0, 0.0));
    m_vertex = Base::Vector3d(0.0, 0.0, 0.0);
}

anglePoints::anglePoints(const anglePoints& ap) : m_ends(ap.ends()), m_vertex(ap.vertex()) {}

anglePoints& anglePoints::operator=(const anglePoints& ap)
{
    m_ends = ap.ends();
    m_vertex = ap.vertex();
    return *this;
}

// move the points by offset
void anglePoints::move(const Base::Vector3d& offset)
{
    m_ends.move(offset);
    m_vertex = m_vertex - offset;
}

// project the points onto the dvp's paper plane.
void anglePoints::project(const DrawViewPart* dvp)
{
    m_ends.project(dvp);
    m_vertex = projectToView(dvp, m_vertex);
}

// map the points onto the dvp's XY coordinate system
// obsolete. see above.
void anglePoints::mapToPage(const DrawViewPart* dvp)
{
    m_ends.mapToPage(dvp);

    gp_Trsf xOXYZ;
    gp_Ax3 OXYZ;
    xOXYZ.SetTransformation(OXYZ, gp_Ax3(dvp->getRotatedCS()));
    gp_Vec gvVertex = Base::convertTo<gp_Vec>(m_vertex).Transformed(xOXYZ);
    m_vertex = Base::convertTo<Base::Vector3d>(gvVertex);
}

// map the points onto the coordinate system used for drawing where -Y direction is "up"
// obsolete. see above
void anglePoints::invertY()
{
    m_ends.invertY();
    m_vertex = DU::invertY(m_vertex);
}

//! return unscaled, unrotated version of this anglePoints.  caller is responsible for
//! for ensuring this anglePoints is in scaled, rotated form before calling this method.
anglePoints anglePoints::toCanonicalForm(DrawViewPart* dvp) const
{
    anglePoints result;
    result.m_ends = m_ends.toCanonicalForm(dvp);
    result.m_vertex = CosmeticVertex::makeCanonicalPoint(dvp, m_vertex);
    return result;
}

//! return scaled and rotated version of this anglePoints.  caller is responsible for
//! for ensuring this anglePoints is in canonical form before calling this method.
anglePoints anglePoints::toDisplayForm(DrawViewPart* dvp) const
{
    anglePoints result;
    result.m_ends = m_ends.toDisplayForm(dvp);
    result.m_vertex = m_vertex * dvp->getScale();
    auto rotationDeg = dvp->Rotation.getValue();
    if (rotationDeg != 0.0) {
        auto rotationRad = Base::toRadians(rotationDeg);
        result.m_vertex.RotateZ(rotationRad);
    }
    return result;
}
void anglePoints::dump(const std::string& text) const
{
    Base::Console().message("anglePoints - {}\n", text);
    Base::Console().message("anglePoints - ends - first: {}  second: {}\n",
                            DU::formatVector(first()), DU::formatVector(second()));
    Base::Console().message("anglePoints - vertex: {}\n", DU::formatVector(vertex()));
}

arcPoints::arcPoints() :
    isArc(false),
    radius(0.0),
    arcCW(false)
{
    center = Base::Vector3d(0.0, 0.0, 0.0);
    onCurve.first(Base::Vector3d(0.0, 0.0, 0.0));
    onCurve.second(Base::Vector3d(0.0, 0.0, 0.0));
    arcEnds.first(Base::Vector3d(0.0, 0.0, 0.0));
    arcEnds.second(Base::Vector3d(0.0, 0.0, 0.0));
    midArc = Base::Vector3d(0.0, 0.0, 0.0);
}

arcPoints& arcPoints::operator=(const arcPoints& ap)
{
    isArc = ap.isArc;
    radius = ap.radius;
    center = ap.center;
    onCurve = ap.onCurve;
    arcEnds = ap.arcEnds;
    midArc = ap.midArc;
    arcCW = ap.arcCW;
    return *this;
}

void arcPoints::move(const Base::Vector3d& offset)
{
    center = center - offset;
    onCurve.first(onCurve.first() - offset);
    onCurve.second(onCurve.second() - offset);
    arcEnds.first(arcEnds.first() - offset);
    arcEnds.second(arcEnds.second() - offset);
    midArc = midArc - offset;
}

void arcPoints::project(const DrawViewPart* dvp)
{
    radius = radius * dvp->getScale();
    center = projectToView(dvp, center);
    onCurve.first(projectToView(dvp, onCurve.first()));
    onCurve.second(projectToView(dvp, onCurve.second()));
    arcEnds.first(projectToView(dvp, arcEnds.first()));
    arcEnds.second(projectToView(dvp, arcEnds.second()));
    midArc = projectToView(dvp, midArc);
}

// obsolete. see above
void arcPoints::mapToPage(const DrawViewPart* dvp)
{
    gp_Trsf xOXYZ;
    gp_Ax3 OXYZ;
    xOXYZ.SetTransformation(OXYZ, gp_Ax3(dvp->getRotatedCS()));

    gp_Vec gvCenter = Base::convertTo<gp_Vec>(center).Transformed(xOXYZ);
    center = Base::convertTo<Base::Vector3d>(gvCenter);
    gp_Vec gvOnCurve1 = Base::convertTo<gp_Vec>(onCurve.first()).Transformed(xOXYZ);
    onCurve.first(Base::convertTo<Base::Vector3d>(gvOnCurve1));
    gp_Vec gvOnCurve2 = Base::convertTo<gp_Vec>(onCurve.second()).Transformed(xOXYZ);
    onCurve.second(Base::convertTo<Base::Vector3d>(gvOnCurve2));
    gp_Vec gvArcEnds1 = Base::convertTo<gp_Vec>(arcEnds.first()).Transformed(xOXYZ);
    arcEnds.first(Base::convertTo<Base::Vector3d>(gvArcEnds1));
    gp_Vec gvArcEnds2 = Base::convertTo<gp_Vec>(arcEnds.second()).Transformed(xOXYZ);
    arcEnds.second(Base::convertTo<Base::Vector3d>(gvArcEnds2));
    gp_Vec gvMidArc = Base::convertTo<gp_Vec>(midArc).Transformed(xOXYZ);
    midArc = Base::convertTo<Base::Vector3d>(gvMidArc);
}

// obsolete. see above
void arcPoints::invertY()
{
    center = DU::invertY(center);
    onCurve.invertY();
    arcEnds.invertY();
    midArc = DU::invertY(midArc);
}

//! return scaled and rotated version of this arcPoints.  caller is responsible for
//! for ensuring this arcPoints is in canonical form before calling this method.
arcPoints arcPoints::toDisplayForm(DrawViewPart* dvp) const
{
    arcPoints result;
    result.onCurve = onCurve.toDisplayForm(dvp);
    result.arcEnds = arcEnds.toDisplayForm(dvp);
    result.center = center * dvp->getScale();
    result.midArc = midArc * dvp->getScale();
    result.radius = radius * dvp->getScale();
    auto rotationDeg = dvp->Rotation.getValue();
    if (rotationDeg != 0.0) {
        auto rotationRad = Base::toRadians(rotationDeg);
        result.center.RotateZ(rotationRad);
        result.midArc.RotateZ(rotationRad);
    }
    return result;
}

//! return unscaled, unrotated version of this arcPoints.  caller is responsible for
//! for ensuring this arcPoints is in scaled, rotated form before calling this method.
arcPoints arcPoints::toCanonicalForm(DrawViewPart* dvp) const
{
    arcPoints result;
    result.onCurve = onCurve.toCanonicalForm(dvp);
    result.arcEnds = arcEnds.toCanonicalForm(dvp);
    result.center = CosmeticVertex::makeCanonicalPoint(dvp, center);
    result.midArc = CosmeticVertex::makeCanonicalPoint(dvp, midArc);
    result.radius = radius / dvp->getScale();
    return result;
}


void arcPoints::dump(const std::string& text) const
{
    Base::Console().message("arcPoints - {}\n", text);
    Base::Console().message("arcPoints - radius: {:.3f} center: {}\n", radius,
                            DrawUtil::formatVector(center));
    Base::Console().message("arcPoints - isArc: {} arcCW: {}\n", isArc, arcCW);
    Base::Console().message("arcPoints - onCurve: {}  {}\n",
                            DrawUtil::formatVector(onCurve.first()),
                            DrawUtil::formatVector(onCurve.second()));
    Base::Console().message("arcPoints - arcEnds: {}  {}\n",
                            DrawUtil::formatVector(arcEnds.first()),
                            DrawUtil::formatVector(arcEnds.second()));
    Base::Console().message("arcPoints - midArc: {}\n", DrawUtil::formatVector(midArc));
}


areaPoint::areaPoint() :
    area(0.0),
    actualArea(0.0),
    center(Base::Vector3d())
{
}

areaPoint& areaPoint::operator=(const areaPoint& ap)
{
    area = ap.area;
    center = ap.center;
    actualArea = ap.actualArea;
    return *this;
}

void areaPoint::move(const Base::Vector3d& offset)
{
    center = center - offset;
}

void areaPoint::project(const DrawViewPart* dvp)
{
    center = projectToView(dvp, center);
}

void areaPoint::invertY()
{
    center = DU::invertY(center);
}

void areaPoint::dump(const std::string& text) const
{
    Base::Console().message("areaPoint - {}\n", text);
    Base::Console().message("areaPoint - area: {:.3f} center: {}\n", area,
        DrawUtil::formatVector(center));
}
