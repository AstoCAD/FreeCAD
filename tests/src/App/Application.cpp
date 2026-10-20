// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>
#include <filesystem>
#include <memory>
#include <set>
#include <vector>
#include "App/Application.h"
#include "App/Document.h"
#include "App/DocumentObjectGroup.h"
#include "App/Link.h"
#include "Base/FileInfo.h"
#include "Base/Exception.h"
#include <src/TempDirectory.h>

#define FC_OS_MACOSX 1
#include "App/ProgramOptionsUtilities.h"
#include <src/App/InitApplication.h>


using namespace App::Util;

using Spr = std::pair<std::string, std::string>;


class ApplicationTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }
};

TEST_F(ApplicationTest, fCustomSyntaxLookup)
{
    Spr res {customSyntax("-display")};
    Spr exp {"display", "null"};
    EXPECT_EQ(res, exp);
};
TEST_F(ApplicationTest, fCustomSyntaxMac)
{
    Spr res {customSyntax("-psn_stuff")};
    Spr exp {"psn", "stuff"};
    EXPECT_EQ(res, exp);
};
TEST_F(ApplicationTest, fCustomSyntaxWidgetCount)
{
    Spr res {customSyntax("-widgetcount")};
    Spr exp {"widgetcount", ""};
    EXPECT_EQ(res, exp);
}
TEST_F(ApplicationTest, fCustomSyntaxNotFound)
{
    Spr res {customSyntax("-displayx")};
    Spr exp {"", ""};
    EXPECT_EQ(res, exp);
};
TEST_F(ApplicationTest, fCustomSyntaxAmpersand)
{
    Spr res {customSyntax("@freddie")};
    Spr exp {"response-file", "freddie"};
    EXPECT_EQ(res, exp);
};
TEST_F(ApplicationTest, fCustomSyntaxEmptyIn)
{
    Spr res {customSyntax("")};
    Spr exp {"", ""};
    EXPECT_EQ(res, exp);
};

class ApplicationDocumentPathTest: public ApplicationTest
{
protected:
    void SetUp() override
    {
        _originalDirectory = std::filesystem::current_path();
        auto& app = App::GetApplication();
        for (auto* doc : app.getDocuments()) {
            _initialDocuments.insert(doc->getName());
        }
        if (auto* active = app.getActiveDocument()) {
            _previousActiveDocument = active->getName();
        }
        _storage = std::make_unique<tests::TempDirectory>("fc28683");
        std::filesystem::create_directories(_storage->path() / "source");
        std::filesystem::create_directories(_storage->path() / "owner");
        _sourceFile = (_storage->path() / "source" / "box.FCStd").lexically_normal();
        _ownerFile = (_storage->path() / "owner" / "owner.FCStd").lexically_normal();

        auto name = app.getUniqueDocumentName("DocumentPathSource");
        auto* source = app.newDocument(name.c_str());
        ASSERT_NE(source, nullptr);
        ASSERT_NE(source->addObject<App::DocumentObjectGroup>("Target"), nullptr);
        ASSERT_TRUE(source->saveAs(Base::FileInfo::pathToString(_sourceFile).c_str()));
        app.closeDocument(name.c_str());
    }

    void TearDown() override
    {
        auto& app = App::GetApplication();
        std::vector<std::string> names;
        for (auto* doc : app.getDocuments()) {
            if (!_initialDocuments.contains(doc->getName())) {
                names.emplace_back(doc->getName());
            }
        }
        // This includes source documents automatically reopened through an XLink.
        for (auto it = names.rbegin(); it != names.rend(); ++it) {
            app.closeDocument(it->c_str());
        }
        if (auto* previous = app.getDocument(_previousActiveDocument.c_str())) {
            app.setActiveDocument(previous);
        }
        std::error_code error;
        std::filesystem::current_path(_originalDirectory, error);
        EXPECT_FALSE(error) << error.message();
        _storage.reset();
    }

