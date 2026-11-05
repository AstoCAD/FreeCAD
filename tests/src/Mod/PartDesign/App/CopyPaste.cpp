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
#include <App/GeoFeature.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/Origin.h>
#include <App/Part.h>
#include <Base/Placement.h>

#include <Mod/PartDesign/App/Body.h>
#include <Mod/PartDesign/App/DatumPlane.h>
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

    // A sketch on the XY plane of body and a pad of it, added at the body insert point
    PartDesign::Pad* addPad(PartDesign::Body* body, const char* name)
    {
        auto sketch = _doc->addObject<Sketcher::SketchObject>((std::string(name) + "Sketch").c_str());
        body->addObject(sketch);
        sketch->AttachmentSupport.setValue(body->getOrigin()->getXY(), "");
        sketch->MapMode.setValue("FlatFace");
        auto pad = _doc->addObject<PartDesign::Pad>(name);
        body->addObject(pad);
        pad->Profile.setValue(sketch);
        return pad;
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

TEST_F(CopyPasteRulesPDTest, padIsCopiedWithItsSketchWithoutAsking)
{
    auto pad = _doc->addObject<PartDesign::Pad>("Pad");
    _body1->addObject(pad);
    pad->Profile.setValue(_sketch);
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({pad}));
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({pad, _sketch}));
    const std::vector<App::DocumentObject*> expected {_body1->getOrigin()->getXY(), _sketch, pad};
    EXPECT_EQ(CopyPasteRules::getObjectsToCopy({pad}), expected);
}

TEST_F(CopyPasteRulesPDTest, padInAChainIsCopiedWithoutThePreviousFeatures)
{
    auto p0 = addPad(_body1, "P0");
    auto p1 = addPad(_body1, "P1");
    ASSERT_EQ(p1->BaseFeature.getValue(), p0);
    EXPECT_TRUE(CopyPasteRules::canCopyWithoutAsking({p1}));
    auto objs = CopyPasteRules::getObjectsToCopy({p1});
    const std::vector<App::DocumentObject*> expected {
        _body1->getOrigin()->getXY(), p1->Profile.getValue(), p1};
    EXPECT_EQ(objs, expected);
    // Without a rebuilt link, the export is the full dependency list as before
    EXPECT_EQ(CopyPasteRules::getObjectsToCopy({p0}),
              App::Document::getDependencyList({p0}, App::Document::DepSort));
    // Selecting the chain copies the chain
    auto chain = CopyPasteRules::getObjectsToCopy({p0, p1});
    EXPECT_NE(std::find(chain.begin(), chain.end(), p0), chain.end());
}

TEST_F(CopyPasteRulesPDTest, padOnAFaceOfThePreviousFeatureStillAsks)
{
    auto p0 = addPad(_body1, "P0");
    auto p1 = addPad(_body1, "P1");
    static_cast<Sketcher::SketchObject*>(p1->Profile.getValue())
        ->AttachmentSupport.setValue(p0, "Face6");
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({p1}));

    auto p2 = addPad(_body1, "P2");
    p2->UpToFace.setValue(p0, std::vector<std::string> {"Face1"});
    EXPECT_FALSE(CopyPasteRules::canCopyWithoutAsking({p2}));
}

TEST_F(CopyPasteRulesPDTest, padCopiedFromAChainIsRebasedInTheTargetBody)
{
    auto p0 = addPad(_body1, "P0");
    auto p1 = addPad(_body1, "P1");
    auto q1 = addPad(_body2, "Q1");

    auto pasted = _doc->copyObject(CopyPasteRules::getObjectsToCopy({p1}), false, true);
    auto newPad = findOfType<PartDesign::Pad>(pasted);
    ASSERT_NE(newPad, nullptr);
    ASSERT_EQ(pasted.size(), 3u);  // XY plane, sketch, pad: not P0 nor its sketch

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _body2), _body2);
    EXPECT_EQ(newPad->BaseFeature.getValue(), q1);
    EXPECT_EQ(newPad->_Body.getValue(), _body2);
    EXPECT_EQ(_body2->Tip.getValue(), newPad);
    auto newSketch = static_cast<Sketcher::SketchObject*>(newPad->Profile.getValue());
    EXPECT_TRUE(_body2->hasObject(newSketch));
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _body2->getOrigin()->getXY());
    EXPECT_EQ(countOrphanDatums(), 0);
    // The source chain is untouched
    EXPECT_EQ(p1->BaseFeature.getValue(), p0);
    EXPECT_EQ(_body1->Tip.getValue(), p1);
}

