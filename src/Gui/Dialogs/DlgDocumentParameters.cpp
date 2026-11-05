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

#include <algorithm>
#include <cstring>
#include <limits>
#include <map>

#include <QCheckBox>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QFont>
#include <QFormLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPointer>
#include <QPushButton>
#include <QSet>
#include <QSpinBox>
#include <QStyledItemDelegate>
#include <QTreeWidget>
#include <QVBoxLayout>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/PropertyUnits.h>
#include <App/UserParameters.h>
#include <App/VarSet.h>
#include <Base/Exception.h>
#include <Base/Quantity.h>

#include "Dialogs/DlgDocumentParameters.h"
#include "Dialogs/DocumentParameters.h"
#include "ui_DlgDocumentParameters.h"
#include "Application.h"
#include "BitmapFactory.h"
#include "Document.h"
#include "ExpressionCompleter.h"
#include "MainWindow.h"
#include "NumericLocale.h"
#include "QuantitySpinBox.h"
#include "Selection.h"

using namespace Gui;
using namespace Gui::Dialog;

namespace
{

constexpr int ObjectRole = Qt::UserRole;
constexpr int PathRole = Qt::UserRole + 1;
constexpr int CategoryRole = Qt::UserRole + 2;
constexpr int DynamicRole = Qt::UserRole + 3;
constexpr int ValueEditableRole = Qt::UserRole + 4;
constexpr int HolderRole = Qt::UserRole + 5;
constexpr int GroupKeyRole = Qt::UserRole + 6;

const char* const EditorName = "parameterEditor";

QString fromStd(const std::string& text)
{
    return QString::fromStdString(text);
}

bool isNumberValue(const App::any& value)
{
    return value.type() == typeid(Base::Quantity) || value.type() == typeid(double)
        || value.type() == typeid(float);
}

Base::Quantity toQuantity(const App::any& value)
{
    if (value.type() == typeid(Base::Quantity)) {
        return App::any_cast<Base::Quantity>(value);
    }
    if (value.type() == typeid(float)) {
        return Base::Quantity(App::any_cast<float>(value));
    }
    return Base::Quantity(App::any_cast<double>(value));
}

/// A transaction that is aborted unless it is committed.
class ParameterTransaction
{
public:
    explicit ParameterTransaction(const char* name)
        : id(App::GetApplication().setActiveTransaction(
              App::TransactionName {.name = name, .temporary = false}
          ))
    {}
    ~ParameterTransaction()
    {
        if (id != 0) {
            App::GetApplication().abortTransaction(id);
        }
    }
    ParameterTransaction(const ParameterTransaction&) = delete;
    ParameterTransaction(ParameterTransaction&&) = delete;
    ParameterTransaction& operator=(const ParameterTransaction&) = delete;
    ParameterTransaction& operator=(ParameterTransaction&&) = delete;

    void commit()
    {
        if (id != 0) {
            App::GetApplication().commitTransaction(id);
            id = 0;
        }
    }

private:
    int id;
};

class ParameterItemDelegate: public QStyledItemDelegate
{
public:
    explicit ParameterItemDelegate(DlgDocumentParameters* dialog)
        : QStyledItemDelegate(dialog)
        , dialog(dialog)
    {}

    QWidget* createEditor(
        QWidget* parent,
        const QStyleOptionViewItem& /*option*/,
        const QModelIndex& index
    ) const override
    {
        return dialog->createEditor(parent, index);
    }

    // The editors are initialized by createEditor().
    void setEditorData(QWidget* /*editor*/, const QModelIndex& /*index*/) const override
    {}

