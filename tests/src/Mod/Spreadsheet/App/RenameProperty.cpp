// SPDX-License-Identifier: LGPL-2.1-or-later

/****************************************************************************
 *   Copyright (c) 2025 Pieter Hijma <info@pieterhijma.net>                 *
 *                                                                          *
 *   This file is part of the FreeCAD CAx development system.               *
 *                                                                          *
 *   This library is free software; you can redistribute it and/or          *
 *   modify it under the terms of the GNU Library General Public            *
 *   License as published by the Free Software Foundation; either           *
 *   version 2 of the License, or (at your option) any later version.       *
 *                                                                          *
 *   This library  is distributed in the hope that it will be useful,       *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of         *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          *
 *   GNU Library General Public License for more details.                   *
 *                                                                          *
 *   You should have received a copy of the GNU Library General Public      *
 *   License along with this library; see the file COPYING.LIB. If not,     *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,          *
 *   Suite 330, Boston, MA  02111-1307, USA                                 *
 *                                                                          *
 ****************************************************************************/

#include <gtest/gtest.h>

#include <memory>
#include <string>

#include <App/Expression.h>
#include <App/ObjectIdentifier.h>
#include <Mod/Spreadsheet/App/Sheet.h>

#include "src/App/Property.h"

class SpreadsheetRenameProperty: public RenameProperty
{
protected:
    void SetUp() override
    {
        // The tests share the document. Removing the objects of a test that used transactions
        // leaves a transaction open, which would take in the changes of the next test.
        doc->clearUndos();
        RenameProperty::SetUp();
        sheet = freecad_cast<Spreadsheet::Sheet*>(doc->addObject("Spreadsheet::Sheet", "Sheet"));
    }

    void TearDown() override
    {
        doc->removeObject(sheet->getNameInDocument());
        RenameProperty::TearDown();
    }

    Spreadsheet::Sheet* sheet {};
};

App::Document* RenameProperty::doc {nullptr};

