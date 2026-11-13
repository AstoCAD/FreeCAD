// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>
#include <algorithm>
#include <limits>
#include <string>
#include <vector>

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
#include <App/PropertyPythonObject.h>
#include <Base/Console.h>
#include <Base/Interpreter.h>
#include <Mod/Assembly/App/ContactGeometry.h>
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepPrimAPI_MakeSphere.hxx>
#include <BRepAlgoAPI_Cut.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepBuilderAPI_Transform.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <gp_Ax2.hxx>
#include <gp_Pln.hxx>
#include <gp_Trsf.hxx>
#include <Mod/Assembly/App/AssemblyObject.h>
#include <Mod/Assembly/App/BomObject.h>
#include <Mod/Assembly/App/AssemblyUtils.h>
#include <Mod/Assembly/App/Groups.h>
#include <Mod/Part/App/FeaturePartBox.h>
#include <Mod/Part/App/PartFeature.h>
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

TEST(ContactGeometry, MirroredFacesKeepOutwardSampleNormals)
{
    const auto plate = BRepPrimAPI_MakeBox(gp_Pnt(-50, -50, -10), 100, 100, 10).Shape();
    const auto cube = BRepPrimAPI_MakeBox(gp_Pnt(0, -5, -1), 10, 10, 10).Shape();
    gp_Trsf mirror;
    mirror.SetMirror(gp_Ax2(gp_Pnt(), gp_Dir(1, 0, 0)));
    const auto mirrored = BRepBuilderAPI_Transform(cube, mirror, true).Shape();
    for (const auto& resting : {cube, mirrored}) {
        BRepMesh_IncrementalMesh(resting, 0.1);
        BRepMesh_IncrementalMesh(plate, 0.1);
        Assembly::ContactGeometry geometry(resting, plate);
        // The cube penetrates the plate by 1 mm. Its bottom face samples
        // carry the area, so the weighted support covers the 10 x 10 face.
        double area = 0;
        for (const auto& contact : geometry.points({}, {})) {
            if (contact.weight > 0) {
                area += contact.weight;
                EXPECT_NEAR(contact.normal.z, 1, 1e-9);
                EXPECT_NEAR(contact.penetration, 1, 1e-6);
            }
        }
        EXPECT_NEAR(area, 100, 1e-6);
    }
}

TEST(ContactGeometry, ClearanceHasNoContactWhileThinCrossingSolidsDo)
{
    const auto outer = BRepPrimAPI_MakeBox(gp_Pnt(-1, -5, -5), 2, 10, 10).Shape();
    const auto hole = BRepPrimAPI_MakeBox(gp_Pnt(-2, -2, -2), 4, 4, 4).Shape();
    const auto bore = BRepAlgoAPI_Cut(outer, hole).Shape();
    const auto shaft = BRepPrimAPI_MakeBox(gp_Pnt(-3, -1, -1), 6, 2, 2).Shape();
    // No quadrature point of these crossing plates lies inside the other plate.
    const auto first = BRepPrimAPI_MakeBox(gp_Pnt(-5, -0.05, -5), 10, 0.1, 10).Shape();
    const auto second = BRepPrimAPI_MakeBox(gp_Pnt(-0.05, -5, -5), 0.1, 10, 10).Shape();
    for (const auto& shape : {bore, shaft, first, second}) {
        BRepMesh_IncrementalMesh(shape, 0.1);
    }
    EXPECT_TRUE(Assembly::ContactGeometry(shaft, bore).points({}, {}).empty());
    EXPECT_FALSE(Assembly::ContactGeometry(first, second).points({}, {}).empty());
}

class AssemblyObjectTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
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

