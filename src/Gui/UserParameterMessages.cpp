// SPDX-License-Identifier: LGPL-2.1-or-later

#include "UserParameterMessages.h"

#include <string>

#include <QCoreApplication>

QString Gui::userParameterNameStatusText(const App::UserParameters::NameStatus status, const QString& name)
{
    using App::UserParameters::NameStatus;

    // Not an exhaustive switch on purpose: a status added to App before its text is added here
    // still gets a message (see the default branch).
    switch (status) {
        case NameStatus::Available:
            return {};
        case NameStatus::Invalid:
            return QCoreApplication::translate(
                       "Gui::UserParameters",
                       "'%1' is not a valid parameter name: use letters, digits and underscores, "
                       "do not start with a digit or an underscore, and do not use a unit or a "
                       "constant"
            )
                .arg(name);
        case NameStatus::UsedByParameter:
            return QCoreApplication::translate(
                       "Gui::UserParameters",
                       "A user parameter named '%1' already exists in the document"
            )
                .arg(name);
        case NameStatus::UsedByObject:
            return QCoreApplication::translate(
                       "Gui::UserParameters",
                       "An object of this document is named or labeled '%1'"
            )
                .arg(name);
        case NameStatus::UsedByOwnerProperty:
            return QCoreApplication::translate(
                       "Gui::UserParameters",
                       "The object already has a property named '%1'"
            )
                .arg(name);
        case NameStatus::CellAddress:
            return QCoreApplication::translate(
                       "Gui::UserParameters",
                       "'%1' is a spreadsheet cell address and cannot name a user parameter"
            )
                .arg(name);
        case NameStatus::PythonAttribute:
            return QCoreApplication::translate(
                       "Gui::UserParameters",
                       "'%1' is an attribute of the object in Python and cannot name a user parameter"
            )
                .arg(name);
        default:
            break;
    }

    // A status without a translated text yet: the reason given by App (in English) tells more
    // than a generic refusal.
    const std::string reason = App::UserParameters::nameStatusMessage(status, name.toStdString());
    if (!reason.empty()) {
        return QString::fromStdString(reason);
    }
    return QCoreApplication::translate("Gui::UserParameters", "'%1' cannot name a user parameter")
        .arg(name);
}
