// SPDX-License-Identifier: LGPL-2.1-or-later

#include <src/App/InitApplication.h>
#include <App/Document.h>
#include <Mod/Measure/App/MeasureLength.h>
#include <Mod/Part/App/PartFeature.h>
#include <Base/Placement.h>
#include <gtest/gtest.h>
#include <numbers>
#include <BRepBuilderAPI_MakeEdge.hxx>
#include <gp_Ax2.hxx>
#include <gp_Circ.hxx>
#include <TopoDS_Edge.hxx>

class MeasureLength: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        document = App::GetApplication().newDocument("MeasureLength");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(document->getName());
    }

    App::Document* document {nullptr};
};

// https://github.com/FreeCAD/FreeCAD/issues/28930
TEST_F(MeasureLength, labelIsAttachedToTheMiddleOfACurvedEdge)
{
    // half circle of radius 10 from (10, 0) to (-10, 0) through (0, 10)
    gp_Circ circle(gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)), 10.0);
    auto arc = document->addObject<Part::Feature>("Arc");
    TopoDS_Edge edge = BRepBuilderAPI_MakeEdge(circle, 0.0, std::numbers::pi).Edge();
    arc->Shape.setValue(edge);

    auto length = document->addObject<Measure::MeasureLength>("Length");
    length->Elements.setValues({arc}, {"Edge1"});
    document->recompute();

    EXPECT_NEAR(length->Length.getValue(), 10.0 * std::numbers::pi, 1e-6);
    Base::Vector3d position = length->getPlacement().getPosition();
    EXPECT_NEAR(position.x, 0.0, 1e-6);
    EXPECT_NEAR(position.y, 10.0, 1e-6);
    EXPECT_NEAR(position.z, 0.0, 1e-6);
}
