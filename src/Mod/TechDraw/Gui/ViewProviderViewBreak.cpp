/***************************************************************************
 *   Copyright (c) 2026 FreeCAD contributors                              *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 ***************************************************************************/

#include "ViewProviderViewBreak.h"

using namespace TechDrawGui;

PROPERTY_SOURCE(TechDrawGui::ViewProviderViewBreak, Gui::ViewProviderDocumentObject)

ViewProviderViewBreak::ViewProviderViewBreak()
{
    sPixmap = "actions/TechDraw_BrokenView";
    Gui::ViewProviderSuppressibleExtension::initExtension(this);
}