    // The document is changed instead of the model: the tree is rebuilt afterwards.
    void setModelData(QWidget* editor, QAbstractItemModel* /*model*/, const QModelIndex& index) const override
    {
        dialog->commitEditor(editor, index);
    }

private:
    DlgDocumentParameters* dialog;
};

QString nameErrorText(Parameters::NameError error, const QString& name)
{
    using Parameters::NameError;
    switch (error) {
        case NameError::None:
            return {};
        case NameError::Empty:
            return DlgDocumentParameters::tr("The name cannot be empty");
        case NameError::NotIdentifier:
            return DlgDocumentParameters::tr(
                       "'%1' is not a valid name: use letters, digits and underscores, and do not "
                       "start with a digit"
            )
                .arg(name);
        case NameError::Constant:
            return DlgDocumentParameters::tr("'%1' is a constant").arg(name);
        case NameError::Unit:
            return DlgDocumentParameters::tr("'%1' is a unit").arg(name);
        case NameError::ExistsInObject:
            return DlgDocumentParameters::tr("'%1' already exists in this object").arg(name);
        case NameError::ExistsInDocument:
            return DlgDocumentParameters::tr("A user parameter named '%1' already exists in the document")
                .arg(name);
        case NameError::CellAddress:
            return DlgDocumentParameters::tr(
                       "'%1' is a spreadsheet cell address and cannot name a user parameter"
            )
                .arg(name);
    }
    return {};
}

QString userParameterNameErrorText(App::UserParameters::NameStatus status, const QString& name)
{
    using App::UserParameters::NameStatus;
    switch (status) {
        case NameStatus::Available:
            return {};
        case NameStatus::Invalid:
            return DlgDocumentParameters::tr(
                       "'%1' is not a valid parameter name: use letters, digits and underscores, "
                       "do not start with a digit or an underscore, and do not use a unit or a "
                       "constant"
            )
                .arg(name);
        case NameStatus::UsedByParameter:
            return nameErrorText(Parameters::NameError::ExistsInDocument, name);
        case NameStatus::UsedByObject:
            return DlgDocumentParameters::tr("An object of this document is named or labeled '%1'")
                .arg(name);
        case NameStatus::UsedByOwnerProperty:
            return nameErrorText(Parameters::NameError::ExistsInObject, name);
        case NameStatus::CellAddress:
            return nameErrorText(Parameters::NameError::CellAddress, name);
    }
    return {};
}

/**
 * The error for the new name \a name of a parameter held by \a holder, empty if it can be used.
 * User parameters follow the rules of App::UserParameters (the same as for `name = value` typed
 * in an input); \a exclude is the property being renamed, if any.
 */
QString nameError(
    const App::DocumentObject* holder,
    const QString& name,
    bool userParameter,
    const App::Property* exclude = nullptr
)
{
    const std::string nameStd = name.toStdString();
    if (!userParameter || !holder || nameStd.empty()) {
        return nameErrorText(Parameters::checkName(holder, nameStd, userParameter, exclude), name);
    }
    if (exclude && nameStd == exclude->getName()) {
        return {};
    }
    return userParameterNameErrorText(
        App::UserParameters::checkName(holder->getDocument(), nameStd, holder),
        name
    );
}

/// The error for a new parameter with the value of \a expr, empty if its type can hold it.
QString valueTypeError(const App::Expression& expr, bool userParameter)
{
    const std::string type = Parameters::propertyTypeForExpression(expr);
    if (type == "App::PropertyString" && userParameter) {
        return DlgDocumentParameters::tr("A user parameter needs a numeric value");
    }
    if (!type.empty()) {
        return {};
    }
    App::ExpressionPtr result = expr.eval();
    if (auto* number = freecad_cast<App::NumberExpression*>(result.get())) {
        return DlgDocumentParameters::tr("No parameter type can store the unit '%1'")
            .arg(QString::fromStdString(number->getUnit().getString()));
    }
    return DlgDocumentParameters::tr("The value must be a number, a quantity or a string");
}

/// Throw if the result of \a expr has a unit that does not fit the parameter at \a path.
void checkUnit(const App::ObjectIdentifier& path, const App::Expression& expr)
{
    App::Property* prop = path.getProperty();
    if (!prop || prop->getTypeId() == App::PropertyQuantity::getClassTypeId()) {
        return;  // a plain quantity takes the unit of its value
    }
    App::ExpressionPtr result = expr.eval();
    auto* number = freecad_cast<App::NumberExpression*>(result.get());
    if (!number || number->getQuantity().isDimensionless()) {
        return;
    }
    App::any current = path.getValue();
    if (current.type() != typeid(Base::Quantity)) {
        return;
    }
    const Base::Unit& unit = App::any_cast<Base::Quantity>(current).getUnit();
    if (unit != Base::Unit::One && unit != number->getUnit()) {
        throw Base::UnitsMismatchError("Unit mismatch between result and required unit");
    }
}

QPointer<DlgDocumentParameters> openDialog;  // NOLINT

}  // namespace

/* TRANSLATOR Gui::Dialog::DlgDocumentParameters */

DlgDocumentParameters::DlgDocumentParameters(App::Document* doc, QWidget* parent)
    : QDialog(parent)
    , documentName(doc ? doc->getName() : "")
    , ui(new Ui_DlgDocumentParameters)
{
    ui->setupUi(this);
    if (doc) {
        setWindowTitle(tr("Parameters - %1").arg(QString::fromUtf8(doc->Label.getValue())));
    }

    ui->treeParameters->setItemDelegate(new ParameterItemDelegate(this));
    ui->treeParameters->header()->setStretchLastSection(true);

    connect(ui->lineEditFilter, &QLineEdit::textChanged, this, &DlgDocumentParameters::onFilterChanged);
    connect(ui->checkBoxModel, &QCheckBox::toggled, this, &DlgDocumentParameters::refresh);
    connect(ui->pushButtonAdd, &QPushButton::clicked, this, &DlgDocumentParameters::onAdd);
    connect(ui->pushButtonDelete, &QPushButton::clicked, this, &DlgDocumentParameters::onDelete);
    connect(ui->pushButtonUndo, &QPushButton::clicked, this, &DlgDocumentParameters::onUndo);
    connect(ui->buttonBox, &QDialogButtonBox::rejected, this, &DlgDocumentParameters::reject);
    connect(
        ui->treeParameters,
        &QTreeWidget::currentItemChanged,
        this,
        &DlgDocumentParameters::updateButtons
    );

    refresh();
    for (int column = ColumnName; column < ColumnComment; ++column) {
        ui->treeParameters->resizeColumnToContents(column);
    }
}

DlgDocumentParameters::~DlgDocumentParameters() = default;

DlgDocumentParameters* DlgDocumentParameters::showFor(App::Document* doc)
{
    if (!doc) {
        return nullptr;
    }
    if (openDialog && openDialog->documentName != doc->getName()) {
        openDialog->close();
        openDialog = nullptr;
    }
    if (!openDialog) {
        openDialog = new DlgDocumentParameters(doc, getMainWindow());
        openDialog->setAttribute(Qt::WA_DeleteOnClose);
        // Not exec(): see the class documentation.
        openDialog->setWindowModality(Qt::ApplicationModal);
    }
    else {
        openDialog->refresh();
    }
    openDialog->show();
    openDialog->raise();
    openDialog->activateWindow();
    return openDialog;
}

App::Document* DlgDocumentParameters::document() const
{
    return documentName.empty() ? nullptr : App::GetApplication().getDocument(documentName.c_str());
}

