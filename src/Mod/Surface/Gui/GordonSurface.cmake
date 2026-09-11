# SPDX-License-Identifier: LGPL-2.1-or-later
qt_add_resources(GordonSurface_QRC_SRCS Resources/GordonSurface.qrc OPTIONS ${FREECAD_RCC_OPTIONS})
target_sources(SurfaceGui PRIVATE
    ${GordonSurface_QRC_SRCS}
    AppGordonSurfaceGui.cpp CommandGordonSurface.cpp
    ViewProviderGordonSurface.cpp ViewProviderGordonSurface.h
)
