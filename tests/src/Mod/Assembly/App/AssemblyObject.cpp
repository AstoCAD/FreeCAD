// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <FCConfig.h>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObjectGroup.h>
#include <App/Expression.h>
#include <App/Link.h>
#include <App/ObjectIdentifier.h>
#include <App/Part.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <Mod/Assembly/App/AssemblyLink.h>
#include <Mod/Assembly/App/ContactGeometry.h>
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepPrimAPI_MakeSphere.hxx>
#include <BRepAlgoAPI_Cut.hxx>
#include <Mod/Assembly/App/AssemblyObject.h>
#include <Mod/Assembly/App/AssemblyUtils.h>
#include <Mod/Assembly/App/Groups.h>
#include <Mod/Part/App/FeaturePartBox.h>
#include <Mod/Part/App/LinkArrayLinear.h>
#include <Base/Exception.h>
#include <src/App/InitApplication.h>

TEST(ContactGeometry, SweptTranslationFindsThinWallBetweenSeparatedEndpoints)
{
    Assembly::ContactGeometry geometry(BRepPrimAPI_MakeSphere(1).Shape(),
        BRepPrimAPI_MakeBox(gp_Pnt(-0.05, -5, -5), 0.1, 10, 10).Shape(), false);
    const Base::Placement start(Base::Vector3d(-3, 0, 0), Base::Rotation());
    const Base::Placement end(Base::Vector3d(3, 0, 0), Base::Rotation());
    const auto fraction = geometry.sweep(start, end, {}, {});
    EXPECT_NEAR(fraction, 1.95 / 6, 1e-6);
    EXPECT_FALSE(geometry.acceptStep(start, end, {}, {}));
}

TEST(ContactGeometry, SweptRotationFindsObstacleBetweenSeparatedEndpoints)
{
    Assembly::ContactGeometry geometry(
        BRepPrimAPI_MakeBox(gp_Pnt(-5, -0.1, -0.1), 10, 0.2, 0.2).Shape(),
        BRepPrimAPI_MakeSphere(gp_Pnt(3, 0, 0), 0.25).Shape(), false);
    const Base::Placement start(Base::Vector3d(), Base::Rotation(Base::Vector3d(0, 0, 1), -1));
    const Base::Placement end(Base::Vector3d(), Base::Rotation(Base::Vector3d(0, 0, 1), 1));
    const auto fraction = geometry.sweep(start, end, {}, {});
    EXPECT_GT(fraction, 0.3);
    EXPECT_LT(fraction, 0.5);
    EXPECT_FALSE(geometry.acceptStep(start, end, {}, {}));
    EXPECT_EQ(geometry.sweep(start, start, {}, {}), 1);
}

TEST(ContactGeometry, DragCanLeaveAnInitiallyTouchingSurface)
{
    Assembly::ContactGeometry geometry(BRepPrimAPI_MakeSphere(1).Shape(),
        BRepPrimAPI_MakeBox(gp_Pnt(1, -5, -5), 1, 10, 10).Shape(), false);
    const Base::Placement away(Base::Vector3d(-10, 0, 0), Base::Rotation());
    const Base::Placement through(Base::Vector3d(10, 0, 0), Base::Rotation());
    const Base::Placement along(Base::Vector3d(0, 3, 0), Base::Rotation());
    EXPECT_EQ(geometry.sweep({}, away, {}, {}, true), 1);
    EXPECT_EQ(geometry.sweep({}, through, {}, {}, true), 0);
    EXPECT_EQ(geometry.sweep({}, along, {}, {}, true), 1);
}

TEST(ContactGeometry, ConcavePassageIsNotReplacedByAConvexHull)
{
    const auto outer = BRepPrimAPI_MakeBox(gp_Pnt(-1, -5, -5), 2, 10, 10).Shape();
    const auto hole = BRepPrimAPI_MakeBox(gp_Pnt(-2, -2, -2), 4, 4, 4).Shape();
    const auto tunnel = BRepAlgoAPI_Cut(outer, hole).Shape();
    Assembly::ContactGeometry geometry(BRepPrimAPI_MakeSphere(0.2).Shape(), tunnel, false);
    const Base::Placement start(Base::Vector3d(-3, 0, 0), Base::Rotation());
    const Base::Placement end(Base::Vector3d(3, 0, 0), Base::Rotation());
    EXPECT_EQ(geometry.sweep(start, end, {}, {}), 1);
    const Base::Placement wallStart(Base::Vector3d(-3, 3, 0), Base::Rotation());
    const Base::Placement wallEnd(Base::Vector3d(3, 3, 0), Base::Rotation());
    EXPECT_NEAR(geometry.sweep(wallStart, wallEnd, {}, {}), 0.3, 1e-6);
}

class AssemblyObjectTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
        Part::LinearPatternExtension::init();
        Part::LinkArray::init();
        Part::LinkArrayLinear::init();
        Part::AttachExtension::init();
        Part::Primitive::init();
        Part::Box::init();
    }

    void SetUp() override
    {
        try {
            _docName = App::GetApplication().getUniqueDocumentName("test");
            auto _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
            _assemblyObj = _doc->addObject<Assembly::AssemblyObject>();
            _jointGroupObj = _assemblyObj->addObject<Assembly::JointGroup>("jointGroupTest");
        }
        catch (const Base::Exception& e) {
            FAIL() << e.what();
        }
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_docName.c_str());
    }

    Assembly::AssemblyObject* getObject()
    {
        return _assemblyObj;
    }

private:
    // TODO: use shared_ptr or something else here?
    Assembly::AssemblyObject* _assemblyObj;
    Assembly::JointGroup* _jointGroupObj;
    std::string _docName;
};

TEST_F(AssemblyObjectTest, createAssemblyObject)  // NOLINT
{
    // Arrange

    // Act

    // Assert
}

TEST_F(AssemblyObjectTest, detectsNestedGroundedJointsAndRigidGroups)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();
    auto* jointGroup = assembly->getJointGroup();
    ASSERT_NE(jointGroup, nullptr);

    auto* folder = doc->addObject<App::DocumentObjectGroup>("JointFolder");
    jointGroup->addObject(folder);

    auto* box1 = doc->addObject<Part::Box>("Box1");
    auto* box2 = doc->addObject<Part::Box>("Box2");
    assembly->addObject(box1);
    assembly->addObject(box2);

    auto* grounded = doc->addObject("App::FeaturePython", "GroundedJoint");
    auto* objectToGround = dynamic_cast<App::PropertyLink*>(
        grounded->addDynamicProperty("App::PropertyLink", "ObjectToGround")
    );
    ASSERT_NE(objectToGround, nullptr);
    objectToGround->setValue(box1);
    folder->addObject(grounded);

    auto* rigid = doc->addObject("App::FeaturePython", "RigidGroup");
    auto* suppressed = dynamic_cast<App::PropertyBool*>(
        rigid->addDynamicProperty("App::PropertyBool", "Suppressed")
    );
    auto* rigidMembers = dynamic_cast<App::PropertyLinkList*>(
        rigid->addDynamicProperty("App::PropertyLinkList", "ObjectsToRigidGroup")
    );
    ASSERT_NE(suppressed, nullptr);
    ASSERT_NE(rigidMembers, nullptr);
    suppressed->setValue(false);
    rigidMembers->setValues({box1, box2});
    folder->addObject(rigid);

    EXPECT_EQ(assembly->getGroundedJoints(), std::vector<App::DocumentObject*> {grounded});
    EXPECT_EQ(assembly->getRigidGroups(), std::vector<App::DocumentObject*> {rigid});
}

TEST_F(AssemblyObjectTest, jointGroupFoldersArePlainDocumentGroups)  // NOLINT
{
    auto* doc = getObject()->getDocument();
    auto* folder = doc->addObject<App::DocumentObjectGroup>("JointFolder");
    auto* part = doc->addObject<App::Part>("PartGroup");

    EXPECT_TRUE(Assembly::isJointGroupFolder(folder));
    EXPECT_FALSE(Assembly::isJointGroupFolder(part));
}

TEST_F(AssemblyObjectTest, assemblyLinkMapsExpandedPartLinkArrayElementReferences)  // NOLINT
{
    auto* doc = getObject()->getDocument();
    auto* sourceAssembly = doc->addObject<Assembly::AssemblyObject>("SourceAssembly");
    auto* box = doc->addObject<Part::Box>("Box");
    auto* array = doc->addObject<Part::LinkArrayLinear>("LinearArray");
    array->LinkedObject.setValue(box);
    array->Occurrences.setValue(2);
    array->Occurrences2.setValue(1);
    array->Length.setValue(10.0);
    array->execute();
    sourceAssembly->addObject(array);

    auto* assemblyLink = doc->addObject<Assembly::AssemblyLink>("AssemblyLink");
    assemblyLink->LinkedObject.setValue(sourceAssembly);
    assemblyLink->synchronizeComponents();

    const auto elements = array->ElementList.getValues();
    ASSERT_EQ(elements.size(), 2);
    auto linkIt = assemblyLink->objLinkMap.find(array);
    ASSERT_NE(linkIt, assemblyLink->objLinkMap.end());
    auto prefixIt = assemblyLink->objSubPrefixMap.find(elements[1]);
    ASSERT_NE(prefixIt, assemblyLink->objSubPrefixMap.end());
    EXPECT_EQ(prefixIt->second, "1");

    auto* joint = doc->addObject("App::FeaturePython", "SourceJoint");
    auto* linkedJoint = doc->addObject("App::FeaturePython", "LinkedJoint");
    auto* sourceRef = dynamic_cast<App::PropertyXLinkSub*>(
        joint->addDynamicProperty("App::PropertyXLinkSub", "Reference1")
    );
    auto* linkedRef = dynamic_cast<App::PropertyXLinkSub*>(
        linkedJoint->addDynamicProperty("App::PropertyXLinkSub", "Reference1")
    );
    ASSERT_NE(sourceRef, nullptr);
    ASSERT_NE(linkedRef, nullptr);
    sourceRef->setValue(elements[1], std::vector<std::string> {"Face1"});

    assemblyLink->handleJointReference(joint, linkedJoint, "Reference1");

    EXPECT_EQ(linkedRef->getValue(), linkIt->second);
    ASSERT_EQ(linkedRef->getSubValues().size(), 1);
    EXPECT_EQ(linkedRef->getSubValues().front(), "1.Face1");
}

