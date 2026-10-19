// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <QApplication>

#include <memory>
#include <string>
#include <vector>

#include <src/App/InitApplication.h>
#include <src/TempDirectory.h>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Link.h>
#include <App/Part.h>
#include <Base/Exception.h>
#include <Gui/Application.h>
#include <Gui/Selection/Selection.h>
#include <Gui/Selection/SoFCUnifiedSelection.h>

namespace
{

class ObjectNameGate: public Gui::SelectionGate
{
public:
    explicit ObjectNameGate(const char* allowedName)
        : _allowedName(allowedName)
    {}

    bool allow(App::Document*, App::DocumentObject* obj, const char*) override
    {
        if (!obj || _allowedName != obj->getNameInDocument()) {
            notAllowedReason = "rejected by test gate";
            return false;
        }
        return true;
    }

private:
    std::string _allowedName;
};

class SelectionTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
        // This GTest executable has no Qt main function.
        // Selection notifications need the GUI singleton, but no rendered views.
        if (!QApplication::instance()) {
            static int argc = 1;
            static char name[] = "SelectionTest";
            static char* argv[] = {name, nullptr};
            new QApplication(argc, argv);
        }
        ASSERT_NE(qobject_cast<QApplication*>(QApplication::instance()), nullptr);
        if (!Gui::Application::Instance) {
            new Gui::Application(false);
        }
    }

    void SetUp() override
    {
        // The reduced GUI singleton has no MacroManager. Keep logging disabled
        // through document/selection cleanup as well as the test body.
        _selectionLogDisabler = std::make_unique<Gui::SelectionLogDisabler>(true);
        // Keep model documents headless: these tests need no GUI documents/views.
        App::DocumentInitFlags createFlags;
        createFlags.createView = false;
        _docName = App::GetApplication().getUniqueDocumentName("selection_test");
        _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser", createFlags);
        _allowedObject = _doc->addObject("App::FeatureTest", "Allowed");
        _rejectedObject = _doc->addObject("App::FeatureTest", "Rejected");
    }

    void TearDown() override
    {
        Gui::Selection().rmvSelectionGate();
        Gui::Selection().clearSelection();
        if (App::GetApplication().getDocument(_docName.c_str())) {
            App::GetApplication().closeDocument(_docName.c_str());
        }
        if (!_otherDocName.empty() && App::GetApplication().getDocument(_otherDocName.c_str())) {
            App::GetApplication().closeDocument(_otherDocName.c_str());
        }
        _directory.reset();
        _selectionLogDisabler.reset();
    }

    std::string _docName;
    std::string _otherDocName;
    App::Document* _doc {};
    App::DocumentObject* _allowedObject {};
    App::DocumentObject* _rejectedObject {};
    std::unique_ptr<Gui::SelectionLogDisabler> _selectionLogDisabler;
    std::unique_ptr<tests::TempDirectory> _directory;
};

Gui::SelectionPickPolicy::Candidate pickCandidate(
    const void* owner,
    int priority,
    bool closeToFirst,
    bool hasGate,
    bool passesGate
)
{
    Gui::SelectionPickPolicy::Candidate candidate;
    candidate.owner = owner;
    candidate.priority = priority;
    candidate.closeToFirst = closeToFirst;
    candidate.hasGate = hasGate;
    candidate.passesGate = passesGate;
    return candidate;
}

}  // namespace

TEST_F(SelectionTest, testSelectionAllowsObjectsWhenNoGateIsInstalled)
{
    EXPECT_TRUE(Gui::Selection().testSelection(_doc, _allowedObject));
}

TEST_F(SelectionTest, testSelectionUsesActiveGateWithoutKeepingRejectionReason)
{
    auto* gate = new ObjectNameGate(_allowedObject->getNameInDocument());
    gate->notAllowedReason = "existing reason";
    Gui::Selection().addSelectionGate(gate, Gui::ResolveMode::NoResolve);

    EXPECT_TRUE(Gui::Selection().testSelection(_doc, _allowedObject));
    EXPECT_EQ(gate->notAllowedReason, "existing reason");

    EXPECT_FALSE(Gui::Selection().testSelection(_doc, _rejectedObject));
    EXPECT_EQ(gate->notAllowedReason, "existing reason");
    EXPECT_FALSE(Gui::Selection().hasPreselection());
    EXPECT_FALSE(Gui::Selection().hasSelection(_docName.c_str(), Gui::ResolveMode::NoResolve));
}

