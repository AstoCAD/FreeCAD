// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2015 Eivind Kvedalen <eivind@kvedalen.name>             *
 *                                                                         *
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
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/

#include <boost/tokenizer.hpp>
#include <boost/regex.hpp>
#include <algorithm>
#include <cmath>
#include <deque>
#include <memory>
#include <sstream>
#include <tuple>
#include <list>
#include <map>
#include <string>
#include <set>
#include <vector>

#include <QString>

#include <boost_graph_adjacency_list.hpp>
#include <boost/graph/topological_sort.hpp>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DynamicProperty.h>
#include <App/ExpressionParser.h>
#include <App/FeaturePythonPyImp.h>
#include <Base/Exception.h>
#include <Base/FileInfo.h>
#include <Base/Reader.h>
#include <Base/Stream.h>
#include <Base/StringUtils.h>
#include <Base/Writer.h>

#include "Sheet.h"
#include "SheetObserver.h"
#include "SheetParameter.h"
#include "SheetPy.h"
#include "Utils.h"


FC_LOG_LEVEL_INIT("Spreadsheet", true, true)

using namespace Base;
using namespace App;
using namespace Spreadsheet;

PROPERTY_SOURCE(Spreadsheet::Sheet, App::DocumentObject)

using DependencyList = boost::adjacency_list<
    boost::vecS,         // class OutEdgeListS  : a Sequence or an AssociativeContainer
    boost::vecS,         // class VertexListS   : a Sequence or a RandomAccessContainer
    boost::directedS,    // class DirectedS     : This is a directed graph
    boost::no_property,  // class VertexProperty:
    boost::no_property,  // class EdgeProperty:
    boost::no_property,  // class GraphProperty:
    boost::listS         // class EdgeListS:
    >;
using Traits = boost::graph_traits<DependencyList>;
using Vertex = Traits::vertex_descriptor;
using Edge = Traits::edge_descriptor;

/**
 * Construct a new Sheet object.
 */

Sheet::Sheet()
    : DocumentObject()
    , props(PropertyContainer::dynamicProps)
    , cells(this)
{
    ADD_PROPERTY_TYPE(cells, (), "Spreadsheet", (PropertyType)(Prop_Hidden), "Cell contents");
    ADD_PROPERTY_TYPE(
        columnWidths,
        (),
        "Spreadsheet",
        (PropertyType)(Prop_ReadOnly | Prop_Hidden | Prop_Output),
        "Column widths"
    );
    ADD_PROPERTY_TYPE(
        rowHeights,
        (),
        "Spreadsheet",
        (PropertyType)(Prop_ReadOnly | Prop_Hidden | Prop_Output),
        "Row heights"
    );
    ADD_PROPERTY_TYPE(
        rowHeights,
        (),
        "Spreadsheet",
        (PropertyType)(Prop_ReadOnly | Prop_Hidden),
        "Row heights"
    );
    ExpressionEngine.expressionChanged.connect([this](const App::ObjectIdentifier&) {
        this->updateBindings();
    });
}

/**
 * @brief Sheet::~Sheet
 *
 * The destructor; clear properties to release all memory.
 *
 */

Sheet::~Sheet()
{
    try {
        clearAll();
    }
    catch (...) {
        // Don't let an exception propagate out of a destructor (calls terminate())
        Base::Console().error(
            "clearAll() resulted in an exception when deleting the spreadsheet : {}\n",
            getNameInDocument()
        );
    }
}

/**
 * Clear all cells in the sheet.  These are implemented as dynamic
 * properties, for example "A1" is added as a dynamic property. Since
 * now users may add dynamic properties, we need to try to avoid
 * removing those, too, so we check whether the dynamic property name
 * is a valid cell address name before removing it.
 */

void Sheet::clearAll()
{
    cells.clear();

    std::vector<std::string> propNames = props.getDynamicPropertyNames();

    for (const auto& propName : propNames) {
        if (cells.isValidCellAddressName(propName.c_str())) {
            this->removeDynamicProperty(propName.c_str());
        }
    }

    propAddress.clear();
    cellErrors.clear();
    columnWidths.clear();
    rowHeights.clear();
}

// validate import/export parameters
bool Sheet::getCharsFromPrefs(char& delim, char& quote, char& escape, std::string& errMsg)
{
    bool isValid = true;
    auto param = SheetParameter::instance();
    QString delimiter = QString::fromStdString(param->getImportExportDelimiter());
    QString quoteChar = QString::fromStdString(param->getImportExportQuoteCharacter());
    QString escapeChar = QString::fromStdString(param->getImportExportEscapeCharacter());

    delim = delimiter.size() == 1 ? delimiter[0].toLatin1() : '\0';
    if (delimiter.compare(QLatin1String("tab"), Qt::CaseInsensitive) == 0
        || delimiter.compare(QLatin1String("\\t"), Qt::CaseInsensitive) == 0) {
        delim = '\t';
    }
    else if (delimiter.compare(QLatin1String("comma"), Qt::CaseInsensitive) == 0) {
        delim = ',';
    }
    else if (delimiter.compare(QLatin1String("semicolon"), Qt::CaseInsensitive) == 0) {
        delim = ';';
    }
    if (delim != '\0' && quoteChar.size() == 1 && escapeChar.size() == 1) {
        quote = quoteChar[0].toLatin1();
        escape = escapeChar[0].toLatin1();
    }
    else {
        isValid = false;
        std::string importExport = errMsg;
        std::stringstream errStream;
        errStream << "Invalid spreadsheet Import/Export parameter.\n";
        if (delim == '\0') {
            errStream
                << "Unrecognized delimiter: " << delimiter.toStdString()
                << " (recognized tokens: \\t, tab, semicolon, comma, or any single character)\n";
        }
        if (quoteChar.size() != 1) {
            errStream << "Invalid quote character: " << quoteChar.toStdString()
                      << " (quote character must be one single character)\n";
        }
        if (escapeChar.size() != 1) {
            errStream << "Invalid escape character: " << escapeChar.toStdString()
                      << " (escape character must be one single character)\n";
        }
        errStream << importExport << " not done.\n";
        errMsg = errStream.str();
    }
    return isValid;
}


/**
 * Import a file into the spreadsheet object.
 *
 * @param filename   Name of file to import
 * @param delimiter  The field delimiter character used.
 * @param quoteChar  Quote character, if any (set to '\0' to disable).
 * @param escapeChar The escape character used, if any (set to '0' to disable).
 *
 * @returns True if successful, false if something failed.
 */

bool Sheet::importFromFile(const std::string& filename, char delimiter, char quoteChar, char escapeChar)
{
    Base::FileInfo fi(filename);
    Base::ifstream file(fi, std::ios::in);
    int row = 0;

    PropertySheet::AtomicPropertyChange signaller(cells);

    clearAll();

    if (file.is_open()) {
        std::string line;

        while (std::getline(file, line)) {
            using namespace boost;

            // Files saved as "CSV UTF-8" (e.g. by Excel) start with a byte order mark, which is
            // not part of the first cell
            if (row == 0 && line.starts_with("\xEF\xBB\xBF")) {
                line.erase(0, 3);
            }

            try {
                escaped_list_separator<char> e;
                int col = 0;

                if (quoteChar) {
                    e = escaped_list_separator<char>(escapeChar, delimiter, quoteChar);
                }
                else {
                    e = escaped_list_separator<char>('\0', delimiter, '\0');
                }

                tokenizer<escaped_list_separator<char>> tok(line, e);

                for (tokenizer<escaped_list_separator<char>>::iterator i = tok.begin();
                     i != tok.end();
                     ++i) {
                    if (!i->empty()) {
                        setCell(CellAddress(row, col), (*i).c_str());
                    }
                    col++;
                }
            }
            catch (...) {
                signaller.tryInvoke();
                return false;
            }

            ++row;
        }
        file.close();
        signaller.tryInvoke();
        return true;
    }
    else {
        return false;
    }
}

