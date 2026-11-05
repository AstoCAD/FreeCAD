// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <QString>

#include <FCGlobal.h>

#include <App/UserParameters.h>

namespace Gui
{

/**
 * The translated text telling the user why @p name cannot name a new user parameter.
 *
 * Every input that creates or renames a user parameter (quantity fields, the formula dialog, the
 * Parameters dialog, on-view parameters) shows this text for a status returned by
 * App::UserParameters::checkName(). Empty for App::UserParameters::NameStatus::Available.
 */
GuiExport QString userParameterNameStatusText(App::UserParameters::NameStatus status, const QString& name);

}  // namespace Gui