App::DocumentObject* DlgDocumentParameters::objectOf(const QTreeWidgetItem* item) const
{
    App::Document* doc = document();
    if (!doc || !item) {
        return nullptr;
    }
    QString name = item->data(ColumnName, ObjectRole).toString();
    if (name.isEmpty()) {
        return nullptr;
    }
    return doc->getObject(name.toUtf8().constData());
}

App::Property* DlgDocumentParameters::propertyOf(const QTreeWidgetItem* item) const
{
    App::ObjectIdentifier path;
    if (!identifierOf(item, path)) {
        return nullptr;
    }
    return path.getProperty();
}

bool DlgDocumentParameters::identifierOf(const QTreeWidgetItem* item, App::ObjectIdentifier& path) const
{
    App::DocumentObject* obj = objectOf(item);
    if (!obj) {
        return false;
    }
    std::string pathText = item->data(ColumnName, PathRole).toString().toStdString();
    if (pathText.empty()) {
        return false;
    }
    try {
        if (pathText.find('.') == std::string::npos) {
            App::Property* prop = obj->getPropertyByName(pathText.c_str());
            if (!prop) {
                return false;
            }
            path = App::ObjectIdentifier(*prop);
        }
        else {
            // the leading dot makes the path local to obj (e.g. ".Constraints.width")
            path = App::ObjectIdentifier::parse(obj, "." + pathText);
        }
    }
    catch (const Base::Exception&) {
        return false;
    }
    return path.getProperty() != nullptr;
}

QTreeWidgetItem* DlgDocumentParameters::findItem(const QString& objectName, const QString& path) const
{
    QTreeWidget* tree = ui->treeParameters;
    for (int i = 0; i < tree->topLevelItemCount(); ++i) {
        QTreeWidgetItem* group = tree->topLevelItem(i);
        for (int j = 0; j < group->childCount(); ++j) {
            QTreeWidgetItem* item = group->child(j);
            if (item->data(ColumnName, ObjectRole).toString() == objectName
                && item->data(ColumnName, PathRole).toString() == path) {
                return item;
            }
        }
    }
    return nullptr;
}

QTreeWidgetItem* DlgDocumentParameters::itemFromIndex(const QModelIndex& index) const
{
    if (!index.isValid()) {
        return nullptr;
    }
    QModelIndex first = index.sibling(index.row(), ColumnName);
    QString objectName = first.data(ObjectRole).toString();
    if (objectName.isEmpty()) {
        return nullptr;
    }
    return findItem(objectName, first.data(PathRole).toString());
}

void DlgDocumentParameters::scheduleRefresh()
{
    if (refreshScheduled) {
        return;
    }
    refreshScheduled = true;
    // Queued: this may be called from an item delegate while its editor is open.
    QMetaObject::invokeMethod(this, &DlgDocumentParameters::refresh, Qt::QueuedConnection);
}

