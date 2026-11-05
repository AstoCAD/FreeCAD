// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <string>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/PropertyUnits.h>
#include <App/UserParameters.h>
#include <Mod/Spreadsheet/App/Sheet.h>
#include <Mod/Spreadsheet/App/Utils.h>

#include "src/App/InitApplication.h"

// NOLINTBEGIN(readability-magic-numbers)

class SpreadsheetUserParameters: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        docName = App::GetApplication().getUniqueDocumentName("sheet_userparams");
        doc = App::GetApplication().newDocument(docName.c_str(), "testUser");
        holder = doc->addObject("App::VarSet", "Holder");
        auto* param = freecad_cast<App::PropertyDistance*>(
            holder->addDynamicProperty("App::PropertyDistance", "myVar", "UserParameters")
        );
        param->setValue(23.0);
        sheet = freecad_cast<Spreadsheet::Sheet*>(doc->addObject("Spreadsheet::Sheet", "Sheet"));
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(docName.c_str());
    }

    std::string qualified(const std::string& typed)
    {
        std::string content = typed;
        Spreadsheet::qualifyUserParameters(sheet, content);
        return content;
    }

    std::string docName;
    App::Document* doc {};
    App::DocumentObject* holder {};
    Spreadsheet::Sheet* sheet {};
};

TEST_F(SpreadsheetUserParameters, bareNameIsQualified)
{
    std::string content = "=myVar";
    EXPECT_TRUE(Spreadsheet::qualifyUserParameters(sheet, content));
    EXPECT_EQ(content, "=Holder.myVar");
    EXPECT_EQ(qualified("=2*myVar"), "=2 * Holder.myVar");

    // The qualified content evaluates in the cell.
    sheet->setCell("A1", qualified("=2*myVar").c_str());
    doc->recompute();
    auto* cell = freecad_cast<App::PropertyQuantity*>(sheet->getPropertyByName("A1"));
    ASSERT_NE(cell, nullptr);
    EXPECT_DOUBLE_EQ(cell->getValue(), 46.0);
}

TEST_F(SpreadsheetUserParameters, existingMeaningKept)
{
    // Not formulas, or nothing to qualify: unchanged.
    for (const char* typed : {"myVar", "'=myVar", "23 mm", "=", "=Holder.myVar", "=2*3", "=A1"}) {
        std::string content = typed;
        EXPECT_FALSE(Spreadsheet::qualifyUserParameters(sheet, content)) << typed;
        EXPECT_EQ(content, typed);
    }
    // Parse errors are left to the cell.
    std::string broken = "=2*(myVar";
    EXPECT_FALSE(Spreadsheet::qualifyUserParameters(sheet, broken));
    EXPECT_EQ(broken, "=2*(myVar");

}

TEST_F(SpreadsheetUserParameters, aliasWins)
{
    sheet->setCell("B1", "5");
    sheet->setAlias(App::CellAddress("B1"), "myVar");
    EXPECT_EQ(qualified("=myVar"), "=myVar");
    doc->recompute();
    EXPECT_EQ(qualified("=myVar"), "=myVar");
}

TEST_F(SpreadsheetUserParameters, sheetPropertyWins)
{
    sheet->addDynamicProperty("App::PropertyFloat", "myVar", "Base");
    EXPECT_EQ(qualified("=myVar"), "=myVar");
}

TEST_F(SpreadsheetUserParameters, cellNamedParameterNotQualified)
{
    // A parameter named like an (empty) cell does not take over references to the cell.
    holder->addDynamicProperty("App::PropertyDistance", "B5", "UserParameters");
    EXPECT_EQ(qualified("=B5"), "=B5");
    // Only the cell is left alone: the parameters of the same formula are still resolved, as
    // they are beside a cell that no parameter is named like.
    EXPECT_EQ(qualified("=B5 + myVar"), "=B5 + Holder.myVar");
    EXPECT_EQ(qualified("=A1 + myVar"), "=A1 + Holder.myVar");
}

