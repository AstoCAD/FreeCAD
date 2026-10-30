// SPDX-License-Identifier: LGPL-2.1-or-later

#include <src/App/InitApplication.h>
#include <App/Document.h>
#include <Base/Exception.h>
#include <Base/Placement.h>
#include <Base/Rotation.h>
#include <Base/Vector3D.h>
#include <Mod/Measure/App/Measurement.h>
#include <Mod/Part/App/PartFeature.h>

#include <BRep_Builder.hxx>
#include <BRepBuilderAPI_MakeEdge.hxx>
#include <BRepBuilderAPI_MakeVertex.hxx>
#include <TopoDS_Compound.hxx>
#include <TopoDS_Edge.hxx>
#include <TopoDS_Vertex.hxx>
#include <gp_Ax2.hxx>
#include <gp_Circ.hxx>
#include <gp_Pnt.hxx>
#include <gtest/gtest.h>

#include <cmath>
#include <initializer_list>

// NOLINTBEGIN(readability-magic-numbers,cppcoreguidelines-avoid-magic-numbers)

class MeasurementPointAngleTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        document = App::GetApplication().newDocument("MeasurementPointAngle");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(document->getName());
    }

    Part::Feature* makeVertices(const char* name, std::initializer_list<gp_Pnt> points) const
    {
        BRep_Builder builder;
        TopoDS_Compound compound;
        builder.MakeCompound(compound);
        for (const auto& point : points) {
            builder.Add(compound, BRepBuilderAPI_MakeVertex(point).Vertex());
        }

        auto feature = document->addObject<Part::Feature>(name);
        feature->Shape.setValue(compound);
        return feature;
    }

    void checkSeparateObjects(
        const gp_Pnt& endpoint,
        double expectedAngle,
        const Base::Vector3d& translation = Base::Vector3d()
    ) const
    {
        auto first = makeVertices("FirstEnd", {gp_Pnt(1.0, 0.0, 0.0)});
        // The unused second vertex is valid and lies along the first ray. Reading
        // Vertex2 from the apex object would incorrectly give zero degrees.
        auto apex = makeVertices("Apex", {gp_Pnt(0.0, 0.0, 0.0), gp_Pnt(1.0, 0.0, 0.0)});
        auto last = makeVertices(
            "SecondEnd",
            {gp_Pnt(9.0, 9.0, 9.0),
             gp_Pnt(endpoint.X() - translation.x,
                    endpoint.Y() - translation.y,
                    endpoint.Z() - translation.z)}
        );
        last->Placement.setValue(Base::Placement(translation, Base::Rotation()));
        document->recompute();

        Measure::Measurement measurement;
        measurement.addReference3D(first, "Vertex1");
        measurement.addReference3D(apex, "Vertex1");
        measurement.addReference3D(last, "Vertex2");

        ASSERT_EQ(measurement.getType(), Measure::MeasureType::Points);
        EXPECT_NEAR(measurement.angle(), expectedAngle, 1e-7);
    }

    App::Document* document {};
};

TEST_F(MeasurementPointAngleTest, ThreeObjectsRightAngle)
{
    checkSeparateObjects(gp_Pnt(0.0, 1.0, 0.0), 90.0);
}

TEST_F(MeasurementPointAngleTest, ThreeObjectsAcuteAngle)
{
    checkSeparateObjects(gp_Pnt(0.5, std::sqrt(3.0) / 2.0, 0.0), 60.0);
}

TEST_F(MeasurementPointAngleTest, ThirdObjectPlacementIsApplied)
{
    checkSeparateObjects(
        gp_Pnt(-0.5, std::sqrt(3.0) / 2.0, 0.0),
        120.0,
        Base::Vector3d(2.0, -3.0, 4.0)
    );
}

TEST_F(MeasurementPointAngleTest, ThreeVerticesInOneObject)
{
    auto feature = makeVertices(
        "AllPoints",
        {gp_Pnt(1.0, 0.0, 0.0), gp_Pnt(0.0, 0.0, 0.0), gp_Pnt(0.0, 1.0, 0.0)}
    );
    document->recompute();

    Measure::Measurement measurement;
    measurement.addReference3D(feature, "Vertex1");
    measurement.addReference3D(feature, "Vertex2");
    measurement.addReference3D(feature, "Vertex3");

    ASSERT_EQ(measurement.getType(), Measure::MeasureType::Points);
    EXPECT_NEAR(measurement.angle(), 90.0, 1e-7);
}