TEST_F(AssemblyObjectTest, dragContactPropagatesThroughComponentsVisitedEarlier)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();

    auto addBox = [&](const char* name, double x) {
        auto* box = doc->addObject<Part::Box>(name);
        box->Length.setValue(10.0);
        box->Width.setValue(10.0);
        box->Height.setValue(10.0);
        box->Placement.setValue(Base::Placement(Base::Vector3d(x, 0, 0), Base::Rotation()));
        box->execute();
        assembly->addObject(box);
        return box;
    };

    auto* first = addBox("First", 0.0);
    auto* second = addBox("Second", 11.0);
    auto* dragged = addBox("Dragged", 22.0);

    auto* contact = doc->addObject("App::FeaturePython", "GeneralContact");
    contact->addDynamicProperty("App::PropertyString", "ContactType");
    auto* mode = dynamic_cast<App::PropertyEnumeration*>(
        contact->addDynamicProperty("App::PropertyEnumeration", "Mode")
    );
    auto* suppressed = dynamic_cast<App::PropertyBool*>(
        contact->addDynamicProperty("App::PropertyBool", "Suppressed")
    );
    auto* friction = dynamic_cast<App::PropertyBool*>(
        contact->addDynamicProperty("App::PropertyBool", "FrictionEnabled")
    );
    ASSERT_NE(mode, nullptr);
    ASSERT_NE(suppressed, nullptr);
    ASSERT_NE(friction, nullptr);
    mode->setEnums({"Between two components", "General collision detection"});
    mode->setValue("General collision detection");
    suppressed->setValue(false);
    friction->setValue(false);
    assembly->addObject(contact);

    const Base::Placement previous = dragged->Placement.getValue();
    dragged->Placement.setValue(Base::Placement(Base::Vector3d(16.0, 0, 0), Base::Rotation()));
    assembly->resolveContactMove({dragged}, {{dragged, previous}});

    EXPECT_LT(first->Placement.getValue().getPosition().x, -3.0);
    EXPECT_NEAR(second->Placement.getValue().getPosition().x, 6.0, 0.05);
    EXPECT_NEAR(dragged->Placement.getValue().getPosition().x, 16.0, 1e-9);
}

TEST_F(AssemblyObjectTest, contactSetsGateDraggingAndRespectExclusions)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();
    const auto box = [&](const char* name, double x) {
        auto* object = doc->addObject<Part::Box>(name);
        object->Length.setValue(10);
        object->Width.setValue(10);
        object->Height.setValue(10);
        object->Placement.setValue(Base::Placement(Base::Vector3d(x,0,0),Base::Rotation()));
        object->execute();
        assembly->addObject(object);
        return object;
    };
    auto* first = box("First", 0);
    auto* second = box("Second", 11);
    auto* other = box("Other", 50);
    auto* group = doc->addObject<Assembly::SimulationGroup>("Simulations");
    assembly->addObject(group);
    auto* contact = doc->addObject("App::FeaturePython", "ContactSet");
    group->addObject(contact);
    contact->addDynamicProperty("App::PropertyString", "ContactType");
    auto* mode = static_cast<App::PropertyEnumeration*>(contact->addDynamicProperty("App::PropertyEnumeration", "Mode"));
    mode->setEnums({"Within a component set"});
    contact->addDynamicProperty("App::PropertyBool", "Suppressed");
    contact->addDynamicProperty("App::PropertyBool", "FrictionEnabled");
    auto* members = static_cast<App::PropertyLinkList*>(contact->addDynamicProperty("App::PropertyLinkListGlobal", "ComponentsI"));
    members->setValues({first, second});
    auto* endpoints = static_cast<App::PropertyLinkList*>(contact->addDynamicProperty("App::PropertyLinkListHidden", "ExcludedPair_0"));
    auto* exclusions = static_cast<App::PropertyStringList*>(contact->addDynamicProperty("App::PropertyStringList", "ExcludedPairs"));
    EXPECT_TRUE(assembly->requiresContactSolveForMove({first}));
    EXPECT_FALSE(assembly->requiresContactSolveForMove({other}));
    endpoints->setValues({first, second});
    exclusions->setValues(std::vector<std::string>{"ExcludedPair_0"});
    EXPECT_FALSE(assembly->requiresContactSolveForMove({first}));
    exclusions->setValues(std::vector<std::string>{});
    const auto previous = first->Placement.getValue();
    first->Placement.setValue(Base::Placement(Base::Vector3d(6,0,0),Base::Rotation()));
    assembly->resolveContactMove({first}, {{first, previous}});
    EXPECT_GE(second->Placement.getValue().getPosition().x, 15.9);
    EXPECT_DOUBLE_EQ(other->Placement.getValue().getPosition().x, 50);
}