    void checkExternalLinkPersistence(App::Document* source, bool changeDirectory)
    {
        auto& app = App::GetApplication();
        auto* target = source->getObject("Target");
        ASSERT_NE(target, nullptr);
        auto ownerName = app.getUniqueDocumentName("DocumentPathOwner");
        auto* owner = app.newDocument(ownerName.c_str());
        ASSERT_NE(owner, nullptr);
        ASSERT_TRUE(owner->saveAs(Base::FileInfo::pathToString(_ownerFile).c_str()));
        if (changeDirectory) {
            std::filesystem::current_path(_ownerFile.parent_path());
        }
        auto* link = owner->addObject<App::Link>("Link");
        ASSERT_NE(link, nullptr);
        ASSERT_NO_THROW(link->setLink(-1, target));
        ASSERT_EQ(link->getLinkedObject(), target);
        ASSERT_TRUE(owner->save());
        const std::string sourceName = source->getName();
        app.closeDocument(ownerName.c_str());
        app.closeDocument(sourceName.c_str());

        auto* reopened = app.openDocument(Base::FileInfo::pathToString(_ownerFile).c_str());
        ASSERT_NE(reopened, nullptr);
        auto* restoredLink = freecad_cast<App::Link*>(reopened->getObject("Link"));
        ASSERT_NE(restoredLink, nullptr);
        auto* restoredTarget = restoredLink->getLinkedObject();
        ASSERT_NE(restoredTarget, nullptr);
        EXPECT_STREQ(restoredTarget->getNameInDocument(), "Target");
        EXPECT_EQ(
            Base::FileInfo::stringToPath(restoredTarget->getDocument()->getFileName()),
            _sourceFile
        );
    }

    std::filesystem::path _sourceFile;
    std::filesystem::path _ownerFile;
    std::unique_ptr<tests::TempDirectory> _storage;

private:
    std::filesystem::path _originalDirectory;
    std::set<std::string> _initialDocuments;
    std::string _previousActiveDocument;
};

TEST_F(ApplicationDocumentPathTest, relativeCommandLineOpenKeepsAbsoluteSourcePath)
{
    // Regression: https://github.com/FreeCAD/FreeCAD/issues/28683
    std::filesystem::current_path(_sourceFile.parent_path());
    const auto processed = App::Application::processFiles({"box.FCStd"});
    ASSERT_EQ(processed, (std::list<std::string> {"box.FCStd"}));
    auto* source = App::GetApplication().getActiveDocument();
    ASSERT_NE(source, nullptr);
    const auto registered = Base::FileInfo::stringToPath(source->getFileName());
    ASSERT_TRUE(registered.is_absolute()) << source->getFileName();
    EXPECT_EQ(registered, _sourceFile);
    checkExternalLinkPersistence(source, false);
}

TEST_F(ApplicationDocumentPathTest, relativeOpenReusesAbsolutePathAcrossWorkingDirectoryChange)
{
    auto& app = App::GetApplication();
    std::filesystem::current_path(_sourceFile.parent_path());
    auto* source = app.openDocument("box.FCStd");
    ASSERT_NE(source, nullptr);
    const auto registered = Base::FileInfo::stringToPath(source->getFileName());
    ASSERT_TRUE(registered.is_absolute()) << source->getFileName();
    EXPECT_EQ(registered, _sourceFile);
    const auto requestedName = Base::FileInfo::pathToString(_sourceFile);
    const auto count = app.getDocuments().size();
    EXPECT_EQ(app.openDocument(requestedName.c_str()), source);
    EXPECT_EQ(app.getDocuments().size(), count);
    checkExternalLinkPersistence(source, true);
}