/**
 * Write an escaped version of the string \a s to the stream \a out.
 *
 * @param s          The string to write.
 * @param quoteChar  The quote character.
 * @param escapeChar The escape character.
 * @param stream     The stream to output the escaped string to.
 *
 */

static void writeEscaped(std::string const& s, char quoteChar, char escapeChar, std::ostream& out)
{
    out << quoteChar;
    for (char c : s) {
        if (c == quoteChar) {
            out << escapeChar;
            out << c;
        }
        // importFromFile() reads the escape character as the start of an escape sequence and a
        // newline as the end of the row: escape them too, with the sequences its tokenizer
        // understands (escape character + escape character, escape character + 'n')
        else if (escapeChar && c == escapeChar) {
            out << escapeChar;
            out << c;
        }
        else if (escapeChar && c == '\n') {
            out << escapeChar;
            out << 'n';
        }
        else {
            out << c;
        }
    }
    out << quoteChar;
}

/**
 * Characters that make exportToFile() write a field quoted and escaped.
 */

static std::string charsToEscape(char delimiter, char quoteChar, char escapeChar)
{
    std::string chars {quoteChar, delimiter};
    if (escapeChar) {
        chars += escapeChar;
        chars += '\n';
    }
    return chars;
}

/**
 * Export spreadsheet data to file.
 *
 * @param filename   Filename to store data to.
 * @param delimiter  Field delimiter
 * @param quoteChar  Quote character ('\0' to disable)
 * @param escapeChar Escape character ('\0' to disable)
 *
 * @returns True if store is successful, false if something failed.
 *
 */

bool Sheet::exportToFile(const std::string& filename, char delimiter, char quoteChar, char escapeChar) const
{
    Base::ofstream file;
    int prevRow = -1, prevCol = -1;

    Base::FileInfo fi(filename);
    file.open(fi, std::ios::out | std::ios::ate | std::ios::binary);

    if (!file.is_open()) {
        return false;
    }

    auto usedCells = cells.getNonEmptyCells();
    auto i = usedCells.begin();

    // Every row starts at the leftmost used column, so that rows keep their column layout
    int firstCol = -1;
    for (const auto& address : usedCells) {
        if (firstCol == -1 || address.col() < firstCol) {
            firstCol = address.col();
        }
    }
    prevCol = firstCol;
    const std::string escapedChars = charsToEscape(delimiter, quoteChar, escapeChar);

    while (i != usedCells.end()) {
        Property* prop = getProperty(*i);

        if (prevRow != -1 && prevRow != i->row()) {
            for (int j = prevRow; j < i->row(); ++j) {
                file << std::endl;
            }
            prevCol = firstCol;
        }
        if (prevCol != -1 && i->col() != prevCol) {
            for (int j = prevCol; j < i->col(); ++j) {
                file << delimiter;
            }
        }

        std::stringstream field;

        // Write numbers with all their digits (the stream default of 6 significant digits
        // would round e.g. 1234567.891 to 1.23457e+06), so that the file reads back exactly
        if (auto p = freecad_cast<PropertyQuantity*>(prop)) {
            field << Base::StringUtils::formatDouble(p->getValue());
        }
        else if (auto p = freecad_cast<PropertyFloat*>(prop)) {
            field << Base::StringUtils::formatDouble(p->getValue());
        }
        else if (auto p = freecad_cast<PropertyInteger*>(prop)) {
            field << p->getValue();
        }
        else if (auto p = freecad_cast<PropertyString*>(prop)) {
            field << p->getValue();
        }
        else {
            assert(0);
        }

        std::string str = field.str();

        if (quoteChar
            && str.find_first_of(escapedChars) != std::string::npos) {
            writeEscaped(str, quoteChar, escapeChar, file);
        }
        else {
            file << str;
        }

        prevRow = i->row();
        prevCol = i->col();
        ++i;
    }
    file << std::endl;
    file.close();

    return true;
}

/**
 * Merge a rectangle specified by \a range into one logical cell.
 * Data in all but the upper right cell are cleared when the cells are merged.
 *
 * @param range Range to merge.
 * @returns True if the cells were merged, false if the merge was unsuccessful.
 *
 */

bool Sheet::mergeCells(const Range& range)
{
    return cells.mergeCells(range.from(), range.to());
}

/**
 * Split a previously merged cell specified by \a address into its individual cells.
 * The address can point to any of the cells that make up the merged cell.
 *
 * @param address Address of cell to split
 *
 */

void Sheet::splitCell(CellAddress address)
{
    cells.splitCell(address);
}

/**
 * Copy the first row (\a down) or the first column of \a range into the
 * rest of the range, the way copy and paste does: contents, formatting and
 * relative cell references are shifted, absolute references are kept, and
 * empty source cells clear their targets.
 *
 * @param range Range to fill. Ranges with merged cells are rejected.
 * @param down  True to fill downwards, false to fill to the right.
 *
 */

static void fillRange(Sheet* sheet, PropertySheet& cells, const Range& range, bool down)
{
    const CellAddress from = range.from();
    const CellAddress to = range.to();
    if ((down && range.rowCount() < 2) || (!down && range.colCount() < 2)) {
        return;
    }

    if (cells.hasSpan()) {
        Range r(range);
        do {
            if (sheet->isMergedCell(*r)) {
                throw Base::ValueError("Cannot fill a range that contains merged cells");
            }
        } while (r.next());
    }

    const Range source = down ? Range(from, CellAddress(from.row(), to.col()))
                              : Range(from, CellAddress(to.row(), from.col()));

    Base::StringWriter writer;
    cells.copyCells(writer, {source});
    const std::string buffer = writer.getString();

    // Paste the source line once per target line: pasting it once over the
    // whole target would tile only the expressions, not the formatting.
    const int count = down ? range.rowCount() : range.colCount();
    for (int i = 1; i < count; ++i) {
        const Range target = down
            ? Range(CellAddress(from.row() + i, from.col()), CellAddress(from.row() + i, to.col()))
            : Range(CellAddress(from.row(), from.col() + i), CellAddress(to.row(), from.col() + i));
        Base::StringIStreambuf buf(buffer);
        std::istream in(nullptr);
        in.rdbuf(&buf);
        Base::XMLReader reader("<memory>", in);
        cells.pasteCells(reader, target);
    }
}

void Sheet::fillDown(const Range& range)
{
    fillRange(this, cells, range, true);
}

void Sheet::fillRight(const Range& range)
{
    fillRange(this, cells, range, false);
}

/**
 * The sort key of a cell expression without references (a typed number,
 * quantity or text), evaluated as the recompute would: \a kind 0 with
 * \a number, or 1 with \a text. Returns false for other expressions.
 */

static bool constantSortKey(const Expression* expression, int& kind, double& number, QString& text)
{
    if (!expression || !expression->getIdentifiers().empty()) {
        return false;
    }
    try {
        const std::unique_ptr<Expression> value = expression->eval();
        if (auto* constant = freecad_cast<ConstantExpression*>(value.get());
            constant && !constant->isNumber()) {
            return false;
        }
        if (auto* result = freecad_cast<NumberExpression*>(value.get())) {
            kind = 0;
            number = result->getValue();
            return true;
        }
        if (auto* result = freecad_cast<StringExpression*>(value.get())) {
            kind = 1;
            text = QString::fromStdString(result->getText());
            return true;
        }
    }
    catch (const Base::Exception&) {
        // Not computable: sorted by its contents
    }
    return false;
}

/**
 * Sort the rows of \a range by the computed values of \a column, which must be
 * a column of the range. Numbers (and quantities, by value) come before text,
 * text is compared without case, empty cells always come last, and rows with
 * equal keys keep their order. Descending order reverses all but the empty
 * cells, like other spreadsheets.
 *
 * Only the cells of the range move, with their formatting. Their references
 * keep referring to the same data, and references from outside the range keep
 * pointing to the same position (see PropertySheet::permuteRows). Ranges with
 * merged cells or aliases, and formulas in the range that reference a range
 * only partly inside the sorted rows, are rejected with Base::ValueError.
 * All changes are one property change, so one undo step. Recompute the
 * document to update the values.
 */

