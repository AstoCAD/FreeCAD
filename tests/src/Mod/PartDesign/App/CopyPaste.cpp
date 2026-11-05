// SPDX-License-Identifier: LGPL-2.1-or-later

// Copy/Paste rules of https://github.com/FreeCAD/FreeCAD/issues/9251 with PartDesign bodies.
// The clipboard round trip is emulated by Document::copyObject(), which exports and imports
// the same objects as Std_Copy/Std_Paste.

#include <gtest/gtest.h>

#include <algorithm>

#include "src/App/InitApplication.h"

#include <App/Application.h>
#include <App/CopyPasteRules.h>
#include <App/Datums.h>
#include <App/Document.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/Origin.h>
#include <App/Part.h>

#include <Mod/PartDesign/App/Body.h>
#include <Mod/PartDesign/App/FeaturePad.h>
#include <Mod/Sketcher/App/SketchObject.h>

// NOLINTBEGIN(readability-magic-numbers,cppcoreguidelines-avoid-magic-numbers)

using App::CopyPasteRules;

class CopyPasteRulesPDTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _docName = App::GetApplication().getUniqueDocumentName("CopyPaste");
        _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
        _part = _doc->addObject<App::Part>("Part");
        _body1 = _doc->addObject<PartDesign::Body>("Body1");
        _part->addObject(_body1);
        _body2 = _doc->addObject<PartDesign::Body>("Body2");
        _sketch = _doc->addObject<Sketcher::SketchObject>("Sketch");
        _body1->addObject(_sketch);
        _sketch->AttachmentSupport.setValue(_body1->getOrigin()->getXY(), "");
        _sketch->MapMode.setValue("FlatFace");
        _doc->recompute();
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_docName.c_str());
    }

    // What Std_Copy exports when it does not ask (all dependencies), imported back.
    std::vector<App::DocumentObject*> copyPaste(const std::vector<App::DocumentObject*>& sel)
    {
        auto deps = App::Document::getDependencyList(sel, App::Document::DepSort);
        return _doc->copyObject(deps, false, true);
    }

    template<typename T>
    static T* findOfType(const std::vector<App::DocumentObject*>& objs)
    {
        for (auto obj : objs) {
            if (obj->isDerivedFrom<T>()) {
                return static_cast<T*>(obj);
            }
        }
        return nullptr;
    }

    int countOrphanDatums() const
    {
        auto objs = _doc->getObjects();
        return static_cast<int>(std::count_if(objs.begin(), objs.end(), [](auto obj) {
            return CopyPasteRules::isOrphanDatum(obj);
        }));
    }

    // NOLINTBEGIN(cppcoreguidelines-non-private-member-variables-in-classes)
    std::string _docName;
    App::Document* _doc {};
    App::Part* _part {};
    PartDesign::Body* _body1 {};
    PartDesign::Body* _body2 {};
    Sketcher::SketchObject* _sketch {};
    // NOLINTEND(cppcoreguidelines-non-private-member-variables-in-classes)
};

TEST_F(CopyPasteRulesPDTest, sketchOnOriginPlaneIsCopiedWithoutAsking)
{
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({_sketch}));
}

TEST_F(CopyPasteRulesPDTest, padWithoutItsSketchStillAsks)
{
    auto pad = _doc->addObject<PartDesign::Pad>("Pad");
    _body1->addObject(pad);
    pad->Profile.setValue(_sketch);
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({pad}));
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({pad, _sketch}));
}

TEST_F(CopyPasteRulesPDTest, sketchAttachedToAnotherFeatureStillAsks)
{
    auto other = _doc->addObject<Sketcher::SketchObject>("Other");
    _body1->addObject(other);
    _sketch->AttachmentSupport.setValue(other, "");
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({_sketch}));
}

TEST_F(CopyPasteRulesPDTest, bodyCopyIncludesFeaturesButNotParentPart)
{
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({_body1}));
    auto deps = App::Document::getDependencyList({_body1}, App::Document::DepSort);
    EXPECT_NE(std::find(deps.begin(), deps.end(), _sketch), deps.end());
    EXPECT_NE(std::find(deps.begin(), deps.end(), _body1->getOrigin()), deps.end());
    EXPECT_EQ(std::find(deps.begin(), deps.end(), _part), deps.end());

    auto pasted = copyPaste({_body1});
    auto roots = CopyPasteRules::getRootObjects(pasted);
    ASSERT_EQ(roots.size(), 1u);
    auto newBody = dynamic_cast<PartDesign::Body*>(roots.front());
    ASSERT_NE(newBody, nullptr);
    EXPECT_NE(newBody, _body1);
    EXPECT_EQ(newBody->Group.getValues().size(), 1u);
    EXPECT_NE(newBody->getOrigin(), _body1->getOrigin());

    // Nothing selected: stays at the root, the Part is untouched
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, nullptr), nullptr);
    EXPECT_EQ(App::GeoFeatureGroupExtension::getGroupOfObject(newBody), nullptr);
    EXPECT_EQ(_part->Group.getValues().size(), 1u);
}

