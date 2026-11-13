#include <gtest/gtest.h>
#include <Base/Exception.h>
#include <Base/Matrix.h>
#include <Base/Rotation.h>


// NOLINTBEGIN(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)
TEST(Rotation, TestNonUniformScaleLeft)
{
    Base::Rotation rot;
    rot.setYawPitchRoll(45.0, 0.0, 0.0);

    Base::Matrix4D mat;
    rot.getValue(mat);

    Base::Matrix4D scale;
    scale.scale(1.0, std::sqrt(3.0), 1.0);

    Base::Rotation scaled_rot(scale * mat);

    rot.setYawPitchRoll(60.0, 0.0, 0.0);
    EXPECT_EQ(scaled_rot.isSame(rot, 1.0e-7), true);
    EXPECT_EQ(rot.isSame(scaled_rot, 1.0e-7), true);
}

TEST(Rotation, TestNonUniformScaleRight)
{
    Base::Rotation rot;
    rot.setYawPitchRoll(20.0, 0.0, 0.0);

    Base::Matrix4D mat;
    rot.getValue(mat);

    Base::Matrix4D scale;
    scale.scale(2.0, 3.0, 4.0);

    Base::Rotation scaled_rot(mat * scale);

    EXPECT_EQ(scaled_rot.isSame(rot, 1.0e-7), true);
    EXPECT_EQ(rot.isSame(scaled_rot, 1.0e-7), true);
}

TEST(Rotation, TestUniformScaleGT1)
{
    Base::Rotation rot;
    rot.setYawPitchRoll(20.0, 0.0, 0.0);

    Base::Matrix4D mat;
    rot.getValue(mat);

    Base::Matrix4D scale;
    scale.scale(3.0, 3.0, 3.0);

    Base::Rotation scaled_rot(mat * scale);

    EXPECT_EQ(scaled_rot.isSame(rot, 1.0e-7), true);
    EXPECT_EQ(rot.isSame(scaled_rot, 1.0e-7), true);
}

TEST(Rotation, TestUniformScaleLT1)
{
    Base::Matrix4D mat;
    mat.scale(0.5);

    Base::Rotation scaled_rot(mat);

    EXPECT_EQ(scaled_rot.isSame(scaled_rot, 1.0e-7), true);
}

TEST(Rotation, TestRotationDecompose)
{
    Base::Matrix4D mat;
    mat.setCol(0, Base::Vector3d {1, 0, 0});
    mat.setCol(1, Base::Vector3d {1, 1, 0});
    mat.setCol(2, Base::Vector3d {0, 0, 1});

    // decompose rotation part
    EXPECT_TRUE(Base::Rotation {mat}.isIdentity());
}

TEST(Rotation, TestNearlyParallelAndOppositeVectors)
{
    // Rotations between vectors that differ only by rounding-sized amounts must still map the
    // first vector onto the second one (neither NaN nor a wrong rotation axis).
    for (int a = 1; a <= 5; ++a) {
        for (int b = 1; b <= 5; ++b) {
            for (int c = 1; c <= 5; ++c) {
                for (double delta : {1e-15, 2e-15, 3e-15, 1e-14, 1e-13, 1e-12}) {
                    for (double sign : {1.0, -1.0}) {
                        Base::Vector3d from(a, b, c);
                        Base::Vector3d to(sign * a, sign * b, sign * (c + delta));
                        Base::Rotation rot(from, to);
                        Base::Vector3d result = rot.multVec(from).Normalize();
                        double error = (result - to.Normalize()).Length();
                        EXPECT_LT(error, 1e-7) << "from (" << a << ", " << b << ", " << c
                                               << ") delta " << delta << " sign " << sign;
                    }
                }
            }
        }
    }
}
// NOLINTEND(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)