void Sheet::sortRows(const Range& range, int column, bool ascending)
{
    if (column < range.from().col() || column > range.to().col()) {
        throw Base::ValueError("The sort column must be a column of the range");
    }
    if (range.rowCount() < 2) {
        return;
    }

    struct Key
    {
        int kind;  // 0: number, 1: text, 2: empty
        double number;
        QString text;
    };
    std::vector<Key> keys;
    for (int row = range.from().row(); row <= range.to().row(); ++row) {
        Key key {2, 0.0, QString()};
        const CellAddress address(row, column);
        const Cell* cell = getCell(address);
        if (cell && cell->getExpression()) {
            const Property* prop = getProperty(address);
            if (prop && prop->isDerivedFrom<App::PropertyFloat>()) {
                key = {0, static_cast<const App::PropertyFloat*>(prop)->getValue(), QString()};
            }
            else if (prop && prop->isDerivedFrom<App::PropertyInteger>()) {
                key = {
                    0,
                    static_cast<double>(static_cast<const App::PropertyInteger*>(prop)->getValue()),
                    QString()
                };
            }
            else if (prop && prop->isDerivedFrom<App::PropertyString>()) {
                key = {
                    1,
                    0.0,
                    QString::fromUtf8(static_cast<const App::PropertyString*>(prop)->getValue())
                };
            }
            else if (!prop && constantSortKey(cell->getExpression(), key.kind, key.number, key.text)) {
                // Not computed yet (no recompute since it was set): a constant
                // such as "10" or "5 mm" sorts by its value, not its text
            }
            else {
                std::string content;
                cell->getStringContent(content);
                key = {1, 0.0, QString::fromStdString(content)};
            }
            if (key.kind == 0 && std::isnan(key.number)) {
                key = {1, 0.0, QStringLiteral("nan")};
            }
        }
        keys.push_back(key);
    }

    std::vector<int> order;
    for (int i = 0; i < static_cast<int>(keys.size()); ++i) {
        order.push_back(i);
    }
    std::stable_sort(order.begin(), order.end(), [&keys, ascending](int a, int b) {
        const Key& ka = keys[a];
        const Key& kb = keys[b];
        if (ka.kind == 2 || kb.kind == 2) {
            return ka.kind != 2 && kb.kind == 2;
        }
        const Key& x = ascending ? ka : kb;
        const Key& y = ascending ? kb : ka;
        if (x.kind != y.kind) {
            return x.kind < y.kind;
        }
        if (x.kind == 0) {
            return x.number < y.number;
        }
        return QString::compare(x.text, y.text, Qt::CaseInsensitive) < 0;
    });

    for (int& row : order) {
        row += range.from().row();
    }
    cells.permuteRows(range, order);
}

static bool matchCellText(const QString& subject, const QString& text, bool matchCase, bool wholeCell)
{
    const Qt::CaseSensitivity cs = matchCase ? Qt::CaseSensitive : Qt::CaseInsensitive;
    return wholeCell ? QString::compare(subject, text, cs) == 0 : subject.contains(text, cs);
}

// The contents of a cell as typed, without the apostrophe that marks text.
static QString searchableContent(const Cell* cell, bool& isText)
{
    std::string content;
    cell->getStringContent(content);
    isText = !content.empty() && content[0] == '\'';
    return QString::fromStdString(isText ? content.substr(1) : content);
}

/**
 * Find the cells whose contents (or, with \a values, formatted values) contain
 * \a text, or are \a text with \a wholeCell. Text cells are matched without
 * their leading apostrophe. Returns the addresses row by row.
 */

