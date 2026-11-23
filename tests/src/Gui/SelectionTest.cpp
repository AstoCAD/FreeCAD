// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <string>
#include <vector>

#include <src/App/InitApplication.h>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <Base/Interpreter.h>
#include <Gui/Selection/Selection.h>
#include <Gui/Selection/SelectionFilter.h>
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

// The functions of the FreeCADGui.Selection Python module are protected members
class SelectionModuleAccess: public Gui::SelectionSingleton
{
public:
    static PyObject* addSelectionGate(PyObject* args)
    {
        return sAddSelectionGate(nullptr, args);
    }
};

class SelectionTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        // Keep this fixture headless even if another Gui gtest already created
        // Gui::Application in the shared binary.
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
    }

    std::string _docName;
    App::Document* _doc {};
    App::DocumentObject* _allowedObject {};
    App::DocumentObject* _rejectedObject {};
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

TEST(SelectionFilterGateTest, emptyFilterGatesNoGeometryType)
{
    // An empty filter string has no syntax tree; box selection asks the gate for its types
    Gui::SelectionFilterGate gate("");

    EXPECT_TRUE(gate.getGatedTypes({"Vertex", "Edge", "Face"}).empty());
}

TEST_F(SelectionTest, testRemovingPythonGateWithoutGilReleasesIt)
{
    PyObject* gateRef = nullptr;
    {
        Base::PyGILStateLocker lock;
        Py::Object gate = Base::Interpreter().runStringObject(
            "type('Gate', (), {'allow': lambda self, doc, obj, sub: True})()"
        );
        gateRef = PyWeakref_NewRef(gate.ptr(), nullptr);
        ASSERT_NE(gateRef, nullptr);
        PyObject* args = Py_BuildValue("(O)", gate.ptr());
        PyObject* result = SelectionModuleAccess::addSelectionGate(args);
        Py_DECREF(args);
        ASSERT_NE(result, nullptr);
        Py_DECREF(result);
    }
    // The selection gate now holds the only reference to the Python gate. C++ code removes
    // the active gate without holding the GIL, e.g. the task view when another document is
    // activated.
    ASSERT_FALSE(PyGILState_Check());
    Gui::Selection().rmvSelectionGate();

    Base::PyGILStateLocker lock;
    PyObject* referent = PyObject_CallObject(gateRef, nullptr);
    EXPECT_EQ(referent, Py_None);
    Py_XDECREF(referent);
    Py_DECREF(gateRef);
}

TEST(SelectionFilterGateTest, allowsOnlySubElementsWhenEveryEntryNamesOne)
{
    // A filter entry without SUBELEMENT lets whole objects through: box selection must keep
    // selecting objects with such a gate, although getGatedTypes() reports every type for it
    Gui::SelectionFilterGate objectGate("SELECT App::FeatureTest");
    Gui::SelectionFilterGate mixedGate(
        "SELECT App::FeatureTest SUBELEMENT Edge SELECT App::DocumentObjectGroup"
    );
    Gui::SelectionFilterGate edgeGate("SELECT App::FeatureTest SUBELEMENT Edge");
    Gui::SelectionFilterGate edgeFaceGate(
        "SELECT App::FeatureTest SUBELEMENT Edge SELECT App::FeatureTest SUBELEMENT Face"
    );
    Gui::SelectionFilterGate emptyGate("");

    EXPECT_FALSE(objectGate.getGatedTypes({"Vertex", "Edge", "Face"}).empty());
    EXPECT_FALSE(objectGate.allowsOnlySubElements());
    EXPECT_FALSE(mixedGate.allowsOnlySubElements());
    EXPECT_TRUE(edgeGate.allowsOnlySubElements());
    EXPECT_TRUE(edgeFaceGate.allowsOnlySubElements());
    EXPECT_FALSE(emptyGate.allowsOnlySubElements());
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
