// SPDX-License-Identifier: LGPL-2.1-or-later

#include <src/App/InitApplication.h>
#include <App/Document.h>
#include <App/Part.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/Link.h>
#include <App/MeasureManager.h>
#include <Mod/Measure/App/MeasureDistance.h>
#include <Mod/Part/App/PartFeature.h>
#include <Base/Placement.h>
#include <Base/Rotation.h>
#include <Base/Vector3D.h>
#include <gtest/gtest.h>
#include <cmath>
#include <numbers>
#include <BRep_Builder.hxx>
#include <BRepBuilderAPI_MakeEdge.hxx>
#include <BRepBuilderAPI_MakeVertex.hxx>
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepPrimAPI_MakeSphere.hxx>
#include <gp_Circ.hxx>
#include <gp_Trsf.hxx>
#include <gp_Vec.hxx>
#include <TopLoc_Location.hxx>
#include <TopoDS_Compound.hxx>
#include <TopoDS_Edge.hxx>
#include <TopoDS_Wire.hxx>

class MeasureDistance: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        document = App::GetApplication().newDocument("Measure");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(document->getName());
    }

    App::Document* getDocument() const
    {
        return document;
    }

    TopoDS_Edge makeCircle(const gp_Pnt& pnt) const
    {
        gp_Circ circle;
        circle.SetLocation(pnt);
        circle.SetRadius(1.0);
        BRepBuilderAPI_MakeEdge mkEdge(circle);
        return mkEdge.Edge();
    }

    void checkNestedLinkScale(const Base::Vector3d& scale) const
    {
        auto container = document->addObject<App::Part>("Source");
        auto first = document->addObject<Part::Feature>("First");
        first->Shape.setValue(BRepBuilderAPI_MakeVertex(gp_Pnt(0.0, 0.0, 0.0)).Vertex());
        auto second = document->addObject<Part::Feature>("Second");
        second->Shape.setValue(BRepBuilderAPI_MakeVertex(gp_Pnt(3.0, 4.0, 5.0)).Vertex());
        auto group = container->getExtensionByType<App::GeoFeatureGroupExtension>();
        group->addObject(first);
        group->addObject(second);
        auto link = document->addObject<App::Link>("Link");
        link->setLink(-1, container);
        link->LinkPlacement.setValue(Base::Placement(
            Base::Vector3d(10.0, 20.0, 30.0),
            Base::Rotation(Base::Vector3d(0.0, 0.0, 1.0), std::numbers::pi / 2.0)
        ));
        link->ScaleVector.setValue(scale);

        auto distance = document->addObject<Measure::MeasureDistance>("Distance");
        distance->Element1.setValue(link, {"First.Vertex1"});
        distance->Element2.setValue(link, {"Second.Vertex1"});
        document->recompute();

        const double dx = 3.0 * scale.x;
        const double dy = 4.0 * scale.y;
        const double dz = 5.0 * scale.z;
        EXPECT_NEAR(distance->Distance.getValue(), std::sqrt(dx * dx + dy * dy + dz * dz), 1e-7);
        EXPECT_NEAR(distance->DistanceX.getValue(), std::abs(dy), 1e-7);
        EXPECT_NEAR(distance->DistanceY.getValue(), std::abs(dx), 1e-7);
        EXPECT_NEAR(distance->DistanceZ.getValue(), std::abs(dz), 1e-7);
        EXPECT_EQ(distance->Position1.getValue(), Base::Vector3d(10.0, 20.0, 30.0));
        const auto endpoint = distance->Position2.getValue();
        EXPECT_NEAR(endpoint.x, 10.0 - dy, 1e-7);
        EXPECT_NEAR(endpoint.y, 20.0 + dx, 1e-7);
        EXPECT_NEAR(endpoint.z, 30.0 + dz, 1e-7);
    }

private:
    App::Document* document {};
};

