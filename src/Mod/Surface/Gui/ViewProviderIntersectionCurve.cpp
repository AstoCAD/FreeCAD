// SPDX-License-Identifier: LGPL-2.1-or-later

#include <Gui/BitmapFactory.h>

#include "ViewProviderIntersectionCurve.h"

using namespace SurfaceGui;

PROPERTY_SOURCE(SurfaceGui::ViewProviderIntersectionCurve, PartGui::ViewProviderPartExt)

QIcon ViewProviderIntersectionCurve::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Surface_IntersectionCurve");
}
