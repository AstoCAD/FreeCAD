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

#include <algorithm>

#include <QCheckBox>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

#include <App/Document.h>
#include <Base/Exception.h>
#include <Base/Tools.h>
#include <Gui/CommandT.h>
#include <Gui/MainWindow.h>
#include <Mod/Spreadsheet/App/Sheet.h>

#include "DlgFindReplace.h"
#include "SheetTableView.h"


using namespace SpreadsheetGui;
using App::CellAddress;

DlgFindReplace::DlgFindReplace(SheetTableView* view, Spreadsheet::Sheet* sheet)
    : QDialog(Gui::getMainWindow())
    , view(view)
    , sheet(sheet)
{
    setWindowTitle(tr("Find and Replace"));
    setObjectName(QStringLiteral("SpreadsheetFindReplace"));

    findEdit = new QLineEdit(this);
    findEdit->setObjectName(QStringLiteral("findText"));
    replaceEdit = new QLineEdit(this);
    replaceEdit->setObjectName(QStringLiteral("replaceText"));
    matchCase = new QCheckBox(tr("Match case"), this);
    matchCase->setObjectName(QStringLiteral("matchCase"));
    wholeCell = new QCheckBox(tr("Entire cell contents"), this);
    wholeCell->setObjectName(QStringLiteral("wholeCell"));
    inValues = new QCheckBox(tr("Search in values"), this);
    inValues->setObjectName(QStringLiteral("inValues"));
    inValues->setToolTip(tr("Search the displayed values instead of the cell contents (no replace)"));
    status = new QLabel(this);
    status->setObjectName(QStringLiteral("status"));

    nextButton = new QPushButton(tr("Find Next"), this);
    nextButton->setObjectName(QStringLiteral("findNext"));
    nextButton->setDefault(true);
    previousButton = new QPushButton(tr("Find Previous"), this);
    previousButton->setObjectName(QStringLiteral("findPrevious"));
    replaceButton = new QPushButton(tr("Replace"), this);
    replaceButton->setObjectName(QStringLiteral("replace"));
    replaceAllButton = new QPushButton(tr("Replace All"), this);
    replaceAllButton->setObjectName(QStringLiteral("replaceAll"));
    auto closeButton = new QPushButton(tr("Close"), this);

    auto grid = new QGridLayout;
    grid->addWidget(new QLabel(tr("Find:"), this), 0, 0);
    grid->addWidget(findEdit, 0, 1);
    grid->addWidget(new QLabel(tr("Replace with:"), this), 1, 0);
    grid->addWidget(replaceEdit, 1, 1);
    grid->addWidget(matchCase, 2, 1);
    grid->addWidget(wholeCell, 3, 1);
    grid->addWidget(inValues, 4, 1);
    grid->addWidget(status, 5, 0, 1, 2);

    auto buttons = new QVBoxLayout;
    buttons->addWidget(nextButton);
    buttons->addWidget(previousButton);
    buttons->addWidget(replaceButton);
    buttons->addWidget(replaceAllButton);
    buttons->addStretch();
    buttons->addWidget(closeButton);

    auto layout = new QHBoxLayout(this);
    layout->addLayout(grid);
    layout->addLayout(buttons);

    connect(nextButton, &QPushButton::clicked, this, &DlgFindReplace::findNext);
    connect(previousButton, &QPushButton::clicked, this, &DlgFindReplace::findPrevious);
    connect(replaceButton, &QPushButton::clicked, this, &DlgFindReplace::replace);
    connect(replaceAllButton, &QPushButton::clicked, this, &DlgFindReplace::replaceAll);
    connect(closeButton, &QPushButton::clicked, this, &QDialog::close);
    connect(findEdit, &QLineEdit::textChanged, this, &DlgFindReplace::updateButtons);
    connect(inValues, &QCheckBox::toggled, this, &DlgFindReplace::updateButtons);
    updateButtons();
}

void DlgFindReplace::setFindText(const QString& text)
{
    findEdit->setText(text);
    findEdit->selectAll();
    findEdit->setFocus();
}