TEST_F(CopyPasteRulesPDTest, padCopiedFromAChainPastedAtRootLosesItsBodyLinks)
{
    addPad(_body1, "P0");
    auto p1 = addPad(_body1, "P1");

    auto pasted = _doc->copyObject(CopyPasteRules::getObjectsToCopy({p1}), false, true);
    auto newPad = findOfType<PartDesign::Pad>(pasted);
    ASSERT_NE(newPad, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, nullptr), nullptr);
    // Not linked to Body1 or its features any more
    EXPECT_EQ(newPad->BaseFeature.getValue(), nullptr);
    EXPECT_EQ(newPad->_Body.getValue(), nullptr);
    EXPECT_EQ(countOrphanDatums(), 0);
}

TEST_F(CopyPasteRulesPDTest, chainCopiedTogetherKeepsItsLinksAtRoot)
{
    auto p0 = addPad(_body1, "P0");
    auto p1 = addPad(_body1, "P1");
    auto pasted = copyPaste({p0, p1});
    PartDesign::Pad* newP0 = nullptr;
    PartDesign::Pad* newP1 = nullptr;
    for (auto obj : pasted) {
        if (obj->isDerivedFrom<PartDesign::Pad>()) {
            (newP0 ? newP1 : newP0) = static_cast<PartDesign::Pad*>(obj);
        }
    }
    ASSERT_NE(newP1, nullptr);
    CopyPasteRules::placePastedObjects(pasted, nullptr);
    EXPECT_EQ(newP1->BaseFeature.getValue(), newP0);
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

TEST_F(CopyPasteRulesPDTest, sketchPastedAtRootIsDetachedAtItsSourceGlobalPlacement)
{
    _part->Placement.setValue(Base::Placement(Base::Vector3d(10, 0, 0), Base::Rotation()));
    _body1->Placement.setValue(
        Base::Placement(Base::Vector3d(0, 20, 0), Base::Rotation(Base::Vector3d(0, 0, 1), 0.5)));
    _sketch->AttachmentOffset.setValue(
        Base::Placement(Base::Vector3d(1, 2, 3), Base::Rotation()));
    _doc->recompute();
    const auto local = _sketch->Placement.getValue();
    const auto global = App::GeoFeature::getGlobalPlacement(_sketch);
    ASSERT_FALSE(global.isSame(local, 1e-7));

    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);
    EXPECT_EQ(countOrphanDatums(), 1);

    // What Std_Paste does with nothing selected and no active body
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, nullptr, {{newSketch, global}}), nullptr);
    EXPECT_EQ(App::GeoFeatureGroupExtension::getGroupOfObject(newSketch), nullptr);
    EXPECT_TRUE(newSketch->AttachmentSupport.getValues().empty());
    EXPECT_STREQ(newSketch->MapMode.getValueAsString(), "Deactivated");
    EXPECT_TRUE(newSketch->Placement.getValue().isSame(global, 1e-7));
    EXPECT_EQ(countOrphanDatums(), 0);
    _doc->recompute();
    EXPECT_TRUE(newSketch->isValid());
    EXPECT_TRUE(newSketch->Placement.getValue().isSame(global, 1e-7));
    // The original is untouched
    EXPECT_EQ(_sketch->AttachmentSupport.getValues().front(), _body1->getOrigin()->getXY());
    EXPECT_TRUE(_sketch->Placement.getValue().isSame(local, 1e-7));
}

TEST_F(CopyPasteRulesPDTest, sketchPastedAtRootWithoutSourcePlacementKeepsItsPlacement)
{
    _sketch->AttachmentOffset.setValue(
        Base::Placement(Base::Vector3d(1, 2, 3), Base::Rotation()));
    _doc->recompute();
    const auto local = _sketch->Placement.getValue();

    // e.g. pasted from another FreeCAD instance: same placement as the attached copy had
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);
    CopyPasteRules::finishPastedObjects(pasted);
    EXPECT_STREQ(newSketch->MapMode.getValueAsString(), "Deactivated");
    EXPECT_TRUE(newSketch->Placement.getValue().isSame(local, 1e-7));
    EXPECT_EQ(countOrphanDatums(), 0);
}

TEST_F(CopyPasteRulesPDTest, copiedOriginPlanePastedAtRootIsKept)
{
    auto pasted = copyPaste({_body1->getOrigin()->getXY()});
    ASSERT_EQ(pasted.size(), 1u);
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, nullptr), nullptr);
    EXPECT_TRUE(pasted.front()->isAttachedToDocument());
    EXPECT_EQ(countOrphanDatums(), 1);
}