TEST_F(MeasurementPointAngleTest, TwoPerpendicularLines)
{
    auto first = document->addObject<Part::Feature>("FirstLine");
    first->Shape.setValue(BRepBuilderAPI_MakeEdge(gp_Pnt(), gp_Pnt(1.0, 0.0, 0.0)).Edge());
    auto second = document->addObject<Part::Feature>("SecondLine");
    second->Shape.setValue(BRepBuilderAPI_MakeEdge(gp_Pnt(), gp_Pnt(0.0, 1.0, 0.0)).Edge());
    document->recompute();

    Measure::Measurement measurement;
    measurement.addReference3D(first, "Edge1");
    measurement.addReference3D(second, "Edge1");

    ASSERT_EQ(measurement.getType(), Measure::MeasureType::TwoLines);
    EXPECT_NEAR(measurement.angle(), 90.0, 1e-7);
}

// The referenced elements can disappear after the measurement was set up, e.g. when the
// referenced object changes. This used to dereference a null shape and crash.
TEST_F(MeasurementPointAngleTest, MissingElementsThrowInsteadOfCrashing)
{
    auto points = makeVertices(
        "Points",
        {gp_Pnt(1.0, 0.0, 0.0), gp_Pnt(0.0, 0.0, 0.0), gp_Pnt(0.0, 1.0, 0.0)}
    );

    BRep_Builder builder;
    TopoDS_Compound lines;
    builder.MakeCompound(lines);
    builder.Add(lines, BRepBuilderAPI_MakeEdge(gp_Pnt(), gp_Pnt(1.0, 0.0, 0.0)).Edge());
    builder.Add(lines, BRepBuilderAPI_MakeEdge(gp_Pnt(0.0, 1.0, 0.0), gp_Pnt(1.0, 1.0, 0.0)).Edge());
    auto parallel = document->addObject<Part::Feature>("ParallelLines");
    parallel->Shape.setValue(lines);

    TopoDS_Compound circles;
    builder.MakeCompound(circles);
    builder.Add(circles, BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(), 1.0)).Edge());
    builder.Add(
        circles,
        BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0.0, 0.0, 1.0), gp_Dir(1.0, 0.0, 0.0)), 2.0))
            .Edge()
    );
    auto circleFeature = document->addObject<Part::Feature>("Circles");
    circleFeature->Shape.setValue(circles);
    document->recompute();

    Measure::Measurement pointAngle;
    pointAngle.addReference3D(points, "Vertex1");
    pointAngle.addReference3D(points, "Vertex2");
    pointAngle.addReference3D(points, "Vertex3");
    ASSERT_EQ(pointAngle.getType(), Measure::MeasureType::Points);

    Measure::Measurement lineDistance;
    lineDistance.addReference3D(parallel, "Edge1");
    lineDistance.addReference3D(parallel, "Edge2");
    ASSERT_EQ(lineDistance.getType(), Measure::MeasureType::TwoParallelLines);

    Measure::Measurement circleAngle;
    circleAngle.addReference3D(circleFeature, "Edge1");
    circleAngle.addReference3D(circleFeature, "Edge2");
    ASSERT_EQ(circleAngle.getType(), Measure::MeasureType::TwoCircles);

    Measure::Measurement circleRadius;
    circleRadius.addReference3D(circleFeature, "Edge1");
    ASSERT_EQ(circleRadius.getType(), Measure::MeasureType::Circle);

    // Replace every shape by a single vertex, so the referenced elements are gone
    const TopoDS_Vertex lonelyVertex = BRepBuilderAPI_MakeVertex(gp_Pnt(5.0, 5.0, 5.0)).Vertex();
    points->Shape.setValue(lonelyVertex);
    parallel->Shape.setValue(lonelyVertex);
    circleFeature->Shape.setValue(lonelyVertex);
    document->recompute();

    EXPECT_THROW(pointAngle.angle(), Base::ValueError);
    EXPECT_THROW(lineDistance.lineLineDistance(), Base::ValueError);
    EXPECT_THROW(circleAngle.angle(), Base::ValueError);
    EXPECT_THROW(circleAngle.circleCenterDistance(), Base::ValueError);
    EXPECT_THROW(circleRadius.radius(), Base::ValueError);
}

// NOLINTEND(readability-magic-numbers,cppcoreguidelines-avoid-magic-numbers)
