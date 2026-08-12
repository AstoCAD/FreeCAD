/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, version 2.1 or later.      *
 ***************************************************************************/

#include "DrawViewBrokenOutSection.h"

#include "DrawViewPart.h"

using namespace TechDraw;

PROPERTY_SOURCE_WITH_EXTENSIONS(TechDraw::DrawViewBrokenOutSection, App::DocumentObject)

DrawViewBrokenOutSection::DrawViewBrokenOutSection()
{
    static constexpr auto group = "Broken-out section";

    App::SuppressibleExtension::initExtension(this);
    ADD_PROPERTY_TYPE(Outline, (Base::Vector3d()), group, App::Prop_None,
                      "Control points of the closed periodic B-spline outline.");
    ADD_PROPERTY_TYPE(Depth, (10.0), group, App::Prop_None,
                      "Cut depth measured from the front of the viewed shape.");
}

void DrawViewBrokenOutSection::onChanged(const App::Property* property)
{
    App::DocumentObject::onChanged(property);
    if (isRestoring()
        || (property != &Outline && property != &Depth && property != &Suppressed)) {
        return;
    }

    for (auto* parent : getInList()) {
        if (parent && parent->isDerivedFrom<DrawViewPart>()) {
            parent->touch();
            if (property == &Suppressed) {
                parent->recomputeFeature();
                static_cast<DrawViewPart*>(parent)->requestPaint();
            }
        }
    }
}
