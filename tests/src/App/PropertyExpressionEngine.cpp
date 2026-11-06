// SPDX-License-Identifier: LGPL-2.1-or-later

#include <algorithm>

#include <gtest/gtest.h>

#include "Base/Quantity.h"

#include "App/Application.h"
#include "App/Document.h"
#include "App/DocumentObject.h"
#include "App/Expression.h"
#include "App/ObjectIdentifier.h"
#include "App/PropertyExpressionEngine.h"
#include "App/PropertyLinks.h"
#include "App/PropertyStandard.h"

#include "src/App/InitApplication.h"

// clang-format off

class PropertyExpressionEngineTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _doc_name = App::GetApplication().getUniqueDocumentName("test");
        _this_doc = App::GetApplication().newDocument(_doc_name.c_str(), "testUser");
        _this_obj = _this_doc -> addObject("Sketcher::SketchObject");
        _source_name = std::string("this_origin");
        _source_prop = _this_obj -> addDynamicProperty("App::PropertyString", _source_name.c_str()); // property with length as string
        _target_name = std::string("this_length");
        _target_prop = _this_obj -> addDynamicProperty("App::PropertyLength", _target_name.c_str()); // property with reference to source
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_doc_name.c_str());
    }

    std::string doc_name() { return _doc_name; }
    App::Document* this_doc() { return _this_doc; }
    App::DocumentObject* this_obj() { return _this_obj; }
    std::string source_name() { return _source_name; }
    App::Property* source_prop() { return _source_prop; }
    std::string target_name() { return _target_name; }
    App::Property* target_prop() { return _target_prop; }

private:
    std::string _doc_name;
    App::Document* _this_doc {};
    App::DocumentObject* _this_obj {};
    std::string _source_name;
    App::Property* _source_prop {};
    std::string _target_name;
    App::Property* _target_prop {};
};

// https://github.com/FreeCAD/FreeCAD/issues/11965
TEST_F(PropertyExpressionEngineTest, executeCrossPropertyReference)
{
    auto source_text = std::string("1.5 m"); // provided in source
    auto target_text = std::string("1500 mm"); // expected in target

    auto source_path = App::ObjectIdentifier::parse(this_obj(), source_name());
    source_prop()->setPathValue(source_path, source_text);

    auto target_expr = "parsequant(" + source_name() + ")"; // Solution B: parsequant() function

    auto target_path = App::ObjectIdentifier::parse(this_obj(), target_name());
    std::shared_ptr<App::Expression> target_rule(App::Expression::parse(this_obj(), target_expr));
    this_obj()->setExpression(target_path, target_rule);

    this_obj() -> ExpressionEngine.execute();

    auto source_entry = source_prop() -> getPathValue(source_path);
    ASSERT_TRUE(source_entry.type() == typeid(std::string));
    auto source_value = App::any_cast<std::string>(source_entry);

    auto target_entry = target_prop() -> getPathValue(target_path);
    ASSERT_TRUE(target_entry.type() == typeid(Base::Quantity));
    auto target_quant = App::any_cast<Base::Quantity>(target_entry);
    auto target_value = target_quant.getValue();
    auto target_unit = target_quant.getUnit().getString();

    auto verify_quant = Base::Quantity::parse(target_text);

    EXPECT_EQ(target_quant, verify_quant) << ""
        "expecting equal: source_text='" + source_text + "' target_text='" + target_text + "'"
        "instead produced: target_value='" + std::to_string(target_value) + "' target_unit='" + target_unit + "'"
    ;
}

// clang-format on

class ExpressionDependencyLifetimeTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        documentName = App::GetApplication().getUniqueDocumentName("ExpressionDependencyLifetime");
        document = App::GetApplication().newDocument(documentName.c_str(), "testUser");
        source = document->addObject("App::FeaturePython", "Source");
        source->addDynamicProperty("App::PropertyFloat", "Value");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(documentName.c_str());
    }

    App::DocumentObject* addDependent(const char* name)
    {
        auto* dependent = document->addObject("App::FeaturePython", name);
        dependent->addDynamicProperty("App::PropertyFloat", "Value");
        const auto path = App::ObjectIdentifier::parse(dependent, "Value");
        dependent->setExpression(
            path,
            std::shared_ptr<App::Expression>(App::Expression::parse(dependent, "Source.Value"))
        );
        return dependent;
    }

    std::string documentName;
    App::Document* document {};
    App::DocumentObject* source {};
};

