// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
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

#pragma once

#include <memory>
#include <string>
#include <utility>

#include <QDialog>
#include <QString>

#include <App/ObjectIdentifier.h>
#include <FCGlobal.h>

class QModelIndex;
class QTreeWidgetItem;

namespace App
{
class Document;
class DocumentObject;
class Property;
}  // namespace App

namespace Gui::Dialog
{

class Ui_DlgDocumentParameters;

/**
 * The Parameters dialog (Std_Parameters): a table of the parameters of a
 * document, see Gui::Parameters, where they can be edited, renamed, added and
 * deleted.  Every change is a separate transaction so that it can be undone.
 *
 * The dialog is application modal but not run with exec(), like the dialog of
 * ViewProviderVarSet: exec() would block the command that opens it before it
 * closes its own transaction.
 *
 * Its size and position, the widths of its columns and "Show model parameters"
 * are kept in the user parameters when it closes, and restored when it opens.
 */
class GuiExport DlgDocumentParameters: public QDialog
{
    Q_OBJECT

public:
    enum Column
    {
        ColumnName = 0,
        ColumnType = 1,
        ColumnExpression = 2,
        ColumnValue = 3,
        ColumnComment = 4
    };

    explicit DlgDocumentParameters(App::Document* doc, QWidget* parent = nullptr);
    ~DlgDocumentParameters() override;

    DlgDocumentParameters(const DlgDocumentParameters&) = delete;
    DlgDocumentParameters(DlgDocumentParameters&&) = delete;
    DlgDocumentParameters& operator=(const DlgDocumentParameters&) = delete;
    DlgDocumentParameters& operator=(DlgDocumentParameters&&) = delete;

    /// Open the dialog for \a doc, or raise it if it is already open.
    static DlgDocumentParameters* showFor(App::Document* doc);

    /** @name Actions, each in its own transaction.
     * They return false and show a message if the action is refused.
     */
    //@{
    bool renameParameter(QTreeWidgetItem* item, const QString& newName);
    bool setParameterExpression(QTreeWidgetItem* item, const QString& text);
    bool setParameterValue(QTreeWidgetItem* item, const App::any& value);
    bool deleteParameter(QTreeWidgetItem* item, bool confirm);
    /// Add a user parameter. It becomes a property of the object that holds the user parameters
    /// of the document (App::UserParameters::holder), which is created, in the same transaction,
    /// when the document has none.
    bool addUserParameter(const QString& name, const QString& expression, const QString& comment);
    /// Add a property to the variable set \a varSet, or to a new variable set if it is nullptr.
    bool addParameter(
        App::DocumentObject* varSet,
        const QString& name,
        const QString& expression,
        const QString& comment
    );
    //@}

    /// Find the item of the parameter at \a path of the object named \a objectName.
    QTreeWidgetItem* findItem(const QString& objectName, const QString& path) const;

    /// Used by the item delegate.
    QWidget* createEditor(QWidget* parent, const QModelIndex& index) const;
    void commitEditor(QWidget* editor, const QModelIndex& index);

public Q_SLOTS:
    void refresh();
    void done(int result) override;

protected:
    void changeEvent(QEvent* e) override;

private:
    void onFilterChanged();
    void onAdd();
    void onDelete();
    void onUndo();
    void updateButtons();

    void applyFilter();
    void showMessage(const QString& text, bool error = true);
    App::Document* document() const;
    App::DocumentObject* objectOf(const QTreeWidgetItem* item) const;
    App::Property* propertyOf(const QTreeWidgetItem* item) const;
    bool identifierOf(const QTreeWidgetItem* item, App::ObjectIdentifier& path) const;
    QTreeWidgetItem* itemFromIndex(const QModelIndex& index) const;
    /// What "Add" proposes for a new parameter: the name of a variable set, or of the object that
    /// holds the user parameters, which the document may not have yet.
    QString defaultAddTarget() const;
    void scheduleRefresh();
    void saveLayout() const;

    std::string documentName;
    std::unique_ptr<Ui_DlgDocumentParameters> ui;
    bool refreshScheduled = false;
    /// The object name and path of the item to select after the next refresh.
    std::pair<QString, QString> selectAfterRefresh;
};

}  // namespace Gui::Dialog