// NOLINTBEGIN
TEST_F(MeasureDistance, testCurvedFaceValidSelection)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/29235
    App::Document* doc = getDocument();

    auto sphere = doc->addObject<Part::Feature>("Sphere");
    sphere->Shape.setValue(BRepPrimAPI_MakeSphere(5.0).Solid());

    auto box = doc->addObject<Part::Feature>("Box");
    box->Shape.setValue(BRepPrimAPI_MakeBox(gp_Pnt(20.0, 0.0, 0.0), 10.0, 10.0, 10.0).Solid());

    doc->recompute();

    App::MeasureSelectionItem item1 {App::SubObjectT {sphere, "Face1"}, Base::Vector3d {}};
    App::MeasureSelectionItem item2 {App::SubObjectT {box, "Face1"}, Base::Vector3d {}};

    EXPECT_TRUE(Measure::MeasureDistance::isValidSelection({item1, item2}));
}

TEST_F(MeasureDistance, testCurvedFaceDistance)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/29235
    App::Document* doc = getDocument();

    auto sphere = doc->addObject<Part::Feature>("Sphere");
    sphere->Shape.setValue(BRepPrimAPI_MakeSphere(5.0).Solid());

    auto box = doc->addObject<Part::Feature>("Box");
    box->Shape.setValue(BRepPrimAPI_MakeBox(gp_Pnt(20.0, 0.0, 0.0), 10.0, 10.0, 10.0).Solid());

    auto md = doc->addObject<Measure::MeasureDistance>("Distance");
    md->Element1.setValue(sphere, {"Face1"});
    md->Element2.setValue(box, {"Face1"});

    doc->recompute();

    EXPECT_NEAR(md->Distance.getValue(), 15.0, 1e-6);
}

TEST_F(MeasureDistance, testCircleCircle)
{
    App::Document* doc = getDocument();
    auto p1 = doc->addObject<Part::Feature>("Shape1");
    p1->Shape.setValue(makeCircle(gp_Pnt(0.0, 0.0, 0.0)));
    auto p2 = doc->addObject<Part::Feature>("Shape2");
    p2->Shape.setValue(makeCircle(gp_Pnt(3.0, 4.0, 0.0)));

    auto md = doc->addObject<Measure::MeasureDistance>("Distance");
    md->Element1.setValue(p1, {"Edge1"});
    md->Element2.setValue(p2, {"Edge1"});

    doc->recompute();

    EXPECT_DOUBLE_EQ(md->Distance.getValue(), 5.0);
    EXPECT_DOUBLE_EQ(md->DistanceX.getValue(), 3.0);
    EXPECT_DOUBLE_EQ(md->DistanceY.getValue(), 4.0);
    EXPECT_DOUBLE_EQ(md->DistanceZ.getValue(), 0.0);
    EXPECT_EQ(md->Position1.getValue(), Base::Vector3d(0.0, 0.0, 0.0));
    EXPECT_EQ(md->Position2.getValue(), Base::Vector3d(3.0, 4.0, 0.0));
}

TEST_F(MeasureDistance, testCircleCircleWithPlacement)
{
    // Baseline for issue #30365: distance and the reported positions must respect
    // each object's own top-level Placement. Worked *before* #30423.
    App::Document* doc = getDocument();
    auto p1 = doc->addObject<Part::Feature>("Shape1");
    p1->Shape.setValue(makeCircle(gp_Pnt(0.0, 0.0, 0.0)));
    p1->Placement.setValue(Base::Placement(Base::Vector3d(10.0, 0.0, 0.0), Base::Rotation()));
    auto p2 = doc->addObject<Part::Feature>("Shape2");
    p2->Shape.setValue(makeCircle(gp_Pnt(0.0, 0.0, 0.0)));
    p2->Placement.setValue(Base::Placement(Base::Vector3d(10.0, 0.0, 5.0), Base::Rotation()));

    auto md = doc->addObject<Measure::MeasureDistance>("Distance");
    md->Element1.setValue(p1, {"Edge1"});
    md->Element2.setValue(p2, {"Edge1"});

    doc->recompute();

    EXPECT_DOUBLE_EQ(md->Distance.getValue(), 5.0);
    EXPECT_DOUBLE_EQ(md->DistanceX.getValue(), 0.0);
    EXPECT_DOUBLE_EQ(md->DistanceY.getValue(), 0.0);
    EXPECT_DOUBLE_EQ(md->DistanceZ.getValue(), 5.0);
    EXPECT_EQ(md->Position1.getValue(), Base::Vector3d(10.0, 0.0, 0.0));
    EXPECT_EQ(md->Position2.getValue(), Base::Vector3d(10.0, 0.0, 5.0));
}