void DlgFindReplace::updateButtons()
{
    const bool hasText = !findEdit->text().isEmpty();
    nextButton->setEnabled(hasText);
    previousButton->setEnabled(hasText);
    replaceButton->setEnabled(hasText && !inValues->isChecked());
    replaceAllButton->setEnabled(hasText && !inValues->isChecked());
    replaceEdit->setEnabled(!inValues->isChecked());
}

std::vector<CellAddress> DlgFindReplace::matches() const
{
    return sheet->findCells(
        findEdit->text().toStdString(),
        matchCase->isChecked(),
        wholeCell->isChecked(),
        inValues->isChecked()
    );
}

bool DlgFindReplace::findNext()
{
    return find(true);
}

bool DlgFindReplace::findPrevious()
{
    return find(false);
}

bool DlgFindReplace::find(bool forward)
{
    const auto found = matches();
    if (found.empty()) {
        status->setText(tr("Not found"));
        return false;
    }

    auto target = forward ? found.front() : found.back();
    const QModelIndex current = view->currentIndex();
    if (current.isValid()) {
        const CellAddress address(current.row(), current.column());
        if (forward) {
            auto it = std::upper_bound(found.begin(), found.end(), address);
            if (it != found.end()) {
                target = *it;
            }
        }
        else {
            auto it = std::lower_bound(found.begin(), found.end(), address);
            if (it != found.begin()) {
                target = *(--it);
            }
        }
    }

    const QModelIndex index = view->model()->index(target.row(), target.col());
    view->selectionModel()->setCurrentIndex(index, QItemSelectionModel::ClearAndSelect);
    view->scrollTo(index);
    status->setText(tr("%n match(es)", "", static_cast<int>(found.size())));
    return true;
}

void DlgFindReplace::replace()
{
    const QModelIndex current = view->currentIndex();
    const auto found = matches();
    if (current.isValid()) {
        const CellAddress address(current.row(), current.column());
        if (std::binary_search(found.begin(), found.end(), address)) {
            App::Document* doc = sheet->getDocument();
            doc->openTransaction(QT_TRANSLATE_NOOP("Command", "Replace"));
            try {
                replaceCells(address.toString());
                doc->commitTransaction();
                Gui::cmdAppDocument(doc, "recompute()");
            }
            catch (const Base::Exception& e) {
                doc->abortTransaction();
                status->setText(QString::fromUtf8(e.what()));
                return;
            }
        }
    }
    find(true);
}

void DlgFindReplace::replaceAll()
{
    // Sheet::replaceCells() changes every cell whose contents match
    const auto found = sheet->findCells(
        findEdit->text().toStdString(),
        matchCase->isChecked(),
        wholeCell->isChecked(),
        false
    );
    const int count = static_cast<int>(found.size());
    if (count == 0) {
        status->setText(tr("Not found"));
        return;
    }
    App::Document* doc = sheet->getDocument();
    doc->openTransaction(QT_TRANSLATE_NOOP("Command", "Replace All"));
    try {
        replaceCells();
    }
    catch (const Base::Exception& e) {
        doc->abortTransaction();
        status->setText(QString::fromUtf8(e.what()));
        return;
    }
    doc->commitTransaction();
    Gui::cmdAppDocument(doc, "recompute()");
    status->setText(tr("%n cell(s) replaced", "", count));
}

/// Run Sheet.replaceCells() with the dialog's options, in \a range if given,
/// through the command interface so that it is recorded in macros.
void DlgFindReplace::replaceCells(const std::string& range)
{
    const auto quoted = [](const QString& text) {
        return "'" + Base::Tools::escapeEncodeString(text.toStdString()) + "'";
    };
    std::string args = quoted(findEdit->text()) + ", " + quoted(replaceEdit->text()) + ", "
        + (matchCase->isChecked() ? "True" : "False") + ", "
        + (wholeCell->isChecked() ? "True" : "False");
    if (!range.empty()) {
        args += ", '" + range + "'";
    }
    Gui::cmdAppObjectArgs(sheet, "replaceCells(%s)", args);
}

#include "moc_DlgFindReplace.cpp"