void DlgDocumentParameters::refresh()
{
    refreshScheduled = false;
    App::Document* doc = document();
    if (!doc) {
        close();
        return;
    }

    QTreeWidget* tree = ui->treeParameters;

    QString currentObject;
    QString currentPath;
    if (!selectAfterRefresh.first.isEmpty()) {
        currentObject = selectAfterRefresh.first;
        currentPath = selectAfterRefresh.second;
        selectAfterRefresh = {};
    }
    else if (QTreeWidgetItem* current = tree->currentItem()) {
        currentObject = current->data(ColumnName, ObjectRole).toString();
        currentPath = current->data(ColumnName, PathRole).toString();
    }

    QSet<QString> collapsed;
    for (int i = 0; i < tree->topLevelItemCount(); ++i) {
        QTreeWidgetItem* group = tree->topLevelItem(i);
        if (!group->isExpanded()) {
            collapsed.insert(group->data(ColumnName, GroupKeyRole).toString());
        }
    }

    tree->clear();

    auto makeGroup = [tree](const QString& title, const QString& key, const QIcon& icon) {
        auto* group = new QTreeWidgetItem(tree);
        group->setText(ColumnName, title);
        group->setData(ColumnName, GroupKeyRole, key);
        group->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        QFont font = group->font(ColumnName);
        font.setBold(true);
        group->setFont(ColumnName, font);
        group->setFirstColumnSpanned(true);
        if (!icon.isNull()) {
            group->setIcon(ColumnName, icon);
        }
        return group;
    };

    QTreeWidgetItem* userGroup = makeGroup(tr("User Parameters"), QStringLiteral("#user"), QIcon());
    userGroup->setToolTip(
        ColumnName,
        tr("Properties in the group '%1' of the objects of the document")
            .arg(QString::fromLatin1(Parameters::userParametersGroup()))
    );

    std::map<std::string, QTreeWidgetItem*> varSetGroups;
    std::vector<App::DocumentObject*> varSets = doc->getObjectsOfType(App::VarSet::getClassTypeId());
    std::ranges::stable_sort(varSets, [](const App::DocumentObject* a, const App::DocumentObject* b) {
        return std::strcmp(a->Label.getValue(), b->Label.getValue()) < 0;
    });
    QIcon varSetIcon = BitmapFactory().iconFromTheme("VarSet");
    for (App::DocumentObject* varSet : varSets) {
        QString name = QString::fromLatin1(varSet->getNameInDocument());
        QTreeWidgetItem* group = makeGroup(
            QString::fromUtf8(varSet->Label.getValue()),
            QStringLiteral("#varset:") + name,
            varSetIcon
        );
        group->setData(ColumnName, HolderRole, name);
        group->setToolTip(ColumnName, tr("Variable set %1").arg(name));
        varSetGroups[varSet->getNameInDocument()] = group;
    }

    bool includeModel = ui->checkBoxModel->isChecked();
    QTreeWidgetItem* modelGroup = nullptr;
    if (includeModel) {
        modelGroup = makeGroup(tr("Model Parameters"), QStringLiteral("#model"), QIcon());
        modelGroup->setToolTip(
            ColumnName,
            tr("Properties bound to an expression and named sketch constraints")
        );
    }

    QBrush disabledText = palette().brush(QPalette::Disabled, QPalette::Text);
    QTreeWidgetItem* current = nullptr;
    for (const Parameters::Entry& entry : Parameters::collect(doc, includeModel)) {
        QTreeWidgetItem* parent = nullptr;
        switch (entry.category) {
            case Parameters::Category::User:
                parent = userGroup;
                break;
            case Parameters::Category::VarSet: {
                auto it = varSetGroups.find(entry.objectName);
                parent = it == varSetGroups.end() ? nullptr : it->second;
                break;
            }
            case Parameters::Category::Model:
                parent = modelGroup;
                break;
        }
        if (!parent) {
            continue;
        }

        auto* item = new QTreeWidgetItem(parent);
        item->setText(ColumnName, fromStd(entry.name));
        item->setText(ColumnType, fromStd(entry.type));
        item->setText(ColumnExpression, fromStd(entry.expression));
        item->setText(ColumnValue, fromStd(entry.value));
        item->setText(ColumnComment, fromStd(entry.comment));
        item->setToolTip(
            ColumnName,
            QStringLiteral("%1.%2").arg(fromStd(entry.objectLabel), fromStd(entry.path))
        );
        item->setToolTip(ColumnComment, fromStd(entry.comment));
        item->setData(ColumnName, ObjectRole, fromStd(entry.objectName));
        item->setData(ColumnName, PathRole, fromStd(entry.path));
        item->setData(ColumnName, CategoryRole, static_cast<int>(entry.category));
        item->setData(
            ColumnName,
            DynamicRole,
            entry.isDynamic && entry.category != Parameters::Category::Model
        );
        item->setData(ColumnName, ValueEditableRole, entry.valueEditable);
        item->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsEditable);
        if (!entry.valueEditable) {
            item->setForeground(ColumnValue, disabledText);
        }
        if (!entry.isDynamic || entry.category == Parameters::Category::Model) {
            item->setForeground(ColumnName, disabledText);
        }

        if (fromStd(entry.objectName) == currentObject && fromStd(entry.path) == currentPath) {
            current = item;
        }
    }

    for (int i = 0; i < tree->topLevelItemCount(); ++i) {
        QTreeWidgetItem* group = tree->topLevelItem(i);
        group->setExpanded(!collapsed.contains(group->data(ColumnName, GroupKeyRole).toString()));
    }
    if (current) {
        tree->setCurrentItem(current);
    }

    applyFilter();
    updateButtons();
}

void DlgDocumentParameters::onFilterChanged()
{
    applyFilter();
}

void DlgDocumentParameters::applyFilter()
{
    const QString filter = ui->lineEditFilter->text().trimmed();
    QTreeWidget* tree = ui->treeParameters;
    for (int i = 0; i < tree->topLevelItemCount(); ++i) {
        QTreeWidgetItem* group = tree->topLevelItem(i);
        bool groupMatches = !filter.isEmpty()
            && group->text(ColumnName).contains(filter, Qt::CaseInsensitive);
        int visible = 0;
        for (int j = 0; j < group->childCount(); ++j) {
            QTreeWidgetItem* item = group->child(j);
            bool matches = filter.isEmpty() || groupMatches;
            for (int column : {ColumnName, ColumnType, ColumnExpression, ColumnComment}) {
                if (matches) {
                    break;
                }
                matches = item->text(column).contains(filter, Qt::CaseInsensitive);
            }
            item->setHidden(!matches);
            visible += matches ? 1 : 0;
        }
        group->setHidden(!filter.isEmpty() && visible == 0 && !groupMatches);
    }
}

void DlgDocumentParameters::updateButtons()
{
    QTreeWidgetItem* current = ui->treeParameters->currentItem();
    ui->pushButtonDelete->setEnabled(current && current->data(ColumnName, DynamicRole).toBool());
    App::Document* doc = document();
    ui->pushButtonUndo->setEnabled(doc && doc->getAvailableUndos() > 0);
}

void DlgDocumentParameters::showMessage(const QString& text, bool error)
{
    QPalette palette = ui->labelMessage->palette();
    palette.setColor(
        QPalette::WindowText,
        error ? QColor(Qt::red) : this->palette().color(QPalette::WindowText)
    );
    ui->labelMessage->setPalette(palette);
    ui->labelMessage->setText(text);
}

void DlgDocumentParameters::changeEvent(QEvent* e)
{
    if (e->type() == QEvent::LanguageChange) {
        ui->retranslateUi(this);
        if (App::Document* doc = document()) {
            setWindowTitle(tr("Parameters - %1").arg(QString::fromUtf8(doc->Label.getValue())));
        }
        scheduleRefresh();
    }
    QDialog::changeEvent(e);
}

