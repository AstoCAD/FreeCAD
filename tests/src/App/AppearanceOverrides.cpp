// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include "App/Material.h"

using App::AppearanceOverrides;
using App::Material;
using Names = std::vector<std::string>;
using Looks = std::vector<Material>;

namespace
{

Material look(float red, float green, float blue, const char* uuid = "")
{
    Material material;
    material.diffuseColor = Base::Color(red, green, blue);
    material.uuid = uuid;
    return material;
}

const Material aluminium = look(0.7F, 0.7F, 0.7F, "aluminium-card");  // NOLINT
const Material brass = look(0.8F, 0.6F, 0.2F, "brass-card");          // NOLINT
const Material red = look(1.0F, 0.0F, 0.0F);                           // NOLINT
const Material blue = look(0.0F, 0.0F, 1.0F);                          // NOLINT

}  // namespace

TEST(AppearanceOverrides, names)
{
    EXPECT_EQ(AppearanceOverrides::faceName(0), "Face1");
    EXPECT_EQ(AppearanceOverrides::faceIndex("Face1"), 0);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Face12"), 11);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Face"), -1);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Face0"), -1);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Face01"), -1);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Face1a"), -1);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Edge1"), -1);
    EXPECT_EQ(AppearanceOverrides::faceIndex("Object"), -1);
}

TEST(AppearanceOverrides, sameLookIgnoresTheCard)
{
    Material copy = aluminium;
    copy.uuid = "another-card";
    EXPECT_TRUE(AppearanceOverrides::sameLook(aluminium, copy));

    // The transparency is no part of the look, the colours are
    Material transparent = aluminium;
    transparent.transparency = 0.5F;  // NOLINT
    EXPECT_TRUE(AppearanceOverrides::sameLook(aluminium, transparent));
    Material shiny = aluminium;
    shiny.shininess = 0.1F;  // NOLINT
    EXPECT_FALSE(AppearanceOverrides::sameLook(aluminium, shiny));
}

TEST(AppearanceOverrides, materialWithoutAppearanceHasNoLook)
{
    EXPECT_FALSE(AppearanceOverrides::hasLook(Material()));
    EXPECT_TRUE(AppearanceOverrides::hasLook(aluminium));
}

TEST(AppearanceOverrides, objectAppearanceIsAnOverride)
{
    auto names = AppearanceOverrides::afterChange({}, {aluminium}, {red}, aluminium);
    EXPECT_EQ(names, Names {"Object"});
}

TEST(AppearanceOverrides, materialLookIsNoOverride)
{
    auto names = AppearanceOverrides::afterChange({"Object"}, {red}, {aluminium}, aluminium);
    EXPECT_TRUE(names.empty());
}

TEST(AppearanceOverrides, objectAppearanceReplacesFaceOverrides)
{
    auto names = AppearanceOverrides::afterChange(
        {"Face2", "Feature:Pad"},
        {aluminium, red, aluminium},
        {blue},
        aluminium
    );
    // Names of a kind this version does not handle are kept
    EXPECT_EQ(names, (Names {"Object", "Feature:Pad"}));
}

TEST(AppearanceOverrides, paintedFacesAreOverrides)
{
    // The whole object follows the material, then face 2 is painted
    auto names
        = AppearanceOverrides::afterChange({}, {aluminium}, {aluminium, red, aluminium}, aluminium);
    EXPECT_EQ(names, Names {"Face2"});

    // Then face 3 too: face 2 keeps its override
    names = AppearanceOverrides::afterChange(
        names,
        {aluminium, red, aluminium},
        {aluminium, red, blue},
        aluminium
    );
    EXPECT_EQ(names, (Names {"Face2", "Face3"}));
}

TEST(AppearanceOverrides, unchangedFacesKeepTheObjectOverride)
{
    auto names = AppearanceOverrides::afterChange({"Object"}, {red}, {red, blue, red}, aluminium);
    EXPECT_EQ(names, (Names {"Object", "Face2"}));
}

