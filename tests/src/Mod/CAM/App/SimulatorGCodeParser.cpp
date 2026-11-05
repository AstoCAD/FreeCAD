// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <vector>

#include <Mod/CAM/PathSimulator/AppGL/GCodeParser.h>

using CAMSimulator::GCodeParser;
using CAMSimulator::MillMotion;

// NOLINTBEGIN(cppcoreguidelines-*,readability-*)
namespace
{

struct Move
{
    float x, y, z;
    bool rapid;
};

void expectMoves(const std::vector<MillMotion>& ops, const std::vector<Move>& expected)
{
    ASSERT_EQ(ops.size(), expected.size());
    for (size_t i = 0; i < ops.size(); i++) {
        SCOPED_TRACE(i);
        EXPECT_FLOAT_EQ(ops[i].x, expected[i].x);
        EXPECT_FLOAT_EQ(ops[i].y, expected[i].y);
        EXPECT_FLOAT_EQ(ops[i].z, expected[i].z);
        EXPECT_EQ(ops[i].rapid, expected[i].rapid);
    }
}

}  // namespace

// G98 goes down to R before feeding, and comes back to the start height
// https://github.com/FreeCAD/FreeCAD/pull/34025
TEST(SimulatorGCodeParser, drillCycleG98UsesRAndReturnsToStart)
{
    GCodeParser parser;
    parser.AddLine("G0 X0 Y0 Z10");
    parser.AddLine("G98");
    parser.AddLine("G81 X5 Y0 Z-2 R3");

    expectMoves(
        parser.Operations,
        {
            {0, 0, 10, true},
            {5, 0, 10, true},
            {5, 0, 3, true},
            {5, 0, -2, false},
            {5, 0, 10, true},
        }
    );
}

// G99 retracts to R only, so the next hole is reached at the R plane
TEST(SimulatorGCodeParser, drillCycleG99RetractsToR)
{
    GCodeParser parser;
    parser.AddLine("G0 X0 Y0 Z10");
    parser.AddLine("G99");
    parser.AddLine("G81 X5 Y0 Z-2 R3");
    parser.AddLine("G81 X10 Y0 Z-2 R3");

    expectMoves(
        parser.Operations,
        {
            {0, 0, 10, true},
            {5, 0, 10, true},
            {5, 0, 3, true},
            {5, 0, -2, false},
            {5, 0, 3, true},
            {10, 0, 3, true},
            {10, 0, -2, false},
            {10, 0, 3, true},
        }
    );
}
// NOLINTEND(cppcoreguidelines-*,readability-*)
