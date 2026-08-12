/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *   This file is part of FreeCAD.                                         *
 ***************************************************************************/

#include "BrokenOutSectionUtils.h"

#include <GeomAPI_Interpolate.hxx>
#include <GeomConvert_BSplineCurveToBezierCurve.hxx>
#include <Geom_BezierCurve.hxx>
#include <Precision.hxx>
#include <Standard_Failure.hxx>
#include <TColgp_HArray1OfPnt.hxx>
#include <gp_Pnt.hxx>

#include <Mod/TechDraw/App/DrawViewPart.h>

#include "Rez.h"

using namespace TechDrawGui;

QPainterPath TechDrawGui::periodicBSplinePath(
    const std::vector<QPointF>& interpolationPoints)
{
    QPainterPath path;
    if (interpolationPoints.size() < 3) {
        if (!interpolationPoints.empty()) {
            path.moveTo(interpolationPoints.front());
            for (size_t i = 1; i < interpolationPoints.size(); ++i) {
                path.lineTo(interpolationPoints[i]);
            }
        }
        return path;
    }

    Handle(TColgp_HArray1OfPnt) points = new TColgp_HArray1OfPnt(
        1, static_cast<Standard_Integer>(interpolationPoints.size()));
    for (size_t i = 0; i < interpolationPoints.size(); ++i) {
        points->SetValue(static_cast<Standard_Integer>(i + 1),
                         gp_Pnt(interpolationPoints[i].x(),
                                interpolationPoints[i].y(), 0.0));
    }

    GeomAPI_Interpolate interpolate(points, true, Precision::Confusion());
    try {
        interpolate.Perform();
    }
    catch (const Standard_Failure&) {
        return path;
    }
    if (!interpolate.IsDone()) {
        return path;
    }

    GeomConvert_BSplineCurveToBezierCurve converter(interpolate.Curve());
    for (Standard_Integer arcIndex = 1;
         arcIndex <= converter.NbArcs(); ++arcIndex) {
        const Handle(Geom_BezierCurve) arc = converter.Arc(arcIndex);
        const auto point = [&arc](Standard_Integer index) {
            const gp_Pnt pole = arc->Pole(index);
            return QPointF(pole.X(), pole.Y());
        };
        if (arcIndex == 1) {
            path.moveTo(point(1));
        }
        if (arc->Degree() == 1) {
            path.lineTo(point(2));
        }
        else if (arc->Degree() == 2) {
            path.quadTo(point(2), point(3));
        }
        else if (arc->Degree() == 3) {
            path.cubicTo(point(2), point(3), point(4));
        }
        else {
            constexpr int samples = 24;
            for (int sample = 1; sample <= samples; ++sample) {
                const double parameter = arc->FirstParameter()
                    + (arc->LastParameter() - arc->FirstParameter())
                        * static_cast<double>(sample) / samples;
                const gp_Pnt value = arc->Value(parameter);
                path.lineTo(value.X(), value.Y());
            }
        }
    }
    path.closeSubpath();
    return path;
}

QPainterPath TechDrawGui::brokenOutSectionPath(
    const TechDraw::DrawViewPart* view,
    const std::vector<Base::Vector3d>& modelPoints)
{
    std::vector<QPointF> displayedPoints;
    if (!view) {
        return {};
    }
    displayedPoints.reserve(modelPoints.size());
    for (const Base::Vector3d& point : modelPoints) {
        const Base::Vector3d displayed = view->mapPointToBrokenView(point);
        displayedPoints.emplace_back(
            Rez::guiX(displayed.x), -Rez::guiX(displayed.y));
    }
    return periodicBSplinePath(displayedPoints);
}