QWidget* DlgDocumentParameters::createEditor(QWidget* parent, const QModelIndex& index) const
{
    QTreeWidgetItem* item = itemFromIndex(index);
    App::DocumentObject* obj = objectOf(item);
    if (!obj) {
        return nullptr;
    }

    QWidget* editor = nullptr;
    switch (index.column()) {
        case ColumnName: {
            if (!item->data(ColumnName, DynamicRole).toBool()) {
                return nullptr;
            }
            auto* edit = new QLineEdit(parent);
            edit->setText(item->data(ColumnName, PathRole).toString());
            editor = edit;
            break;
        }
        case ColumnExpression: {
            auto* edit = new ExpressionLineEdit(parent);
            edit->setDocumentObject(obj);
            edit->setText(item->text(ColumnExpression));
            editor = edit;
            break;
        }
        case ColumnValue: {
            if (!item->data(ColumnName, ValueEditableRole).toBool()) {
                return nullptr;
            }
            App::ObjectIdentifier path;
            if (!identifierOf(item, path)) {
                return nullptr;
            }
            App::any value;
            try {
                value = path.getValue();
            }
            catch (const Base::Exception&) {
                return nullptr;
            }
            if (isNumberValue(value)) {
                Base::Quantity quantity = toQuantity(value);
                auto* spin = new QuantitySpinBox(parent);
                spin->setUnit(quantity.getUnit());
                spin->setMinimum(std::numeric_limits<double>::lowest());
                spin->setMaximum(std::numeric_limits<double>::max());
                spin->setValue(quantity);
                editor = spin;
            }
            else if (value.type() == typeid(long) || value.type() == typeid(int)) {
                long number = value.type() == typeid(long) ? App::any_cast<long>(value)
                                                           : App::any_cast<int>(value);
                auto* spin = new QSpinBox(parent);
                spin->setRange(std::numeric_limits<int>::min(), std::numeric_limits<int>::max());
                spin->setValue(static_cast<int>(std::clamp<long>(
                    number,
                    std::numeric_limits<int>::min(),
                    std::numeric_limits<int>::max()
                )));
                editor = spin;
            }
            else if (value.type() == typeid(bool)) {
                auto* combo = new QComboBox(parent);
                combo->addItem(tr("False"));
                combo->addItem(tr("True"));
                combo->setCurrentIndex(App::any_cast<bool>(value) ? 1 : 0);
                editor = combo;
            }
            else if (value.type() == typeid(std::string)) {
                auto* edit = new QLineEdit(parent);
                edit->setText(fromStd(App::any_cast<std::string>(value)));
                editor = edit;
            }
            break;
        }
        default:
            break;
    }

    if (editor) {
        editor->setObjectName(QLatin1String(EditorName));
    }
    return editor;
}

void DlgDocumentParameters::commitEditor(QWidget* editor, const QModelIndex& index)
{
    QTreeWidgetItem* item = itemFromIndex(index);
    if (!item || !editor) {
        return;
    }

    switch (index.column()) {
        case ColumnName:
            if (auto* edit = qobject_cast<QLineEdit*>(editor)) {
                renameParameter(item, edit->text());
            }
            break;
        case ColumnExpression:
            if (auto* edit = qobject_cast<QLineEdit*>(editor)) {
                setParameterExpression(item, edit->text());
            }
            break;
        case ColumnValue: {
            App::ObjectIdentifier path;
            if (!identifierOf(item, path)) {
                return;
            }
            App::any current;
            try {
                current = path.getValue();
            }
            catch (const Base::Exception&) {
                return;
            }
            App::any value;
            if (auto* quantitySpin = qobject_cast<QuantitySpinBox*>(editor)) {
                Base::Quantity quantity = quantitySpin->value();
                if (current.type() == typeid(Base::Quantity)) {
                    value = quantity;
                }
                else {
                    value = quantity.getValue();
                }
            }
            else if (auto* spin = qobject_cast<QSpinBox*>(editor)) {
                value = static_cast<long>(spin->value());
            }
            else if (auto* combo = qobject_cast<QComboBox*>(editor)) {
                value = combo->currentIndex() == 1;
            }
            else if (auto* edit = qobject_cast<QLineEdit*>(editor)) {
                value = edit->text().toStdString();
            }
            else {
                return;
            }
            setParameterValue(item, value);
            break;
        }
        default:
            break;
    }
}

bool DlgDocumentParameters::renameParameter(QTreeWidgetItem* item, const QString& newName)
{
    App::DocumentObject* obj = objectOf(item);
    App::Property* prop = propertyOf(item);
    if (!obj || !prop || !item->data(ColumnName, DynamicRole).toBool()) {
        showMessage(tr("This parameter cannot be renamed"));
        return false;
    }

    const QString name = newName.trimmed();
    const std::string nameStd = name.toStdString();
    const QString oldName = QString::fromLatin1(prop->getName());
    if (nameStd == prop->getName()) {
        return true;
    }

    const bool userParameter = Parameters::isUserParameter(prop);
    const QString error = nameError(obj, name, userParameter, prop);
    if (!error.isEmpty()) {
        showMessage(error);
        return false;
    }

    try {
        ParameterTransaction transaction(QT_TRANSLATE_NOOP("Command", "Rename parameter"));
        const bool renamed = userParameter ? App::UserParameters::rename(prop, nameStd)
                                           : obj->renameDynamicProperty(prop, nameStd.c_str());
        if (!renamed) {
            showMessage(tr("Cannot rename '%1'").arg(oldName));
            return false;
        }
        transaction.commit();
    }
    catch (const Base::Exception& e) {
        showMessage(QString::fromUtf8(e.what()));
        return false;
    }

    showMessage(tr("Renamed '%1' to '%2'").arg(oldName, name), false);
    selectAfterRefresh = {item->data(ColumnName, ObjectRole).toString(), name};
    scheduleRefresh();
    return true;
}

