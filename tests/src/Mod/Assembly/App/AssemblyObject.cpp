// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <FCConfig.h>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObjectGroup.h>
#include <App/Part.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <App/Expression.h>
#include <App/ObjectIdentifier.h>
#include <Mod/Assembly/App/AssemblyObject.h>
#include <Mod/Assembly/App/AssemblyUtils.h>
#include <Mod/Part/App/FeaturePartBox.h>
#include <Mod/Assembly/App/Groups.h>
#include <src/App/InitApplication.h>

class AssemblyObjectTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _docName = App::GetApplication().getUniqueDocumentName("test");
        auto _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
        _assemblyObj = _doc->addObject<Assembly::AssemblyObject>();
        _jointGroupObj = _assemblyObj->addObject<Assembly::JointGroup>("jointGroupTest");
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