TEST_F(AssemblyObjectTest, partBoxFixtureUsesRegisteredFeatureHierarchy)
{
    const auto classType = Part::Box::getClassTypeId();
    const auto registeredType = Base::Type::fromName("Part::Box");
    EXPECT_EQ(classType, registeredType);
    EXPECT_TRUE(classType.isDerivedFrom(Part::Feature::getClassTypeId()));
    EXPECT_TRUE(registeredType.isDerivedFrom(Part::Feature::getClassTypeId()));
    EXPECT_TRUE(registeredType.isDerivedFrom(App::DocumentObject::getClassTypeId()));
}

TEST_F(AssemblyObjectTest, bomMirrorDetectionUsesActualLinkScaleVector)
{
    auto* doc = getObject()->getDocument();
    auto* bom = doc->addObject<Assembly::BomObject>("Bom");
    auto* link = doc->addObject<App::Link>("ComponentLink");
    EXPECT_FALSE(bom->isObjMirrored(link));

    link->Scale.setValue(-1.0);
    EXPECT_TRUE(bom->isObjMirrored(link));
    link->ScaleVector.setValue(-1.0, -1.0, 1.0);
    EXPECT_EQ(link->Scale.getValue(), -1.0);
    EXPECT_FALSE(bom->isObjMirrored(link));

    link->Scale.setValue(1.0);
    link->ScaleVector.setValue(-1.0, 2.0, 3.0);
    EXPECT_EQ(link->Scale.getValue(), 1.0);
    EXPECT_TRUE(bom->isObjMirrored(link));
}

TEST_F(AssemblyObjectTest, bomMirrorDetectionHandlesPlainObjectsAndUnownedElements)
{
    auto* doc = getObject()->getDocument();
    auto* bom = doc->addObject<Assembly::BomObject>("Bom");
    auto* plain = doc->addObject<App::DocumentObject>("Plain");
    EXPECT_FALSE(bom->isObjMirrored(nullptr));
    EXPECT_FALSE(bom->isObjMirrored(plain));

    auto* element = doc->addObject<App::LinkElement>("UnownedElement");
    ASSERT_EQ(element->getLinkGroup(), nullptr);
    element->ScaleVector.setValue(-1.0, 1.0, 1.0);
    EXPECT_TRUE(bom->isObjMirrored(element));
    element->ScaleVector.setValue(-1.0, -1.0, 1.0);
    EXPECT_FALSE(bom->isObjMirrored(element));
    element->Scale.setValue(-1.0);
    EXPECT_TRUE(bom->isObjMirrored(element));
}

TEST_F(AssemblyObjectTest, bomMirrorDetectionCombinesArrayElementAndOwnerReflections)
{
    auto* doc = getObject()->getDocument();
    auto* bom = doc->addObject<Assembly::BomObject>("Bom");
    auto* source = doc->addObject<App::DocumentObject>("Source");
    auto* array = doc->addObject<App::Link>("Array");
    array->LinkedObject.setValue(source);
    array->ElementCount.setValue(2);
    array->ShowElement.setValue(true);
    doc->recompute();
    const auto elements = array->ElementList.getValues();
    ASSERT_EQ(elements.size(), 2);
    auto* element = dynamic_cast<App::LinkElement*>(elements.front());
    ASSERT_NE(element, nullptr);
    ASSERT_EQ(element->getLinkGroup(), array);

    element->ScaleVector.setValue(-1.0, 1.0, 1.0);
    EXPECT_TRUE(bom->isObjMirrored(element));
    array->ScaleVector.setValue(1.0, -1.0, 1.0);
    EXPECT_FALSE(bom->isObjMirrored(element));

    element->ScaleVector.setValue(-1.0, -1.0, 1.0);
    EXPECT_TRUE(bom->isObjMirrored(element));
    array->ScaleVector.setValue(1.0, -1.0, -1.0);
    EXPECT_FALSE(bom->isObjMirrored(element));

    element->ScaleVector.setValue(0.0, -1.0, 1.0);
    EXPECT_FALSE(bom->isObjMirrored(element));
}

