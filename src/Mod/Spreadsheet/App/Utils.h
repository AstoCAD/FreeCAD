// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: 2015 Eivind Kvedalen
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1            *
 *   of the License, or (at your option) any later version.                   *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful,               *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty              *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                  *
 *   See the GNU Lesser General Public License for more details.              *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD. If not, see https://www.gnu.org/licenses     *
 *                                                                            *
 ******************************************************************************/

#pragma once

#include <map>
#include <memory>
#include <set>
#include <string>

#include <Mod/Spreadsheet/SpreadsheetGlobal.h>


namespace Spreadsheet
{

SpreadsheetExport std::string columnName(int col);
SpreadsheetExport std::string rowName(int row);

SpreadsheetExport void createRectangles(
    std::set<std::pair<int, int>>& cells,
    std::map<std::pair<int, int>, std::pair<int, int>>& rectangles
);
SpreadsheetExport std::string quote(const std::string& input);
SpreadsheetExport std::string unquote(const std::string& input);

class Sheet;

/**
 * Resolve the user parameters (App::UserParameters) that the cell content @p content, as typed
 * by the user into @p sheet, refers to by their bare name: `=2*myVar` becomes
 * `=2 * Holder.myVar`.
 *
 * Only identifiers that do not resolve today are changed (see
 * App::UserParameters::qualifyReferences): cells, aliases and the sheet's properties keep their
 * meaning. An identifier that is a cell address or an alias of the sheet is never changed, even
 * when a user parameter has the same name (`=B5` keeps referring to the cell B5, also when it is
 * empty); the other identifiers of the formula are still resolved. Nothing is changed (returns
 * false) for content that is not a formula or does not parse.
 */
SpreadsheetExport bool qualifyUserParameters(Sheet* sheet, std::string& content);

}  // namespace Spreadsheet
