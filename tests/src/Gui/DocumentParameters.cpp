// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <algorithm>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/ObjectIdentifier.h>
#include <App/PropertyUnits.h>
#include <Base/Unit.h>
#include <Gui/Dialogs/DocumentParameters.h>
#include <src/App/InitApplication.h>

// NOLINTBEGIN(readability-magic-numbers)

namespace
{

using Gui::Parameters::Category;
using Gui::Parameters::Entry;
using Gui::Parameters::NameError;

class DocumentParameters: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        docName = App::GetApplication().getUniqueDocumentName("parameters");
        doc = App::GetApplication().newDocument(docName.c_str(), "testUser");
        varSet = doc->addObject("App::VarSet", "VarSet");
        feature = doc->addObject("App::FeatureTest", "Feature");
        other = doc->addObject("App::FeatureTest", "Other");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(docName.c_str());
    }

    static void setExpression(App::DocumentObject* obj, const char* prop, const char* text)
    {
        App::ObjectIdentifier path(*obj->getPropertyByName(prop));
        std::shared_ptr<App::Expression> expr(App::ExpressionParser::parse(obj, text));
        obj->setExpression(path, expr);
    }

    static const Entry* find(const std::vector<Entry>& entries, const std::string& name)
    {
        auto it = std::ranges::find_if(entries, [&name](const Entry& e) { return e.name == name; });
        return it == entries.end() ? nullptr : &*it;
    }

    std::string docName;
    App::Document* doc {};
    App::DocumentObject* varSet {};
    App::DocumentObject* feature {};
    App::DocumentObject* other {};
};

TEST_F(DocumentParameters, collectsUserParametersAndVarSets)
{
    auto* myVar = feature->addDynamicProperty("App::PropertyLength", "myVar", "UserParameters", "doc");
    static_cast<App::PropertyLength*>(myVar)->setValue(3.0);
    feature->addDynamicProperty("App::PropertyLength", "notAParameter", "Base");
    varSet->addDynamicProperty("App::PropertyLength", "width", "Base", "the width");
    varSet->addDynamicProperty("App::PropertyInteger", "hidden", "Base", "", App::Prop_Hidden);

    std::vector<Entry> entries = Gui::Parameters::collect(doc, false);

    ASSERT_EQ(entries.size(), 2U);
    EXPECT_EQ(entries[0].category, Category::User);
    EXPECT_EQ(entries[0].name, "myVar");
    EXPECT_EQ(entries[0].objectName, "Feature");
    EXPECT_EQ(entries[0].type, "Length");
    EXPECT_EQ(entries[0].comment, "doc");
    EXPECT_NE(entries[0].value.find('3'), std::string::npos);
    EXPECT_TRUE(entries[0].isDynamic);
    EXPECT_TRUE(entries[0].valueEditable);

    EXPECT_EQ(entries[1].category, Category::VarSet);
    EXPECT_EQ(entries[1].name, "width");
    EXPECT_EQ(entries[1].objectName, "VarSet");
    EXPECT_EQ(entries[1].comment, "the width");
}

TEST_F(DocumentParameters, userParameterOfVarSetIsListedOnce)
{
    varSet->addDynamicProperty("App::PropertyLength", "shared", "UserParameters");

    std::vector<Entry> entries = Gui::Parameters::collect(doc, false);

    ASSERT_EQ(entries.size(), 1U);
    EXPECT_EQ(entries[0].category, Category::VarSet);
    EXPECT_TRUE(Gui::Parameters::collectUserParameters(doc).empty());
}

TEST_F(DocumentParameters, expressionIsShownAndValueIsNotEditable)
{
    varSet->addDynamicProperty("App::PropertyLength", "width", "Base");
    setExpression(varSet, "width", "2 mm * 3");
    doc->recompute();

    std::vector<Entry> entries = Gui::Parameters::collect(doc, false);

    const Entry* width = find(entries, "width");
    ASSERT_NE(width, nullptr);
    EXPECT_FALSE(width->expression.empty());
    EXPECT_FALSE(width->valueEditable);
}

TEST_F(DocumentParameters, modelParametersAreOptional)
{
    varSet->addDynamicProperty("App::PropertyFloat", "factor", "Base");
    setExpression(feature, "Float", "VarSet.factor * 2");
    doc->recompute();

    EXPECT_EQ(find(Gui::Parameters::collect(doc, false), "Feature.Float"), nullptr);

    std::vector<Entry> entries = Gui::Parameters::collect(doc, true);
    const Entry* model = find(entries, "Feature.Float");
    ASSERT_NE(model, nullptr);
    EXPECT_EQ(model->category, Category::Model);
    EXPECT_EQ(model->path, "Float");
    EXPECT_EQ(model->expression, "VarSet.factor * 2");
    EXPECT_FALSE(model->isDynamic);
}

