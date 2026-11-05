// SPDX-License-Identifier: LGPL-2.1-or-later

// Copy/Paste rules of https://github.com/FreeCAD/FreeCAD/issues/9251 with plain groups.

#include "gtest/gtest.h"

#include <src/App/InitApplication.h>

#include <App/Application.h>
#include <App/CopyPasteRules.h>
#include <App/Document.h>
#include <App/DocumentObjectGroup.h>
#include <App/FeatureTest.h>
#include <App/Origin.h>
#include <App/Part.h>

using App::CopyPasteRules;

class CopyPasteRulesTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _docName = App::GetApplication().getUniqueDocumentName("test");
        _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
        _group = _doc->addObject<App::DocumentObjectGroup>("Group");
        _child = _doc->addObject<App::FeatureTest>("Child");
        _group->addObject(_child);
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_docName.c_str());
    }

    // NOLINTBEGIN(cppcoreguidelines-non-private-member-variables-in-classes)
    std::string _docName;
    App::Document* _doc {};
    App::DocumentObjectGroup* _group {};
    App::FeatureTest* _child {};
    // NOLINTEND(cppcoreguidelines-non-private-member-variables-in-classes)
};

TEST_F(CopyPasteRulesTest, groupIsCopiedWithItsChildrenWithoutAsking)
{
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({_group}));
}

TEST_F(CopyPasteRulesTest, emptySelectionAsks)
{
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({}));
}

TEST_F(CopyPasteRulesTest, linkOutsideTheGroupAsks)
{
    auto outside = _doc->addObject<App::FeatureTest>("Outside");
    _child->Link.setValue(outside);
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({_group}));
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({_child}));
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({_group, outside}));
}

TEST_F(CopyPasteRulesTest, parentGroupIsNotACopyDependency)
{
    auto deps = App::Document::getDependencyList({_child});
    ASSERT_EQ(deps.size(), 1u);
    EXPECT_EQ(deps.front(), _child);
}

TEST_F(CopyPasteRulesTest, originPlaneIsExplained)
{
    auto part = _doc->addObject<App::Part>("Part");
    _child->LinkSub.setValue(part->getOrigin()->getXY());
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({_child}));
}

TEST_F(CopyPasteRulesTest, rootObjectsExcludeOwnedObjects)
{
    auto roots = CopyPasteRules::getRootObjects({_child, _group});
    ASSERT_EQ(roots.size(), 1u);
    EXPECT_EQ(roots.front(), _group);
}

TEST_F(CopyPasteRulesTest, pasteContainers)
{
    auto part = _doc->addObject<App::Part>("Part");
    EXPECT_TRUE(CopyPasteRules::isPasteContainer(_group));
    EXPECT_TRUE(CopyPasteRules::isPasteContainer(part));
    EXPECT_FALSE(CopyPasteRules::isPasteContainer(_child));
    EXPECT_FALSE(CopyPasteRules::isPasteContainer(part->getOrigin()));
    EXPECT_FALSE(CopyPasteRules::isPasteContainer(nullptr));
    EXPECT_EQ(CopyPasteRules::getParentContainer(_child), _group);
    EXPECT_EQ(CopyPasteRules::getParentContainer(part->getOrigin()->getXY()), part);
}

TEST_F(CopyPasteRulesTest, pastedNextToSelectedChildGoesIntoItsGroup)
{
    auto other = _doc->addObject<App::FeatureTest>("Other");
    auto pasted = _doc->copyObject({other}, false, true);
    ASSERT_EQ(pasted.size(), 1u);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _child), _group);
    EXPECT_TRUE(_group->hasObject(pasted.front()));
}

TEST_F(CopyPasteRulesTest, pastedObjectsAreInsertedAfterSelectedChild)
{
    auto last = _doc->addObject<App::FeatureTest>("Last");
    _group->addObject(last);
    auto a = _doc->addObject<App::FeatureTest>("A");
    auto b = _doc->addObject<App::FeatureTest>("B");
    auto pasted = _doc->copyObject({a, b}, false, true);
    ASSERT_EQ(pasted.size(), 2u);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _child), _group);
    const std::vector<App::DocumentObject*> expected {_child, pasted[0], pasted[1], last};
    EXPECT_EQ(_group->Group.getValues(), expected);
}

TEST_F(CopyPasteRulesTest, pastedOnSelectedGroupIsAppended)
{
    auto last = _doc->addObject<App::FeatureTest>("Last");
    _group->addObject(last);
    auto other = _doc->addObject<App::FeatureTest>("Other");
    auto pasted = _doc->copyObject({other}, false, true);
    ASSERT_EQ(pasted.size(), 1u);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _group), _group);
    const std::vector<App::DocumentObject*> expected {_child, last, pasted[0]};
    EXPECT_EQ(_group->Group.getValues(), expected);
}

TEST_F(CopyPasteRulesTest, pastedOnRootObjectStaysAtRoot)
{
    auto other = _doc->addObject<App::FeatureTest>("Other");
    auto pasted = _doc->copyObject({_child}, false, true);
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, other), nullptr);
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, nullptr), nullptr);
    EXPECT_FALSE(_group->hasObject(pasted.front()));
}
