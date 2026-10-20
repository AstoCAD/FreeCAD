// SPDX-License-Identifier: LGPL-2.1-or-later

#include <src/App/InitApplication.h>
#include <App/Document.h>
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

// NOLINTEND(readability-magic-numbers,cppcoreguidelines-avoid-magic-numbers)
