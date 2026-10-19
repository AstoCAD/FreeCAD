// SPDX-License-Identifier: LGPL-2.1-or-later

#include <src/App/InitApplication.h>
#include <App/Document.h>
#include <App/Part.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/Link.h>
#include <App/MeasureManager.h>
#include <Mod/Measure/App/MeasurePosition.h>
#include <Mod/Part/App/PartFeature.h>
#include <Base/Placement.h>
#include <Base/Rotation.h>
#include <Base/Vector3D.h>
#include <gtest/gtest.h>
#include <numbers>
#include <BRepBuilderAPI_MakeVertex.hxx>
#include <gp_Pnt.hxx>

class MeasurePosition: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        document = App::GetApplication().newDocument("MeasurePosition");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(document->getName());
    }

    App::Document* getDocument() const
    {
        return document;
    }

    // Create a Part::Feature whose shape is a single vertex at the given local point.
    Part::Feature* makeVertexFeature(const char* name, const gp_Pnt& point) const
    {
        auto feature = document->addObject<Part::Feature>(name);
        feature->Shape.setValue(BRepBuilderAPI_MakeVertex(point).Vertex());
        return feature;
    }

    // Wrap the feature in an App::Part container carrying the given placement. The
    // container's placement is what distinguishes the leaf object's local frame from
    // its global frame, which is the situation that regressed in issue #30365.
    App::Part* makeContainer(
        const char* name,
        const Base::Placement& placement,
        App::DocumentObject* child
    ) const
    {
        auto container = document->addObject<App::Part>(name);
        container->Placement.setValue(placement);
        container->getExtensionByType<App::GeoFeatureGroupExtension>()->addObject(child);
        return container;
    }

    void checkNestedLinkScale(const Base::Vector3d& scale) const
    {
        auto feature = makeVertexFeature("Leaf", gp_Pnt(3.0, 4.0, 5.0));
        auto container = makeContainer("Source", Base::Placement(), feature);
        auto link = document->addObject<App::Link>("Link");
        link->setLink(-1, container);
        link->LinkPlacement.setValue(Base::Placement(
            Base::Vector3d(10.0, 20.0, 30.0),
            Base::Rotation(Base::Vector3d(0.0, 0.0, 1.0), std::numbers::pi / 2.0)
        ));
        link->ScaleVector.setValue(scale);

        auto position = document->addObject<Measure::MeasurePosition>("Position");
        position->Element.setValue(link, {"Leaf.Vertex1"});
        document->recompute();

        const auto value = position->Position.getValue();
        EXPECT_NEAR(value.x, 10.0 - 4.0 * scale.y, 1e-7);
        EXPECT_NEAR(value.y, 20.0 + 3.0 * scale.x, 1e-7);
        EXPECT_NEAR(value.z, 30.0 + 5.0 * scale.z, 1e-7);
    }

private:
    App::Document* document {};
};

// NOLINTBEGIN
TEST_F(MeasurePosition, testVertexNoPlacement)
{
    // Baseline: with an identity placement the measured position is the local point.
    App::Document* doc = getDocument();

    auto feature = makeVertexFeature("Vertex", gp_Pnt(1.0, 2.0, 3.0));
    doc->recompute();

    auto mp = doc->addObject<Measure::MeasurePosition>("Position");
    mp->Element.setValue(feature, {"Vertex1"});
    doc->recompute();

    EXPECT_EQ(mp->Position.getValue(), Base::Vector3d(1.0, 2.0, 3.0));
}

TEST_F(MeasurePosition, testVertexWithLocalPlacement)
{
    // A top-level object's own Placement must be applied. This path already worked
    // before the fix (via Part::ShapeOption::Transform); the test guards against a
    // future regression in the leaf-placement path.
    App::Document* doc = getDocument();

    auto feature = makeVertexFeature("Vertex", gp_Pnt(1.0, 2.0, 3.0));
    feature->Placement.setValue(Base::Placement(Base::Vector3d(10.0, 20.0, 30.0), Base::Rotation()));
    doc->recompute();

    auto mp = doc->addObject<Measure::MeasurePosition>("Position");
    mp->Element.setValue(feature, {"Vertex1"});
    doc->recompute();

    EXPECT_EQ(mp->Position.getValue(), Base::Vector3d(11.0, 22.0, 33.0));
}

TEST_F(MeasurePosition, testVertexInTranslatedContainer)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/30365
    // The vertex feature has an identity placement, but it lives inside a container
    // (App::Part) that is translated. The measured position must reflect the
    // container's placement, i.e. the global placement of the leaf. Before the fix
    // only the leaf's own (identity) placement was applied and the container offset
    // was lost.
    App::Document* doc = getDocument();

    auto feature = makeVertexFeature("Leaf", gp_Pnt(1.0, 2.0, 3.0));
    auto container = makeContainer(
        "Container",
        Base::Placement(Base::Vector3d(10.0, 20.0, 30.0), Base::Rotation()),
        feature
    );
    doc->recompute();

    auto mp = doc->addObject<Measure::MeasurePosition>("Position");
    mp->Element.setValue(container, {"Leaf.Vertex1"});
    doc->recompute();

    EXPECT_EQ(mp->Position.getValue(), Base::Vector3d(11.0, 22.0, 33.0));
}