std::vector<CellAddress> Sheet::findCells(const std::string& text, bool matchCase, bool wholeCell, bool values)
{
    std::vector<CellAddress> result;
    if (text.empty()) {
        return result;
    }
    const QString needle = QString::fromStdString(text);
    for (const auto& address : cells.getNonEmptyCells()) {
        Cell* cell = getCell(address);
        if (!cell) {
            continue;
        }
        QString subject;
        if (values) {
            if (!getProperty(address)) {
                continue;
            }
            subject = QString::fromStdString(cell->getFormattedQuantity());
        }
        else {
            bool isText = false;
            subject = searchableContent(cell, isText);
        }
        if (matchCellText(subject, needle, matchCase, wholeCell)) {
            result.push_back(address);
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

/**
 * Replace \a text by \a replacement in the contents of the matching cells
 * (see findCells), or the whole contents with \a wholeCell, limited to
 * \a ranges when given. Text cells stay text. The new contents are set as if
 * typed, so bare user parameter names are qualified. Returns the number of
 * cells changed. Recompute the document to update the values.
 */

int Sheet::replaceCells(
    const std::string& text,
    const std::string& replacement,
    bool matchCase,
    bool wholeCell,
    const std::vector<Range>& ranges
)
{
    if (text.empty()) {
        throw Base::ValueError("The text to replace is empty");
    }
    const QString needle = QString::fromStdString(text);
    const QString with = QString::fromStdString(replacement);
    const Qt::CaseSensitivity cs = matchCase ? Qt::CaseSensitive : Qt::CaseInsensitive;

    auto inRanges = [&ranges](const CellAddress& address) {
        if (ranges.empty()) {
            return true;
        }
        for (const auto& range : ranges) {
            if (address.row() >= range.from().row() && address.row() <= range.to().row()
                && address.col() >= range.from().col() && address.col() <= range.to().col()) {
                return true;
            }
        }
        return false;
    };

    int count = 0;
    for (const auto& address : findCells(text, matchCase, wholeCell, false)) {
        if (!inRanges(address)) {
            continue;
        }
        const Cell* cell = getCell(address);
        bool isText = false;
        QString content = searchableContent(cell, isText);
        if (wholeCell) {
            content = with;
        }
        else {
            content.replace(needle, with, cs);
        }
        std::string newContent = (isText ? "'" : "") + content.toStdString();
        if (!isText) {
            qualifyUserParameters(this, newContent);
        }
        // setContent, not setCell: an empty result must not clear the formatting
        setContent(address, newContent.c_str());
        ++count;
    }
    return count;
}

/**
 * Get contents of the cell specified by \a address, or 0 if it is not defined
 *
 * @returns A CellContent object or 0.
 */

Cell* Sheet::getCell(CellAddress address)
{
    return cells.getValue(address);
}

/**
 * Get contents of the cell specified by \a address, or 0 if it is not defined
 *
 * @returns A CellContent object or 0.
 */

const Cell* Sheet::getCell(CellAddress address) const
{
    return cells.getValue(address);
}

/**
 * Get cell contents specified by \a address.
 *
 * @param address
 */

Cell* Sheet::getNewCell(CellAddress address)
{
    Cell* cell = getCell(address);

    if (!cell) {
        cell = cells.createCell(address);
    }

    return cell;
}

/**
 * Set cell given by \a address to \a contents.
 *
 * @param address  Address of cell to set.
 * @param contents New contents of given cell.
 *
 */

void Sheet::setCell(const char* address, const char* contents)
{
    assert(address && contents);

    setCell(CellAddress(address), contents);
}

/**
 * Set cell at \a address to \a value. If a merged cell is specified, the upper right corner of the
 * merged cell must be specified.
 *
 * @param address    Row position of cell.
 * @param value      String value of expression.
 *
 */

void Sheet::setCell(CellAddress address, const char* value)
{
    assert(value);


    if (*value == '\0') {
        clear(address, false);
        return;
    }

    setContent(address, value);
}

/**
 * Get the Python object for the Sheet.
 *
 * @returns The Python object.
 */

PyObject* Sheet::getPyObject()
{
    if (PythonObject.is(Py::_None())) {
        // ref counter is set to 1
        PythonObject = Py::Object(new SheetPy(this), true);
    }
    return Py::new_reference_to(PythonObject);
}

/**
 * Get the Cell Property for the cell at \a key.
 *
 * @returns The Property object.
 *
 */

Property* Sheet::getProperty(CellAddress key) const
{
    return props.getDynamicPropertyByName(key.toString(CellAddress::Cell::ShowRowColumn).c_str());
}

std::string Sheet::getCanonicalPropertyName(const char* name) const
{
    App::CellAddress address = getCellAddress(name, true);
    if (!address.isValid()) {
        return {};
    }

    return address.toString(CellAddress::Cell::ShowRowColumn);
}

/**
 * @brief Get a dynamic property.
 * @param addr Name of dynamic propeerty.
 * @return Pointer to property, or 0 if it does not exist.
 */

Property* Sheet::getProperty(const char* addr) const
{
    return props.getDynamicPropertyByName(addr);
}

/**
 * Get the address as \a address of the Property \a prop. This function
 * throws an exception if the property is not found.
 *
 */

bool Sheet::getCellAddress(const Property* prop, CellAddress& address)
{
    std::map<const Property*, CellAddress>::const_iterator i = propAddress.find(prop);

    if (i != propAddress.end()) {
        address = i->second;
        return true;
    }
    return false;
}

App::CellAddress Sheet::getCellAddress(const char* name, bool silent) const
{
    return cells.getCellAddress(name, silent);
}

App::Range Sheet::getRange(const char* name, bool silent) const
{
    return cells.getRange(name, silent);
}

std::tuple<App::CellAddress, App::CellAddress> Sheet::getUsedRange() const
{
    return cells.getUsedRange();
}

/**
 * @brief Get a map with column indices and widths.
 * @return Map with results.
 */

std::map<int, int> Sheet::getColumnWidths() const
{
    return columnWidths.getValues();
}

/**
 * @brief Get a map with row indices and heights.
 * @return Map with results
 */

std::map<int, int> Sheet::getRowHeights() const
{
    return rowHeights.getValues();
}


/**
 * Update internal structure when document is set for this property.
 */

void Sheet::onSettingDocument()
{
    cells.documentSet();
}

/**
 * Set the property for cell \p key to a PropertyFloat with the value \a value.
 * If the Property exists, but of wrong type, the previous Property is destroyed and recreated as
 * the correct type.
 *
 * @param key   The address of the cell we want to create a Property for
 * @param value The value we want to assign to the Property.
 *
 */

Property* Sheet::setFloatProperty(CellAddress key, double value)
{
    std::string name = key.toString(CellAddress::Cell::ShowRowColumn);
    Property* prop = props.getDynamicPropertyByName(name.c_str());
    PropertyFloat* floatProp;

    if (!prop || !prop->is<PropertyFloat>()) {
        if (prop) {
            this->removeDynamicProperty(name.c_str());
            propAddress.erase(prop);
        }
        floatProp = freecad_cast<PropertyFloat*>(addDynamicProperty(
            "App::PropertyFloat",
            name.c_str(),
            nullptr,
            nullptr,
            Prop_ReadOnly | Prop_Hidden | Prop_NoPersist
        ));
    }
    else {
        floatProp = static_cast<PropertyFloat*>(prop);
    }

    propAddress[floatProp] = key;
    floatProp->setValue(value);

    return floatProp;
}

Property* Sheet::setIntegerProperty(CellAddress key, long value)
{
    std::string name = key.toString(CellAddress::Cell::ShowRowColumn);
    Property* prop = props.getDynamicPropertyByName(name.c_str());
    PropertyInteger* intProp;

    if (!prop || !prop->is<PropertyInteger>()) {
        if (prop) {
            this->removeDynamicProperty(name.c_str());
            propAddress.erase(prop);
        }
        intProp = freecad_cast<PropertyInteger*>(addDynamicProperty(
            "App::PropertyInteger",
            name.c_str(),
            nullptr,
            nullptr,
            Prop_ReadOnly | Prop_Hidden | Prop_NoPersist
        ));
    }
    else {
        intProp = static_cast<PropertyInteger*>(prop);
    }

    propAddress[intProp] = key;
    intProp->setValue(value);

    return intProp;
}


/**
 * Set the property for cell \p key to a PropertyQuantity with \a value and \a unit.
 * If the Property exists, but of wrong type, the previous Property is destroyed and recreated as
 * the correct type.
 *
 * @param key   The address of the cell we want to create a Property for
 * @param value The value we want to assign to the Property.
 * @param unit  The associated unit for \a value.
 *
 */

Property* Sheet::setQuantityProperty(CellAddress key, double value, const Base::Unit& unit)
{
    std::string name = key.toString(CellAddress::Cell::ShowRowColumn);
    Property* prop = props.getDynamicPropertyByName(name.c_str());
    PropertySpreadsheetQuantity* quantityProp;

    if (!prop || !prop->is<PropertySpreadsheetQuantity>()) {
        if (prop) {
            this->removeDynamicProperty(name.c_str());
            propAddress.erase(prop);
        }
        Property* p = addDynamicProperty(
            "Spreadsheet::PropertySpreadsheetQuantity",
            name.c_str(),
            nullptr,
            nullptr,
            Prop_ReadOnly | Prop_Hidden | Prop_NoPersist
        );
        quantityProp = freecad_cast<PropertySpreadsheetQuantity*>(p);
    }
    else {
        quantityProp = static_cast<PropertySpreadsheetQuantity*>(prop);
    }

    propAddress[quantityProp] = key;
    quantityProp->setValue(value);
    quantityProp->setUnit(unit);

    cells.setComputedUnit(key, unit);

    return quantityProp;
}

/**
 * Set the property for cell \p key to a PropertyString with \a value.
 * If the Property exists, but of wrong type, the previous Property is destroyed and recreated as
 * the correct type.
 *
 * @param key   The address of the cell we want to create a Property for
 * @param value The value we want to assign to the Property.
 *
 */

Property* Sheet::setStringProperty(CellAddress key, const std::string& value)
{
    std::string name = key.toString(CellAddress::Cell::ShowRowColumn);
    Property* prop = props.getDynamicPropertyByName(name.c_str());
    PropertyString* stringProp = freecad_cast<PropertyString*>(prop);

    if (!stringProp) {
        if (prop) {
            this->removeDynamicProperty(name.c_str());
            propAddress.erase(prop);
        }
        stringProp = freecad_cast<PropertyString*>(addDynamicProperty(
            "App::PropertyString",
            name.c_str(),
            nullptr,
            nullptr,
            Prop_ReadOnly | Prop_Hidden | Prop_NoPersist
        ));
    }

    propAddress[stringProp] = key;
    stringProp->setValue(value.c_str());

    return stringProp;
}

Property* Sheet::setObjectProperty(CellAddress key, Py::Object object)
{
    std::string name = key.toString(CellAddress::Cell::ShowRowColumn);
    Property* prop = props.getDynamicPropertyByName(name.c_str());
    PropertyPythonObject* pyProp = freecad_cast<PropertyPythonObject*>(prop);

    if (!pyProp) {
        if (prop) {
            this->removeDynamicProperty(name.c_str());
            propAddress.erase(prop);
        }
        pyProp = freecad_cast<PropertyPythonObject*>(addDynamicProperty(
            "App::PropertyPythonObject",
            name.c_str(),
            nullptr,
            nullptr,
            Prop_ReadOnly | Prop_Hidden | Prop_NoPersist
        ));
    }

    propAddress[pyProp] = key;
    pyProp->setValue(object);

    return pyProp;
}

struct CurrentAddressLock
{
    CurrentAddressLock(int& r, int& c, const CellAddress& addr)
        : row(r)
        , col(c)
    {
        row = addr.row();
        col = addr.col();
    }
    ~CurrentAddressLock()
    {
        row = -1;
        col = -1;
    }

    int& row;
    int& col;
};

/**
 * Update the Property given by \a key. This will also eventually trigger recomputations of cells
 * depending on \a key.
 *
 * @param key The address of the cell we want to recompute.
 *
 */

void Sheet::updateProperty(CellAddress key)
{
    Cell* cell = getCell(key);

    if (cell) {
        std::unique_ptr<Expression> output;
        const Expression* input = cell->getExpression();

        if (input) {
            CurrentAddressLock lock(currentRow, currentCol, key);
            output = input->eval();
        }
        else {
            std::string s;

            if (cell->getStringContent(s) && !s.empty()) {
                output = std::make_unique<StringExpression>(this, s);
            }
            else {
                this->removeDynamicProperty(key.toString().c_str());
                return;
            }
        }

        /* Eval returns either NumberExpression or StringExpression, or
         * PyObjectExpression objects */
        auto number = freecad_cast<NumberExpression*>(output.get());
        if (number) {
            long l;
            auto constant = freecad_cast<ConstantExpression*>(output.get());
            if (constant && !constant->isNumber()) {
                Base::PyGILStateLocker lock;
                setObjectProperty(key, constant->getPyValue());
            }
            else if (number->getUnit() != Unit::One) {
                setQuantityProperty(key, number->getValue(), number->getUnit());
            }
            else if (number->isInteger(&l)) {
                setIntegerProperty(key, l);
            }
            else {
                setFloatProperty(key, number->getValue());
            }
        }
        else {
            auto str_expr = freecad_cast<StringExpression*>(output.get());
            if (str_expr) {
                setStringProperty(key, str_expr->getText().c_str());
            }
            else {
                Base::PyGILStateLocker lock;
                auto py_expr = freecad_cast<PyObjectExpression*>(output.get());
                if (py_expr) {
                    setObjectProperty(key, py_expr->getPyValue());
                }
                else {
                    setObjectProperty(key, Py::Object());
                }
            }
        }
    }
    else {
        clear(key);
    }

    cellUpdated(key);
}

/**
 * Retrieve a specific Property given by \a name.
 * This function might throw an exception if something fails, but might also
 * return 0 in case the property is not found.
 *
 * @returns The property, or 0 if not found.
 *
 */

Property* Sheet::getPropertyByName(const char* name) const
{
    CellAddress addr = getCellAddress(name, true);
    Property* prop = nullptr;
    if (addr.isValid()) {
        prop = getProperty(addr);
    }
    if (prop) {
        return prop;
    }
    else {
        return DocumentObject::getPropertyByName(name);
    }
}

Property* Sheet::getDynamicPropertyByName(const char* name) const
{
    CellAddress addr = getCellAddress(name, true);
    Property* prop = nullptr;
    if (addr.isValid()) {
        prop = getProperty(addr);
    }
    if (prop) {
        return prop;
    }
    else {
        return DocumentObject::getDynamicPropertyByName(name);
    }
}

void Sheet::getPropertyNamedList(std::vector<std::pair<const char*, Property*>>& List) const
{
    DocumentObject::getPropertyNamedList(List);
    List.reserve(List.size() + cells.aliasProp.size());
    for (auto& v : cells.aliasProp) {
        auto prop = getProperty(v.first);
        if (prop) {
            List.emplace_back(v.second.c_str(), prop);
        }
    }
}

void Sheet::visitProperties(const std::function<void(App::Property*)>& visitor) const
{
    DocumentObject::visitProperties(visitor);
    for (const auto& v : cells.aliasProp) {
        auto prop = getProperty(v.first);
        if (prop != nullptr) {
            visitor(prop);
        }
    };
}

void Sheet::touchCells(Range range)
{
    do {
        cells.setDirty(*range);
    } while (range.next());
}

void Sheet::recomputeCells(Range range)
{
    do {
        recomputeCell(*range);
    } while (range.next());
}

/**
 * @brief Recompute cell at address \a p.
 * @param p Address of cell.
 */

void Sheet::recomputeCell(CellAddress p)
{
    Cell* cell = cells.getValue(p);

    try {
        if (cell && cell->hasException()) {
            std::string content;
            cell->getStringContent(content);
            cell->setContent(content.c_str());
        }

        updateProperty(p);

        if (!cell || !cell->hasException()) {
            cells.clearDirty(p);
            cellErrors.erase(p);
        }
    }
    catch (const Base::Exception& e) {
        QString msg = QStringLiteral("ERR: %1").arg(QString::fromUtf8(e.what()));

        setStringProperty(p, msg.toStdString());
        if (cell) {
            cell->setException(e.what());
        }
        else {
            e.reportException();
        }

        // Mark as erroneous
        cellErrors.insert(p);
        cellUpdated(p);

        if (e.isDerivedFrom<Base::AbortException>()) {
            throw;
        }
    }
}

PropertySheet::BindingType Sheet::getCellBinding(
    Range& range,
    ExpressionPtr* pStart,
    ExpressionPtr* pEnd,
    App::ObjectIdentifier* pTarget
) const
{
    range.normalize();
    do {
        CellAddress addr = *range;
        for (const auto& r : boundRanges) {
            if (addr.row() >= r.from().row() && addr.row() <= r.to().row()
                && addr.col() >= r.from().col() && addr.col() <= r.to().col()) {
                auto res = cells.getBinding(r, pStart, pEnd, pTarget);
                if (res != PropertySheet::BindingNone) {
                    range = r;
                    return res;
                }
            }
        }
    } while (range.next());
    return PropertySheet::BindingNone;
}

static inline unsigned _getBorder(
    const Sheet* sheet,
    const std::vector<App::Range>& ranges,
    const App::CellAddress& address
)
{
    unsigned flags = 0;
    int rows, cols;
    sheet->getSpans(address, rows, cols);
    --rows;
    --cols;
    for (auto& range : ranges) {
        auto from = range.from();
        auto to = range.to();
        if (address.row() < from.row() || address.row() + rows > to.row()
            || address.col() < from.col() || address.col() + cols > to.col()) {
            continue;
        }
        if (address.row() == from.row()) {
            flags |= Sheet::BorderTop;
        }
        if (address.row() == to.row() || address.row() + rows == to.row()) {
            flags |= Sheet::BorderBottom;
        }
        if (address.col() == from.col()) {
            flags |= Sheet::BorderLeft;
        }
        if (address.col() == to.col() || address.col() + cols == to.col()) {
            flags |= Sheet::BorderRight;
        }
        if (flags == Sheet::BorderAll) {
            break;
        }
    }
    return flags;
}

unsigned Sheet::getCellBindingBorder(App::CellAddress address) const
{
    return _getBorder(this, boundRanges, address);
}

void Sheet::updateBindings()
{
    std::set<Range> oldRangeSet(boundRanges.begin(), boundRanges.end());
    std::set<Range> newRangeSet;
    std::set<Range> rangeSet;
    boundRanges.clear();
    for (const auto& v : ExpressionEngine.getExpressions()) {
        CellAddress from, to;
        if (!cells.isBindingPath(v.first, &from, &to)) {
            continue;
        }
        App::Range range(from, to, true);
        if (!oldRangeSet.erase(range)) {
            newRangeSet.insert(range);
        }
        rangeSet.insert(range);
    }
    boundRanges.reserve(rangeSet.size());
    boundRanges.insert(boundRanges.end(), rangeSet.begin(), rangeSet.end());
    for (const auto& range : oldRangeSet) {
        rangeUpdated(range);
    }
    for (const auto& range : newRangeSet) {
        rangeUpdated(range);
    }
}

/**
 * Update the document properties.
 *
 */

DocumentObjectExecReturn* Sheet::execute()
{
    updateBindings();

    // Get dirty cells that we have to recompute
    std::set<CellAddress> dirtyCells = cells.getDirty();

    // Always recompute cells that have failed
    for (auto cellError : cellErrors) {
        cells.recomputeDependencies(cellError);
        dirtyCells.insert(cellError);
    }

    DependencyList graph;
    std::map<CellAddress, Vertex> VertexList;
    std::map<Vertex, CellAddress> VertexIndexList;
    std::deque<CellAddress> workQueue(dirtyCells.begin(), dirtyCells.end());
    while (!workQueue.empty()) {
        CellAddress currPos = workQueue.front();
        workQueue.pop_front();

        // Insert into map of CellPos -> Index, if it doesn't exist already
        auto res = VertexList.emplace(currPos, Vertex());
        if (res.second) {
            res.first->second = add_vertex(graph);
            VertexIndexList[res.first->second] = currPos;
        }

        // Process cells that depend on the current cell
        for (auto& dep : providesTo(currPos)) {
            auto resDep = VertexList.emplace(dep, Vertex());
            if (resDep.second) {
                resDep.first->second = add_vertex(graph);
                VertexIndexList[resDep.first->second] = dep;
                if (dirtyCells.insert(dep).second) {
                    workQueue.push_back(dep);
                }
            }
            // Add edge to graph to signal dependency
            add_edge(res.first->second, resDep.first->second, graph);
        }
    }
    // Compute cells
    std::list<Vertex> make_order;
    // Sort graph topologically to find evaluation order
    try {
        boost::topological_sort(graph, std::front_inserter(make_order));
        // Recompute cells
        FC_LOG("recomputing " << getFullName());
        for (auto& pos : make_order) {
            const auto& addr = VertexIndexList[pos];
            FC_TRACE(addr.toString());
            recomputeCell(addr);
        }
    }
    catch (std::exception&) {
        for (auto& v : VertexList) {
            Cell* cell = cells.getValue(v.first);
            // Mark as erroneous
            if (cell) {
                cellErrors.insert(v.first);
                cell->setException("Pending computation due to cyclic dependency", true);
                cellUpdated(v.first);
            }
        }

        // Try to be more user friendly by finding individual loops
        while (!dirtyCells.empty()) {

            std::deque<CellAddress> workQueue;
            DependencyList graph;
            std::map<CellAddress, Vertex> VertexList;
            std::map<Vertex, CellAddress> VertexIndexList;

            CellAddress currentAddr = *dirtyCells.begin();
            workQueue.push_back(currentAddr);
            dirtyCells.erase(dirtyCells.begin());

            while (!workQueue.empty()) {
                CellAddress currPos = workQueue.front();
                workQueue.pop_front();

                // Insert into map of CellPos -> Index, if it doesn't exist already
                auto res = VertexList.emplace(currPos, Vertex());
                if (res.second) {
                    res.first->second = add_vertex(graph);
                    VertexIndexList[res.first->second] = currPos;
                }

                // Process cells that depend on the current cell
                for (auto& dep : providesTo(currPos)) {
                    auto resDep = VertexList.emplace(dep, Vertex());
                    if (resDep.second) {
                        resDep.first->second = add_vertex(graph);
                        VertexIndexList[resDep.first->second] = dep;
                        workQueue.push_back(dep);
                        dirtyCells.erase(dep);
                    }
                    // Add edge to graph to signal dependency
                    add_edge(res.first->second, resDep.first->second, graph);
                }
            }

            std::list<Vertex> make_order;
            try {
                boost::topological_sort(graph, std::front_inserter(make_order));
            }
            catch (std::exception&) {  // TODO: evaluate using a more specific exception (not_a_dag)
                // Cycle detected; flag all with errors
                Base::Console().error(
                    "Cyclic dependency detected in spreadsheet : {}\n",
                    getNameInDocument()
                );
                std::ostringstream ss;
                ss << "Cyclic dependency";
                int count = 0;
                for (auto& v : VertexList) {
                    if (count++ % 20 == 0) {
                        ss << std::endl;
                    }
                    else {
                        ss << ", ";
                    }
                    ss << v.first.toString();
                }
                std::string msg = ss.str();
                for (auto& v : VertexList) {
                    Cell* cell = cells.getValue(v.first);
                    if (cell) {
                        cell->setException(msg.c_str(), true);
                        cellUpdated(v.first);
                    }
                }
            }
        }
    }

    // Signal update of column widths
    const std::set<int>& dirtyColumns = columnWidths.getDirty();

    for (int dirtyColumn : dirtyColumns) {
        columnWidthChanged(dirtyColumn, columnWidths.getValue(dirtyColumn));
    }

    // Signal update of row heights
    const std::set<int>& dirtyRows = rowHeights.getDirty();

    for (int dirtyRow : dirtyRows) {
        rowHeightChanged(dirtyRow, rowHeights.getValue(dirtyRow));
    }

    // cells.clearDirty();
    rowHeights.clearDirty();
    columnWidths.clearDirty();

    if (cellErrors.empty()) {
        return DocumentObject::StdReturn;
    }
    else {
        return new DocumentObjectExecReturn("One or more cells failed contains errors.", this);
    }
}

/**
 * Determine whether this object needs to be executed to update internal structures.
 *
 */

short Sheet::mustExecute() const
{
    if (!cellErrors.empty() || cells.isDirty()) {
        return 1;
    }
    return DocumentObject::mustExecute();
}


/**
 * Clear the cell at \a address. If \a all is false, only the text or expression
 * contents are cleared. If \a all is true everything in the cell
 * is cleared, including color, style, etc.
 *
 * @param address Address of cell to clear
 * @param all     Whether we should clear all or not.
 *
 */

void Sheet::clear(CellAddress address, bool /*all*/)
{
    if (auto cell = getCell(address)) {
        // Remove alias, if defined
        std::string aliasStr;
        if (cell->getAlias(aliasStr)) {
            this->removeDynamicProperty(aliasStr.c_str());
        }
        cells.clear(address);
    }

    std::string addr = address.toString();
    if (auto prop = props.getDynamicPropertyByName(addr.c_str())) {
        propAddress.erase(prop);
        this->removeDynamicProperty(addr.c_str());
    }
}

/**
 * Get row an column span for the cell at (row, col).
 *
 * @param address Address of cell
 * @param rows The number of unit cells this cell spans
 * @param cols The number of unit rows this cell spans
 *
 */

void Sheet::getSpans(CellAddress address, int& rows, int& cols) const
{
    return cells.getSpans(address, rows, cols);
}

/**
 * Determine whether this cell is merged with another or not.
 *
 * @param address
 *
 * @returns True if cell is merged, false if not.
 *
 */

bool Sheet::isMergedCell(CellAddress address) const
{
    return cells.isMergedCell(address);
}

App::CellAddress Spreadsheet::Sheet::getAnchor(App::CellAddress address) const
{
    return cells.getAnchor(address);
}

/**
 * @brief Set column with of column \a col to \a width-
 * @param col   Index of column.
 * @param width New width of column.
 */

void Sheet::setColumnWidth(int col, int width)
{
    columnWidths.setValue(col, width);
}

/**
 * @brief Get column with of column at index \a col.
 * @param col
 * @return
 */

int Sheet::getColumnWidth(int col) const
{
    return columnWidths.getValue(col);
}

/**
 * @brief Set row height of row given by index in \p row to \a height.
 * @param row Row index.
 * @param height New height of row.
 */

void Sheet::setRowHeight(int row, int height)
{
    rowHeights.setValue(row, height);
}

/**
 * @brief Get height of row at index \a row.
 * @param row Index of row.
 * @return Height
 */

int Sheet::getRowHeight(int row) const
{
    return rowHeights.getValue(row);
}

/**
 * Get a vector of strings with addresses of all used cells.
 *
 * @returns vector of strings.
 *
 */

std::vector<std::string> Sheet::getUsedCells() const
{
    std::vector<std::string> usedCells;
    for (const auto& addr : cells.getUsedCells()) {
        usedCells.push_back(addr.toString());
    }

    return usedCells;
}

void Sheet::updateColumnsOrRows(bool horizontal, int section, int count)
{
    const auto& sizes = horizontal ? columnWidths.getValues() : rowHeights.getValues();
    auto iter = sizes.lower_bound(section);
    if (iter != sizes.end()) {
        std::map<int, int> newsizes(sizes.begin(), iter);
        if (count > 0) {
            for (; iter != sizes.end(); ++iter) {
                newsizes.emplace(iter->first + count, iter->second);
            }
        }
        else {
            iter = sizes.lower_bound(section - count);
            if (iter != sizes.end()) {
                for (; iter != sizes.end(); ++iter) {
                    newsizes.emplace(iter->first + count, iter->second);
                }
            }
        }
        if (horizontal) {
            columnWidths.setValues(newsizes);
        }
        else {
            rowHeights.setValues(newsizes);
        }
    }
}

/**
 * Insert \a count columns at before column \a col in the spreadsheet.
 *
 * @param col   Address of column where the columns are inserted.
 * @param count Number of columns to insert
 *
 */

void Sheet::insertColumns(int col, int count)
{
    // With a zero count every cell would be moved onto itself, which frees it
    if (count <= 0) {
        return;
    }
    cells.insertColumns(col, count);
    updateColumnsOrRows(true, col, count);
}

/**
 * Remove \a count columns at column \a col.
 *
 * @param col   Address of first column to remove.
 * @param count Number of columns to remove.
 *
 */

void Sheet::removeColumns(int col, int count)
{
    // With a zero count every cell would be moved onto itself, which frees it
    if (count <= 0) {
        return;
    }

    // Remove aliases, if defined
    for (const auto& address : cells.getColumns(col, count)) {
        auto cell = getCell(address);
        std::string aliasStr;
        if (cell && cell->getAlias(aliasStr)) {
            removeDynamicProperty(aliasStr.c_str());
        }
    }

    cells.removeColumns(col, count);
    updateColumnsOrRows(true, col, -count);
}

/**
 * Insert \a count rows at row \a row.
 *
 * @param row   Address of row where the rows are inserted.
 * @param count Number of rows to insert.
 *
 */

void Sheet::insertRows(int row, int count)
{
    // With a zero count every cell would be moved onto itself, which frees it
    if (count <= 0) {
        return;
    }
    cells.insertRows(row, count);
    updateColumnsOrRows(false, row, count);
}

/**
 * Remove \a count rows starting at \a row from the spreadsheet.
 *
 * @param row   Address of first row to remove.
 * @param count Number of rows to remove.
 *
 */

void Sheet::removeRows(int row, int count)
{
    // With a zero count every cell would be moved onto itself, which frees it
    if (count <= 0) {
        return;
    }

    // Remove aliases, if defined
    for (const auto& address : cells.getRows(row, count)) {
        auto cell = getCell(address);
        std::string aliasStr;
        if (cell && cell->getAlias(aliasStr)) {
            removeDynamicProperty(aliasStr.c_str());
        }
    }

    cells.removeRows(row, count);
    updateColumnsOrRows(false, row, -count);
}

/**
 * @brief Set content of cell at \a address to \a value.
 * @param address Address of cell
 * @param value New value
 */

void Sheet::setContent(CellAddress address, const char* value)
{
    cells.setContent(address, value);
}

/**
 * @brief Set alignment of content in cell at \a address to \a alignment.
 * @param address Address of cell
 * @param alignment New alignment
 */

void Sheet::setAlignment(CellAddress address, int alignment)
{
    cells.setAlignment(address, alignment);
}

/**
 * @brief Set alignment of content in cells part of \a range to \a alignment.
 * @param range Range of cells
 * @param alignment New alignment
 */

void Sheet::setAlignment(App::Range range, int alignment)
{
    cells.setAlignment(range, alignment);
}

/**
 * @brief Set style of cell at \a address to \a style.
 * @param address Address of cell
 * @param style New style
 */

void Sheet::setStyle(CellAddress address, const std::set<std::string>& style)
{
    cells.setStyle(address, style);
}

/**
 * @brief Set style of cells of \a range to \a style.
 * @param range Range of cells
 * @param style New style
 */

void Sheet::setStyle(Range range, const std::set<std::string>& style)
{
    cells.setStyle(range, style);
}

/**
 * @brief Set foreground (text color) of cell at address \a address to \a color.
 * @param address Address of cell
 * @param color New color
 */

void Sheet::setForeground(CellAddress address, const Color& color)
{
    cells.setForeground(address, color);
}

/**
 * @brief Set foreground (text color) of cells part of \a range to \a color.
 * @param range Range of cells
 * @param alignment New color
 */

void Sheet::setForeground(App::Range range, const Color& color)
{
    cells.setForeground(range, color);
}

/**
 * @brief Clears foreground (text color) of cell at address \a address.
 * @param address Address of cell
 */

void Sheet::clearForeground(CellAddress address)
{
    cells.clearForeground(address);
}

/**
 * @brief Set background color of cell at address \a address to \a color.
 * @param address Address of cell
 * @param color New color
 */

void Sheet::setBackground(CellAddress address, const Color& color)
{
    cells.setBackground(address, color);
}

/**
 * @brief Set background color of cells part of \a range to \a color.
 * @param range Range of cells
 * @param alignment New color
 */

void Sheet::setBackground(App::Range range, const Color& color)
{
    cells.setBackground(range, color);
}

/**
 * @brief Clears background color of cell at address \a address.
 * @param address Address of cell
 */

void Sheet::clearBackground(CellAddress address)
{
    cells.clearBackground(address);
}

/**
 * @brief Set display unit of cell at address \a address to \a unit.
 * @param address Address of cell
 * @param unit New unit
 */

void Sheet::setDisplayUnit(CellAddress address, const std::string& unit)
{
    cells.setDisplayUnit(address, unit);
}

/**
 * @brief Set display unit for cells part of \a range to \a unit.
 * @param range Range of cells
 * @param unit New unit
 */

void Sheet::setDisplayUnit(App::Range range, const std::string& unit)
{
    cells.setDisplayUnit(range, unit);
}

/**
 * @brief Set the number of decimals shown for numbers in the cells of \a range.
 * @param range Range of cells
 * @param decimals 0 to 15, or a negative value to use the unit preferences again
 */

void Sheet::setDecimals(App::Range range, int decimals)
{
    cells.setDecimals(range, decimals);
}

/**
 * @brief Set how the numbers of the cells in \a range are written.
 * @param range Range of cells
 * @param format The number format; General is the default
 */

void Sheet::setNumberFormat(App::Range range, Cell::NumberFormat format)
{
    cells.setNumberFormat(range, format);
}

/**
 * @brief Draw or remove borders on the cells of \a range.
 * @param range Range of cells
 * @param borders Or'ed Cell::BORDER_* values
 * @param mode How the borders combine with those of the cells, see PropertySheet::BorderMode
 */

void Sheet::setBorders(App::Range range, int borders, PropertySheet::BorderMode mode)
{
    cells.setBorders(range, borders, mode);
}

/**
 * @brief Set computed unit for cell at address \a address to \a unit.
 * @param address Address of cell
 * @param unit New unit.
 */

void Sheet::setComputedUnit(CellAddress address, const Base::Unit& unit)
{
    cells.setComputedUnit(address, unit);
}

/**
 * @brief Set computed unit for cells part of \a range to \a unit.
 * @param address Address of cell
 * @param unit New unit.
 */

void Sheet::setComputedUnit(App::Range range, const Base::Unit& unit)
{
    cells.setComputedUnit(range, unit);
}

/**
 * @brief Set alias for cell at address \a address to \a alias. If the alias
 * is an empty string, the existing alias is removed.
 * @param address Address of cell
 * @param alias New alias.
 */

void Sheet::setAlias(CellAddress address, const std::string& alias)
{
    std::string existingAlias = getAddressFromAlias(alias);

    if (!existingAlias.empty()) {
        if (existingAlias == address.toString()) {  // Same as old?
            return;
        }
        else {
            throw Base::ValueError("Alias already defined");
        }
    }
    else if (alias.empty()) {  // Empty?
        cells.setAlias(address, "");
    }
    else if (isValidAlias(alias)) {  // Valid?
        cells.setAlias(address, alias);
    }
    else {
        switch (classifyReservedAliasName(alias)) {
            case ReservedAliasToken::Unit:
                throw Base::ValueError("Invalid alias: name conflicts with a reserved unit token");
            case ReservedAliasToken::Constant:
                throw Base::ValueError("Invalid alias: name conflicts with a reserved constant token");
            case ReservedAliasToken::None:
                break;
        }
        throw Base::ValueError("Invalid alias");
    }
}

/**
 * @brief Get cell given an alias string
 * @param alias Alias for cell
 *
 * @returns Name of cell, or empty string if not defined
 */

std::string Sheet::getAddressFromAlias(const std::string& alias) const
{
    // The alias map is what defines the address of an alias. Do not require the cell itself:
    // inserting or removing rows/columns moves the aliases before their cells, and the
    // dependencies of the cells moved in between resolve ranges such as "first:last" here.
    auto it = cells.revAliasProp.find(alias);

    if (it != cells.revAliasProp.end()) {
        return it->second.toString();
    }
    return {};
}

Sheet::ReservedAliasToken Sheet::classifyReservedAliasName(const std::string& candidate)
{
    if (ExpressionParser::isTokenAUnit(candidate)) {
        return ReservedAliasToken::Unit;
    }
    if (ExpressionParser::isTokenAConstant(candidate)) {
        return ReservedAliasToken::Constant;
    }
    return ReservedAliasToken::None;
}

/**
 * @brief Determine whether a given alias candidate is valid or not.
 *
 * A candidate is valid is the string is syntactically correct,
 * and the alias does not conflict with an existing property.
 *
 */

bool Sheet::isValidAlias(const std::string& candidate)
{
    // Valid syntactically?
    if (!cells.isValidAlias(candidate)) {
        return false;
    }

    // Existing alias? Then it's ok
    if (!getAddressFromAlias(candidate).empty()) {
        return true;
    }

    // Check to see that is does not crash with any other property in the Sheet object.
    if (getPropertyByName(candidate.c_str())) {
        return false;
    }
    else {
        return true;
    }
}

/**
 * @brief Set row and column span for the cell at address \a address to \a rows and \a columns.
 * @param address Address to upper right corner of cell
 * @param rows Rows to span
 * @param columns Columns to span
 */

void Sheet::setSpans(CellAddress address, int rows, int columns)
{
    cells.setSpans(address, rows, columns);
}

/**
 * @brief Return a set of dependencies links for cell at \a address.
 * @param address Address of cell
 * @return Set of dependencies.
 */

std::set<std::string> Sheet::dependsOn(CellAddress address) const
{
    return cells.getDeps(address);
}

/**
 * @brief Compute links to cells that cell at \a address provides input to.
 * @param address Address of cell
 * @param result Set of links.
 */

void Sheet::providesTo(CellAddress address, std::set<std::string>& result) const
{
    std::string fullName = getFullName() + ".";
    std::set<CellAddress> tmpResult = cells.getDeps(fullName + address.toString());

    for (const auto& i : tmpResult) {
        result.insert(fullName + i.toString());
    }
}

/**
 * @brief Compute links to cells that cell at \a address provides input to.
 * @param address Address of cell
 * @param result Set of links.
 */

std::set<CellAddress> Sheet::providesTo(CellAddress address) const
{
    return cells.getDeps(getFullName() + "." + address.toString());
}

void Sheet::onDocumentRestored()
{
    auto ret = execute();
    if (ret != DocumentObject::StdReturn) {
        FC_ERR("Failed to restore " << getFullName() << ": " << ret->Why);
        delete ret;
    }
}

void Sheet::renameObjectIdentifiers(const std::map<ObjectIdentifier, ObjectIdentifier>& paths)
{
    DocumentObject::renameObjectIdentifiers(paths);

    cells.renameObjectIdentifiers(paths);
}
bool Sheet::hasCell(const std::vector<App::Range>& ranges) const
{
    for (auto range : ranges) {
        do {
            if (cells.getValue(*range)) {
                return true;
            }
        } while (range.next());
    }
    return false;
}

std::string Sheet::getRow(int offset) const
{
    if (currentRow < 0) {
        throw Base::RuntimeError("No current row");
    }
    int row = currentRow + offset;
    if (row < 0 || row > CellAddress::MAX_ROWS) {
        throw Base::ValueError("Out of range");
    }
    return std::to_string(row + 1);
}

std::string Sheet::getColumn(int offset) const
{
    if (currentCol < 0) {
        throw Base::RuntimeError("No current column");
    }
    int col = currentCol + offset;
    if (col < 0 || col > CellAddress::MAX_COLUMNS) {
        throw Base::ValueError("Out of range");
    }
    if (col < 26) {
        char txt[2];
        txt[0] = (char)('A' + col);
        txt[1] = 0;
        return txt;
    }

    col -= 26;
    char txt[3];
    txt[0] = (char)('A' + (col / 26));
    txt[1] = (char)('A' + (col % 26));
    txt[2] = 0;
    return txt;
}

void Sheet::onChanged(const App::Property* prop)
{
    if (prop == &cells) {
        decltype(copyCutRanges) tmp;
        tmp.swap(copyCutRanges);
        for (auto& range : tmp) {
            rangeUpdated(range);
        }
    }
    else {
        cells.slotChangedObject(*this, *prop);
    }
    App::DocumentObject::onChanged(prop);
}

void Sheet::setCopyOrCutRanges(const std::vector<App::Range>& ranges, bool copy)
{
    std::set<Range> rangeSet(copyCutRanges.begin(), copyCutRanges.end());
    copyCutRanges = ranges;
    rangeSet.insert(copyCutRanges.begin(), copyCutRanges.end());
    for (const auto& range : rangeSet) {
        rangeUpdated(range);
    }
    hasCopyRange = copy;
}

const std::vector<Range>& Sheet::getCopyOrCutRange(bool copy) const
{
    static const std::vector<Range> nullRange;
    if (hasCopyRange != copy) {
        return nullRange;
    }
    return copyCutRanges;
}

unsigned Sheet::getCopyOrCutBorder(CellAddress address, bool copy) const
{
    if (hasCopyRange != copy) {
        return 0;
    }
    return _getBorder(this, copyCutRanges, address);
}

///////////////////////////////////////////////////////////////////////////////

TYPESYSTEM_SOURCE(Spreadsheet::PropertySpreadsheetQuantity, App::PropertyQuantity)

Property* PropertySpreadsheetQuantity::Copy() const
{
    PropertySpreadsheetQuantity* obj = new PropertySpreadsheetQuantity();

    obj->_dValue = _dValue;
    obj->_Unit = _Unit;

    return obj;
}

void PropertySpreadsheetQuantity::Paste(const Property& from)
{
    const auto& src = dynamic_cast<const PropertySpreadsheetQuantity&>(from);
    aboutToSetValue();
    _dValue = src._dValue;
    _Unit = src._Unit;
    hasSetValue();
}

// Python sheet feature ---------------------------------------------------------

namespace App
{
/// @cond DOXERR
PROPERTY_SOURCE_TEMPLATE(Spreadsheet::SheetPython, Spreadsheet::Sheet)
template<>
const char* Spreadsheet::SheetPython::getViewProviderName() const
{
    return "SpreadsheetGui::ViewProviderSheetPython";
}
template<>
PyObject* Spreadsheet::SheetPython::getPyObject()
{
    if (PythonObject.is(Py::_None())) {
        // ref counter is set to 1
        PythonObject = Py::Object(new FeaturePythonPyT<Spreadsheet::SheetPy>(this), true);
    }
    return Py::new_reference_to(PythonObject);
}
/// @endcond

// explicit template instantiation
template class SpreadsheetExport FeaturePythonT<Spreadsheet::Sheet>;
}  // namespace App