TEST(SelectionPickPolicyTest, canFinalizeSinglePickWhenNoGateIsInstalled)
{
    int owner {};
    std::vector<Gui::SelectionPickPolicy::Candidate> candidates {
        pickCandidate(&owner, 0, true, false, true),
    };

    EXPECT_TRUE(Gui::SelectionPickPolicy::canFinalizeSinglePick(candidates));
}

TEST(SelectionPickPolicyTest, continuesSinglePickWhenGateRejectedAllCurrentCandidates)
{
    int owner {};
    std::vector<Gui::SelectionPickPolicy::Candidate> candidates {
        pickCandidate(&owner, 0, true, true, false),
    };

    EXPECT_FALSE(Gui::SelectionPickPolicy::canFinalizeSinglePick(candidates));
}

TEST(SelectionPickPolicyTest, choosesAllowedCandidateWhenPreferredPickIsRejected)
{
    int firstOwner {};
    int secondOwner {};
    std::vector<Gui::SelectionPickPolicy::Candidate> candidates {
        pickCandidate(&firstOwner, 1, true, true, false),
        pickCandidate(&secondOwner, 0, true, true, true),
    };

    EXPECT_EQ(Gui::SelectionPickPolicy::choosePreferredPick(candidates), 1U);
}

TEST(SelectionPickPolicyTest, preservesPriorityChoiceWithinFirstOwner)
{
    int firstOwner {};
    int secondOwner {};
    std::vector<Gui::SelectionPickPolicy::Candidate> candidates {
        pickCandidate(&firstOwner, 1, true, false, true),
        pickCandidate(&firstOwner, 2, true, false, true),
        pickCandidate(&secondOwner, 3, true, false, true),
    };

    EXPECT_EQ(Gui::SelectionPickPolicy::choosePreferredPick(candidates), 1U);
}

TEST(SelectionPickPolicyTest, keepsPreferredPickWhenNoCandidatePassesGate)
{
    int firstOwner {};
    int secondOwner {};
    std::vector<Gui::SelectionPickPolicy::Candidate> candidates {
        pickCandidate(&firstOwner, 1, true, true, false),
        pickCandidate(&secondOwner, 0, true, true, false),
    };

    EXPECT_EQ(Gui::SelectionPickPolicy::choosePreferredPick(candidates), 0U);
}

TEST_F(SelectionTest, testGetObjectsOfTypeRespectsDocumentFilter)
{
    App::DocumentInitFlags createFlags;
    createFlags.createView = false;
    const std::string otherName = App::GetApplication().getUniqueDocumentName("selection_other");
    _otherDocName = otherName;
    auto* otherDoc = App::GetApplication().newDocument(otherName.c_str(), "testUser", createFlags);
    auto* otherObject = otherDoc->addObject("App::FeatureTest", "Other");
    Gui::Selection().clearSelection();
    EXPECT_TRUE(Gui::Selection().addSelection(_docName.c_str(), _allowedObject->getNameInDocument()));
    EXPECT_TRUE(Gui::Selection().addSelection(otherName.c_str(), otherObject->getNameInDocument()));

    const auto type = App::DocumentObject::getClassTypeId();
    EXPECT_EQ(Gui::Selection().getObjectsOfType(type, _docName.c_str()),
              (std::vector<App::DocumentObject*> {_allowedObject}));
    EXPECT_EQ(Gui::Selection().getObjectsOfType(type, otherName.c_str()),
              (std::vector<App::DocumentObject*> {otherObject}));
    App::GetApplication().setActiveDocument(_docName.c_str());
    EXPECT_EQ(Gui::Selection().getObjectsOfType(type),
              (std::vector<App::DocumentObject*> {_allowedObject}));
    const std::vector<App::DocumentObject*> allObjects {_allowedObject, otherObject};
    EXPECT_EQ(Gui::Selection().getObjectsOfType(type, "*"), allObjects);
    EXPECT_TRUE(Gui::Selection().getObjectsOfType(type, "nonexistent_selection_document").empty());

    App::GetApplication().setActiveDocument(static_cast<App::Document*>(nullptr));
    EXPECT_TRUE(Gui::Selection().getObjectsOfType(type).empty());
    EXPECT_EQ(Gui::Selection().getObjectsOfType(type, _docName.c_str()),
              (std::vector<App::DocumentObject*> {_allowedObject}));
    EXPECT_EQ(Gui::Selection().getObjectsOfType(type, "*"), allObjects);

    App::GetApplication().setActiveDocument(_docName.c_str());
    Gui::Selection().clearSelection();
    App::GetApplication().closeDocument(otherName.c_str());
}

