// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 ***************************************************************************/

#pragma once

#include <vector>

#include <QDialog>

#include <App/Range.h>

class QCheckBox;
class QLabel;
class QLineEdit;
class QPushButton;

namespace Spreadsheet
{
class Sheet;
}

namespace SpreadsheetGui
{

class SheetTableView;

/// Find and replace in the cells of a sheet; the search itself is Sheet::findCells/replaceCells.
class DlgFindReplace: public QDialog
{
    Q_OBJECT

public:
    DlgFindReplace(SheetTableView* view, Spreadsheet::Sheet* sheet);

    void setFindText(const QString& text);

    bool findNext();
    bool findPrevious();
    void replace();
    void replaceAll();

private:
    bool find(bool forward);
    std::vector<App::CellAddress> matches() const;
    void updateButtons();

    SheetTableView* view;
    Spreadsheet::Sheet* sheet;
    QLineEdit* findEdit;
    QLineEdit* replaceEdit;
    QCheckBox* matchCase;
    QCheckBox* wholeCell;
    QCheckBox* inValues;
    QLabel* status;
    QPushButton* nextButton;
    QPushButton* previousButton;
    QPushButton* replaceButton;
    QPushButton* replaceAllButton;
};

}  // namespace SpreadsheetGui