TEST(AppearanceOverrides, removedFacesLoseTheirOverride)
{
    auto names = AppearanceOverrides::afterChange(
        {"Face2", "Face5"},
        {aluminium, red, aluminium, aluminium, blue},
        {aluminium, red, aluminium},
        aluminium
    );
    EXPECT_EQ(names, Names {"Face2"});
}

TEST(AppearanceOverrides, materialChangesTheLookWithoutOverride)
{
    Looks result;
    EXPECT_TRUE(AppearanceOverrides::followMaterial({}, {aluminium}, brass, result));
    ASSERT_EQ(result.size(), 1U);
    EXPECT_EQ(result[0].uuid, brass.uuid);
    EXPECT_TRUE(AppearanceOverrides::sameLook(result[0], brass));
}

TEST(AppearanceOverrides, materialKeepsTheObjectOverride)
{
    Looks result;
    EXPECT_FALSE(AppearanceOverrides::followMaterial({"Object"}, {red}, brass, result));
    EXPECT_EQ(result, Looks {red});
}

TEST(AppearanceOverrides, materialKeepsFaceOverrides)
{
    Looks result;
    EXPECT_TRUE(
        AppearanceOverrides::followMaterial({"Face2"}, {aluminium, red, aluminium}, brass, result)
    );
    ASSERT_EQ(result.size(), 3U);
    EXPECT_TRUE(AppearanceOverrides::sameLook(result[0], brass));
    EXPECT_TRUE(AppearanceOverrides::sameLook(result[1], red));
    EXPECT_TRUE(AppearanceOverrides::sameLook(result[2], brass));
}

TEST(AppearanceOverrides, materialWithoutAppearanceKeepsTheLook)
{
    Looks result;
    EXPECT_FALSE(AppearanceOverrides::followMaterial({}, {aluminium}, Material(), result));
    EXPECT_EQ(result, Looks {aluminium});
}

TEST(AppearanceOverrides, sameMaterialChangesNothing)
{
    Looks result;
    EXPECT_FALSE(AppearanceOverrides::followMaterial({}, {aluminium}, aluminium, result));
}

namespace
{
Material seeThrough(const Material& look, float transparency)
{
    Material result = look;
    result.transparency = transparency;
    return result;
}
}  // namespace

TEST(AppearanceOverrides, transparencyIsNoOverride)
{
    // Of the whole object
    auto names = AppearanceOverrides::afterChange(
        {},
        {aluminium},
        {seeThrough(aluminium, 0.6F)},  // NOLINT
        aluminium
    );
    EXPECT_TRUE(names.empty());

    // Of a face
    names = AppearanceOverrides::afterChange(
        {},
        {aluminium},
        {aluminium, seeThrough(aluminium, 0.6F), aluminium},  // NOLINT
        aluminium
    );
    EXPECT_TRUE(names.empty());

    // A face override stays one when its transparency changes
    names = AppearanceOverrides::afterChange(
        {"Face2"},
        {aluminium, red, aluminium},
        {aluminium, seeThrough(red, 0.6F), aluminium},  // NOLINT
        aluminium
    );
    EXPECT_EQ(names, Names {"Face2"});
}

TEST(AppearanceOverrides, transparencyKeepsALookThatDiffersFromTheMaterial)
{
    // A material without appearance (Air) kept the previous look: it still follows the material
    auto names = AppearanceOverrides::afterChange(
        {},
        {aluminium},
        {seeThrough(aluminium, 0.6F)},  // NOLINT
        Material()
    );
    EXPECT_TRUE(names.empty());

    // An old file whose default look was guessed to follow the material
    Material defaultLook = look(0.8F, 0.8F, 0.8F);  // NOLINT
    names = AppearanceOverrides::afterChange(
        {},
        {defaultLook},
        {seeThrough(defaultLook, 0.6F)},  // NOLINT
        brass
    );
    EXPECT_TRUE(names.empty());

    // An object override stays one
    names = AppearanceOverrides::afterChange(
        {"Object"},
        {red},
        {seeThrough(red, 0.6F)},  // NOLINT
        brass
    );
    EXPECT_EQ(names, Names {"Object"});
}