TEST_F(MeasureDistance, testTwoBoxesMovedByContainers)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/30365
    // Mirrors the issue report: two bodies built at the origin and then moved. Requires #30423 fix.
    App::Document* doc = getDocument();

    auto box1 = doc->addObject<Part::Feature>("Box1");
    box1->Shape.setValue(BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Solid());
    auto container1 = doc->addObject<App::Part>("Container1");
    container1->getExtensionByType<App::GeoFeatureGroupExtension>()->addObject(box1);

    auto box2 = doc->addObject<Part::Feature>("Box2");
    box2->Shape.setValue(BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Solid());
    auto container2 = doc->addObject<App::Part>("Container2");
    container2->Placement.setValue(Base::Placement(Base::Vector3d(50.0, 0.0, 0.0), Base::Rotation()));
    container2->getExtensionByType<App::GeoFeatureGroupExtension>()->addObject(box2);

    auto md = doc->addObject<Measure::MeasureDistance>("Distance");
    md->Element1.setValue(container1, {"Box1.Vertex1"});
    md->Element2.setValue(container2, {"Box2.Vertex1"});

    doc->recompute();

    EXPECT_DOUBLE_EQ(md->Distance.getValue(), 50.0);
    EXPECT_DOUBLE_EQ(md->DistanceX.getValue(), 50.0);
    EXPECT_DOUBLE_EQ(md->DistanceY.getValue(), 0.0);
    EXPECT_DOUBLE_EQ(md->DistanceZ.getValue(), 0.0);
}

TEST_F(MeasureDistance, testLinkedCompoundKeepsInternalLocation)
{
    // Centre = link (100,0,0) + the edge's own (0,0,20); the other circle sits at (100,0,0).
    App::Document* doc = getDocument();

    TopoDS_Edge edge = makeCircle(gp_Pnt(0.0, 0.0, 0.0));
    gp_Trsf trsf;
    trsf.SetTranslation(gp_Vec(0.0, 0.0, 20.0));
    edge.Move(TopLoc_Location(trsf));
    BRep_Builder builder;
    TopoDS_Compound compound;
    builder.MakeCompound(compound);
    builder.Add(compound, edge);

    auto feature = doc->addObject<Part::Feature>("Shape");
    feature->Shape.setValue(compound);
    auto link = doc->addObject<App::Link>("Link");
    link->setLink(-1, feature);
    link->LinkPlacement.setValue(Base::Placement(Base::Vector3d(100.0, 0.0, 0.0), Base::Rotation()));

    auto circle = doc->addObject<Part::Feature>("Circle");
    circle->Shape.setValue(makeCircle(gp_Pnt(100.0, 0.0, 0.0)));

    auto md = doc->addObject<Measure::MeasureDistance>("Distance");
    md->Element1.setValue(link, {"Edge1"});
    md->Element2.setValue(circle, {"Edge1"});

    doc->recompute();

    EXPECT_DOUBLE_EQ(md->Distance.getValue(), 20.0);
    EXPECT_EQ(md->Position1.getValue(), Base::Vector3d(100.0, 0.0, 20.0));
    EXPECT_EQ(md->Position2.getValue(), Base::Vector3d(100.0, 0.0, 0.0));
}

// Regression: https://github.com/FreeCAD/FreeCAD/issues/29822.
TEST_F(MeasureDistance, testTranslatedRotatedUnscaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(1.0, 1.0, 1.0));
}