bool DlgDocumentParameters::setParameterExpression(QTreeWidgetItem* item, const QString& text)
{
    App::DocumentObject* obj = objectOf(item);
    App::ObjectIdentifier path;
    if (!obj || !identifierOf(item, path)) {
        return false;
    }

    const QString trimmed = text.trimmed();
    auto info = obj->getExpression(path);
    std::string oldText = info.expression ? info.expression->toString() : std::string();

    std::shared_ptr<App::Expression> expr;
    if (!trimmed.isEmpty()) {
        try {
            const auto formatting = numericLocaleContextFor(locale());
            expr = App::ExpressionParser::parseUserInput(obj, trimmed.toUtf8().constData(), formatting);
            if (!expr) {
                throw Base::ValueError("Invalid expression");
            }
            // user parameters typed by their bare name, as offered by the completer
            App::UserParameters::qualifyReferences(obj, *expr);
            std::string error = obj->ExpressionEngine.validateExpression(path, expr);
            if (!error.empty()) {
                throw Base::RuntimeError(error.c_str());
            }
            checkUnit(path, *expr);
        }
        catch (const Base::Exception& e) {
            showMessage(tr("Invalid expression: %1").arg(QString::fromUtf8(e.what())));
            return false;
        }
        if (expr->toString() == oldText) {
            return true;
        }
    }
    else if (oldText.empty()) {
        return true;
    }

    try {
        ParameterTransaction transaction(QT_TRANSLATE_NOOP("Command", "Set parameter expression"));
        obj->setExpression(path, expr);
        obj->getDocument()->recompute();
        transaction.commit();
    }
    catch (const Base::Exception& e) {
        showMessage(QString::fromUtf8(e.what()));
        return false;
    }

    showMessage(QString(), false);
    scheduleRefresh();
    return true;
}

bool DlgDocumentParameters::setParameterValue(QTreeWidgetItem* item, const App::any& value)
{
    App::DocumentObject* obj = objectOf(item);
    App::ObjectIdentifier path;
    if (!obj || !identifierOf(item, path)) {
        return false;
    }

    try {
        if (App::isAnyEqual(path.getValue(), value)) {
            return true;
        }
    }
    catch (const Base::Exception&) {
        // compare failed: set the value anyway
    }

    try {
        ParameterTransaction transaction(QT_TRANSLATE_NOOP("Command", "Set parameter value"));
        path.setValue(value);
        obj->getDocument()->recompute();
        transaction.commit();
    }
    catch (const Base::Exception& e) {
        showMessage(QString::fromUtf8(e.what()));
        return false;
    }
    catch (const std::exception& e) {
        showMessage(tr("Cannot set the value: %1").arg(QString::fromUtf8(e.what())));
        return false;
    }

    showMessage(QString(), false);
    scheduleRefresh();
    return true;
}

bool DlgDocumentParameters::deleteParameter(QTreeWidgetItem* item, bool confirm)
{
    App::DocumentObject* obj = objectOf(item);
    App::Property* prop = propertyOf(item);
    if (!obj || !prop || !item->data(ColumnName, DynamicRole).toBool()) {
        showMessage(tr("This parameter cannot be deleted"));
        return false;
    }

    const std::string name = prop->getName();
    const QString label = QString::fromUtf8(obj->Label.getValue());

    if (confirm) {
        std::vector<Parameters::Reference> refs = Parameters::findReferences(obj, name);
        QString text = tr("Delete the parameter '%1' of '%2'?").arg(fromStd(name), label);
        QMessageBox::Icon icon = QMessageBox::Question;
        if (!refs.empty()) {
            QStringList lines;
            for (const auto& ref : refs) {
                if (ref.path.empty()) {
                    lines << tr("%1 (may reference it)").arg(fromStd(ref.objectLabel));
                }
                else {
                    lines << QStringLiteral("%1.%2").arg(fromStd(ref.objectLabel), fromStd(ref.path));
                }
            }
            text += QStringLiteral("\n\n") + tr("It is referenced by:") + QStringLiteral("\n")
                + lines.join(QStringLiteral("\n")) + QStringLiteral("\n\n")
                + tr("These expressions will fail to evaluate.");
            icon = QMessageBox::Warning;
        }
        QMessageBox box(icon, tr("Delete parameter"), text, QMessageBox::Yes | QMessageBox::No, this);
        box.setObjectName(QStringLiteral("messageBoxDeleteParameter"));
        box.setDefaultButton(refs.empty() ? QMessageBox::Yes : QMessageBox::No);
        if (box.exec() != QMessageBox::Yes) {
            return false;
        }
    }

    try {
        ParameterTransaction transaction(QT_TRANSLATE_NOOP("Command", "Delete parameter"));
        if (!obj->removeDynamicProperty(name.c_str())) {
            showMessage(tr("Cannot delete '%1'").arg(fromStd(name)));
            return false;
        }
        transaction.commit();
    }
    catch (const Base::Exception& e) {
        showMessage(QString::fromUtf8(e.what()));
        return false;
    }

    showMessage(tr("Deleted '%1'").arg(fromStd(name)), false);
    scheduleRefresh();
    return true;
}