// Tests whether we can rename a property that is used in a spreadsheet
TEST_F(SpreadsheetRenameProperty, renameProperty)
{
    // Arrange
    sheet->setCell("A1", "=VarSet.Variable");
    doc->recompute();
    auto* propSpreadsheet = static_cast<App::PropertyInteger*>(sheet->getPropertyByName("A1"));

    // Assert before the rename
    EXPECT_EQ(prop->getValue(), value);
    EXPECT_EQ(propSpreadsheet->getValue(), value);

    // Act
    bool isRenamed = varSet->renameDynamicProperty(prop, "NewName");
    doc->recompute();

    // Assert after the rename
    EXPECT_TRUE(isRenamed);
    EXPECT_STREQ(varSet->getPropertyName(prop), "NewName");
    EXPECT_EQ(prop->getValue(), value);

    EXPECT_EQ(varSet->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_EQ(varSet->getDynamicPropertyByName("NewName"), prop);

    std::string cellContent;
    sheet->getCell(App::CellAddress("A1"))->getStringContent(cellContent);

    EXPECT_EQ(cellContent, "=VarSet.NewName");
    EXPECT_EQ(propSpreadsheet->getValue(), value);
}

namespace
{

std::string cellContent(const Spreadsheet::Sheet* sheet, const char* address)
{
    std::string content;
    if (const auto* cell = sheet->getCell(App::CellAddress(address))) {
        cell->getStringContent(content);
    }
    return content;
}

long cellValue(const Spreadsheet::Sheet* sheet, const char* address)
{
    const auto* cell = freecad_cast<App::PropertyInteger*>(sheet->getPropertyByName(address));
    return cell ? cell->getValue() : -1;
}

// The expression of the only property of the object that is bound to one
std::string boundExpression(const App::DocumentObject* object)
{
    const auto expressions = object->ExpressionEngine.getExpressions();
    return expressions.size() == 1 ? expressions.begin()->second->toString() : std::string();
}

// An object with an integer property "Target" bound to the expression
App::DocumentObject* addDependent(App::Document* doc, const std::string& expression)
{
    auto* object = doc->addObject("App::VarSet", "Dependent");
    const auto* target = object->addDynamicProperty("App::PropertyInteger", "Target", "Variables");
    object->setExpression(
        App::ObjectIdentifier(*target),
        std::shared_ptr<App::Expression>(App::Expression::parse(object, expression))
    );
    return object;
}

long targetValue(const App::DocumentObject* object)
{
    const auto* target = freecad_cast<App::PropertyInteger*>(object->getPropertyByName("Target"));
    return target ? target->getValue() : -1;
}

}  // namespace

// Renaming in a transaction while the undo history holds copies of the cells: of an earlier edit
// of the sheet, and of the cell that the rename itself rewrites. These copies have no container.
TEST_F(SpreadsheetRenameProperty, renameInTransactionUndoRedo)
{
    // Arrange
    auto* dependent = addDependent(doc, "VarSet.Variable + 1");
    doc->openTransaction("Edit cell");
    sheet->setCell("B1", "42");
    doc->commitTransaction();
    doc->openTransaction("Refer to property");
    sheet->setCell("A1", "=VarSet.Variable");
    doc->commitTransaction();
    doc->recompute();
    ASSERT_EQ(cellValue(sheet, "A1"), value);
    ASSERT_EQ(targetValue(dependent), value + 1);

    // Act
    doc->openTransaction("Rename property");
    bool isRenamed = false;
    EXPECT_NO_THROW(isRenamed = varSet->renameDynamicProperty(prop, "NewName"));
    doc->commitTransaction();
    doc->recompute();

    // Assert
    EXPECT_TRUE(isRenamed);
    EXPECT_EQ(varSet->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_EQ(varSet->getDynamicPropertyByName("NewName"), prop);
    EXPECT_EQ(cellContent(sheet, "A1"), "=VarSet.NewName");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), "VarSet.NewName + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);

    // Act: undo the rename
    EXPECT_TRUE(doc->undo());
    doc->recompute();

    // Assert
    EXPECT_EQ(varSet->getDynamicPropertyByName("Variable"), prop);
    EXPECT_EQ(varSet->getDynamicPropertyByName("NewName"), nullptr);
    EXPECT_EQ(cellContent(sheet, "A1"), "=VarSet.Variable");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), "VarSet.Variable + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);
    EXPECT_FALSE(sheet->isError());
    EXPECT_FALSE(dependent->isError());

    // Act: redo the rename
    EXPECT_TRUE(doc->redo());
    doc->recompute();

    // Assert
    EXPECT_EQ(varSet->getDynamicPropertyByName("NewName"), prop);
    EXPECT_EQ(cellContent(sheet, "A1"), "=VarSet.NewName");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), "VarSet.NewName + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);
    EXPECT_FALSE(sheet->isError());
    EXPECT_FALSE(dependent->isError());

    // Act: undo down to the copies that the history held before the rename, and come back
    EXPECT_TRUE(doc->undo());
    EXPECT_TRUE(doc->undo());
    doc->recompute();
    EXPECT_EQ(varSet->getDynamicPropertyByName("Variable"), prop);
    EXPECT_EQ(cellContent(sheet, "A1"), "");
    EXPECT_EQ(cellContent(sheet, "B1"), "42");
    EXPECT_TRUE(doc->redo());
    doc->recompute();
    EXPECT_EQ(cellContent(sheet, "A1"), "=VarSet.Variable");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_TRUE(doc->redo());
    doc->recompute();

    // Assert
    EXPECT_EQ(varSet->getDynamicPropertyByName("NewName"), prop);
    EXPECT_EQ(cellContent(sheet, "A1"), "=VarSet.NewName");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), "VarSet.NewName + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);
    EXPECT_FALSE(sheet->isError());
    EXPECT_FALSE(dependent->isError());

    // Tear down
    doc->removeObject(dependent->getNameInDocument());
}

