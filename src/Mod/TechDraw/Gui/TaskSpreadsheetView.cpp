/* SPDX - License - Identifier: LGPL - 2.1 - or -later
 ****************************************************************************
 *                                                                          *
 *   Copyright (c) 2025 Pierre-Louis Boyer                                  *
 *                                                                          *
 *   This file is part of FreeCAD.                                          *
 *                                                                          *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, either version 2.1 of the   *
 *   License, or (at your option) any later version.                        *
 *                                                                          *
 *   FreeCAD is distributed in the hope that it will be useful, but         *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of             *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
 *   Lesser General Public License for more details.                        *
 *                                                                          *
 *   You should have received a copy of the GNU Lesser General Public       *
 *   License along with FreeCAD. If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                       *
 *                                                                          *
 ***************************************************************************/

#include "PreCompiled.h"
#ifndef _PreComp_
#include <QPushButton>
#include <QLineEdit>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QFontComboBox>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QMessageBox>
#include <QHeaderView> // For table header
#include <QRegularExpression>
#include <QRegularExpressionMatch>
#include <boost_regex.hpp> // For DrawViewSpreadsheet's internal parsing if we need similar logic
#endif

#include "TaskSpreadsheetView.h"
#include "ui_TaskSpreadsheetView.h"

// FreeCAD Base Includes
#include <Base/Console.h>
#include <Base/Tools.h> // For getUniqueObjectName

// FreeCAD App Includes
#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <Mod/Spreadsheet/App/Sheet.h>
#include <Mod/Spreadsheet/App/Cell.h> // For setting cell content

// FreeCAD Gui Includes
#include <Gui/Application.h>
#include <Gui/Command.h>
#include <Gui/CommandT.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/MainWindow.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Widgets.h> // For Gui::ColorButton

// TechDraw Includes
#include <Mod/TechDraw/App/DrawPage.h>
#include <Mod/TechDraw/App/DrawViewSpreadsheet.h>
#include <Mod/TechDraw/App/DrawUtil.h> // For getUniqueObjectName if not in Base::Tools
#include <Mod/TechDraw/App/Preferences.h> // For default font/size
#include <Mod/TechDraw/App/LineGroup.h>
#include <Mod/TechDraw/Gui/ViewProviderSpreadsheet.h> // For ClaimSheetAsChild
#include "PreferencesGui.h"