TEST_F(MeasureDistance, testUniformlyScaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(2.0, 2.0, 2.0));
}

TEST_F(MeasureDistance, testNegativelyScaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, -1.0, -1.0));
}

TEST_F(MeasureDistance, testReflectedNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, 1.0, 1.0));
}

TEST_F(MeasureDistance, testNonuniformlyScaledNestedLink)
{
    checkNestedLinkScale(Base::Vector3d(2.0, 3.0, 4.0));
}

TEST_F(MeasureDistance, testNestedLinkWithTwoReflectedAxesXY)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, -1.0, 1.0));
}

TEST_F(MeasureDistance, testNestedLinkWithTwoReflectedAxesXZ)
{
    checkNestedLinkScale(Base::Vector3d(-1.0, 1.0, -1.0));
}

TEST_F(MeasureDistance, testNestedLinkWithTwoReflectedAxesYZ)
{
    checkNestedLinkScale(Base::Vector3d(1.0, -1.0, -1.0));
}

TEST_F(MeasureDistance, testReciprocalLinkScalesKeepIntermediateTranslation)
{
    auto doc = getDocument();
    auto source = doc->addObject<App::Part>("Source");
    auto first = doc->addObject<Part::Feature>("First");
    first->Shape.setValue(BRepBuilderAPI_MakeVertex(gp_Pnt(0.0, 0.0, 0.0)).Vertex());
    auto second = doc->addObject<Part::Feature>("Second");
    second->Shape.setValue(BRepBuilderAPI_MakeVertex(gp_Pnt(3.0, 4.0, 5.0)).Vertex());
    const Base::Placement leafPlacement(Base::Vector3d(1.0, 2.0, 3.0), Base::Rotation());
    first->Placement.setValue(leafPlacement);
    second->Placement.setValue(leafPlacement);
    auto group = source->getExtensionByType<App::GeoFeatureGroupExtension>();
    group->addObject(first);
    group->addObject(second);
    auto inner = doc->addObject<App::Link>("Inner");
    inner->setLink(-1, source);
    inner->Scale.setValue(0.5);
    inner->LinkPlacement.setValue(Base::Placement(Base::Vector3d(5.0, 6.0, 7.0), Base::Rotation()));
    auto middle = doc->addObject<App::Part>("Middle");
    middle->getExtensionByType<App::GeoFeatureGroupExtension>()->addObject(inner);
    auto outer = doc->addObject<App::Link>("Outer");
    outer->setLink(-1, middle);
    outer->Scale.setValue(2.0);
    outer->LinkPlacement.setValue(Base::Placement(
        Base::Vector3d(10.0, 20.0, 30.0),
        Base::Rotation(Base::Vector3d(0.0, 0.0, 1.0), std::numbers::pi / 2.0)
    ));
    auto distance = doc->addObject<Measure::MeasureDistance>("Distance");
    distance->Element1.setValue(outer, {"Inner.First.Vertex1"});
    distance->Element2.setValue(outer, {"Inner.Second.Vertex1"});
    doc->recompute();

    EXPECT_NEAR(distance->Distance.getValue(), std::sqrt(50.0), 1e-7);
    EXPECT_NEAR(distance->DistanceX.getValue(), 4.0, 1e-7);
    EXPECT_NEAR(distance->DistanceY.getValue(), 3.0, 1e-7);
    EXPECT_NEAR(distance->DistanceZ.getValue(), 5.0, 1e-7);
    const auto firstPosition = distance->Position1.getValue();
    EXPECT_NEAR(firstPosition.x, -4.0, 1e-7);
    EXPECT_NEAR(firstPosition.y, 31.0, 1e-7);
    EXPECT_NEAR(firstPosition.z, 47.0, 1e-7);
    const auto secondPosition = distance->Position2.getValue();
    EXPECT_NEAR(secondPosition.x, -8.0, 1e-7);
    EXPECT_NEAR(secondPosition.y, 34.0, 1e-7);
    EXPECT_NEAR(secondPosition.z, 52.0, 1e-7);
}
// NOLINTEND
