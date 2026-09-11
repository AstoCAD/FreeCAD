# SPDX-License-Identifier: LGPL-2.1-or-later
target_sources(Surface PRIVATE
    AppGordonSurface.cpp
    FeatureGordonSurface.cpp FeatureGordonSurface.h
    GordonSurfaceBuilder.cpp GordonSurfaceBuilder.h
)
target_include_directories(Surface SYSTEM PRIVATE ${EIGEN3_INCLUDE_DIR})