// Regression for https://github.com/FreeCAD/FreeCAD/issues/33685.
TEST_F(ExpressionDependencyLifetimeTest, DeletionRemovesPropertyBacklinks)
{
    addDependent("Dependent");
    ASSERT_EQ(source->getInList().size(), 1);
    ASSERT_EQ(source->getInListProp().size(), 1);

    document->removeObject("Dependent");

    EXPECT_TRUE(source->getInList().empty());
    EXPECT_TRUE(source->getInListProp().empty());
}

TEST_F(ExpressionDependencyLifetimeTest, DeletionPreservesOtherDependents)
{
    addDependent("Deleted");
    auto* remaining = addDependent("Remaining");
    ASSERT_EQ(source->getInListProp().size(), 2);

    document->removeObject("Deleted");

    ASSERT_EQ(source->getInList().size(), 1);
    EXPECT_EQ(source->getInList().front(), remaining);
    ASSERT_EQ(source->getInListProp().size(), 1);
    EXPECT_EQ(source->getInListProp().front().fromObj, remaining);
}

TEST_F(ExpressionDependencyLifetimeTest, UndoRedoRestoresPropertyBacklinks)
{
    addDependent("Dependent");
    ASSERT_EQ(source->getInListProp().size(), 1);

    document->openTransaction("Delete dependent");
    document->removeObject("Dependent");
    document->commitTransaction();
    EXPECT_TRUE(source->getInListProp().empty());

    ASSERT_TRUE(document->undo());
    auto* restored = document->getObject("Dependent");
    ASSERT_NE(restored, nullptr);
    ASSERT_EQ(source->getInListProp().size(), 1);
    EXPECT_EQ(source->getInListProp().front().fromObj, restored);

    auto* sourceValue = dynamic_cast<App::PropertyFloat*>(source->getPropertyByName("Value"));
    auto* restoredValue = dynamic_cast<App::PropertyFloat*>(restored->getPropertyByName("Value"));
    ASSERT_NE(sourceValue, nullptr);
    ASSERT_NE(restoredValue, nullptr);
    sourceValue->setValue(17.0);
    document->recompute();
    EXPECT_DOUBLE_EQ(restoredValue->getValue(), 17.0);

    ASSERT_TRUE(document->redo());
    EXPECT_EQ(document->getObject("Dependent"), nullptr);
    EXPECT_TRUE(source->getInListProp().empty());

    ASSERT_TRUE(document->undo());
    ASSERT_EQ(source->getInListProp().size(), 1);
    EXPECT_EQ(source->getInListProp().front().fromObj, document->getObject("Dependent"));
}

TEST_F(ExpressionDependencyLifetimeTest, DeletionRemovesEveryReferencedProperty)
{
    source->addDynamicProperty("App::PropertyFloat", "OtherValue");
    auto* dependent = addDependent("Dependent");
    dependent->setExpression(
        App::ObjectIdentifier::parse(dependent, "Value"),
        std::shared_ptr<App::Expression>(
            App::Expression::parse(dependent, "Source.Value + Source.OtherValue")
        )
    );
    ASSERT_EQ(source->getInList().size(), 1);
    ASSERT_EQ(source->getInListProp().size(), 2);

    document->removeObject("Dependent");

    EXPECT_TRUE(source->getInList().empty());
    EXPECT_TRUE(source->getInListProp().empty());
}

// The out list holds one entry per link, as the in list holds one back link per link. The
// expression engine, itself a link property, was listed a second time.
TEST_F(ExpressionDependencyLifetimeTest, OutListListsExpressionLinksOnce)
{
    auto* dependent = addDependent("Dependent");
    auto countSource = [this](const std::vector<App::DocumentObject*>& list) {
        return std::ranges::count(list, source);
    };
    EXPECT_EQ(countSource(dependent->getOutList()), 1);
    EXPECT_EQ(source->getInList().size(), 1);

    auto* link = dynamic_cast<App::PropertyLink*>(
        dependent->addDynamicProperty("App::PropertyLink", "Base")
    );
    ASSERT_NE(link, nullptr);
    link->setValue(source);

    EXPECT_EQ(countSource(dependent->getOutList()), 2);
    EXPECT_EQ(source->getInList().size(), 2);
    EXPECT_EQ(countSource(dependent->getOutList(App::DocumentObject::OutListNoHidden)), 2);
    // only the link property is left without the expression engine
    EXPECT_EQ(countSource(dependent->getOutList(App::DocumentObject::OutListNoExpression)), 1);
    link->setValue(nullptr);
    EXPECT_TRUE(dependent->getOutList(App::DocumentObject::OutListNoExpression).empty());
}