TEST_F(AssemblyObjectTest, bomMirrorDetectionUsesSignWithoutMagnitudeOverflowOrUnderflow)
{
    auto* doc = getObject()->getDocument();
    auto* bom = doc->addObject<Assembly::BomObject>("Bom");
    auto* link = doc->addObject<App::Link>("ComponentLink");
    link->ScaleVector.setValue(-1e-200, 1e-200, 1e-200);
    EXPECT_TRUE(bom->isObjMirrored(link));
    link->ScaleVector.setValue(-1e200, 1e200, 1e200);
    EXPECT_TRUE(bom->isObjMirrored(link));
    link->ScaleVector.setValue(-1e200, -1e200, 1e200);
    EXPECT_FALSE(bom->isObjMirrored(link));
    link->ScaleVector.setValue(-1.0, 0.0, 1.0);
    EXPECT_FALSE(bom->isObjMirrored(link));
    link->ScaleVector.setValue(-1.0, std::numeric_limits<double>::quiet_NaN(), 1.0);
    EXPECT_FALSE(bom->isObjMirrored(link));
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

TEST_F(AssemblyObjectTest, dragContactPropagatesThroughComponentsVisitedEarlier)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();

    auto addBox = [&](const char* name, double x) {
        auto* box = doc->addObject<Part::Box>(name);
        box->Length.setValue(10.0);
        box->Width.setValue(10.0);
        box->Height.setValue(10.0);
        box->execute();
        box->Placement.setValue(Base::Placement(Base::Vector3d(x, 0, 0), Base::Rotation()));
        assembly->addObject(box);
        return box;
    };

    auto* first = addBox("First", 0.0);
    auto* second = addBox("Second", 11.0);
    auto* dragged = addBox("Dragged", 22.0);
    ASSERT_DOUBLE_EQ(first->Placement.getValue().getPosition().x, 0.0);
    ASSERT_DOUBLE_EQ(second->Placement.getValue().getPosition().x, 11.0);
    ASSERT_DOUBLE_EQ(dragged->Placement.getValue().getPosition().x, 22.0);

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
    auto* group = doc->addObject<Assembly::SimulationGroup>("Simulations");
    assembly->addObject(group);
    group->addObject(contact);
    ASSERT_EQ(assembly->getContacts(), std::vector<App::DocumentObject*> {contact});
    ASSERT_TRUE(assembly->requiresContactSolveForMove({dragged}));

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
        object->execute();
        object->Placement.setValue(Base::Placement(Base::Vector3d(x,0,0),Base::Rotation()));
        assembly->addObject(object);
        return object;
    };
    auto* first = box("First", 0);
    auto* second = box("Second", 11);
    auto* other = box("Other", 50);
    ASSERT_DOUBLE_EQ(first->Placement.getValue().getPosition().x, 0.0);
    ASSERT_DOUBLE_EQ(second->Placement.getValue().getPosition().x, 11.0);
    ASSERT_DOUBLE_EQ(other->Placement.getValue().getPosition().x, 50.0);
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

namespace
{
class ContactWarningCollector final: public Base::ILogger
{
public:
    void sendLog(
        const std::string& /*notifiername*/,
        const std::string& msg,
        Base::LogStyle level,
        Base::IntendedRecipient /*recipient*/,
        Base::ContentType /*content*/
    ) override
    {
        if (level == Base::LogStyle::Warning) {
            warnings.push_back(msg);
        }
    }

    const char* name() override
    {
        return "AssemblyContactWarningCollector";
    }

    std::vector<std::string> warnings;
};
}  // namespace