TEST_F(DocumentParameters, checkName)
{
    auto* myVar = feature->addDynamicProperty("App::PropertyLength", "myVar", "UserParameters");

    EXPECT_EQ(Gui::Parameters::checkName(other, "", true), NameError::Empty);
    EXPECT_EQ(Gui::Parameters::checkName(other, "1abc", true), NameError::NotIdentifier);
    EXPECT_EQ(Gui::Parameters::checkName(other, "a b", true), NameError::NotIdentifier);
    EXPECT_EQ(Gui::Parameters::checkName(other, "pi", true), NameError::Constant);
    EXPECT_EQ(Gui::Parameters::checkName(other, "mm", true), NameError::Unit);
    EXPECT_EQ(Gui::Parameters::checkName(other, "Float", true), NameError::ExistsInObject);
    // user parameter names are unique in the document
    EXPECT_EQ(Gui::Parameters::checkName(other, "myVar", true), NameError::ExistsInDocument);
    // ... but a variable set has its own names
    EXPECT_EQ(Gui::Parameters::checkName(varSet, "myVar", false), NameError::None);
    // renaming a parameter to its own name is fine
    EXPECT_EQ(Gui::Parameters::checkName(feature, "myVar", true, myVar), NameError::None);
    EXPECT_EQ(Gui::Parameters::checkName(other, "fresh", true), NameError::None);
    // a user parameter cannot be named like a spreadsheet cell, a variable set property can
    EXPECT_EQ(Gui::Parameters::checkName(other, "B5", true), NameError::CellAddress);
    EXPECT_EQ(Gui::Parameters::checkName(varSet, "B5", false), NameError::None);
    EXPECT_EQ(Gui::Parameters::checkName(other, "b5", true), NameError::None);
    EXPECT_EQ(Gui::Parameters::findUserParameter(doc, "myVar"), myVar);
    EXPECT_EQ(Gui::Parameters::findUserParameter(doc, "myVar", myVar), nullptr);
}

TEST_F(DocumentParameters, findReferences)
{
    varSet->addDynamicProperty("App::PropertyFloat", "factor", "Base");
    varSet->addDynamicProperty("App::PropertyFloat", "unused", "Base");
    setExpression(feature, "Float", "VarSet.factor * 2");
    setExpression(other, "Integer", "VarSet.factor + 1");

    auto refs = Gui::Parameters::findReferences(varSet, "factor");
    ASSERT_EQ(refs.size(), 2U);
    auto byFeature = std::ranges::find_if(refs, [](const auto& ref) {
        return ref.objectName == "Feature";
    });
    ASSERT_NE(byFeature, refs.end());
    EXPECT_EQ(byFeature->path, "Float");

    EXPECT_TRUE(Gui::Parameters::findReferences(varSet, "unused").empty());
}

TEST_F(DocumentParameters, propertyTypeForNewParameters)
{
    using Gui::Parameters::propertyTypeForExpression;
    using Gui::Parameters::propertyTypeForUnit;

    // Same types as App::UserParameters::propertyTypeForUnit: a signed distance for lengths
    EXPECT_EQ(propertyTypeForUnit(Base::Unit::Length), "App::PropertyDistance");
    EXPECT_EQ(propertyTypeForUnit(Base::Unit::Angle), "App::PropertyAngle");
    EXPECT_EQ(propertyTypeForUnit(Base::Unit::One), "App::PropertyFloat");
    // no plain App::PropertyQuantity, which loses its unit on save
    const Base::Unit noType = Base::Unit::Length * Base::Unit::Force * Base::Unit::Force;
    EXPECT_EQ(propertyTypeForUnit(noType), "");

    auto length = App::ExpressionParser::parse(feature, "23 mm");
    EXPECT_EQ(propertyTypeForExpression(*length), "App::PropertyDistance");
    auto odd = App::ExpressionParser::parse(feature, "2 mm * 1 N * 1 N");
    EXPECT_EQ(propertyTypeForExpression(*odd), "");
    auto number = App::ExpressionParser::parse(feature, "2 * 3");
    EXPECT_EQ(propertyTypeForExpression(*number), "App::PropertyFloat");
    auto text = App::ExpressionParser::parse(feature, "<<text>>");
    EXPECT_EQ(propertyTypeForExpression(*text), "App::PropertyString");
}

}  // namespace

// NOLINTEND(readability-magic-numbers)
