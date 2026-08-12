/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *   This file is part of FreeCAD.                                         *
 ***************************************************************************/

#pragma once

#include <QPainterPath>
#include <QPointF>

#include <vector>

#include <Base/Vector3D.h>
#include <Mod/TechDraw/TechDrawGlobal.h>

namespace TechDraw
{
class DrawViewPart;
}

namespace TechDrawGui
{

TechDrawGuiExport QPainterPath periodicBSplinePath(
    const std::vector<QPointF>& interpolationPoints);

TechDrawGuiExport QPainterPath brokenOutSectionPath(
    const TechDraw::DrawViewPart* view,
    const std::vector<Base::Vector3d>& modelPoints);

} // namespace TechDrawGui