TEST_F(MeasurePosition, testVertexInRotatedContainer)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/30365
    // The container is rotated 90 degrees about Z, which maps the leaf's local
    // point (1, 0, 0) to the global point (0, 1, 0).
    App::Document* doc = getDocument();

    auto feature = makeVertexFeature("Leaf", gp_Pnt(1.0, 0.0, 0.0));
    Base::Rotation rotation(Base::Vector3d(0.0, 0.0, 1.0), std::numbers::pi / 2.0);
    auto container = makeContainer(
        "Container",
        Base::Placement(Base::Vector3d(0.0, 0.0, 0.0), rotation),
        feature
    );
    doc->recompute();

    auto mp = doc->addObject<Measure::MeasurePosition>("Position");
    mp->Element.setValue(container, {"Leaf.Vertex1"});
    doc->recompute();

    Base::Vector3d position = mp->Position.getValue();
    EXPECT_NEAR(position.x, 0.0, 1e-9);
    EXPECT_NEAR(position.y, 1.0, 1e-9);
    EXPECT_NEAR(position.z, 0.0, 1e-9);
}

TEST_F(MeasurePosition, testVertexContainerAndLocalPlacementCombine)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/30365
    // Both the container placement and the leaf's own placement must be composed.
    // Leaf point (1, 0, 0) + leaf translation (0, 0, 1) = (1, 0, 1), then the
    // container translation (10, 20, 30) gives (11, 20, 31).
    App::Document* doc = getDocument();

    auto feature = makeVertexFeature("Leaf", gp_Pnt(1.0, 0.0, 0.0));
    feature->Placement.setValue(Base::Placement(Base::Vector3d(0.0, 0.0, 1.0), Base::Rotation()));
    auto container = makeContainer(
        "Container",
        Base::Placement(Base::Vector3d(10.0, 20.0, 30.0), Base::Rotation()),
        feature
    );
    doc->recompute();

    auto mp = doc->addObject<Measure::MeasurePosition>("Position");
    mp->Element.setValue(container, {"Leaf.Vertex1"});
    doc->recompute();

    EXPECT_EQ(mp->Position.getValue(), Base::Vector3d(11.0, 20.0, 31.0));
}

// Regression: https://github.com/FreeCAD/FreeCAD/issues/29822.
TEST_F(MeasurePosition, testVertexInTranslatedRotatedUnscaledLink)
{
    checkNestedLinkScale(Base::Vector3d(1.0, 1.0, 1.0));
}

TEST_F(MeasurePosition, testVertexInUniformlyScaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(2.0, 2.0, 2.0));
}

TEST_F(MeasurePosition, testVertexInNegativelyScaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, -1.0, -1.0));
}

TEST_F(MeasurePosition, testVertexInReflectedNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, 1.0, 1.0));
}

TEST_F(MeasurePosition, testVertexInNonuniformlyScaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(2.0, 3.0, 4.0));
}

TEST_F(MeasurePosition, testVertexInNestedLinkWithTwoReflectedAxesXY)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, -1.0, 1.0));
}

TEST_F(MeasurePosition, testVertexInNestedLinkWithTwoReflectedAxesXZ)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, 1.0, -1.0));
}

TEST_F(MeasurePosition, testVertexInNestedLinkWithTwoReflectedAxesYZ)
{
    checkNestedLinkScale(Base::Vector3d(1.0, -1.0, -1.0));
}

TEST_F(MeasurePosition, testReciprocalLinkScalesKeepIntermediateTranslation)
{
    auto feature = makeVertexFeature("Leaf", gp_Pnt(3.0, 4.0, 5.0));
    feature->Placement.setValue(Base::Placement(Base::Vector3d(1.0, 2.0, 3.0), Base::Rotation()));
    auto source = makeContainer("Source", Base::Placement(), feature);
    auto inner = getDocument()->addObject<App::Link>("Inner");
    inner->setLink(-1, source);
    inner->Scale.setValue(0.5);
    inner->LinkPlacement.setValue(Base::Placement(Base::Vector3d(5.0, 6.0, 7.0), Base::Rotation()));
    auto middle = makeContainer("Middle", Base::Placement(), inner);
    auto outer = getDocument()->addObject<App::Link>("Outer");
    outer->setLink(-1, middle);
    outer->Scale.setValue(2.0);
    outer->LinkPlacement.setValue(Base::Placement(
        Base::Vector3d(10.0, 20.0, 30.0),
        Base::Rotation(Base::Vector3d(0.0, 0.0, 1.0), std::numbers::pi / 2.0)
    ));
    auto position = getDocument()->addObject<Measure::MeasurePosition>("Position");
    position->Element.setValue(outer, {"Inner.Leaf.Vertex1"});
    getDocument()->recompute();

    // Leaf (3,4,5) + (1,2,3), inner scale 1/2 + (5,6,7), then outer
    // scale 2, rotation 90 degrees about Z, and translation (10,20,30).
    const auto value = position->Position.getValue();
    EXPECT_NEAR(value.x, -8.0, 1e-7);
    EXPECT_NEAR(value.y, 34.0, 1e-7);
    EXPECT_NEAR(value.z, 52.0, 1e-7);
}

TEST_F(MeasurePosition, testDirectScaledLinkPreservesTransform)
{
    auto feature = makeVertexFeature("Vertex", gp_Pnt(3.0, 4.0, 5.0));
    auto link = getDocument()->addObject<App::Link>("Link");
    link->setLink(-1, feature);
    link->Scale.setValue(2.0);
    link->LinkPlacement.setValue(Base::Placement(
        Base::Vector3d(10.0, 20.0, 30.0),
        Base::Rotation(Base::Vector3d(0.0, 0.0, 1.0), std::numbers::pi / 2.0)
    ));
    auto position = getDocument()->addObject<Measure::MeasurePosition>("Position");
    position->Element.setValue(link, {"Vertex1"});
    getDocument()->recompute();

    const auto value = position->Position.getValue();
    EXPECT_NEAR(value.x, 2.0, 1e-7);
    EXPECT_NEAR(value.y, 26.0, 1e-7);
    EXPECT_NEAR(value.z, 40.0, 1e-7);
}
// NOLINTEND