TEST_F(AssemblyObjectTest, dragReportsANonSolidContactComponentOnce)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();
    auto* box = doc->addObject<Part::Box>("Box");
    box->execute();
    box->Placement.setValue(Base::Placement(Base::Vector3d(0, 0, 50), Base::Rotation()));
    assembly->addObject(box);
    // A sheet is not construction geometry: general contact refuses it.
    // A name of its own: the once-per-message report is process wide.
    auto* sheet = doc->addObject<Part::Feature>("DragNonSolidSheet");
    sheet->Shape.setValue(BRepBuilderAPI_MakeFace(gp_Pln(), -50, 50, -50, 50).Shape());
    assembly->addObject(sheet);

    auto* contact = doc->addObject("App::FeaturePython", "GeneralContact");
    contact->addDynamicProperty("App::PropertyString", "ContactType");
    auto* mode = static_cast<App::PropertyEnumeration*>(
        contact->addDynamicProperty("App::PropertyEnumeration", "Mode")
    );
    mode->setEnums({"Between two components", "General collision detection"});
    mode->setValue("General collision detection");
    contact->addDynamicProperty("App::PropertyBool", "Suppressed");
    contact->addDynamicProperty("App::PropertyBool", "FrictionEnabled");
    auto* group = doc->addObject<Assembly::SimulationGroup>("Simulations");
    assembly->addObject(group);
    group->addObject(contact);

    ContactWarningCollector collector;
    Base::Console().attachObserver(&collector);
    try {
        // Two mouse moves.
        for (double z : {45.0, 40.0}) {
            const auto previous = box->Placement.getValue();
            box->Placement.setValue(Base::Placement(Base::Vector3d(0, 0, z), Base::Rotation()));
            assembly->resolveContactMove({box}, {{box, previous}});
        }
    }
    catch (...) {
        Base::Console().detachObserver(&collector);
        throw;
    }
    Base::Console().detachObserver(&collector);
    const auto aboutSheet = std::ranges::count_if(collector.warnings, [&](const std::string& text) {
        return text.find(sheet->getFullName()) != std::string::npos;
    });
    EXPECT_EQ(aboutSheet, 1);
    EXPECT_NEAR(box->Placement.getValue().getPosition().z, 40, 1e-9);
}

TEST_F(AssemblyObjectTest, frameQueriesWithoutSolverSystem)  // NOLINT
{
    auto* assembly = getObject();
    auto* box = assembly->getDocument()->addObject<Part::Box>("Free");
    box->execute();
    assembly->addObject(box);

    // An island drag with no joint or contact to solve drops the solver system.
    assembly->preDrag({box});
    EXPECT_EQ(assembly->numberOfFrames(), 0U);
    EXPECT_EQ(assembly->updateForFrame(0), -1);
    assembly->postDrag();
}

