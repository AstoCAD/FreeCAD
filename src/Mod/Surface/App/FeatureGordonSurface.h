// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include <App/PropertyLinks.h>
#include <Mod/Part/App/FeaturePartSpline.h>
#include <Mod/Surface/SurfaceGlobal.h>

namespace Surface
{
class SurfaceExport GordonSurface: public Part::Spline
{
    PROPERTY_HEADER_WITH_OVERRIDE(Surface::GordonSurface);

public:
    GordonSurface();
    App::PropertyLinkSubList Profiles;
    App::PropertyLinkSubList Guides;
    App::PropertyFloatConstraint Tolerance;
    App::PropertyIntegerConstraint MaxSamples;
    App::PropertyBool FlipNormal;
    App::PropertyFloat ApproximationError;

    short mustExecute() const override;
    App::DocumentObjectExecReturn* execute() override;
    const char* getViewProviderName() const override
    {
        return "SurfaceGui::ViewProviderGordonSurface";
    }
};
}  // namespace Surface
