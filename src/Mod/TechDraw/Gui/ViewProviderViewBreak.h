/***************************************************************************
 *   Copyright (c) 2026 FreeCAD contributors                              *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 ***************************************************************************/

#pragma once

#include <Gui/ViewProviderDocumentObject.h>
#include <Gui/ViewProviderSuppressibleExtension.h>
#include <Mod/TechDraw/TechDrawGlobal.h>

namespace TechDrawGui
{

class TechDrawGuiExport ViewProviderViewBreak:
    public Gui::ViewProviderDocumentObject,
    public Gui::ViewProviderSuppressibleExtension
{
    PROPERTY_HEADER_WITH_OVERRIDE(TechDrawGui::ViewProviderViewBreak);

public:
    ViewProviderViewBreak();
    ~ViewProviderViewBreak() override = default;
};

} // namespace TechDrawGui