TEST_F(CopyPasteRulesPDTest, sketchAttachedToCopiedDatumPlaneStaysAttachedAtRoot)
{
    auto datum = _doc->addObject<PartDesign::Plane>("DatumPlane");
    _body1->addObject(datum);
    datum->AttachmentSupport.setValue(_body1->getOrigin()->getXY(), "");
    datum->MapMode.setValue("FlatFace");
    _sketch->AttachmentSupport.setValue(datum, "");
    _doc->recompute();

    auto pasted = copyPaste({datum, _sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    auto newDatum = findOfType<PartDesign::Plane>(pasted);
    ASSERT_NE(newSketch, nullptr);
    ASSERT_NE(newDatum, nullptr);
    CopyPasteRules::finishPastedObjects(pasted);
    // The datum plane, attached to the orphan, is detached; the sketch keeps its datum
    EXPECT_STREQ(newDatum->MapMode.getValueAsString(), "Deactivated");
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), newDatum);
    EXPECT_STREQ(newSketch->MapMode.getValueAsString(), "FlatFace");
    EXPECT_EQ(countOrphanDatums(), 0);
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

TEST_F(CopyPasteRulesPDTest, padPastedAfterSelectedFeatureIsInsertedInTheChain)
{
    auto p1 = addPad(_body2, "P1");
    auto p2 = addPad(_body2, "P2");
    auto p1Sketch = p1->Profile.getValue();
    auto p2Sketch = p2->Profile.getValue();
    ASSERT_EQ(_body2->Tip.getValue(), p2);
    ASSERT_EQ(p2->BaseFeature.getValue(), p1);
    auto pad = _doc->addObject<PartDesign::Pad>("Pad");
    _body1->addObject(pad);
    pad->Profile.setValue(_sketch);

    auto pasted = copyPaste({pad, _sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    auto newPad = findOfType<PartDesign::Pad>(pasted);
    ASSERT_NE(newSketch, nullptr);
    ASSERT_NE(newPad, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, p1), _body2);
    const std::vector<App::DocumentObject*> expected {p1Sketch, p1, newSketch, newPad, p2Sketch, p2};
    EXPECT_EQ(_body2->Group.getValues(), expected);
    EXPECT_EQ(newPad->BaseFeature.getValue(), p1);
    EXPECT_EQ(p2->BaseFeature.getValue(), newPad);
    EXPECT_EQ(p1->BaseFeature.getValue(), nullptr);
    EXPECT_EQ(_body2->Tip.getValue(), p2);  // inserted before the Tip: the Tip stays
    EXPECT_FALSE(newPad->Visibility.getValue());
    EXPECT_EQ(newPad->_Body.getValue(), _body2);
    EXPECT_EQ(newSketch->AttachmentSupport.getValues().front(), _body2->getOrigin()->getXY());
    EXPECT_EQ(countOrphanDatums(), 0);
}

TEST_F(CopyPasteRulesPDTest, padPastedAfterSelectedTipBecomesTheTip)
{
    auto p1 = addPad(_body2, "P1");
    auto pad = _doc->addObject<PartDesign::Pad>("Pad");
    _body1->addObject(pad);
    pad->Profile.setValue(_sketch);

    auto pasted = copyPaste({pad, _sketch});
    auto newPad = findOfType<PartDesign::Pad>(pasted);
    ASSERT_NE(newPad, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, p1), _body2);
    EXPECT_EQ(_body2->Group.getValues().back(), newPad);
    EXPECT_EQ(newPad->BaseFeature.getValue(), p1);
    EXPECT_EQ(_body2->Tip.getValue(), newPad);
}

TEST_F(CopyPasteRulesPDTest, sketchPastedAfterSelectedSketchIsInsertedThere)
{
    auto p1 = addPad(_body2, "P1");
    auto p1Sketch = p1->Profile.getValue();
    auto pasted = copyPaste({_sketch});
    auto newSketch = findOfType<Sketcher::SketchObject>(pasted);
    ASSERT_NE(newSketch, nullptr);

    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, p1Sketch), _body2);
    const std::vector<App::DocumentObject*> expected {p1Sketch, newSketch, p1};
    EXPECT_EQ(_body2->Group.getValues(), expected);
    EXPECT_EQ(_body2->Tip.getValue(), p1);
    EXPECT_EQ(p1->BaseFeature.getValue(), nullptr);
}

TEST_F(CopyPasteRulesPDTest, bodyPastedFromFeatureOfBodyInPartGoesAfterThatBody)
{
    auto other = _doc->addObject<PartDesign::Body>("Other");
    _part->addObject(other);
    auto pasted = copyPaste({_body2});
    auto roots = CopyPasteRules::getRootObjects(pasted);
    ASSERT_EQ(roots.size(), 1u);

    // Body1 refuses a body: the Part takes it, right after Body1
    EXPECT_EQ(CopyPasteRules::placePastedObjects(pasted, _sketch), _part);
    const std::vector<App::DocumentObject*> expected {_body1, roots.front(), other};
    EXPECT_EQ(_part->Group.getValues(), expected);
}

// NOLINTEND(readability-magic-numbers,cppcoreguidelines-avoid-magic-numbers)
