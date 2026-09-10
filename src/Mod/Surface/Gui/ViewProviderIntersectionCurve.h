// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Mod/Part/Gui/ViewProviderExt.h>

namespace SurfaceGui
{
class ViewProviderIntersectionCurve: public PartGui::ViewProviderPartExt
{
    PROPERTY_HEADER_WITH_OVERRIDE(SurfaceGui::ViewProviderIntersectionCurve);

public:
    QIcon getIcon() const override;
};
}  // namespace SurfaceGui
