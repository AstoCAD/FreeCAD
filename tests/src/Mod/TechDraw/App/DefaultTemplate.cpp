// SPDX-License-Identifier: LGPL-2.1-or-later
#include <gtest/gtest.h>

#include <string>

#include <QFileInfo>
#include <QString>

#include <Base/Parameter.h>

#include "Mod/TechDraw/App/Preferences.h"
#include "src/App/InitApplication.h"

class TestDefaultTemplate: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }
    void SetUp() override
    {
        // an empty value means "use the default", so restoring "" is equivalent to unset
        _savedTemplateFile =
            TechDraw::Preferences::getPreferenceGroup("Files")->GetASCII("TemplateFile", "");
    }
    void TearDown() override
    {
        auto group = TechDraw::Preferences::getPreferenceGroup("Files");
        if (_savedTemplateFile.empty()) {
            group->RemoveASCII("TemplateFile");
        }
        else {
            group->SetASCII("TemplateFile", _savedTemplateFile);
        }
    }

private:
    std::string _savedTemplateFile;
};

// The shipped default template must exist: TechDraw_PageDefault refuses to create a page
// otherwise, and an unreadable user template falls back to it.
TEST_F(TestDefaultTemplate, defaultTemplateIsReadable)
{
    auto group = TechDraw::Preferences::getPreferenceGroup("Files");
    group->RemoveASCII("TemplateFile");

    const QString fileName = TechDraw::Preferences::defaultTemplate();

    EXPECT_TRUE(QFileInfo(fileName).isReadable()) << fileName.toStdString();
}

TEST_F(TestDefaultTemplate, unreadableTemplateFallsBackToReadableDefault)
{
    auto group = TechDraw::Preferences::getPreferenceGroup("Files");
    group->SetASCII("TemplateFile", "/no/such/dir/missing_template.svg");

    const QString fileName = TechDraw::Preferences::defaultTemplate();

    EXPECT_FALSE(fileName.contains(QStringLiteral("missing_template.svg")));
    EXPECT_TRUE(QFileInfo(fileName).isReadable()) << fileName.toStdString();
}
