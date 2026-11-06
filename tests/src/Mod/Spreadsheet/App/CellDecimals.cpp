// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <sstream>
#include <string>

#include <App/Application.h>
#include <App/Document.h>
#include <App/Expression.h>
#include <App/Range.h>
#include <Base/Reader.h>
#include <Base/Writer.h>
#include <Mod/Spreadsheet/App/Cell.h>
#include <Mod/Spreadsheet/App/PropertySheet.h>
#include <Mod/Spreadsheet/App/Sheet.h>

#include "src/App/InitApplication.h"

// NOLINTBEGIN(readability-magic-numbers)

class SpreadsheetCellDecimals: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        docName = App::GetApplication().getUniqueDocumentName("sheet_decimals");
        doc = App::GetApplication().newDocument(docName.c_str(), "testUser");
        sheet = freecad_cast<Spreadsheet::Sheet*>(doc->addObject("Spreadsheet::Sheet", "Sheet"));
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(docName.c_str());
    }

    int decimalsAt(const char* address)
    {
        int decimals = -1;
        const Spreadsheet::Cell* cell = sheet->getCell(App::CellAddress(address));
        if (!cell || !cell->getDecimals(decimals)) {
            return -1;
        }
        return decimals;
    }

    std::string docName;
    App::Document* doc {};
    Spreadsheet::Sheet* sheet {};
};

// The format of a cell travels with its expression (Std_Expressions copy/paste, and the
// copies of a cell pasted over a larger range): the decimals must be part of it.
TEST_F(SpreadsheetCellDecimals, expressionWithFormatKeepsDecimals)
{
    sheet->setCell("A1", "=1/3");
    sheet->setDecimals(App::Range("A1:A1"), 4);
    const Spreadsheet::Cell* cell = sheet->getCell(App::CellAddress("A1"));
    ASSERT_NE(cell, nullptr);
    const App::Expression* expression = cell->getExpression(true);
    ASSERT_NE(expression, nullptr);
    EXPECT_NE(expression->comment.find("decimals=\"4\""), std::string::npos)
        << expression->comment;
}

TEST_F(SpreadsheetCellDecimals, pasteOneCellOverRangeKeepsDecimals)
{
    sheet->setCell("A1", "1.5");
    sheet->setDecimals(App::Range("A1:A1"), 3);

    Base::StringWriter writer;
    sheet->getCells()->copyCells(writer, {App::Range("A1:A1")});
    std::istringstream in(writer.getString());
    Base::XMLReader reader("<memory>", in);
    sheet->getCells()->pasteCells(reader, App::Range("B1:B3"));

    for (const char* address : {"B1", "B2", "B3"}) {
        EXPECT_EQ(decimalsAt(address), 3) << address;
    }
}

// NOLINTEND(readability-magic-numbers)
