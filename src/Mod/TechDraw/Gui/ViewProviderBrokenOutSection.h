/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *   This file is part of FreeCAD.                                         *
 ***************************************************************************/

#pragma once

#include <Gui/ViewProviderDocumentObject.h>
#include <Gui/ViewProviderSuppressibleExtension.h>
#include <Mod/TechDraw/TechDrawGlobal.h>

namespace TechDrawGui
{
class TechDrawGuiExport ViewProviderBrokenOutSection:
    public Gui::ViewProviderDocumentObject,
    public Gui::ViewProviderSuppressibleExtension
{
    PROPERTY_HEADER_WITH_OVERRIDE(TechDrawGui::ViewProviderBrokenOutSection);

public:
    ViewProviderBrokenOutSection();
    ~ViewProviderBrokenOutSection() override = default;

    bool setEdit(int mode) override;
    bool doubleClicked() override;
    Gui::MDIView* getMDIView() const override;
    const char* getTransactionText() const override { return nullptr; }
};
} // namespace TechDrawGui