TEST_F(ApplicationDocumentPathTest, relativeOpenReusesExactRegisteredPath)
{
    auto& app = App::GetApplication();
    std::filesystem::current_path(_sourceFile.parent_path());
    auto* source = app.openDocument("box.FCStd");
    ASSERT_NE(source, nullptr);
    const std::string registeredName = source->getFileName();
    SCOPED_TRACE(::testing::Message() << "registered='" << registeredName << "'");
    EXPECT_FALSE(source->testStatus(App::Document::PartialDoc));
    EXPECT_FALSE(source->testStatus(App::Document::PartialRestore));
    const auto count = app.getDocuments().size();
    EXPECT_EQ(app.openDocument(registeredName.c_str()), source);
    EXPECT_EQ(app.getDocuments().size(), count);
}

TEST_F(ApplicationDocumentPathTest, absoluteOpenReusesExactInputPath)
{
    auto& app = App::GetApplication();
    const auto requestedName = Base::FileInfo::pathToString(_sourceFile);
    auto* source = app.openDocument(requestedName.c_str());
    ASSERT_NE(source, nullptr);
    SCOPED_TRACE(::testing::Message() << "requested='" << requestedName << "' registered='"
                                    << source->getFileName() << "'");
    EXPECT_FALSE(source->testStatus(App::Document::PartialDoc));
    EXPECT_FALSE(source->testStatus(App::Document::PartialRestore));
    const auto count = app.getDocuments().size();
    EXPECT_EQ(app.openDocument(requestedName.c_str()), source);
    EXPECT_EQ(app.getDocuments().size(), count);
}

TEST_F(ApplicationDocumentPathTest, absoluteOpenPreservesPathAndLinkPersistence)
{
    auto* source = App::GetApplication().openDocument(
        Base::FileInfo::pathToString(_sourceFile).c_str()
    );
    ASSERT_NE(source, nullptr);
    EXPECT_EQ(Base::FileInfo::stringToPath(source->getFileName()), _sourceFile);
    checkExternalLinkPersistence(source, true);
}

TEST_F(ApplicationDocumentPathTest, recoveryKeepsLogicalFilenameAndLabel)
{
    const auto logicalFile = _storage->path() / "owner" / "recovered.FCStd";
    const std::vector<std::string> filenames {Base::FileInfo::pathToString(logicalFile)};
    const std::vector<std::string> paths {Base::FileInfo::pathToString(_sourceFile)};
    const std::vector<std::string> labels {"Recovered document label"};
    std::vector<std::string> errors;
    auto documents = App::GetApplication().openDocuments(filenames, &paths, &labels, &errors);
    ASSERT_EQ(documents.size(), 1);
    ASSERT_EQ(errors.size(), 1);
    EXPECT_TRUE(errors[0].empty()) << errors[0];
    ASSERT_NE(documents[0], nullptr);
    EXPECT_EQ(Base::FileInfo::stringToPath(documents[0]->getFileName()), logicalFile);
    EXPECT_STREQ(documents[0]->Label.getValue(), "Recovered document label");
    EXPECT_NE(documents[0]->getObject("Target"), nullptr);
    EXPECT_FALSE(std::filesystem::exists(logicalFile));
}

TEST_F(ApplicationDocumentPathTest, relativeOpenPreservesSymlinkSpelling)
{
    const auto aliasDirectory = _storage->path() / "alias";
    std::error_code error;
    std::filesystem::create_directory_symlink(_sourceFile.parent_path(), aliasDirectory, error);
    if (error) {
        GTEST_SKIP() << "Directory symlinks are unavailable: " << error.message();
    }
    std::filesystem::current_path(_storage->path());
    auto* source = App::GetApplication().openDocument("alias/box.FCStd");
    ASSERT_NE(source, nullptr);
    const auto registered = Base::FileInfo::stringToPath(source->getFileName());
    ASSERT_TRUE(registered.is_absolute()) << source->getFileName();
    EXPECT_EQ(registered, aliasDirectory / "box.FCStd");
    EXPECT_TRUE(std::filesystem::equivalent(registered, _sourceFile));
}

TEST_F(ApplicationDocumentPathTest, emptyFilenameRetainsFilesystemError)
{
    EXPECT_THROW(App::GetApplication().openDocument(""), Base::FileSystemError);
}