bool DlgDocumentParameters::addParameter(
    App::DocumentObject* holder,
    const QString& name,
    const QString& expression,
    const QString& comment
)
{
    App::Document* doc = document();
    if (!doc || (holder && holder->getDocument() != doc)) {
        return false;
    }

    const QString trimmedName = name.trimmed();
    const std::string nameStd = trimmedName.toStdString();
    const bool inVarSet = !holder || holder->isDerivedFrom<App::VarSet>();
    const QString error = nameError(holder, trimmedName, !inVarSet);
    if (!error.isEmpty()) {
        showMessage(error);
        return false;
    }

    try {
        ParameterTransaction transaction(QT_TRANSLATE_NOOP("Command", "Add parameter"));
        if (!holder) {
            holder = doc->addObject("App::VarSet", "VarSet");
        }

        const auto formatting = numericLocaleContextFor(locale());
        std::shared_ptr<App::Expression> expr = App::ExpressionParser::parseUserInput(
            holder,
            expression.trimmed().toUtf8().constData(),
            formatting
        );
        if (!expr) {
            throw Base::ValueError("Invalid expression");
        }
        // user parameters typed by their bare name, as offered by the completer
        App::UserParameters::qualifyReferences(holder, *expr);
        const QString typeError = valueTypeError(*expr, !inVarSet);
        if (!typeError.isEmpty()) {
            throw Base::TypeError(typeError.toStdString());
        }

        if (!inVarSet) {
            // the same creation as for `name = value` typed in an input
            App::Property* prop = App::UserParameters::createParameter(holder, nameStd, expr);
            if (!comment.isEmpty()) {
                holder->changeDynamicProperty(prop, nullptr, comment.toUtf8().constData());
            }
        }
        else {
            const std::string type = Parameters::propertyTypeForExpression(*expr);
            App::Property* prop = holder->addDynamicProperty(
                type.c_str(),
                nameStd.c_str(),
                "Base",
                comment.toUtf8().constData()
            );
            if (!prop) {
                throw Base::RuntimeError("Cannot add the property");
            }
            App::ObjectIdentifier path(*prop);
            if (expr->getIdentifiers().empty()) {
                // a constant: store the value, not an expression
                App::ExpressionPtr result = expr->eval();
                prop->setPathValue(path, result->getValueAsAny());
            }
            else {
                std::string invalid = holder->ExpressionEngine.validateExpression(path, expr);
                if (!invalid.empty()) {
                    throw Base::RuntimeError(invalid.c_str());
                }
                holder->setExpression(path, expr);
            }
        }
        doc->recompute();
        transaction.commit();
    }
    catch (const Base::Exception& e) {
        showMessage(tr("Cannot add the parameter: %1").arg(QString::fromUtf8(e.what())));
        return false;
    }

    showMessage(tr("Added '%1'").arg(trimmedName), false);
    selectAfterRefresh = {QString::fromLatin1(holder->getNameInDocument()), trimmedName};
    scheduleRefresh();
    return true;
}

App::DocumentObject* DlgDocumentParameters::defaultHolder() const
{
    App::Document* doc = document();
    if (!doc) {
        return nullptr;
    }

    if (QTreeWidgetItem* current = ui->treeParameters->currentItem()) {
        QString holder = current->data(ColumnName, HolderRole).toString();
        auto category = static_cast<Parameters::Category>(
            current->data(ColumnName, CategoryRole).toInt()
        );
        if (holder.isEmpty() && current->data(ColumnName, ObjectRole).isValid()
            && category != Parameters::Category::Model) {
            holder = current->data(ColumnName, ObjectRole).toString();
        }
        if (!holder.isEmpty()) {
            if (App::DocumentObject* obj = doc->getObject(holder.toUtf8().constData())) {
                return obj;
            }
        }
    }

    std::vector<App::DocumentObject*> selection
        = Selection().getObjectsOfType(App::DocumentObject::getClassTypeId(), doc->getName());
    if (selection.size() == 1) {
        return selection.front();
    }

    std::vector<App::DocumentObject*> varSets = doc->getObjectsOfType(App::VarSet::getClassTypeId());
    if (!varSets.empty()) {
        return *std::ranges::min_element(varSets, [](const App::DocumentObject* a, const App::DocumentObject* b) {
            return std::strcmp(a->Label.getValue(), b->Label.getValue()) < 0;
        });
    }
    return nullptr;  // a new variable set
}