TEST_F(SpreadsheetUserParameters, aliasNamedParameterDoesNotStopOtherParameters)
{
    auto* clash = freecad_cast<App::PropertyDistance*>(
        holder->addDynamicProperty("App::PropertyDistance", "ali", "UserParameters")
    );
    clash->setValue(3.0);

    // The alias of an empty cell does not resolve yet: it still names the cell.
    sheet->setAlias(App::CellAddress("B1"), "ali");
    std::string content = "=ali";
    EXPECT_FALSE(Spreadsheet::qualifyUserParameters(sheet, content));
    EXPECT_EQ(content, "=ali");
    EXPECT_EQ(qualified("=ali + myVar"), "=ali + Holder.myVar");
    EXPECT_EQ(qualified("=myVar * (ali + myVar)"), "=Holder.myVar * (ali + Holder.myVar)");

    // Same once the cell has a value, and the formula uses the cell, not the parameter.
    sheet->setCell("B1", "5 mm");
    doc->recompute();
    EXPECT_EQ(qualified("=ali + myVar"), "=ali + Holder.myVar");
    sheet->setCell("A1", qualified("=ali + myVar").c_str());
    doc->recompute();
    auto* cell = freecad_cast<App::PropertyQuantity*>(sheet->getPropertyByName("A1"));
    ASSERT_NE(cell, nullptr);
    EXPECT_DOUBLE_EQ(cell->getValue(), 28.0);
}

TEST_F(SpreadsheetUserParameters, renameInTransactionWithSheetUndoRedo)
{
    auto* param = holder->getDynamicPropertyByName("myVar");
    const auto contentOf = [this](const char* address) {
        std::string content;
        sheet->getCell(App::CellAddress(address))->getStringContent(content);
        return content;
    };
    const auto valueOf = [this](const char* address) {
        auto* cell = freecad_cast<App::PropertyQuantity*>(sheet->getPropertyByName(address));
        return cell ? cell->getValue() : -1.0;
    };

    // The undo history holds copies of the cells: of an edit that does not use the parameter...
    doc->openTransaction("Edit cell");
    sheet->setCell("B1", "42");
    doc->commitTransaction();
    // ... and of the cell that refers to it.
    doc->openTransaction("Refer to parameter");
    sheet->setCell("A1", "=2 * Holder.myVar");
    doc->commitTransaction();
    doc->recompute();
    ASSERT_DOUBLE_EQ(valueOf("A1"), 46.0);

    doc->openTransaction("Rename parameter");
    bool renamed = false;
    EXPECT_NO_THROW(renamed = App::UserParameters::rename(param, "width"));
    doc->commitTransaction();
    doc->recompute();
    EXPECT_TRUE(renamed);
    EXPECT_EQ(holder->getDynamicPropertyByName("width"), param);
    EXPECT_EQ(holder->getDynamicPropertyByName("myVar"), nullptr);
    EXPECT_EQ(contentOf("A1"), "=2 * Holder.width");
    EXPECT_DOUBLE_EQ(valueOf("A1"), 46.0);

    EXPECT_TRUE(doc->undo());
    doc->recompute();
    EXPECT_EQ(holder->getDynamicPropertyByName("myVar"), param);
    EXPECT_EQ(holder->getDynamicPropertyByName("width"), nullptr);
    EXPECT_EQ(contentOf("A1"), "=2 * Holder.myVar");
    EXPECT_DOUBLE_EQ(valueOf("A1"), 46.0);
    EXPECT_FALSE(sheet->isError());

    EXPECT_TRUE(doc->redo());
    doc->recompute();
    EXPECT_EQ(holder->getDynamicPropertyByName("width"), param);
    EXPECT_EQ(contentOf("A1"), "=2 * Holder.width");
    EXPECT_DOUBLE_EQ(valueOf("A1"), 46.0);
    EXPECT_FALSE(sheet->isError());
}

TEST_F(SpreadsheetUserParameters, ambiguousNameNotQualified)
{
    auto* copy = doc->addObject("App::VarSet", "Copy");
    copy->addDynamicProperty("App::PropertyDistance", "myVar", "UserParameters");
    EXPECT_EQ(qualified("=myVar"), "=myVar");
}

TEST_F(SpreadsheetUserParameters, parameterOfTheSheetItself)
{
    sheet->addDynamicProperty("App::PropertyDistance", "own", "UserParameters");
    // `own` already resolves to the sheet's property.
    EXPECT_EQ(qualified("=own"), "=own");
}

// NOLINTEND(readability-magic-numbers)
