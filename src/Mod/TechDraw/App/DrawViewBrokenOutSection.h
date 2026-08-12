/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, version 2.1 or later.      *
 ***************************************************************************/

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyGeo.h>
#include <App/PropertyUnits.h>
#include <App/SuppressibleExtension.h>
#include <Mod/TechDraw/TechDrawGlobal.h>

namespace TechDraw
{

class TechDrawExport DrawViewBrokenOutSection: public App::DocumentObject,
                                                public App::SuppressibleExtension
{
    PROPERTY_HEADER_WITH_EXTENSIONS(TechDraw::DrawViewBrokenOutSection);

public:
    DrawViewBrokenOutSection();
    ~DrawViewBrokenOutSection() override = default;

    App::PropertyVectorList Outline;
    App::PropertyLength Depth;

    void onChanged(const App::Property* property) override;

    const char* getViewProviderName() const override
    {
        return "TechDrawGui::ViewProviderBrokenOutSection";
    }
};

} // namespace TechDraw