void DlgDocumentParameters::onAdd()
{
    App::Document* doc = document();
    if (!doc) {
        return;
    }

    QDialog dlg(this);
    dlg.setObjectName(QStringLiteral("DlgAddParameter"));
    dlg.setWindowTitle(tr("Add Parameter"));
    auto* layout = new QVBoxLayout(&dlg);
    auto* form = new QFormLayout();
    layout->addLayout(form);

    auto* comboHolder = new QComboBox(&dlg);
    comboHolder->setObjectName(QStringLiteral("comboBoxHolder"));
    comboHolder->setToolTip(
        tr("A variable set, or an object that keeps the parameter in its group '%1'")
            .arg(QString::fromLatin1(Parameters::userParametersGroup()))
    );
    auto* lineEditName = new QLineEdit(&dlg);
    lineEditName->setObjectName(QStringLiteral("lineEditName"));
    auto* lineEditExpression = new ExpressionLineEdit(&dlg);
    lineEditExpression->setObjectName(QStringLiteral("lineEditExpression"));
    lineEditExpression->setPlaceholderText(tr("For example: 23 mm"));
    auto* lineEditComment = new QLineEdit(&dlg);
    lineEditComment->setObjectName(QStringLiteral("lineEditComment"));
    auto* labelError = new QLabel(&dlg);
    labelError->setObjectName(QStringLiteral("labelError"));
    labelError->setWordWrap(true);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dlg);
    buttons->setObjectName(QStringLiteral("buttonBox"));

    form->addRow(tr("Holder"), comboHolder);
    form->addRow(tr("Name"), lineEditName);
    form->addRow(tr("Expression"), lineEditExpression);
    form->addRow(tr("Comment"), lineEditComment);
    layout->addWidget(labelError);
    layout->addWidget(buttons);

    // holders: a new variable set, the variable sets, the objects with user
    // parameters and the selected objects
    comboHolder->addItem(BitmapFactory().iconFromTheme("VarSet"), tr("New variable set"), QString());
    std::vector<App::DocumentObject*> varSets = doc->getObjectsOfType(App::VarSet::getClassTypeId());
    std::ranges::stable_sort(varSets, [](const App::DocumentObject* a, const App::DocumentObject* b) {
        return std::strcmp(a->Label.getValue(), b->Label.getValue()) < 0;
    });
    for (App::DocumentObject* varSet : varSets) {
        comboHolder->addItem(
            BitmapFactory().iconFromTheme("VarSet"),
            QString::fromUtf8(varSet->Label.getValue()),
            QString::fromLatin1(varSet->getNameInDocument())
        );
    }
    std::vector<App::DocumentObject*> others;
    for (App::Property* prop : Parameters::collectUserParameters(doc)) {
        if (auto* obj = freecad_cast<App::DocumentObject*>(prop->getContainer())) {
            others.push_back(obj);
        }
    }
    for (App::DocumentObject* obj :
         Selection().getObjectsOfType(App::DocumentObject::getClassTypeId(), doc->getName())) {
        others.push_back(obj);
    }
    if (App::DocumentObject* holder = defaultHolder()) {
        others.push_back(holder);
    }
    for (App::DocumentObject* obj : others) {
        if (!obj || obj->isDerivedFrom<App::VarSet>()) {
            continue;
        }
        QString objName = QString::fromLatin1(obj->getNameInDocument());
        if (comboHolder->findData(objName) >= 0) {
            continue;
        }
        comboHolder->addItem(
            tr("%1 (user parameters)").arg(QString::fromUtf8(obj->Label.getValue())),
            objName
        );
    }
    if (App::DocumentObject* holder = defaultHolder()) {
        int index = comboHolder->findData(QString::fromLatin1(holder->getNameInDocument()));
        comboHolder->setCurrentIndex(std::max(index, 0));
    }

    auto holderObject = [doc, comboHolder]() -> App::DocumentObject* {
        QString name = comboHolder->currentData().toString();
        return name.isEmpty() ? nullptr : doc->getObject(name.toUtf8().constData());
    };

    QPushButton* okButton = buttons->button(QDialogButtonBox::Ok);
    okButton->setText(tr("Add"));

    // a new variable set does not exist yet: complete and check relative to any object
    auto ownerObject = [doc, &holderObject]() -> App::DocumentObject* {
        App::DocumentObject* owner = holderObject();
        if (!owner && !doc->getObjects().empty()) {
            owner = doc->getObjects().front();
        }
        return owner;
    };

    auto validate = [&]() {
        App::DocumentObject* holder = holderObject();
        App::DocumentObject* owner = ownerObject();

        QString error;
        const QString name = lineEditName->text().trimmed();
        const bool inVarSet = !holder || holder->isDerivedFrom<App::VarSet>();
        if (!name.isEmpty()) {
            error = nameError(holder, name, !inVarSet);
        }
        const QString text = lineEditExpression->text().trimmed();
        if (error.isEmpty() && !text.isEmpty()) {
            try {
                const auto formatting = numericLocaleContextFor(lineEditExpression->locale());
                App::ExpressionPtr expr
                    = App::ExpressionParser::parseUserInput(owner, text.toUtf8().constData(), formatting);
                if (expr) {
                    App::UserParameters::qualifyReferences(owner, *expr);
                    error = valueTypeError(*expr, !inVarSet);
                }
                else {
                    error = tr("The value must be a number, a quantity or a string");
                }
            }
            catch (const Base::Exception& e) {
                error = tr("Invalid expression: %1").arg(QString::fromUtf8(e.what()));
            }
        }
        labelError->setText(error);
        okButton->setEnabled(error.isEmpty() && !name.isEmpty() && !text.isEmpty());
    };

    connect(lineEditName, &QLineEdit::textChanged, &dlg, validate);
    connect(lineEditExpression, &QLineEdit::textChanged, &dlg, validate);
    connect(comboHolder, qOverload<int>(&QComboBox::currentIndexChanged), &dlg, [&]() {
        lineEditExpression->setDocumentObject(ownerObject());
        validate();
    });
    connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dlg, &QDialog::reject);
    lineEditExpression->setDocumentObject(ownerObject());
    validate();
    lineEditName->setFocus();

    if (dlg.exec() != QDialog::Accepted) {
        return;
    }
    addParameter(holderObject(), lineEditName->text(), lineEditExpression->text(), lineEditComment->text());
}

void DlgDocumentParameters::onDelete()
{
    if (QTreeWidgetItem* current = ui->treeParameters->currentItem()) {
        deleteParameter(current, true);
    }
}

void DlgDocumentParameters::onUndo()
{
    App::Document* doc = document();
    if (!doc || doc->getAvailableUndos() == 0) {
        return;
    }
    if (Gui::Document* guiDoc = Application::Instance->getDocument(doc)) {
        guiDoc->undo(1);
    }
    showMessage(QString(), false);
    refresh();
}

#include "moc_DlgDocumentParameters.cpp"