namespace TechDrawGui {

//===========================================================================
// TaskSpreadsheetView (The QWidget)
//===========================================================================

TaskSpreadsheetView::TaskSpreadsheetView(TechDraw::DrawViewSpreadsheet* viewToEdit,
                                         Spreadsheet::Sheet* preselectedSheet,
                                         TechDraw::DrawPage* targetPage,
                                         QWidget* parent)
    : QWidget(parent)
    , ui(new Ui_TaskSpreadsheetView())
    , m_viewObject(viewToEdit)
    , m_spreadsheet(preselectedSheet)
    , m_targetPage(targetPage)
    , m_isEditingView(viewToEdit != nullptr)
    , m_spreadsheetWasPreselected(preselectedSheet != nullptr && !m_isEditingView)
    , m_startCol(0), m_startRow(0) // Default A1
    , m_endCol(1), m_endRow(1)     // Default B2
    , m_rangeValid(true)
    , m_isLoadingTable(false)
    , m_isPopulatingGui(false)
{
    ui->setupUi(this);

    // Connect signals
    connect(ui->lineEdit_StartCell, &QLineEdit::editingFinished, this, &TaskSpreadsheetView::onStartCellEditingFinished);
    connect(ui->lineEdit_EndCell, &QLineEdit::editingFinished, this, &TaskSpreadsheetView::onEndCellEditingFinished);
    connect(ui->tableWidget_SpreadsheetData, &QTableWidget::cellChanged, this, &TaskSpreadsheetView::onTableCellChanged);

    connect(ui->fontComboBox_Font, &QFontComboBox::currentFontChanged, this, &TaskSpreadsheetView::onFontChanged);
    connect(ui->doubleSpinBox_TextSize, QOverload<double>::of(&QDoubleSpinBox::valueChanged), this, &TaskSpreadsheetView::onTextSizeChanged);
    connect(ui->doubleSpinBox_Scale, QOverload<double>::of(&QDoubleSpinBox::valueChanged), this, &TaskSpreadsheetView::onScaleChanged);
    connect(ui->cpFrameColor, &Gui::ColorButton::changed, this, &TaskSpreadsheetView::onTextColorChanged);
    connect(ui->doubleSpinBox_LineWidth, QOverload<double>::of(&QDoubleSpinBox::valueChanged), this, &TaskSpreadsheetView::onLineWidthChanged);
    connect(ui->checkBox_ClaimSpreadsheet, &QCheckBox::toggled, this, &TaskSpreadsheetView::onClaimSpreadsheetToggled);
    
    connect(ui->tableWidget_SpreadsheetData->horizontalHeader(), &QHeaderView::sectionResized,
            this, &TaskSpreadsheetView::onTableColumnResized);

    // Initial placeholder text - will be overwritten by loadGuiFrom*
    ui->lineEdit_StartCell->setText(QStringLiteral("A1"));
    ui->lineEdit_EndCell->setText(QStringLiteral("B2"));
    parseCellAddress(ui->lineEdit_StartCell->text(), m_startCol, m_startRow);
    parseCellAddress(ui->lineEdit_EndCell->text(), m_endCol, m_endRow);
}

bool TaskSpreadsheetView::initializeContent()
{
    if (!m_targetPage || !m_targetPage->getDocument()) {
        Base::Console().error(
            "TaskSpreadsheetView::initializeContent: No valid target page or document.\n");
        return false;
    }

    m_isPopulatingGui = true; // Block signals during initial load

    if (m_isEditingView) {
        Gui::Command::openCommand(QT_TRANSLATE_NOOP("Command", "Edit Spreadsheet View"));
    }
    else {
        Gui::Command::openCommand(QT_TRANSLATE_NOOP("Command", "Create Spreadsheet View"));
    }

    
    if (m_isEditingView && m_viewObject) {
        m_spreadsheet = static_cast<Spreadsheet::Sheet*>(m_viewObject->Source.getValue());
        if (!m_spreadsheet->isDerivedFrom<Spreadsheet::Sheet>()) {
            Base::Console().warning( "TaskSpreadsheetView: Source spreadsheet is bad.\n");
            return false;
        }

        loadGuiFromView();
    }
    else {
        if (!m_spreadsheet) {
            if (!createSpreadsheet()) {
                return false;
            }
        }

        if (!createSpreadsheetView()) {
            return false;
        }

        loadGuiFromView();

        ui->checkBox_ClaimSpreadsheet->setChecked(!m_spreadsheetWasPreselected);

        auto* vps = getVps();
        if (vps) {
            vps->ClaimSheetAsChild.setValue(ui->checkBox_ClaimSpreadsheet->isChecked());
        }

        m_viewObject->recomputeFeature();
    }

    m_isPopulatingGui = false;

    revalidateRangeAndUpdatePreview();
    return true;
}


void TaskSpreadsheetView::loadGuiFromView()
{
    ui->lineEdit_StartCell->setText(QString::fromStdString(m_viewObject->CellStart.getValue()));
    ui->lineEdit_EndCell->setText(QString::fromStdString(m_viewObject->CellEnd.getValue()));

    parseCellAddress(ui->lineEdit_StartCell->text(), m_startCol, m_startRow);
    parseCellAddress(ui->lineEdit_EndCell->text(), m_endCol, m_endRow);

    ui->fontComboBox_Font->setCurrentFont(QFont(QString::fromStdString(m_viewObject->Font.getValue())));
    ui->doubleSpinBox_TextSize->setValue(m_viewObject->TextSize.getValue());
    ui->doubleSpinBox_Scale->setValue(m_viewObject->Scale.getValue());
    ui->cpFrameColor->setColor(m_viewObject->TextColor.getValue().asValue<QColor>());
    ui->doubleSpinBox_LineWidth->setValue(m_viewObject->LineWidth.getValue());

    auto* vps = getVps();
    if (vps) {
        ui->checkBox_ClaimSpreadsheet->setChecked(vps->ClaimSheetAsChild.getValue());
    }
}

bool TaskSpreadsheetView::apply()
{
    if (!m_rangeValid) {
        QMessageBox::warning(this, tr("Invalid Range"), tr("The specified cell range is invalid. Please correct it."));
        return false;
    }

    //m_viewObject->Source.setValue(m_spreadsheet);
    Gui::Command::commitCommand();

    m_viewObject->touch();
    m_viewObject->getDocument()->recompute();

    return true;
}

void TaskSpreadsheetView::reject()
{
    Gui::Command::abortCommand();
}

ViewProviderSpreadsheet* TaskSpreadsheetView::getVps()
{
    return dynamic_cast<TechDrawGui::ViewProviderSpreadsheet*>(
        Gui::Application::Instance->getDocument(m_viewObject->getDocument())
            ->getViewProvider(m_viewObject));
}

void TaskSpreadsheetView::changeEvent(QEvent* e)
{
    if (e->type() == QEvent::LanguageChange) {
        ui->retranslateUi(this);
    } else {
        QWidget::changeEvent(e);
    }
}

bool TaskSpreadsheetView::createSpreadsheet()
{
    if (m_spreadsheet) {
        return m_spreadsheet;
    }

    auto* doc = m_targetPage->getDocument();
    const std::string objectName {QT_TR_NOOP("Spreadsheet")};
    std::string objName = doc->getUniqueObjectName(objectName.c_str());
    m_spreadsheet = static_cast<Spreadsheet::Sheet*>(doc->addObject("Spreadsheet::Sheet", objName.c_str()));

    return m_spreadsheet;
}

bool TaskSpreadsheetView::createSpreadsheetView()
{
    if (m_viewObject) {
        return m_viewObject;
    }
    
    auto* doc = m_targetPage->getDocument();
    const std::string objectName {QT_TR_NOOP("Sheet")};
    std::string objName = doc->getUniqueObjectName(objectName.c_str());
    Gui::Command::doCommand(Gui::Command::Doc, "App.getDocument('%s').addObject('TechDraw::DrawViewSpreadsheet', '%s')",
        doc->getName(),
        objName.c_str());
    Gui::Command::doCommand(Gui::Command::Doc, "App.getDocument('%s').%s.translateLabel('DrawViewSpreadsheet', 'Sheet', '%s')",
        doc->getName(),
        objName.c_str(),
        objName.c_str());

    
    m_viewObject = dynamic_cast<TechDraw::DrawViewSpreadsheet*>(doc->getObject(objName.c_str()));
    if (!m_viewObject) {
        return false;
    }

    setViewSource();

    Gui::Command::doCommand(Gui::Command::Doc,
                            "App.getDocument('%s').%s.addView(App.getDocument('%s').%s)",
                            doc->getName(),
                            m_targetPage->getNameInDocument(),
                            doc->getName(),
                            objName.c_str());

    return m_viewObject;
}

void TaskSpreadsheetView::setViewSource()
{
    if (m_viewObject && m_spreadsheet) {
        auto* doc = m_targetPage->getDocument();

        Gui::Command::doCommand(Gui::Command::Doc,
                                "App.getDocument('%s').%s.Source = App.activeDocument().%s",
                                doc->getName(),
                                m_viewObject->getNameInDocument(),
                                m_spreadsheet->getNameInDocument());
    }
}

bool TaskSpreadsheetView::parseCellAddress(const QString& addressStr, int& colIdx, int& rowIdx) const
{
    // A simple parser for "A1", "B2", "AA10" etc.
    // Converts to 0-indexed colIdx, rowIdx
    if (addressStr.isEmpty()) return false;

    QRegularExpression re(QStringLiteral("^([A-Z]+)([1-9][0-9]*)$"), QRegularExpression::CaseInsensitiveOption);
    QRegularExpressionMatch match = re.match(addressStr.toUpper());

    if (!match.hasMatch()) {
        return false;
    }

    QString colStr = match.captured(1);
    QString rowStr = match.captured(2);

    // Convert column letters to 0-indexed integer
    long tempCol = 0;
    for (QChar c : colStr) {
        tempCol = tempCol * 26 + (c.toLatin1() - 'A' + 1);
    }
    colIdx = static_cast<int>(tempCol - 1); // 0-indexed

    bool ok;
    rowIdx = rowStr.toInt(&ok) - 1; // 0-indexed

    return ok && colIdx >= 0 && rowIdx >=0;
}

QString TaskSpreadsheetView::cellAddressToString(int colIdx, int rowIdx) const
{
    // Converts 0-indexed colIdx, rowIdx to "A1" style string
    if (colIdx < 0 || rowIdx < 0) return QString();

    QString colStr;
    int tempCol = colIdx + 1; // 1-indexed for conversion
    while (tempCol > 0) {
        int remainder = (tempCol - 1) % 26;
        colStr.prepend(QChar('A' + remainder));
        tempCol = (tempCol - 1) / 26;
    }
    return colStr + QString::number(rowIdx + 1);
}

std::vector<std::string> TaskSpreadsheetView::getSpreadsheetColumnLetters(unsigned int count) const
{
    std::vector<std::string> headers;
    headers.reserve(count);
    for (unsigned int i = 0; i < count; ++i) {
        headers.push_back(cellAddressToString(i, 0).remove(QRegularExpression(QStringLiteral("[0-9]"))).toStdString());
    }
    return headers;
}

void TaskSpreadsheetView::revalidateRangeAndUpdatePreview()
{
    if (m_isPopulatingGui) {
        return;
    }

    bool startOk = parseCellAddress(ui->lineEdit_StartCell->text(), m_startCol, m_startRow);
    bool endOk = parseCellAddress(ui->lineEdit_EndCell->text(), m_endCol, m_endRow);

    m_rangeValid = startOk && endOk &&
                   m_startCol <= m_endCol &&
                   m_startRow <= m_endRow;

    if (m_rangeValid) {
        ui->lineEdit_StartCell->setStyleSheet(QStringLiteral(""));
        ui->lineEdit_EndCell->setStyleSheet(QStringLiteral(""));
        populateTableWidget();
    }
    else {
        // Indicate error, e.g., red border
        QString errorStyle = QString::fromLatin1("QLineEdit { border: 1px solid red; }");
        if (!startOk || (startOk && endOk && m_startCol > m_endCol) || (startOk && endOk && m_startRow > m_endRow) ) {
            ui->lineEdit_StartCell->setStyleSheet(errorStyle);
        } else {
            ui->lineEdit_StartCell->setStyleSheet(QStringLiteral(""));
        }
        if (!endOk || (startOk && endOk && m_startCol > m_endCol) || (startOk && endOk && m_startRow > m_endRow)) {
            ui->lineEdit_EndCell->setStyleSheet(errorStyle);
        } else {
            ui->lineEdit_EndCell->setStyleSheet(QStringLiteral(""));
        }
        // Clear the table if range is invalid
        ui->tableWidget_SpreadsheetData->clearContents();
        ui->tableWidget_SpreadsheetData->setRowCount(0);
        ui->tableWidget_SpreadsheetData->setColumnCount(0);
    }

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onStartCellEditingFinished()
{
    m_viewObject->CellStart.setValue(ui->lineEdit_StartCell->text().toStdString());
    revalidateRangeAndUpdatePreview();
}

void TaskSpreadsheetView::onEndCellEditingFinished()
{
    m_viewObject->CellEnd.setValue(ui->lineEdit_EndCell->text().toStdString());
    revalidateRangeAndUpdatePreview();
}


void TaskSpreadsheetView::populateTableWidget()
{
    if (m_isLoadingTable || !m_rangeValid) return;
    m_isLoadingTable = true;

    int numCols = m_endCol - m_startCol + 1;
    int numRows = m_endRow - m_startRow + 1;

    // Max columns/rows for sanity (e.g. prevent huge table creation)
    const int MAX_PREVIEW_COLS = 100;
    const int MAX_PREVIEW_ROWS = 200;
    if (numCols <=0 || numRows <=0 || numCols > MAX_PREVIEW_COLS || numRows > MAX_PREVIEW_ROWS) {
        // Base::Console().Warning("TaskSpreadsheetView::populateTableWidget: Range too large or invalid for preview. Cols: %d, Rows: %d\n", numCols, numRows);
        // Don't clear if just too large, but don't populate either. This state handled by m_rangeValid=false path in revalidate.
        // If m_rangeValid is true but exceeds max, we could show a message.
        // For now, just don't populate if it's excessive.
        if (numCols > MAX_PREVIEW_COLS || numRows > MAX_PREVIEW_ROWS) {
             ui->tableWidget_SpreadsheetData->setToolTip(tr("Range too large for preview. Max %1 cols, %2 rows.").arg(MAX_PREVIEW_COLS).arg(MAX_PREVIEW_ROWS));
        } else {
            ui->tableWidget_SpreadsheetData->setToolTip(QStringLiteral(""));
        }
        // If m_rangeValid is true but numCols/Rows is 0 or negative, it's an issue from parseCellAddress.
        // This should have set m_rangeValid to false.
        // If range is valid but 0, table will just be empty.
        ui->tableWidget_SpreadsheetData->setRowCount(numRows > 0 ? numRows : 0);
        ui->tableWidget_SpreadsheetData->setColumnCount(numCols > 0 ? numCols : 0);

        // Set headers even if content is not fully loaded due to size
        if (numCols > 0 && numCols <= MAX_PREVIEW_COLS) {
            QStringList colHeaders;
            for (int c = 0; c < numCols; ++c) {
                colHeaders << cellAddressToString(m_startCol + c, 0)
                                  .remove(QRegularExpression(QStringLiteral("[0-9]")));
            }
            ui->tableWidget_SpreadsheetData->setHorizontalHeaderLabels(colHeaders);
        }
        if (numRows > 0 && numRows <= MAX_PREVIEW_ROWS) {
            QStringList rowHeaders;
            for (int r = 0; r < numRows; ++r) {
                rowHeaders << QString::number(m_startRow + r + 1);
            }
            ui->tableWidget_SpreadsheetData->setVerticalHeaderLabels(rowHeaders);
        }
        ui->tableWidget_SpreadsheetData->clearContents(); // If range too large but headers set.
        m_isLoadingTable = false;
        return;
    }
    ui->tableWidget_SpreadsheetData->setToolTip(QStringLiteral(""));


    ui->tableWidget_SpreadsheetData->setRowCount(numRows);
    ui->tableWidget_SpreadsheetData->setColumnCount(numCols);

    QStringList colHeaders;
    for (int c = 0; c < numCols; ++c) {
        colHeaders << cellAddressToString(m_startCol + c, 0)
                          .remove(QRegularExpression(QStringLiteral("[0-9]")));
    }
    ui->tableWidget_SpreadsheetData->setHorizontalHeaderLabels(colHeaders);

    QStringList rowHeaders;
    for (int r = 0; r < numRows; ++r) {
        rowHeaders << QString::number(m_startRow + r + 1);
    }
    ui->tableWidget_SpreadsheetData->setVerticalHeaderLabels(rowHeaders);

    for (int r_table = 0; r_table < numRows; ++r_table) {
        for (int c_table = 0; c_table < numCols; ++c_table) {
            int sheet_col = m_startCol + c_table;
            int sheet_row = m_startRow + r_table;
            QString address = cellAddressToString(sheet_col, sheet_row);

            App::CellAddress cellAddress(address.toStdString().c_str());
            Spreadsheet::Cell* cell = m_spreadsheet->getCell(cellAddress);
            QTableWidgetItem* item = new QTableWidgetItem();
            if (cell) {
                item->setText(QString::fromStdString(cell->getFormattedQuantity()));
            }
            else {
                item->setText(QString());
            }
            ui->tableWidget_SpreadsheetData->setItem(r_table, c_table, item);
        }
    }

    if (numCols > 0 && numCols <= MAX_PREVIEW_COLS) {
        for (int c_table = 0; c_table < numCols; ++c_table) {
            int pixelWidth = m_spreadsheet->getColumnWidth(m_startCol + c_table);
            ui->tableWidget_SpreadsheetData->setColumnWidth(c_table, pixelWidth);
        }
    }
    else {
        ui->tableWidget_SpreadsheetData->horizontalHeader()->setMinimumSectionSize(85);
        ui->tableWidget_SpreadsheetData->resizeColumnsToContents();
    }

    m_isLoadingTable = false;
}

void TaskSpreadsheetView::onTableCellChanged(int row_table, int column_table)
{
    if (m_isLoadingTable || m_isPopulatingGui) return; // Don't react to programmatic changes

    if (!m_spreadsheet) {
        Base::Console().warning("TaskSpreadsheetView::onTableCellChanged: No spreadsheet to update.\n");
        return;
    }
    if (!m_rangeValid) { // Should not happen if table is populated
        Base::Console().warning("TaskSpreadsheetView::onTableCellChanged: Range invalid, cannot map table cell to spreadsheet.\n");
        return;
    }

    QTableWidgetItem* item = ui->tableWidget_SpreadsheetData->item(row_table, column_table);
    if (!item) return;

    int sheet_col = m_startCol + column_table;
    int sheet_row = m_startRow + row_table;
    QString sheetAddressStr = cellAddressToString(sheet_col, sheet_row);

    updateSpreadsheetCellValue(sheet_row +1 , sheet_col +1, item->text()); // Spreadsheet::Sheet::set uses 1-based indexing for API

    // Potentially re-fetch and display the value if the spreadsheet processed it (e.g. formula)
    // This creates a slight flicker and might be too much. For now, assume direct set is fine.
    /*
    m_isLoadingTable = true; // Prevent recursion
    Spreadsheet::Cell* cell = m_spreadsheet->getCell(sheetAddressStr.toStdString().c_str());
    if (cell) {
        item->setText(QString::fromStdString(cell->getDisplayString()));
    } else {
        item->setText(QString()); // Or handle error
    }
    m_isLoadingTable = false;
    */
}

void TaskSpreadsheetView::updateSpreadsheetCellValue(int sheet_row_1based, int sheet_col_1based, const QString& data)
{
    if (!m_spreadsheet) return;

    m_spreadsheet->setCell(App::CellAddress(sheet_row_1based - 1, sheet_col_1based - 1).toString().c_str(),
        data.toStdString().c_str());

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onFontChanged(const QFont& font)
{
    if (m_isPopulatingGui) {
        return;
    }

    m_viewObject->Font.setValue(ui->fontComboBox_Font->currentFont().family().toStdString());

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onTextSizeChanged(double value)
{
    if (m_isPopulatingGui) {
        return;
    }

    m_viewObject->TextSize.setValue(ui->doubleSpinBox_TextSize->value());

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onScaleChanged(double value)
{
    if (m_isPopulatingGui) {
        return;
    }

    m_viewObject->Scale.setValue(ui->doubleSpinBox_Scale->value());

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onTextColorChanged()
{
    if (m_isPopulatingGui) {
        return;
    }

    Base::Color ac;
    ac.setValue<QColor>(ui->cpFrameColor->color());
    m_viewObject->TextColor.setValue(ac);

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onLineWidthChanged(double value)
{
    if (m_isPopulatingGui) {
        return;
    }

    m_viewObject->LineWidth.setValue(ui->doubleSpinBox_LineWidth->value());

    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onClaimSpreadsheetToggled(bool val)
{
    if (m_isPopulatingGui) {
        return;
    }

    TechDrawGui::ViewProviderSpreadsheet* vp = getVps();
    if (vp) {
        vp->ClaimSheetAsChild.setValue(ui->checkBox_ClaimSpreadsheet->isChecked());
    }

    m_viewObject->touch();
    m_viewObject->recomputeFeature();
}

void TaskSpreadsheetView::onTableColumnResized(int logicalIndex_table,
                                               int oldSize,
                                               int newSize_pixels)
{
    Q_UNUSED(oldSize);
    if (m_isPopulatingGui || m_isLoadingTable || !m_rangeValid) {
        return;  // Don't act on programmatic changes or if sheet/range is invalid
    }

    int sheet_col_idx = m_startCol + logicalIndex_table;

    m_spreadsheet->setColumnWidth(sheet_col_idx, newSize_pixels);

    m_viewObject->recomputeFeature();
}


//===========================================================================
// TaskDlgSpreadsheetView (The Dialog)
//===========================================================================

TaskDlgSpreadsheetView::TaskDlgSpreadsheetView(TechDraw::DrawPage* targetPage,
                                               TechDraw::DrawViewSpreadsheet* viewToEdit,
                                               Spreadsheet::Sheet* preselectedSheet)
    : Gui::TaskView::TaskDialog()
    , m_widget(new TaskSpreadsheetView(viewToEdit, preselectedSheet, targetPage))
{
    m_widget->setWindowTitle(viewToEdit ? tr("Edit Spreadsheet View")
                                        : tr("Create Spreadsheet View"));
    addTaskBox(Gui::BitmapFactory().pixmap("actions/TechDraw_SpreadsheetView"), m_widget);
}

void TaskDlgSpreadsheetView::open()
{
    if (!m_widget->initializeContent()) {
        Base::Console().error("TaskDlgSpreadsheetView::open: Widget initialization failed. Rejecting.\n");
        Gui::Control().closeDialog();
        return;
    }
    Gui::TaskView::TaskDialog::open();
}

bool TaskDlgSpreadsheetView::accept()
{
    return m_widget->apply();
}

bool TaskDlgSpreadsheetView::reject()
{
    m_widget->reject();
    return true; // Always allow reject to close the dialog
}


} // namespace TechDrawGui

#include "moc_TaskSpreadsheetView.cpp"