TEST_F(CopyPasteRulesPDTest, sketchPastedIntoOtherBodyIsReattachedToItsOrigin)
{
    auto pasted = copyPaste({_sketch});
    ASSERT_EQ(pasted.size(), 2u);  // the sketch and an orphan copy of XY_Plane
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);
    EXPECT_EQ(countOrphanDatums(), 1);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _body2), _body2);

    EXPECT_TRUE(_body2->hasObject(newSketch));
    auto support = newSketch->AttachmentSupport.getValues();
    ASSERT_EQ(support.size(), 1u);
    EXPECT_EQ(support.front(), _body2->getOrigin()->getXY());
    EXPECT_STREQ(newSketch->MapMode.getValueAsString(), "FlatFace");
    EXPECT_EQ(countOrphanDatums(), 0);
    _doc->recompute();
    EXPECT_TRUE(newSketch->isValid());
    // The original is untouched
    EXPECT_EQ(_sketch->AttachmentSupport.getValues().front(), _body1->getOrigin()->getXY());
}

TEST_F(CopyPasteRulesPDTest, sketchPastedNextToSelectedSiblingGoesIntoItsBody)
{
    auto sibling = _doc->addObject<Sketcher::SketchObject>("Sibling");
    _body2->addObject(sibling);
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, sibling), _body2);
    EXPECT_TRUE(_body2->hasObject(newSketch));
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _body2->getOrigin()->getXY());
}

TEST_F(CopyPasteRulesPDTest, sketchPastedOnSelectedOriginPlaneGoesIntoItsBody)
{
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _body2->getOrigin()->getXZ()), _body2);
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _body2->getOrigin()->getXY());
}

TEST_F(CopyPasteRulesPDTest, sketchPastedOnItselfStaysInItsBody)
{
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);
    EXPECT_NE(newSketch, _sketch);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _sketch), _body1);
    EXPECT_TRUE(_body1->hasObject(newSketch));
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _body1->getOrigin()->getXY());
    EXPECT_EQ(countOrphanDatums(), 0);
}

TEST_F(CopyPasteRulesPDTest, sketchPastedWithNothingSelectedKeepsTodaysResult)
{
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    auto orphan = findOfType<App::Plane>(pasted);
    ASSERT_NE(newSketch, nullptr);
    ASSERT_NE(orphan, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, nullptr), nullptr);
    EXPECT_EQ(App::GeoFeatureGroupExtension::getGroupOfObject(newSketch), nullptr);
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), orphan);
    EXPECT_EQ(countOrphanDatums(), 1);
}

TEST_F(CopyPasteRulesPDTest, sketchPastedIntoPartUsesThePartOrigin)
{
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _part), _part);
    EXPECT_TRUE(_part->hasObject(newSketch));
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _part->getOrigin()->getXY());
    EXPECT_EQ(countOrphanDatums(), 0);
}

TEST_F(CopyPasteRulesPDTest, bodyPastedOnBodyGoesIntoTheParentPart)
{
    auto pasted = copyPaste({_body2});
    auto roots = CopyPasteRules::getRootObjects(pasted);
    ASSERT_EQ(roots.size(), 1u);

    // A body does not accept a body: the Part around Body1 does
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _body1), _part);
    EXPECT_TRUE(_part->hasObject(roots.front()));
}

TEST_F(CopyPasteRulesPDTest, bodyPastedOnRootBodyStaysAtRoot)
{
    auto pasted = copyPaste({_body1});
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _body2), nullptr);
}

TEST_F(CopyPasteRulesPDTest, padAndSketchPastedIntoOtherBodyKeepTheirOrder)
{
    auto pad = _doc->addObject<PartDesign::Pad>("Pad");
    _body1->addObject(pad);
    pad->Profile.setValue(_sketch);

    auto pasted = copyPaste({pad, _sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    auto newPad = findOfType<PartDesign::Pad>(pasted);
    ASSERT_NE(newSketch, nullptr);
    ASSERT_NE(newPad, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _body2), _body2);
    auto group = _body2->Group.getValues();
    ASSERT_EQ(group.size(), 2u);
    EXPECT_EQ(group[0], newSketch);
    EXPECT_EQ(group[1], newPad);
    EXPECT_EQ(_body2->Tip.getValue(), newPad);
    EXPECT_EQ(newPad->Profile.getValue(), newSketch);
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _body2->getOrigin()->getXY());
}

// NOLINTEND(readability-magic-numbers,cppcoreguidelines-avoid-magic-numbers)
