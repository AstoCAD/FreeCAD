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

#pragma once

#include <set>
#include <string>

#include <App/Expression.h>
#include <App/Material.h>

#include <Mod/Spreadsheet/SpreadsheetGlobal.h>

#include "DisplayUnit.h"
#include "Utils.h"


namespace Base
{
class Unit;
class XMLReader;
class Writer;
}  // namespace Base

namespace Spreadsheet
{

class PropertySheet;
class DisplayUnit;

class SpreadsheetExport Cell
{
private:
    Cell(const Cell& other);

public:
    Cell(const App::CellAddress& _address, PropertySheet* _owner);

    Cell(PropertySheet* _owner, const Cell& other);

    Cell& operator=(const Cell& rhs);

    ~Cell();

    const App::Expression* getExpression(bool withFormat = false) const;

    bool getStringContent(std::string& s, bool persistent = false) const;

    void setContent(const char* value);

    void setAlignment(int _alignment);
    bool getAlignment(int& _alignment) const;

    void setStyle(const std::set<std::string>& _style);
    bool getStyle(std::set<std::string>& style) const;

    void setForeground(const Base::Color& color);
    void clearForeground();
    bool getForeground(Base::Color& color) const;

    void setBackground(const Base::Color& color);
    void clearBackground();
    bool getBackground(Base::Color& color) const;

    void setDisplayUnit(const std::string& unit);
    bool getDisplayUnit(DisplayUnit& unit) const;

    /// Number of decimals shown for numbers; a negative value clears it.
    void setDecimals(int decimals);
    bool getDecimals(int& decimals) const;
    /// The decimals of the cell if set, otherwise those of the unit preferences.
    int getDisplayDecimals() const;

    /// The edges of the cell drawn as lines: an or'ed combination of the BORDER_* values.
    void setBorders(int borders);
    bool getBorders(int& borders) const;

    /// How the numbers of the cell are written
    enum class NumberFormat
    {
        General,     ///< with the decimals of the cell, like 1234.50
        Percent,     ///< multiplied by 100 with a percent sign, like 25.00%; numbers with a unit
                     ///< are written as General
        Scientific,  ///< with an exponent, like 1.23E+03
    };
    void setNumberFormat(NumberFormat format);
    bool getNumberFormat(NumberFormat& format) const;
    /// The text of \a value as the cell shows it: its decimals and number format applied.
    /// \a unitless tells whether the number is shown without a unit (a percentage can only be).
    std::string formatNumber(double value, bool unitless) const;

    /// The formatting of a cell: everything but its content, alias and merging.
    /// Default constructed, it is the formatting of a new cell.
    struct Format
    {
        int alignment = ALIGNMENT_HIMPLIED | ALIGNMENT_LEFT | ALIGNMENT_VIMPLIED | ALIGNMENT_VCENTER;
        std::set<std::string> style;
        bool foregroundSet = false;
        Base::Color foreground;
        bool backgroundSet = false;
        Base::Color background;
        std::string displayUnit;
        int decimals = -1;
        int borders = 0;
        NumberFormat numberFormat = NumberFormat::General;

        bool operator==(const Format& other) const = default;
    };
    Format getFormat() const;
    void setFormat(const Format& format);

    void setAlias(const std::string& n);
    bool getAlias(std::string& n) const;

    void setComputedUnit(const Base::Unit& unit);
    bool getComputedUnit(Base::Unit& unit) const;

    void setSpans(int rows, int columns);
    bool getSpans(int& rows, int& columns) const;

    void setException(const std::string& e, bool silent = false);

    void clearException();

    void clearDirty();

    void setDirty();

    void setResolveException(const std::string& e);

    void clearResolveException();

    const std::string& getException() const
    {
        return exceptionStr;
    }

    bool hasException() const
    {
        return isUsed(EXCEPTION_SET) || isUsed(PARSE_EXCEPTION_SET) || isUsed(RESOLVE_EXCEPTION_SET);
    }

    void moveAbsolute(App::CellAddress newAddress);

    void restore(Base::XMLReader& reader, bool checkAlias = false);