// Renaming while a transaction keeps a deleted sheet alive: its cells cannot be resolved.
TEST_F(SpreadsheetRenameProperty, renameWithDeletedSheetInUndoHistory)
{
    // Arrange
    auto* added = doc->addObject("Spreadsheet::Sheet", "Deleted");
    auto* deleted = freecad_cast<Spreadsheet::Sheet*>(added);
    deleted->setCell("A1", "=VarSet.Variable");
    deleted->setCell("A2", "=A1 + 1");
    doc->recompute();
    doc->openTransaction("Delete sheet");
    doc->removeObject(deleted->getNameInDocument());
    doc->commitTransaction();

    // Act
    doc->openTransaction("Rename property");
    bool isRenamed = false;
    EXPECT_NO_THROW(isRenamed = varSet->renameDynamicProperty(prop, "NewName"));
    doc->commitTransaction();

    // Assert
    EXPECT_TRUE(isRenamed);
    EXPECT_EQ(varSet->getDynamicPropertyByName("NewName"), prop);

    // Act: undo the rename, then the deletion
    EXPECT_TRUE(doc->undo());
    EXPECT_EQ(varSet->getDynamicPropertyByName("Variable"), prop);
    EXPECT_TRUE(doc->undo());
    doc->recompute();

    // Assert: the sheet is back and refers to the property by the name it has again
    ASSERT_EQ(doc->getObject("Deleted"), deleted);
    EXPECT_EQ(cellContent(deleted, "A1"), "=VarSet.Variable");
    EXPECT_EQ(cellValue(deleted, "A1"), value);
    EXPECT_EQ(cellValue(deleted, "A2"), value + 1);
    EXPECT_FALSE(deleted->isError());

    // Tear down
    doc->removeObject(deleted->getNameInDocument());
}

class SpreadsheetMoveProperty: public MoveProperty
{
protected:
    void SetUp() override
    {
        MoveProperty::SetUp();
        sheet = freecad_cast<Spreadsheet::Sheet*>(doc1->addObject("Spreadsheet::Sheet", "Sheet"));
    }

    Spreadsheet::Sheet* sheet {};
};

// Moving in a transaction while the undo history holds copies of the cells
TEST_F(SpreadsheetMoveProperty, moveInTransactionUndoRedo)
{
    // Arrange
    const std::string source = varSet1Doc1->getNameInDocument();
    const std::string target = varSet2Doc1->getNameInDocument();
    auto* dependent = addDependent(doc1, source + ".Variable + 1");
    doc1->openTransaction("Edit cell");
    sheet->setCell("B1", "42");
    doc1->commitTransaction();
    doc1->openTransaction("Refer to property");
    sheet->setCell("A1", ("=" + source + ".Variable").c_str());
    doc1->commitTransaction();
    doc1->recompute();
    ASSERT_EQ(cellValue(sheet, "A1"), value);
    ASSERT_EQ(targetValue(dependent), value + 1);

    // Act
    doc1->openTransaction("Move property");
    App::Property* moved = nullptr;
    EXPECT_NO_THROW(moved = varSet1Doc1->moveDynamicProperty(prop, varSet2Doc1));
    doc1->commitTransaction();
    doc1->recompute();

    // Assert
    EXPECT_NE(moved, nullptr);
    EXPECT_EQ(varSet1Doc1->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_EQ(varSet2Doc1->getDynamicPropertyByName("Variable"), moved);
    EXPECT_EQ(cellContent(sheet, "A1"), "=" + target + ".Variable");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), target + ".Variable + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);

    // Act: undo the move
    EXPECT_TRUE(doc1->undo());
    doc1->recompute();

    // Assert
    EXPECT_NE(varSet1Doc1->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_EQ(varSet2Doc1->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_EQ(cellContent(sheet, "A1"), "=" + source + ".Variable");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), source + ".Variable + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);
    EXPECT_FALSE(sheet->isError());
    EXPECT_FALSE(dependent->isError());

    // Act: redo the move
    EXPECT_TRUE(doc1->redo());
    doc1->recompute();

    // Assert
    EXPECT_EQ(varSet1Doc1->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_NE(varSet2Doc1->getDynamicPropertyByName("Variable"), nullptr);
    EXPECT_EQ(cellContent(sheet, "A1"), "=" + target + ".Variable");
    EXPECT_EQ(cellValue(sheet, "A1"), value);
    EXPECT_EQ(boundExpression(dependent), target + ".Variable + 1");
    EXPECT_EQ(targetValue(dependent), value + 1);
    EXPECT_FALSE(sheet->isError());
    EXPECT_FALSE(dependent->isError());
}
