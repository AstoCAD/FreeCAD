// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once
#include <Mod/Part/Gui/ViewProviderSpline.h>

namespace SurfaceGui
{
class ViewProviderGordonSurface: public PartGui::ViewProviderSpline
{
    PROPERTY_HEADER_WITH_OVERRIDE(SurfaceGui::ViewProviderGordonSurface);

public:
    QIcon getIcon() const override;
    bool doubleClicked() override;

protected:
    bool setEdit(int) override;
    void unsetEdit(int) override;
};
}  // namespace SurfaceGui
