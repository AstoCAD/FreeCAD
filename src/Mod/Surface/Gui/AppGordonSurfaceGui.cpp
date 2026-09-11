// SPDX-License-Identifier: LGPL-2.1-or-later
#include "ViewProviderGordonSurface.h"

void CreateSurfaceGordonSurfaceCommands();

void initSurfaceGordonSurfaceGui()
{
    SurfaceGui::ViewProviderGordonSurface::init();
    CreateSurfaceGordonSurfaceCommands();
}
