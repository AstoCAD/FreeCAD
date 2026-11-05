// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <Inventor/SoDB.h>
#include <Inventor/nodes/SoCoordinate3.h>
#include <Inventor/nodes/SoCube.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoSwitch.h>

#include <Gui/Render/PassUtilities.h>

using namespace Gui::Render::Detail;

// --- map update policy (shadow map, ambient occlusion map) ------------------------------------

TEST(RenderMapUpdate, rendersWithoutUsableMap)
{
    EXPECT_EQ(decideMapUpdate(false, false, true, true, 0.0), MapUpdate::Render);
    EXPECT_EQ(decideMapUpdate(false, true, true, true, 0.0), MapUpdate::Render);
}

TEST(RenderMapUpdate, keepsAnUnchangedMap)
{
    EXPECT_EQ(decideMapUpdate(true, false, false, false, 100.0), MapUpdate::Keep);
    EXPECT_EQ(decideMapUpdate(true, false, true, true, 0.0), MapUpdate::Keep);
}

TEST(RenderMapUpdate, exportsAlwaysGetAnUpToDateMap)
{
    EXPECT_EQ(decideMapUpdate(true, true, false, true, 0.0), MapUpdate::Render);
    EXPECT_EQ(decideMapUpdate(true, true, false, false, 0.0), MapUpdate::Render);
}

TEST(RenderMapUpdate, screenPostponesWhileNavigatingOrRightAfterARender)
{
    // Orbiting: camera-driven nodes change on every frame, the map waits for the end.
    EXPECT_EQ(decideMapUpdate(true, true, true, true, 10.0), MapUpdate::Postpone);
    // Dragging in a sketch: at most one re-render per interval.
    EXPECT_EQ(decideMapUpdate(true, true, true, false, minimumMapUpdateInterval / 2), MapUpdate::Postpone);
    EXPECT_EQ(decideMapUpdate(true, true, true, false, minimumMapUpdateInterval), MapUpdate::Render);
}

TEST(RenderMapUpdate, postponedFlagIsTakenOnce)
{
    takePostponedMapUpdate();
    EXPECT_FALSE(takePostponedMapUpdate());
    notePostponedMapUpdate();
    EXPECT_TRUE(takePostponedMapUpdate());
    EXPECT_FALSE(takePostponedMapUpdate());
}

// --- scene change tracking ---------------------------------------------------------------------

TEST(RenderSceneChange, bareTouchIsNotARenderingChange)
{
    EXPECT_FALSE(isRenderingChange(false, false));
    EXPECT_TRUE(isRenderingChange(true, false));
    EXPECT_TRUE(isRenderingChange(false, true));
}

class RenderSceneChangeTracker: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        SoDB::init();  // idempotent
    }
};

TEST_F(RenderSceneChangeTracker, countsFieldAndChildChangesButNotTouches)
{
    auto* root = new SoSeparator;
    root->ref();
    auto* visibility = new SoSwitch;
    visibility->whichChild = SO_SWITCH_ALL;
    root->addChild(visibility);
    auto* coordinates = new SoCoordinate3;
    visibility->addChild(coordinates);
    auto* shape = new SoCube;
    visibility->addChild(shape);

    SceneChangeTracker tracker;
    EXPECT_TRUE(tracker.track(root));
    EXPECT_FALSE(tracker.track(root));
    const unsigned start = tracker.changes();

    // Preselection, selection and render cache invalidation only touch nodes.
    shape->touch();
    visibility->touch();
    root->touch();
    EXPECT_EQ(tracker.changes(), start);

    // Geometry, visibility and structure changes count.
    coordinates->point.set1Value(0, SbVec3f(1.0F, 2.0F, 3.0F));
    EXPECT_GT(tracker.changes(), start);
    unsigned last = tracker.changes();
    visibility->whichChild = SO_SWITCH_NONE;
    EXPECT_GT(tracker.changes(), last);
    last = tracker.changes();
    visibility->addChild(new SoCube);
    EXPECT_GT(tracker.changes(), last);
    last = tracker.changes();
    visibility->removeChild(2);
    EXPECT_GT(tracker.changes(), last);

    root->unref();
}

TEST_F(RenderSceneChangeTracker, reportsANewNodeAfterTheTrackedOneDied)
{
    SceneChangeTracker tracker;
    auto* first = new SoSeparator;
    first->ref();
    EXPECT_TRUE(tracker.track(first));
    first->unref();  // deleted: the sensor detaches
    auto* second = new SoSeparator;
    second->ref();
    // Even if the allocator reuses the address, the tracker sees a new node.
    EXPECT_TRUE(tracker.track(second));
    EXPECT_FALSE(tracker.track(second));
    second->unref();
}