// https://github.com/FreeCAD/FreeCAD/issues/33405
// Dragging must not run drag steps or postDrag on the half-built solver system left by a
// failed solve: postDrag used to rethrow the solver error out of the GUI event handler.
TEST_F(AssemblyObjectTest, dragAfterFailedSolveDoesNotThrow)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();
    auto* joints = assembly->getJointGroup();
    ASSERT_NE(joints, nullptr);

    Base::Interpreter().runString(
        "class _AssemblyDragTestJointProxy:\n"
        "    def setJointConnectors(self, *args):\n"
        "        pass\n"
        "_assemblyDragTestJointProxy = _AssemblyDragTestJointProxy()\n"
    );

    const auto box = [&](const char* name, double x) {
        auto* object = doc->addObject<Part::Box>(name);
        object->execute();
        object->Placement.setValue(Base::Placement(Base::Vector3d(x, 0, 0), Base::Rotation()));
        assembly->addObject(object);
        return object;
    };
    auto* ground = box("Ground", 0);
    auto* gear1 = box("Gear1", 0);
    auto* gear2 = box("Gear2", 20);

    auto* grounding = doc->addObject("App::FeaturePython", "GroundedJoint");
    joints->addObject(grounding);
    static_cast<App::PropertyLink*>(
        grounding->addDynamicProperty("App::PropertyLink", "ObjectToGround")
    )->setValue(ground);
    // The grounded joint proxy marks the placement read-only; that is what grounds the part.
    ground->Placement.setStatus(App::Property::ReadOnly, true);

    const auto addJoint = [&](const char* name,
                              Assembly::JointType type,
                              App::DocumentObject* first,
                              App::DocumentObject* second,
                              const Base::Vector3d& firstPosition) {
        auto* joint = doc->addObject("App::FeaturePython", name);
        joints->addObject(joint);
        auto* jointType = static_cast<App::PropertyEnumeration*>(
            joint->addDynamicProperty("App::PropertyEnumeration", "JointType")
        );
        jointType->setEnums({"Fixed",
                             "Revolute",
                             "Cylindrical",
                             "Slider",
                             "Ball",
                             "Distance",
                             "Parallel",
                             "Perpendicular",
                             "Angle",
                             "RackPinion",
                             "Screw",
                             "Gears",
                             "Belt"});
        jointType->setValue(static_cast<long>(type));
        joint->addDynamicProperty("App::PropertyBool", "Suppressed");
        joint->addDynamicProperty("App::PropertyFloat", "Distance");
        joint->addDynamicProperty("App::PropertyFloat", "Distance2");
        static_cast<App::PropertyXLinkSub*>(
            joint->addDynamicProperty("App::PropertyXLinkSub", "Reference1")
        )->setValue(first, std::vector<std::string> {""});
        static_cast<App::PropertyXLinkSub*>(
            joint->addDynamicProperty("App::PropertyXLinkSub", "Reference2")
        )->setValue(second, std::vector<std::string> {""});
        static_cast<App::PropertyPlacement*>(
            joint->addDynamicProperty("App::PropertyPlacement", "Placement1")
        )->setValue(Base::Placement(firstPosition, Base::Rotation()));
        joint->addDynamicProperty("App::PropertyPlacement", "Placement2");
        Base::PyGILStateLocker lock;
        joint->getPropertyByName<App::PropertyPythonObject>("Proxy")->setValue(
            Py::Module("__main__").getAttr("_assemblyDragTestJointProxy")
        );
        return joint;
    };
    addJoint("Revolute1", Assembly::JointType::Revolute, ground, gear1, Base::Vector3d(0, 0, 0));
    addJoint("Revolute2", Assembly::JointType::Revolute, ground, gear2, Base::Vector3d(20, 0, 0));
    auto* gear = addJoint("Gear", Assembly::JointType::Gears, gear1, gear2, Base::Vector3d());
    auto* radius1 = gear->getPropertyByName<App::PropertyFloat>("Distance");
    auto* radius2 = gear->getPropertyByName<App::PropertyFloat>("Distance2");
    radius1->setValue(10.0);
    radius2->setValue(10.0);

    ASSERT_EQ(assembly->getJoints().size(), 3U);
    ASSERT_TRUE(assembly->isPartConnected(gear1));
    ASSERT_EQ(assembly->solve(), 0);

    // A zero gear radius makes the solver throw while building the system.
    radius1->setValue(0.0);
    const Base::Placement before1 = gear1->Placement.getValue();
    const Base::Placement before2 = gear2->Placement.getValue();

    EXPECT_NO_THROW(assembly->preDrag({gear1}));
    EXPECT_EQ(assembly->getLastSolverStatus(), -1);
    gear1->Placement.setValue(
        Base::Placement(Base::Vector3d(), Base::Rotation(Base::Vector3d(0, 0, 1), 0.1))
    );
    EXPECT_NO_THROW(assembly->doDragStep());
    EXPECT_NO_THROW(assembly->postDrag());
    EXPECT_TRUE(gear2->Placement.getValue().isSame(before2));

    // Dragging works again once the joint is valid.
    gear1->Placement.setValue(before1);
    radius1->setValue(10.0);
    EXPECT_NO_THROW(assembly->preDrag({gear1}));
    EXPECT_EQ(assembly->getLastSolverStatus(), 0);
    EXPECT_NO_THROW(assembly->postDrag());
}

