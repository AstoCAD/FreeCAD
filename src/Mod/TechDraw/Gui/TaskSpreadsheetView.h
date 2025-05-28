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
#ifndef TECHDRAWGUI_TASKSPREADSHEETVIEW_H
#define TECHDRAWGUI_TASKSPREADSHEETVIEW_H

#include <Gui/TaskView/TaskDialog.h>
#include <QWidget>
#include <memory>  // For std::unique_ptr

// Forward declarations
class Ui_TaskSpreadsheetView;  // The class name from the .ui file for the widget's UI
namespace Spreadsheet
{
class Sheet;
}
namespace TechDraw
{
class DrawViewSpreadsheet;
class DrawPage;
}  // namespace TechDraw
namespace App
{
class DocumentObject;
}  // namespace App
class QTableWidgetItem;
class QFont;
class QColor;
class QAbstractButton;

namespace TechDrawGui
{
class ViewProviderSpreadsheet;

//---------------------------------------------------------------------------
// TaskSpreadsheetView (The QWidget holding the UI elements)
//---------------------------------------------------------------------------
class TaskSpreadsheetView: public QWidget
{
    Q_OBJECT

public:
    explicit TaskSpreadsheetView(TechDraw::DrawViewSpreadsheet* viewToEdit,
                                 Spreadsheet::Sheet* preselectedSheet,
                                 TechDraw::DrawPage* targetPage,
                                 QWidget* parent = nullptr);

    bool initializeContent();

    bool apply();
    void reject();


protected:
    void changeEvent(QEvent* e) override;

private Q_SLOTS:
    void onStartCellEditingFinished();
    void onEndCellEditingFinished();
    void onTableCellChanged(int row, int column);
    void onFontChanged(const QFont& font);
    void onScaleChanged(double value);
    void onTextSizeChanged(double value);
    void onTextColorChanged();
    void onTableColumnResized(int logicalIndex, int oldSize, int newSize);
    void onClaimSpreadsheetToggled(bool val);
    void onLineWidthChanged(double value);
    // void onClaimSpreadsheetToggled(bool checked); // Will be handled in applyChangesAndCommit

private:
    ViewProviderSpreadsheet* getVps();
    void loadGuiFromView();

    void populateTableWidget();
    void updateSpreadsheetCellValue(int tableRow, int tableCol, const QString& data);
    bool createSpreadsheet();
    bool createSpreadsheetView();
    void setViewSource();

    bool parseCellAddress(const QString& address, int& col, int& row) const;  // 0-indexed
    QString cellAddressToString(int col, int row) const;  // 0-indexed to A1 style
    std::vector<std::string> getSpreadsheetColumnLetters(unsigned int count) const;
    void revalidateRangeAndUpdatePreview();

    std::unique_ptr<Ui_TaskSpreadsheetView> ui;
    TechDraw::DrawViewSpreadsheet* m_viewObject;  // The view object being created or edited
    Spreadsheet::Sheet* m_spreadsheet;            // The source spreadsheet
    TechDraw::DrawPage* m_targetPage;             // Page to add new views to

    bool m_isEditingView;                    // True if m_viewObject was non-null at construction
    bool m_spreadsheetWasPreselected;        // True if m_spreadsheet was non-null at construction

    // Parsed range for the table widget, 0-indexed
    int m_startCol, m_startRow;
    int m_endCol, m_endRow;
    bool m_rangeValid;

    bool m_isLoadingTable;               // Flag to prevent feedback loops during table population
    bool m_isPopulatingGui;              // Flag to prevent ui signals during programmatic data load
};


//---------------------------------------------------------------------------
// TaskDlgSpreadsheetView (The TaskDialog itself)
//---------------------------------------------------------------------------
class TaskDlgSpreadsheetView: public Gui::TaskView::TaskDialog
{
    Q_OBJECT

public:
    // If viewToEdit is provided, we are editing an existing DrawViewSpreadsheet.
    // If preselectedSheet is provided (and viewToEdit is null), creating new view for that sheet.
    // If both are null, creating new view and will create a new sheet.
    // targetPage is the page where a new view will be added.
    explicit TaskDlgSpreadsheetView(TechDraw::DrawPage* targetPage,
                                    TechDraw::DrawViewSpreadsheet* viewToEdit = nullptr,
                                    Spreadsheet::Sheet* preselectedSheet = nullptr);

    void open() override;
    bool accept() override;
    bool reject() override;


    QDialogButtonBox::StandardButtons getStandardButtons() const override
    {
        // Ok and Cancel are standard, Apply can be added if needed for non-modal updates
        return QDialogButtonBox::Ok | QDialogButtonBox::Cancel;
    }

private:
    TaskSpreadsheetView* m_widget;
};

}  // namespace TechDrawGui

#endif  // TECHDRAWGUI_TASKSPREADSHEETVIEW_H