    void afterRestore();

    void save(Base::Writer& writer) const;
    void save(std::ostream& os, const char* indent, bool noContent) const;

    bool isUsed() const;

    void mark()
    {
        setUsed(MARK_SET);
    }

    bool isMarked() const
    {
        return isUsed(MARK_SET);
    }

    void visit(App::ExpressionVisitor& v);

    App::CellAddress getAddress() const
    {
        return address;
    }

    std::string getFormattedQuantity();

    /* Alignment */
    static const int ALIGNMENT_LEFT;
    static const int ALIGNMENT_HCENTER;
    static const int ALIGNMENT_RIGHT;
    static const int ALIGNMENT_HORIZONTAL;
    static const int ALIGNMENT_HIMPLIED;
    static const int ALIGNMENT_TOP;
    static const int ALIGNMENT_VCENTER;
    static const int ALIGNMENT_BOTTOM;
    static const int ALIGNMENT_VERTICAL;
    static const int ALIGNMENT_VIMPLIED;

    /* Borders; the same values as Sheet::Border */
    static const int BORDER_TOP;
    static const int BORDER_LEFT;
    static const int BORDER_BOTTOM;
    static const int BORDER_RIGHT;
    static const int BORDER_ALL;

    /* Static functions */
    static int decodeAlignment(const std::string& itemStr, int alignment);
    static std::string encodeAlignment(int alignment);

    static std::string encodeStyle(const std::set<std::string>& style);

    /// Borders as names separated by '|', like "top|bottom".
    static std::string encodeBorders(int borders);
    /// Add the border named \a name ("top", "left", "bottom", "right" or "all") to
    /// \a borders; returns false for an unknown name.
    static bool decodeBorder(const std::string& name, int& borders);

    /// "general", "percent" or "scientific"
    static std::string encodeNumberFormat(NumberFormat format);
    /// Returns false for an unknown name.
    static bool decodeNumberFormat(const std::string& name, NumberFormat& format);

    static std::string encodeColor(const Base::Color& color);
    static Base::Color decodeColor(const std::string& color, const Base::Color& defaultColor);

private:
    void _setAlignment(int _alignment);
    void _setStyle(const std::set<std::string>& _style);
    void _setForeground(const Base::Color& color);
    void _setBackground(const Base::Color& color);
    void _setDisplayUnit(const std::string& unit);
    void _setComputedUnit(const Base::Unit& unit);

    void setParseException(const std::string& e);

    void setExpression(App::ExpressionPtr&& expr);

    void setUsed(unsigned int mask, bool state = true);

    bool isUsed(unsigned int mask) const;

    void freeze();

    void unfreeze();

    /* Used */
    static const unsigned int EXPRESSION_SET;
    static const unsigned int ALIGNMENT_SET;
    static const unsigned int STYLE_SET;
    static const unsigned int BACKGROUND_COLOR_SET;
    static const unsigned int FOREGROUND_COLOR_SET;
    static const unsigned int DISPLAY_UNIT_SET;
    static const unsigned int COMPUTED_UNIT_SET;
    static const unsigned int ALIAS_SET;
    static const unsigned int SPANS_SET;
    static const unsigned int DECIMALS_SET;
    static const unsigned int BORDERS_SET;
    static const unsigned int NUMBER_FORMAT_SET;
    static const unsigned int MARK_SET;
    static const unsigned int EXCEPTION_SET;
    static const unsigned int PARSE_EXCEPTION_SET;
    static const unsigned int RESOLVE_EXCEPTION_SET;

    App::CellAddress address;
    PropertySheet* owner;

    unsigned int used;
    mutable App::ExpressionPtr expression;
    int alignment;
    std::set<std::string> style;
    Base::Color foregroundColor;
    Base::Color backgroundColor;
    DisplayUnit displayUnit;
    std::string alias;
    Base::Unit computedUnit;
    int rowSpan;
    int colSpan;
    int decimals;
    int borders;
    NumberFormat numberFormat;
    std::string exceptionStr;
    App::CellAddress anchor;
    friend class PropertySheet;
};

}  // namespace Spreadsheet