// An ungrounded island is dragged through the solver (prepareMbdForIslandDrag): the dragged
// part is a drag target although it is neither connected to ground nor rigid-clustered, so
// the part jointed to it follows.
TEST_F(AssemblyObjectTest, ungroundedIslandFollowsTheDraggedPart)  // NOLINT
{
    auto* assembly = getObject();
    auto* doc = assembly->getDocument();
    auto* joints = assembly->getJointGroup();
    ASSERT_NE(joints, nullptr);

    Base::Interpreter().runString(
        "class _AssemblyIslandTestJointProxy:\n"
        "    def setJointConnectors(self, *args):\n"
        "        pass\n"
        "_assemblyIslandTestJointProxy = _AssemblyIslandTestJointProxy()\n"
    );

    const auto box = [&](const char* name, double x) {
        auto* object = doc->addObject<Part::Box>(name);
        object->execute();
        object->Placement.setValue(Base::Placement(Base::Vector3d(x, 0, 0), Base::Rotation()));
        assembly->addObject(object);
        return object;
    };
    auto* dragged = box("Dragged", 0);
    auto* follower = box("Follower", 20);

    auto* joint = doc->addObject("App::FeaturePython", "Revolute");
    joints->addObject(joint);
    auto* jointType = static_cast<App::PropertyEnumeration*>(
        joint->addDynamicProperty("App::PropertyEnumeration", "JointType")
    );
    jointType->setEnums({"Fixed",
                         "Revolute",
                         "Cylindrical",
                         "Slider",
                         "Ball",
                         "Distance",
                         "Parallel",
                         "Perpendicular",
                         "Angle",
                         "RackPinion",
                         "Screw",
                         "Gears",
                         "Belt"});
    jointType->setValue(static_cast<long>(Assembly::JointType::Revolute));
    joint->addDynamicProperty("App::PropertyBool", "Suppressed");
    joint->addDynamicProperty("App::PropertyFloat", "Distance");
    joint->addDynamicProperty("App::PropertyFloat", "Distance2");
    static_cast<App::PropertyXLinkSub*>(
        joint->addDynamicProperty("App::PropertyXLinkSub", "Reference1")
    )->setValue(dragged, std::vector<std::string> {""});
    static_cast<App::PropertyXLinkSub*>(
        joint->addDynamicProperty("App::PropertyXLinkSub", "Reference2")
    )->setValue(follower, std::vector<std::string> {""});
    // Both connectors sit at (20, 0, 0) in the assembly: the joint is satisfied as built.
    static_cast<App::PropertyPlacement*>(
        joint->addDynamicProperty("App::PropertyPlacement", "Placement1")
    )->setValue(Base::Placement(Base::Vector3d(20, 0, 0), Base::Rotation()));
    joint->addDynamicProperty("App::PropertyPlacement", "Placement2");
    {
        Base::PyGILStateLocker lock;
        joint->getPropertyByName<App::PropertyPythonObject>("Proxy")->setValue(
            Py::Module("__main__").getAttr("_assemblyIslandTestJointProxy")
        );
    }

    ASSERT_EQ(assembly->getJoints().size(), 1U);
    ASSERT_FALSE(assembly->isPartConnected(dragged));

    assembly->preDrag({dragged});
    dragged->Placement.setValue(Base::Placement(Base::Vector3d(0, 5, 0), Base::Rotation()));
    assembly->doDragStep();
    assembly->postDrag();

    // The drag step holds the dragged part near the requested position and lets it turn;
    // the follower is solved to keep the revolute connectors together.
    const Base::Placement draggedPlc = dragged->Placement.getValue();
    EXPECT_NEAR(draggedPlc.getPosition().y, 5.0, 1e-3);
    Base::Vector3d connector1;
    draggedPlc.multVec(Base::Vector3d(20, 0, 0), connector1);
    const Base::Vector3d connector2 = follower->Placement.getValue().getPosition();
    EXPECT_LT((connector1 - connector2).Length(), 1e-6);
    EXPECT_GT((connector2 - Base::Vector3d(20, 0, 0)).Length(), 0.1);
}