TEST(AppearanceOverrides, materialKeepsTheTransparency)
{
    Looks result;
    EXPECT_TRUE(
        AppearanceOverrides::followMaterial({}, {seeThrough(aluminium, 0.6F)}, brass, result)  // NOLINT
    );
    ASSERT_EQ(result.size(), 1U);
    EXPECT_TRUE(AppearanceOverrides::sameLook(result[0], brass));
    EXPECT_FLOAT_EQ(result[0].transparency, 0.6F);  // NOLINT

    // Per face, the faces keep their own transparency
    EXPECT_TRUE(AppearanceOverrides::followMaterial(
        {},
        {aluminium, seeThrough(aluminium, 0.6F)},  // NOLINT
        brass,
        result
    ));
    ASSERT_EQ(result.size(), 2U);
    EXPECT_FLOAT_EQ(result[0].transparency, 0.0F);
    EXPECT_FLOAT_EQ(result[1].transparency, 0.6F);  // NOLINT

    // Only the transparency differs from the material: nothing to do
    EXPECT_FALSE(
        AppearanceOverrides::followMaterial({}, {seeThrough(brass, 0.6F)}, brass, result)  // NOLINT
    );
}

TEST(AppearanceOverrides, resetKeepsTheTransparency)
{
    Names names {"Object"};
    Looks appearance {seeThrough(red, 0.6F)};  // NOLINT
    AppearanceOverrides::reset(names, appearance, brass);
    EXPECT_TRUE(names.empty());
    ASSERT_EQ(appearance.size(), 1U);
    EXPECT_TRUE(AppearanceOverrides::sameLook(appearance[0], brass));
    EXPECT_FLOAT_EQ(appearance[0].transparency, 0.6F);  // NOLINT
}

TEST(AppearanceOverrides, resetObject)
{
    Names names {"Object", "Face2"};
    Looks appearance {red, blue, red};
    AppearanceOverrides::reset(names, appearance, brass);
    EXPECT_TRUE(names.empty());
    ASSERT_EQ(appearance.size(), 1U);
    EXPECT_TRUE(AppearanceOverrides::sameLook(appearance[0], brass));
}

TEST(AppearanceOverrides, resetFaceToMaterial)
{
    Names names {"Face2", "Face3"};
    Looks appearance {aluminium, red, blue};
    AppearanceOverrides::reset(names, appearance, aluminium, {1});
    EXPECT_EQ(names, Names {"Face3"});
    ASSERT_EQ(appearance.size(), 3U);
    EXPECT_TRUE(AppearanceOverrides::sameLook(appearance[1], aluminium));
    EXPECT_TRUE(AppearanceOverrides::sameLook(appearance[2], blue));

    // Without any face override left there is one look again
    AppearanceOverrides::reset(names, appearance, aluminium, {2});
    EXPECT_TRUE(names.empty());
    EXPECT_EQ(appearance.size(), 1U);
}

TEST(AppearanceOverrides, resetFaceToObjectOverride)
{
    Names names {"Object", "Face2"};
    Looks appearance {red, blue, red};
    AppearanceOverrides::reset(names, appearance, aluminium, {1});
    EXPECT_EQ(names, Names {"Object"});
    ASSERT_EQ(appearance.size(), 1U);
    EXPECT_TRUE(AppearanceOverrides::sameLook(appearance[0], red));
}

TEST(AppearanceOverrides, guessOldFiles)
{
    Material defaultLook = look(0.8F, 0.8F, 0.8F);  // NOLINT
    // The material look or a default look follows the material
    EXPECT_TRUE(AppearanceOverrides::guess({aluminium}, aluminium, defaultLook).empty());
    EXPECT_TRUE(AppearanceOverrides::guess({defaultLook}, aluminium, defaultLook).empty());
    EXPECT_TRUE(AppearanceOverrides::guess({Material()}, aluminium, defaultLook).empty());
    // Anything else is an override
    EXPECT_EQ(AppearanceOverrides::guess({red}, aluminium, defaultLook), Names {"Object"});
    EXPECT_EQ(
        AppearanceOverrides::guess({aluminium, red, defaultLook}, aluminium, defaultLook),
        Names {"Face2"}
    );
}
