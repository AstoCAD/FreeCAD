// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include <cstdio>
#include <fstream>

#include "App/Application.h"
#include "App/Document.h"
#include "App/DocumentObject.h"
#include "App/MergeDocuments.h"
#include "App/PropertyStandard.h"
#include "App/StringHasher.h"
#include "Base/Writer.h"
#include <src/App/InitApplication.h>

using ::testing::Eq;
using ::testing::Ne;

// NOLINTBEGIN(readability-magic-numbers)

class FakeWriter: public Base::Writer
{
    void writeFiles() override
    {}
    std::ostream& Stream() override
    {
        return std::cout;
    }
};

class DocumentTest: public ::testing::Test
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
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_docName.c_str());
    }

    App::Document* doc()
    {
        return _doc;
    }

private:
    std::string _docName;
    App::Document* _doc {};
};


TEST_F(DocumentTest, addStringHasherIndicatesUnwrittenWhenNew)
{
    // Arrange
    App::StringHasherRef hasher(new App::StringHasher);

    // Act
    auto addResult = doc()->addStringHasher(hasher);

    // Assert
    EXPECT_TRUE(addResult.first);
    EXPECT_THAT(addResult.second, Ne(-1));
}

TEST_F(DocumentTest, addStringHasherIndicatesAlreadyWritten)
{
    // Arrange
    App::StringHasherRef hasher(new App::StringHasher);
    doc()->addStringHasher(hasher);

    // Act
    auto addResult = doc()->addStringHasher(hasher);

    // Assert
    EXPECT_FALSE(addResult.first);
}

TEST_F(DocumentTest, getStringHasherGivesExpectedHasher)
{
    // Arrange
    App::StringHasherRef hasher(new App::StringHasher);
    auto pair = doc()->addStringHasher(hasher);
    int index = pair.second;

    // Act
    auto foundHasher = doc()->getStringHasher(index);

    // Assert
    EXPECT_EQ(hasher, foundHasher);
}

TEST_F(DocumentTest, importObjectsRestoresSourceStringHasher)
{
    // Arrange
    auto& app = App::GetApplication();
    const std::string sourceName = app.getUniqueDocumentName("MergeSource");
    App::Document* source = app.newDocument(sourceName.c_str(), "testUser");
    App::StringHasherRef sourceHasher = source->getStringHasher();
    ASSERT_TRUE(sourceHasher);
    sourceHasher->setSaveAll(true);
    sourceHasher->getID("persisted element name");

    const std::string path = App::Application::getTempFileName();
    ASSERT_TRUE(source->saveAs(path.c_str()));
    const std::string savedPath = source->getFileName();
    app.closeDocument(sourceName.c_str());

    std::size_t restoredStringCount = 0;
    auto connection = doc()->signalFinishImportObjects.connect(
        [this, &restoredStringCount](const std::vector<App::DocumentObject*>&) {
            App::StringHasherRef importedHasher = doc()->getStringHasher(0);
            restoredStringCount = importedHasher ? importedHasher->size() : 0;
        }
    );

    // Act
    std::ifstream stream(savedPath, std::ios::in | std::ios::binary);
    ASSERT_TRUE(stream.is_open());
    App::MergeDocuments merge(doc());
    merge.importObjects(stream);

    // Assert
    EXPECT_GT(restoredStringCount, 0);
    connection.disconnect();
    std::remove(savedPath.c_str());
}

TEST_F(DocumentTest, undoRedoRemovesAndRestoresAddedLockedDynamicProperty)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/32285
    auto* object = doc()->addObject("App::FeatureTest", "Feature");
    ASSERT_NE(object, nullptr);
    object->Label.setValue("Unrelated label");
    doc()->clearUndos();

    doc()->openTransaction("Add locked property");
    auto* property = dynamic_cast<App::PropertyInteger*>(
        object->addDynamicProperty("App::PropertyInteger", "LockedInteger")
    );
    ASSERT_NE(property, nullptr);
    property->setValue(123);
    property->setStatus(App::Property::LockDynamic, true);
    doc()->commitTransaction();

    for (int cycle = 0; cycle < 3; ++cycle) {
        SCOPED_TRACE(cycle);
        ASSERT_TRUE(doc()->undo());
        ASSERT_EQ(object->getDynamicPropertyByName("LockedInteger"), nullptr);
        EXPECT_STREQ(object->Label.getValue(), "Unrelated label");

        ASSERT_TRUE(doc()->redo());
        auto* restored = dynamic_cast<App::PropertyInteger*>(
            object->getDynamicPropertyByName("LockedInteger")
        );
        ASSERT_NE(restored, nullptr);
        EXPECT_EQ(restored->getValue(), 123);
        EXPECT_TRUE(restored->testStatus(App::Property::LockDynamic));
        EXPECT_STREQ(object->Label.getValue(), "Unrelated label");
    }
}

TEST_F(DocumentTest, abortRemovesAddedLockedDynamicProperty)
{
    auto* object = doc()->addObject("App::FeatureTest", "Feature");
    ASSERT_NE(object, nullptr);
    object->Label.setValue("Unrelated label");
    doc()->clearUndos();

    doc()->openTransaction("Add locked property");
    auto* property = dynamic_cast<App::PropertyInteger*>(
        object->addDynamicProperty("App::PropertyInteger", "LockedInteger")
    );
    ASSERT_NE(property, nullptr);
    property->setValue(123);
    property->setStatus(App::Property::LockDynamic, true);
    doc()->abortTransaction();

    EXPECT_EQ(object->getDynamicPropertyByName("LockedInteger"), nullptr);
    EXPECT_EQ(doc()->getObject("Feature"), object);
    EXPECT_STREQ(object->Label.getValue(), "Unrelated label");
}

TEST_F(DocumentTest, ordinaryRemovalOfLockedDynamicPropertyRemainsDenied)
{
    auto* object = doc()->addObject("App::FeatureTest", "Feature");
    ASSERT_NE(object, nullptr);
    object->Label.setValue("Original label");
    auto* property = dynamic_cast<App::PropertyInteger*>(
        object->addDynamicProperty("App::PropertyInteger", "LockedInteger")
    );
    ASSERT_NE(property, nullptr);
    property->setValue(123);
    property->setStatus(App::Property::LockDynamic, true);
    doc()->clearUndos();

    EXPECT_FALSE(object->removeDynamicProperty("LockedInteger"));
    EXPECT_EQ(object->getDynamicPropertyByName("LockedInteger"), property);

    doc()->openTransaction("Change unrelated label");
    object->Label.setValue("Changed label");
    EXPECT_FALSE(object->removeDynamicProperty("LockedInteger"));
    doc()->commitTransaction();
    EXPECT_EQ(object->getDynamicPropertyByName("LockedInteger"), property);
    ASSERT_TRUE(doc()->undo());
    EXPECT_STREQ(object->Label.getValue(), "Original label");
    EXPECT_EQ(object->getDynamicPropertyByName("LockedInteger"), property);
    ASSERT_TRUE(doc()->redo());
    EXPECT_STREQ(object->Label.getValue(), "Changed label");
    EXPECT_EQ(object->getDynamicPropertyByName("LockedInteger"), property);
    EXPECT_EQ(property->getValue(), 123);
    EXPECT_TRUE(property->testStatus(App::Property::LockDynamic));
}

// NOLINTEND(readability-magic-numbers)