TEST_F(SelectionTest, testGetObjectsOfTypeFiltersLinkSelectionByOwnerDocument)
{
    App::DocumentInitFlags createFlags;
    createFlags.createView = false;
    const std::string otherName = App::GetApplication().getUniqueDocumentName("selection_link_target");
    _otherDocName = otherName;
    auto* otherDoc = App::GetApplication().newDocument(otherName.c_str(), "testUser", createFlags);
    auto* foreignPart = static_cast<App::Part*>(otherDoc->addObject("App::Part", "ForeignPart"));
    auto* foreignChild = otherDoc->addObject("App::FeatureTest", "ForeignChild");
    foreignPart->addObject(foreignChild);
    // Cross-document links require both documents to have persistent filenames.
    _directory = std::make_unique<tests::TempDirectory>("fc_selection_filter");
    const auto targetFile = _directory->string() + "/SelectionTarget.FCStd";
    const auto ownerFile = _directory->string() + "/SelectionOwner.FCStd";
    otherDoc->saveAs(targetFile.c_str());
    _doc->saveAs(ownerFile.c_str());
    auto* link = static_cast<App::Link*>(_doc->addObject("App::Link", "LocalLink"));
    try {
        link->setLink(-1, foreignPart);
    }
    catch (const Base::Exception& error) {
        FAIL() << "Saved cross-document link fixture: " << error.what();
    }
    otherDoc->recompute();
    _doc->recompute();
    const std::string childPath = std::string(foreignChild->getNameInDocument()) + ".";
    EXPECT_EQ(link->getSubObject(childPath.c_str()), foreignChild);

    Gui::Selection().clearSelection();
    EXPECT_TRUE(Gui::Selection().addSelection(_docName.c_str(), link->getNameInDocument(),
                                            childPath.c_str()));
    App::GetApplication().setActiveDocument(_docName.c_str());
    const auto type = App::DocumentObject::getClassTypeId();
    for (const auto mode : {Gui::ResolveMode::NoResolve, Gui::ResolveMode::OldStyleElement,
                            Gui::ResolveMode::FollowLink}) {
        SCOPED_TRACE(static_cast<int>(mode));
        const auto all = Gui::Selection().getObjectsOfType(type, "*", mode);
        // A link selection belongs to its original document even when resolution
        // returns the foreign child. Filtering the resolved object's document
        // would silently remove this legitimate local selection.
        const std::vector<App::DocumentObject*> expected {
            mode == Gui::ResolveMode::NoResolve ? static_cast<App::DocumentObject*>(link)
                                               : foreignChild};
        EXPECT_EQ(all, expected);
        EXPECT_EQ(Gui::Selection().getObjectsOfType(type, _docName.c_str(), mode), all);
        EXPECT_EQ(Gui::Selection().getObjectsOfType(type, nullptr, mode), all);
        EXPECT_TRUE(Gui::Selection().getObjectsOfType(type, otherName.c_str(), mode).empty());
    }

    Gui::Selection().clearSelection();
    _doc->removeObject(link->getNameInDocument());
    App::GetApplication().closeDocument(otherName.c_str());
}
