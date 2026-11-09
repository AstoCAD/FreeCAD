# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2016 Ulrich Brammer <ulrich1a@users.sourceforge.net>    *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************


__title__ = "FreeCAD Spreadsheet Workbench - XLSX importer"
__author__ = "Ulrich Brammer <ulrich1a@users.sourceforge.net>"
__url__ = ["https://www.freecad.org"]

"""
This library imports an Excel-XLSX-file into FreeCAD.

Version 1.1, Nov. 2016:
Changed parser, adds rad-unit to trigonometric functions in order
to give the same result in FreeCAD.
Added factor to arcus-function in order to give the same result in FreeCAD
Added support for celltype "inlineStr"

Version 1.0:
It uses a minimal parser, in order to translate the IF-function into
the different FreeCAD version.
The other function-names are translated by search and replace.
Features:
- Imports tables defined inside Excel-document
- Set alias definitions
- Translate formulas known by FreeCAD. (see tokenDic as by version 1.1)
- set cross table references
- strings are imported
- references to cells with strings are working
- column widths, custom row heights and merged cells
- bold, italic, underline, RGB text and fill colors, alignment

known issues:
- units are not imported
- string support is minimal, the same as in FreeCAD
"""


import re
import zipfile
import xml.dom.minidom
import FreeCAD as App

try:
    import FreeCADGui
except ValueError:
    gui = False
else:
    gui = True


# The sepToken structure is used in the tokenizer functions isKey and
# getNextToken.
# sepToken defines a search tree for separator tokens with length of 1 to 3 characters
# it is also used as a list of separators between other tokens.
sepToken = {
    "(": None,
    "=": None,
    "<": "branchLower",
    ">": "branchHigher",
    ")": None,
    #  '"':None,
    #  ';':None,
    " ": None,
    ",": None,  # Separator on lists
    "!": None,  # Connector to cells on other Sheets
    "+": None,
    "-": None,
    "*": None,
    "/": None,
    "^": None,
}

branchLower = {">": None, "=": None}

branchHigher = {"=": None}


# Needed to get a reference from a string to a dict
treeDict = {"branchLower": branchLower, "branchHigher": branchHigher}

# The tokenDic is used in parseExpr.
# The tokenDic contains the following information:
# levelchange: -1: tree down, 0, +1: tree up
# replacement token
# function-state: needed to do something special in the parser
#     0 = normal, 1 = the pi-case, 2 = angle-function,
#     3 = IF-function, 4 = IF-truecase, 5 IF-falsecase


tokenDic = {
    "(": (1, "(", 0),
    "=": (0, "==", 0),
    "<>": (0, "!=", 0),
    ">=": (0, ">=", 0),
    "<=": (0, "<=", 0),
    "<": (0, "<", 0),
    ">": (0, ">", 0),
    ",": (0, ",", 0),
    ")": (-1, ")", 0),
    "!": (0, ".", 0),  # Connector to cells on other Sheets
    #  '"'  :( 2 ,'',  0),
    "+": (0, "+", 0),
    "-": (0, "-", 0),
    "*": (0, "*", 0),
    "/": (0, "/", 0),
    "^": (0, "^", 0),
    "IF": (0, "", 3),
    "ABS": (0, "abs", 0),
    "ACOS": (0, "pi/180deg*acos", 0),
    "ASIN": (0, "pi/180deg*asin", 0),
    "ATAN": (0, "pi/180deg*atan", 0),
    "ATAN2": (0, "pi/180deg*atan2", 0),
    "COS": (0, "cos", 2),
    "COSH": (0, "cosh", 2),
    "EXP": (0, "exp", 0),
    "LOG": (0, "log", 0),
    "LOG10": (0, "log10", 0),
    "MOD": (0, "mod", 0),
    "POWER": (0, "pow", 0),
    "SIN": (0, "sin", 2),
    "SINH": (0, "sinh", 2),
    "SQRT": (0, "sqrt", 0),
    "TAN": (0, "tan", 2),
    "TANH": (0, "tanh", 2),
    "AVERAGE": (0, "average", 0),
    "COUNT": (0, "count", 0),
    "MAX": (0, "max", 0),
    "MIN": (0, "min", 0),
    "STDEVA": (0, "stddev", 0),
    "SUM": (0, "sum", 0),
    "PI": (0, "pi", 1),
    "_xlfn.CEILING.MATH": (0, "ceil", 0),
    "_xlfn.FLOOR.MATH": (0, "floor", 0),
}


class exprNode(object):
    """This defines a tree class for expression parsing.
    A tree is built, to step down into the levels of the expression."""

    def __init__(self, parent, state, actIndex):
        self.state = state  # see comment: State used for Angle-functions and IF-function
        self.parent = parent  # Parent tree node
        self.lIndex = actIndex  # Index to the list of tokens
        self.result = ""


class FormulaTranslator(object):
    """This class translates a cell-formula from Excel to FreeCAD."""

    def __init__(self):
        self.tokenList = ["="]

    def translateForm(self, actExpr):
        self.getNextToken(actExpr)
        # print("tokenList: ", self.tokenList)
        self.resultTree = exprNode(None, 0, 1)
        self.resultTree.result = self.tokenList[0]
        self.parseExpr(self.resultTree)
        # print('parseResult: ', self.resultTree.result)
        return self.resultTree.result

    def getNextToken(self, theExpr):
        """This is the recursive tokenizer for an excel formula.
        It appends all identified tokens to self.tokenList."""
        # print('next Token theExpr: ', theExpr)
        # print('actTList: ', self.tokenList)
        tokenComplete = False
        keyToken = False
        if len(theExpr) > 0:
            theTok = theExpr[0]
            theExpr = theExpr[1:]
            if theTok in sepToken:
                keyToken = True
                branch = sepToken[theTok]
                while branch:
                    # print(branch, ' theExpr[0]: ',theExpr[0])
                    if theExpr[0] in treeDict[branch]:
                        branch = treeDict[branch][theExpr[0]]
                        theTok = theTok + theExpr[0]
                        theExpr = theExpr[1:]
                    else:
                        branch = None
                tokenComplete = True
                self.tokenList.append(theTok)
                self.getNextToken(theExpr)
            else:
                if len(theExpr) > 0:
                    while not tokenComplete:
                        if not self.isKey(theExpr):
                            theTok = theTok + theExpr[0]
                            theExpr = theExpr[1:]
                            if len(theExpr) == 0:
                                tokenComplete = True
                        else:
                            tokenComplete = True
                self.tokenList.append(theTok)
                self.getNextToken(theExpr)

    def isKey(self, theExpr):
        # print('look up: ', theExpr)
        keyToken = False
        lenExpr = len(theExpr)
        if theExpr[0] in sepToken:
            branch = sepToken[theExpr[0]]

            if branch is None:
                keyToken = True
            else:
                # print('There is a branch. look up: ', theExpr[1])
                if (lenExpr > 1) and (theExpr[1] in treeDict[branch]):
                    branch = treeDict[branch][theExpr[1]]
                    if branch is None:
                        keyToken = True
                    else:
                        if (lenExpr > 2) and (theExpr[2] in treeDict[branch]):
                            keyToken = True
                else:
                    keyToken = True
        return keyToken

    def parseExpr(self, treeNode):
        token = self.tokenList[treeNode.lIndex]
        treeNode.lIndex += 1
        if token in tokenDic:
            lChange, newToken, funcState = tokenDic[token]
        else:
            lChange = 0
            newToken = token
            funcState = 0
        # print('treeNode.state: ', treeNode.state, ' my.index: ', treeNode.lIndex-1, ' ', token, ' fState: ', funcState)

        if token == ",":
            if treeNode.state == 4:
                newToken = ":"
                treeNode.state = 6
            if treeNode.state == 3:
                newToken = "?"
                treeNode.state = 4

        if funcState == 3:
            funcState = 0
            newNode = exprNode(treeNode, 3, treeNode.lIndex)
            self.parseIF(newNode)
        else:
            treeNode.result = treeNode.result + newToken

        if funcState == 2:
            funcState = 0
            newNode = exprNode(treeNode, 2, treeNode.lIndex)
            self.parseAngle(newNode)
            treeNode.result = treeNode.result + ")"
        elif funcState == 1:
            treeNode.lIndex += 2  # do skip the 2 parentheses of the PI()

        if lChange == -1:
            # print 'state: ', treeNode.state, 'parent.result: ', treeNode.parent.result, ' mine: ', treeNode.result
            treeNode.parent.result = treeNode.parent.result + treeNode.result
            treeNode.parent.lIndex = treeNode.lIndex
            # print('Go one level up, state: ', treeNode.state)
            if treeNode.state < 2:
                # print(' Look up more token above')
                if treeNode.lIndex < len(self.tokenList):
                    self.parseExpr(treeNode.parent)

        elif lChange == 1:
            # print('Go one level down')
            newNode = exprNode(treeNode, 1, treeNode.lIndex)
            self.parseExpr(newNode)
            treeNode.lIndex = newNode.lIndex
        else:
            if treeNode.lIndex < len(self.tokenList):
                # print('parse to the end')
                self.parseExpr(treeNode)

    def parseIF(self, treeNode):
        # print('IF state: ', treeNode.state)
        treeNode.result = treeNode.result + "("
        treeNode.lIndex += 1
        self.parseExpr(treeNode)
        # print('IF result: ', treeNode.result)
        return

    def parseAngle(self, treeNode):
        # print('Angle state: ', treeNode.state)
        treeNode.result = treeNode.result + "(1rad*("
        treeNode.lIndex += 1
        self.parseExpr(treeNode)
        # print('angle result: ', treeNode.result)


def getText(nodelist):
    rc = []
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc.append(node.data)
    return "".join(rc)


def stringItemText(item):
    """The text of a string item (<si> of the shared strings, <is> of a cell):
    its <t>, or the <t> of all its formatted runs, without the phonetic hints."""
    return "".join(
        getText(t.childNodes)
        for t in item.getElementsByTagName("t")
        if t.parentNode.tagName != "rPh"
    )


def handleWorkSheet(theDom, actSheet, strList, cellFormats=None):
    rows = theDom.getElementsByTagName("row")
    sharedFormulas = {}
    for row in rows:
        handleCells(row.getElementsByTagName("c"), actSheet, strList, sharedFormulas)
    # Before merging: formatting a cell inside a merged cell formats the merged cell
    if cellFormats:
        for row in rows:
            handleCellFormats(row.getElementsByTagName("c"), actSheet, cellFormats)
    handleLayout(theDom, actSheet)


def childElements(node, tagName):
    return [
        child
        for child in node.childNodes
        if child.nodeType == child.ELEMENT_NODE and (child.localName or child.tagName) == tagName
    ]


def firstChildElement(node, tagName):
    children = childElements(node, tagName)
    return children[0] if children else None


def decodeColor(colorNode):
    """Returns the (r, g, b, a) floats of an Excel color given as ARGB hex digits,
    or None for theme and indexed colors."""
    if colorNode is None:
        return None
    rgb = colorNode.getAttribute("rgb")
    if len(rgb) == 6:
        rgb = "FF" + rgb
    if len(rgb) != 8:
        return None
    try:
        a, r, g, b = (int(rgb[i : i + 2], 16) / 255.0 for i in range(0, 8, 2))
    except ValueError:
        return None
    # Excel does not use the alpha byte, the colors are opaque
    return (r, g, b, 1.0)


def isOn(node):
    """True for a boolean font property like <b/> or <b val="1"/>."""
    return node is not None and node.getAttribute("val") not in ("0", "false")


def handleStyles(theStyles):
    """Returns the cell formats of xl/styles.xml, indexed like the "s" attribute
    of the cells: a tuple (style set, text color, background color, alignment)."""
    fonts = []
    fontsNode = firstChildElement(theStyles.documentElement, "fonts")
    for font in childElements(fontsNode, "font") if fontsNode else []:
        style = set()
        if isOn(firstChildElement(font, "b")):
            style.add("bold")
        if isOn(firstChildElement(font, "i")):
            style.add("italic")
        underline = firstChildElement(font, "u")
        if underline is not None and underline.getAttribute("val") != "none":
            style.add("underline")
        color = decodeColor(firstChildElement(font, "color"))
        if color == (0.0, 0.0, 0.0, 1.0):
            color = None  # the default text color
        fonts.append((style, color))

    fills = []
    fillsNode = firstChildElement(theStyles.documentElement, "fills")
    for fill in childElements(fillsNode, "fill") if fillsNode else []:
        pattern = firstChildElement(fill, "patternFill")
        color = None
        if pattern is not None and pattern.getAttribute("patternType") == "solid":
            color = decodeColor(firstChildElement(pattern, "fgColor"))
        fills.append(color)

    horizontal = {"left": "left", "center": "center", "centerContinuous": "center", "right": "right"}
    vertical = {"top": "top", "center": "vcenter", "bottom": "bottom"}

    formats = []
    xfsNode = firstChildElement(theStyles.documentElement, "cellXfs")
    for xf in childElements(xfsNode, "xf") if xfsNode else []:
        try:
            style, foreground = fonts[int(xf.getAttribute("fontId") or 0)]
        except (ValueError, IndexError):
            style, foreground = set(), None
        try:
            background = fills[int(xf.getAttribute("fillId") or 0)]
        except (ValueError, IndexError):
            background = None
        alignment = set()
        alignNode = firstChildElement(xf, "alignment")
        if alignNode is not None:
            if alignNode.getAttribute("horizontal") in horizontal:
                alignment.add(horizontal[alignNode.getAttribute("horizontal")])
            if alignNode.getAttribute("vertical") in vertical:
                alignment.add(vertical[alignNode.getAttribute("vertical")])
        formats.append((style, foreground, background, alignment))
    return formats


def readCellFormats(z):
    """Returns the cell formats of an open XLSX zip file (empty without styles)."""
    if "xl/styles.xml" not in z.namelist():
        return []
    theStyles = xml.dom.minidom.parse(z.open("xl/styles.xml"))
    try:
        return handleStyles(theStyles)
    finally:
        theStyles.unlink()


def handleCellFormats(cellList, actCellSheet, cellFormats):
    """Applies the bold, italic, underline, colors and alignment of the cells."""
    for cell in cellList:
        ref = cell.getAttribute("r")
        index = cell.getAttribute("s")
        if not ref or not index:
            continue
        try:
            style, foreground, background, alignment = cellFormats[int(index)]
        except (ValueError, IndexError):
            continue
        if not isSheetCell(ref):
            # Excel writes formatted empty cells beyond the columns and rows
            # FreeCAD has; there is nothing to format there
            continue
        if style:
            actCellSheet.setStyle(ref, style)
        if foreground:
            actCellSheet.setForeground(ref, foreground)
        if background:
            actCellSheet.setBackground(ref, background)
        if alignment:
            actCellSheet.setAlignment(ref, alignment, "keep")


# FreeCAD spreadsheets have the columns A to ZZ
maxColumns = 26 * 26 + 26
# and the rows 1 to 16384
maxRows = 16384


def isSheetCell(ref):
    """True if the cell reference, like "B3", is inside a FreeCAD spreadsheet."""
    if not cellRefPattern.fullmatch(ref):
        return False
    col, row = splitCellRef(ref)
    return 1 <= col <= maxColumns and 1 <= row <= maxRows


def excelWidthToPixels(width):
    """Converts an Excel column width (in widths of the digit "0" of the default
    font, padding included) to pixels, for the default 7 pixel wide digit."""
    digitWidth = 7
    return int(((256 * width + int(128 / digitWidth)) / 256) * digitWidth)


def handleLayout(theDom, actSheet):
    """Imports the column widths, custom row heights and merged cells of a worksheet."""
    for col in theDom.getElementsByTagName("col"):
        width = col.getAttribute("width")
        first = col.getAttribute("min")
        last = col.getAttribute("max")
        if not (width and first and last):
            continue
        try:
            pixels = excelWidthToPixels(float(width))
            first = int(first)
            last = min(int(last), maxColumns)
        except ValueError:
            continue
        if pixels <= 0:
            continue
        for column in range(first, last + 1):
            actSheet.setColumnWidth(columnName(column), pixels)

    for row in theDom.getElementsByTagName("row"):
        if row.getAttribute("customHeight") not in ("1", "true"):
            continue
        try:
            number = int(row.getAttribute("r"))
            # Heights are in points
            pixels = int(round(float(row.getAttribute("ht")) * 96 / 72))
        except ValueError:
            continue
        if pixels > 0:
            try:
                actSheet.setRowHeight(str(number), pixels)
            except ValueError:
                pass

    for merge in theDom.getElementsByTagName("mergeCell"):
        ref = merge.getAttribute("ref")
        if ":" not in ref:
            continue
        try:
            actSheet.mergeCells(ref)
        except Exception as e:
            print(f"Cannot merge cells {ref}: {e}")


# A cell reference like A1, $A1, A$1 or $A$1, not part of a longer name and
# not a sheet name (followed by "!") or a function name (followed by "(").
cellRefPattern = re.compile(r"(?<![A-Za-z0-9_.$])(\$?)([A-Z]{1,3})(\$?)([0-9]+)(?![A-Za-z0-9_.!(])")


def splitCellRef(ref):
    """Returns the (column, row) numbers of a cell reference like "B3", both 1-based."""
    match = cellRefPattern.match(ref)
    col = 0
    for letter in match.group(2):
        col = col * 26 + ord(letter) - ord("A") + 1
    return col, int(match.group(4))


def columnName(col):
    name = ""
    while col > 0:
        col, rest = divmod(col - 1, 26)
        name = chr(ord("A") + rest) + name
    return name


def shiftFormula(theFormula, rowOffset, colOffset):
    """Moves the relative cell references of an Excel formula by the given offsets,
    as Excel does for the cells sharing the formula of another cell."""

    def shiftRef(match):
        colAbs, colName, rowAbs, rowNumber = match.groups()
        col, row = splitCellRef(colName + rowNumber)
        if not colAbs:
            col += colOffset
        if not rowAbs:
            row += rowOffset
        if col < 1 or row < 1:
            return match.group(0)
        return colAbs + columnName(col) + rowAbs + str(row)

    # Do not touch string literals or quoted sheet names
    parts = re.split(r"(\"[^\"]*\"|'[^']*')", theFormula)
    for i in range(0, len(parts), 2):
        parts[i] = cellRefPattern.sub(shiftRef, parts[i])
    return "".join(parts)


def handleCells(cellList, actCellSheet, sList, sharedFormulas=None):
    if sharedFormulas is None:
        sharedFormulas = {}
    for cell in cellList:
        cellAtts = cell.attributes
        refRef = cellAtts.getNamedItem("r")
        ref = getText(refRef.childNodes)

        refType = cellAtts.getNamedItem("t")
        if refType:
            cellType = getText(refType.childNodes)
        else:
            cellType = "n"

        # print("reference: ", ref, ' Cell type: ', cellType)

        if cellType == "inlineStr":
            iStringList = cell.getElementsByTagName("is")
            # print('iString: ', iStringList)
            for stringEle in iStringList:
                theString = stringItemText(stringEle)

                # print('theString: ', theString)
                actCellSheet.set(ref, theString)

        formulaRef = cell.getElementsByTagName("f")
        if len(formulaRef) == 1:
            theFormula = getText(formulaRef[0].childNodes)
            attrs = formulaRef[0].attributes
            attrRef = attrs.getNamedItem("t")
            attrName = getText(attrRef.childNodes) if attrRef else None
            indexRef = attrs.getNamedItem("si")
            indexName = getText(indexRef.childNodes) if indexRef else None
            if attrName == "shared" and indexName is not None:
                if theFormula:
                    # The first cell of a shared formula holds its text
                    sharedFormulas[indexName] = (ref, theFormula)
                elif indexName in sharedFormulas:
                    # The other cells use it with moved relative references
                    masterRef, masterFormula = sharedFormulas[indexName]
                    masterCol, masterRow = splitCellRef(masterRef)
                    col, row = splitCellRef(ref)
                    theFormula = shiftFormula(masterFormula, row - masterRow, col - masterCol)
            if theFormula:
                # print("theFormula: ", theFormula)
                fTrans = FormulaTranslator()
                actCellSheet.set(ref, fTrans.translateForm(theFormula))
            else:
                content = "<f t='{}' si='{}'/>".format(attrName, indexName)
                print(f"Unsupported formula in cell {ref}: {content}")

        else:
            valueRef = cell.getElementsByTagName("v")
            # print('valueRef: ', valueRef)
            if len(valueRef) == 1:
                valueRef = cell.getElementsByTagName("v")[0]
                if valueRef:
                    theValue = getText(valueRef.childNodes)
                    # print("theValue: ", theValue)
                    if cellType == "n":
                        actCellSheet.set(ref, theValue)
                    if cellType == "s":
                        actCellSheet.set(ref, (sList[int(theValue)]))


def handleWorkBookRels(theBookRels):
    theRels = theBookRels.getElementsByTagName("Relationship")
    idTarget = {}
    for rel in theRels:
        relAtts = rel.attributes
        idRef = relAtts.getNamedItem("Id")
        relRef = getText(idRef.childNodes)
        targetRef = relAtts.getNamedItem("Target")
        relTarget = getText(targetRef.childNodes)
        idTarget[relRef] = relTarget
    return idTarget


def handleWorkBook(theBook, theBookRels, sheetDict, Doc):
    theSheets = theBook.getElementsByTagName("sheet")
    theIdTargetMap = handleWorkBookRels(theBookRels)
    # print("theSheets: ", theSheets)
    for sheet in theSheets:
        sheetAtts = sheet.attributes
        nameRef = sheetAtts.getNamedItem("name")
        sheetName = getText(nameRef.childNodes)
        # print("table name: ", sheetName)
        idRef = sheetAtts.getNamedItem("r:id")
        sheetFile = theIdTargetMap[getText(idRef.childNodes)]
        # print("sheetFile: ", sheetFile)
        # add FreeCAD-spreadsheet
        sheetDict[sheetName] = (Doc.addObject("Spreadsheet::Sheet", sheetName), sheetFile)

    theAliases = theBook.getElementsByTagName("definedName")
    for theAlias in theAliases:
        aliAtts = theAlias.attributes
        nameRef = aliAtts.getNamedItem("name")
        aliasName = getText(nameRef.childNodes)
        # print("aliasName: ", aliasName)

        aliasRef = getText(theAlias.childNodes)  # aliasRef can be None
        if aliasRef and "$" in aliasRef:
            refList = aliasRef.split("!$")
            addressList = refList[1].split("$")
            # print("aliasRef: ", aliasRef)
            # print('Sheet Name: ', refList[0])
            # print('Address: ', addressList[0] + addressList[1])
            sheetName = refList[0]
            if len(sheetName) > 1 and sheetName[0] == "'" and sheetName[-1] == "'":
                # Quoted sheet name, like '2024' or 'My sheet'
                sheetName = sheetName[1:-1].replace("''", "'")
            actSheet, sheetFile = sheetDict[sheetName]
            actSheet.setAlias(addressList[0] + addressList[1], aliasName)


def handleStrings(theStr, sList):
    # One string per <si>, which holds one <t> or several formatted runs
    for item in theStr.getElementsByTagName("si"):
        sList.append(stringItemText(item))


def open(nameXLSX):

    if len(nameXLSX) > 0:
        z = zipfile.ZipFile(nameXLSX)

        theDoc = App.newDocument()

        sheetDict = dict()
        stringList = []

        theBookFile = z.open("xl/workbook.xml")
        theBook = xml.dom.minidom.parse(theBookFile)
        theBookRelsFile = z.open("xl/_rels/workbook.xml.rels")
        theBookRels = xml.dom.minidom.parse(theBookRelsFile)
        handleWorkBook(theBook, theBookRels, sheetDict, theDoc)
        theBook.unlink()
        theBookRels.unlink()

        if "xl/sharedStrings.xml" in z.namelist():
            theStringFile = z.open("xl/sharedStrings.xml")
            theStrings = xml.dom.minidom.parse(theStringFile)
            handleStrings(theStrings, stringList)
            theStrings.unlink()

        cellFormats = readCellFormats(z)

        for sheetSpec in sheetDict:
            # print("sheetSpec: ", sheetSpec)
            theSheet, sheetFile = sheetDict[sheetSpec]
            f = z.open("xl/" + sheetFile)
            myDom = xml.dom.minidom.parse(f)

            handleWorkSheet(myDom, theSheet, stringList, cellFormats)
            myDom.unlink()

        z.close()
        # This is needed more than once, otherwise some references are not calculated!
        theDoc.recompute()
        theDoc.recompute()
        theDoc.recompute()
        return theDoc


def insert(nameXLSX, docname):
    try:
        theDoc = App.getDocument(docname)
    except NameError:
        theDoc = App.newDocument(docname)
    App.ActiveDocument = theDoc

    sheetDict = dict()
    stringList = []

    z = zipfile.ZipFile(nameXLSX)
    theBookFile = z.open("xl/workbook.xml")
    theBook = xml.dom.minidom.parse(theBookFile)
    theBookRelsFile = z.open("xl/_rels/workbook.xml.rels")
    theBookRels = xml.dom.minidom.parse(theBookRelsFile)
    handleWorkBook(theBook, theBookRels, sheetDict, theDoc)
    theBook.unlink()
    theBookRels.unlink()

    if "xl/sharedStrings.xml" in z.namelist():
        theStringFile = z.open("xl/sharedStrings.xml")
        theStrings = xml.dom.minidom.parse(theStringFile)
        handleStrings(theStrings, stringList)
        theStrings.unlink()

    cellFormats = readCellFormats(z)

    for sheetSpec in sheetDict:
        # print("sheetSpec: ", sheetSpec)
        theSheet, sheetFile = sheetDict[sheetSpec]
        f = z.open("xl/" + sheetFile)
        myDom = xml.dom.minidom.parse(f)

        handleWorkSheet(myDom, theSheet, stringList, cellFormats)
        myDom.unlink()

    z.close()
    # This is needed more than once, otherwise some references are not calculated!
    theDoc.recompute()
    theDoc.recompute()
    theDoc.recompute()


# ---------------------------------------------------------------------------
# XLSX export
#
# Writes one worksheet per spreadsheet with the computed values, the formulas
# that Excel computes the same way, aliases (as defined names), bold, italic,
# underline, colors, alignment, per-cell decimals, column widths, custom row
# heights and merged cells. Kept simple on purpose:
# - quantities with a unit are written as text with their unit ("10 mm"),
#   dimensionless ones as numbers;
# - a formula is written only if it uses cell references, ranges, aliases of
#   the same sheet, numbers, + - * / and the functions of exportFunctions, and
#   every cell it refers to holds a plain number; otherwise only its value is
#   written. Excel recomputes the formulas when it opens the file.
# ---------------------------------------------------------------------------

import math
from xml.sax.saxutils import escape as _xmlEscape, quoteattr as _xmlQuote

# FreeCAD function -> Excel function (same arguments and results)
exportFunctions = {
    "abs": "ABS",
    "sqrt": "SQRT",
    "exp": "EXP",
    "sum": "SUM",
    "min": "MIN",
    "max": "MAX",
    "average": "AVERAGE",
    "count": "COUNT",
    "pow": "POWER",
}

_mainNS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_relNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_pkgRelNS = "http://schemas.openxmlformats.org/package/2006/relationships"
_xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

_formulaToken = re.compile(
    r"\s+|(?P<ref>\$?[A-Z]{1,3}\$?[0-9]+)(?![A-Za-z0-9_(])"
    r"|(?P<num>[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?)(?![A-Za-z_])"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    # No '^': FreeCAD and Excel do not give it the same precedence and associativity
    r"|(?P<op>[-+*/(),:;])"
)


def _xmlText(text):
    """Escapes text for XML, dropping the characters XML cannot hold."""
    text = "".join(ch for ch in str(text) if ch in "\t\n\r" or ord(ch) >= 0x20)
    return _xmlEscape(text)


def _cellNumbers(ref):
    """(column, row), 1-based, of a reference like "$B$3"."""
    return splitCellRef(ref.replace("$", ""))


def _isPlainNumber(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, App.Units.Quantity):
        return value.Unit == App.Units.Unit()
    return False


def _cellValue(sheet, address):
    try:
        return sheet.get(address)
    except Exception:
        return None


def _excelFormula(sheet, expression, aliases):
    """The Excel formula of a FreeCAD expression (without '='), or None if Excel
    would not compute it the same way."""
    tokens = list(_formulaToken.finditer(expression))
    if not tokens or sum(len(m.group(0)) for m in tokens) != len(expression):
        return None  # characters no token accepts: units, strings, comparisons, ...
    out = []
    for index, match in enumerate(tokens):
        text = match.group(0)
        if text.isspace():
            continue
        if match.group("ref") or match.group("num"):
            out.append(text)
        elif match.group("name"):
            following = next((t.group(0) for t in tokens[index + 1 :] if not t.group(0).isspace()), "")
            if following == "(" and text in exportFunctions:
                out.append(exportFunctions[text])
            elif following != "(" and text in aliases:
                out.append(text)
            else:
                return None  # units, other objects, functions Excel computes differently
        else:
            out.append("," if text == ";" else text)
    formula = "".join(out)

    # Every referenced cell must hold a plain number (or be empty)
    for cells in _rangesOf(formula, aliases):
        if cells is None:
            return None
        for address in cells:
            value = _cellValue(sheet, address)
            if value is None or _isPlainNumber(value):
                continue
            if isinstance(value, str) and value == "":
                continue
            return None
    return formula


def _rangesOf(formula, aliases):
    """The cells referenced by an exported formula, as lists of addresses."""
    names = "|".join(re.escape(name) for name in aliases)
    refPattern = r"\$?[A-Z]{1,3}\$?[0-9]+"
    if names:
        refPattern = r"(?:%s|(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_(]))" % (refPattern, names)
    pattern = re.compile(r"(%s)(?::(%s))?" % (refPattern, refPattern))
    for match in pattern.finditer(formula):
        first = aliases.get(match.group(1), match.group(1))
        last = aliases.get(match.group(2), match.group(2)) if match.group(2) else first
        col1, row1 = _cellNumbers(first)
        col2, row2 = _cellNumbers(last)
        if (abs(col2 - col1) + 1) * (abs(row2 - row1) + 1) > 100000:
            yield None  # too large to check
            continue
        yield [
            columnName(c) + str(r)
            for r in range(min(row1, row2), max(row1, row2) + 1)
            for c in range(min(col1, col2), max(col1, col2) + 1)
        ]


def _hexColor(color):
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in color[:3])
    return "FF%02X%02X%02X" % (r, g, b)


class _Styles:
    """Collects the cell formats into the font, fill, number format and cellXfs
    tables of xl/styles.xml."""

    def __init__(self):
        self.fonts = [""]  # the default font
        self.fills = ['<patternFill patternType="none"/>', '<patternFill patternType="gray125"/>']
        self.numFmts = []
        self.xfs = [None]  # the default format
        self.index = {}

    def _add(self, table, item):
        if item not in table:
            table.append(item)
        return table.index(item)

    def cellStyle(self, sheet, address):
        style = sheet.getStyle(address) or set()
        foreground = sheet.getForeground(address)
        background = sheet.getBackground(address)
        alignment = sheet.getAlignment(address) or set()
        decimals = sheet.getDecimals(address) if hasattr(sheet, "getDecimals") else None

        font = ""
        if "bold" in style:
            font += "<b/>"
        if "italic" in style:
            font += "<i/>"
        if "underline" in style:
            font += "<u/>"
        if foreground:
            font += '<color rgb="%s"/>' % _hexColor(foreground)
        fill = None
        if background:
            fill = (
                '<patternFill patternType="solid"><fgColor rgb="%s"/>'
                '<bgColor indexed="64"/></patternFill>' % _hexColor(background)
            )
        horizontal = next((a for a in ("left", "center", "right") if a in alignment), None)
        vertical = {"top": "top", "vcenter": "center", "bottom": "bottom"}
        vertical = next((vertical[a] for a in ("top", "vcenter", "bottom") if a in alignment), None)
        if "himplied" in alignment:
            horizontal = None
        if "vimplied" in alignment:
            vertical = None

        key = (font, fill, horizontal, vertical, decimals)
        if key == ("", None, None, None, None):
            return 0
        if key in self.index:
            return self.index[key]

        fontId = self._add(self.fonts, font)
        fillId = self._add(self.fills, fill) if fill else 0
        numFmtId = 0
        if decimals is not None:
            code = "0." + "0" * decimals if decimals > 0 else "0"
            numFmtId = 164 + self._add(self.numFmts, code)
        align = ""
        if horizontal or vertical:
            align = "<alignment%s%s/>" % (
                ' horizontal="%s"' % horizontal if horizontal else "",
                ' vertical="%s"' % vertical if vertical else "",
            )
        xf = '<xf numFmtId="%d" fontId="%d" fillId="%d" borderId="0" xfId="0"%s%s%s%s>%s</xf>' % (
            numFmtId,
            fontId,
            fillId,
            ' applyNumberFormat="1"' if numFmtId else "",
            ' applyFont="1"' if fontId else "",
            ' applyFill="1"' if fillId else "",
            ' applyAlignment="1"' if align else "",
            align,
        )
        self.xfs.append(xf)
        self.index[key] = len(self.xfs) - 1
        return self.index[key]

    def xml(self):
        parts = [_xmlHeader, '<styleSheet xmlns="%s">' % _mainNS]
        if self.numFmts:
            parts.append('<numFmts count="%d">' % len(self.numFmts))
            for i, code in enumerate(self.numFmts):
                parts.append('<numFmt numFmtId="%d" formatCode=%s/>' % (164 + i, _xmlQuote(code)))
            parts.append("</numFmts>")
        parts.append('<fonts count="%d">' % len(self.fonts))
        for font in self.fonts:
            parts.append('<font>%s<sz val="11"/><name val="Calibri"/><family val="2"/></font>' % font)
        parts.append('</fonts><fills count="%d">' % len(self.fills))
        for fill in self.fills:
            parts.append("<fill>%s</fill>" % fill)
        parts.append(
            '</fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '</borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
            '</cellStyleXfs><cellXfs count="%d">' % len(self.xfs)
        )
        for xf in self.xfs:
            parts.append(xf or '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>')
        parts.append(
            '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
            "</cellStyles></styleSheet>"
        )
        return "".join(parts)


def _isExcelReference(name):
    """True if Excel reads the name as a cell reference, in A1 or R1C1 style."""
    return bool(
        re.match(r"^[A-Za-z]{1,3}[0-9]+$", name) or re.match(r"^[Rr]?[0-9]*[Cc]?[0-9]*$", name)
    )


def _sheetReference(name):
    """The worksheet name as written in a formula: quoted when Excel would not
    read it as a name (it starts with a digit or looks like a cell reference)."""
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) and not _isExcelReference(name):
        return name
    return "'%s'" % name.replace("'", "''")


def _excelAliases(sheet, used):
    """{alias: address} of the aliases that are valid Excel names (not like a
    cell reference, unique without case)."""
    aliases = {}
    lower = {}
    for address in used:
        alias = sheet.getAlias(address)
        if not alias or _isExcelReference(alias):
            continue
        aliases[alias] = address
        lower.setdefault(alias.lower(), []).append(alias)
    for names in lower.values():
        if len(names) > 1:
            for name in names:
                del aliases[name]
    return aliases


def _worksheetXml(sheet, styles):
    used = sheet.getUsedCells()
    aliases = _excelAliases(sheet, used)

    cells = {}
    for address in used:
        col, row = _cellNumbers(address)
        cells.setdefault(row, []).append((col, address))

    lastCol = max([col for row in cells.values() for col, _ in row] or [0])
    # Only the sizes set in FreeCAD: the others are the default of each application
    widths = sheet.getColumnWidths()
    heights = sheet.getRowHeights()

    parts = [_xmlHeader, '<worksheet xmlns="%s" xmlns:r="%s">' % (_mainNS, _relNS)]
    cols = []
    for col in range(1, lastCol + 1):
        width = widths.get(columnName(col))
        if width is not None:
            cols.append(
                '<col min="%d" max="%d" width="%s" customWidth="1"/>' % (col, col, repr(width / 7.0))
            )
    if cols:
        parts.append("<cols>%s</cols>" % "".join(cols))

    parts.append("<sheetData>")
    for row in sorted(cells):
        height = heights.get(str(row))
        rowAttrs = ' r="%d"' % row
        if height is not None:
            rowAttrs += ' ht="%s" customHeight="1"' % repr(height * 72.0 / 96.0)
        parts.append("<row%s>" % rowAttrs)
        for col, address in sorted(cells[row]):
            parts.append(_cellXml(sheet, address, styles.cellStyle(sheet, address), aliases))
        parts.append("</row>")
    parts.append("</sheetData>")

    merged = sheet.getMergedCells()
    if merged:
        parts.append('<mergeCells count="%d">' % len(merged))
        for ref in merged:
            parts.append('<mergeCell ref="%s"/>' % ref)
        parts.append("</mergeCells>")
    parts.append("</worksheet>")
    return "".join(parts), aliases


def _cellXml(sheet, address, style, aliases):
    attrs = ' r="%s"' % address
    if style:
        attrs += ' s="%d"' % style
    content = sheet.getContents(address)
    if not content:
        return "<c%s/>" % attrs
    value = _cellValue(sheet, address)

    formula = None
    if content.startswith("="):
        formula = _excelFormula(sheet, content[1:], aliases)
    formulaXml = "<f>%s</f>" % _xmlText(formula) if formula else ""

    if _isPlainNumber(value):
        number = float(value.Value if isinstance(value, App.Units.Quantity) else value)
        if math.isfinite(number):
            return "<c%s>%s<v>%s</v></c>" % (attrs, formulaXml, repr(number))
    if value is None:
        text = content  # not computed (error): keep what was typed
    elif isinstance(value, App.Units.Quantity):
        text = _quantityText(value)
    else:
        text = str(value)
    if formula:
        return '<c%s t="str">%s<v>%s</v></c>' % (attrs, formulaXml, _xmlText(text))
    return '<c%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (attrs, _xmlText(text))


def _quantityText(quantity):
    """A quantity as text in the user's preferred unit, at full precision and
    with a '.' decimal point whatever the locale ("0.3333333333333333 mm"), so
    that it reads back as the same quantity; UserString is rounded to the
    decimals of the preferences and uses the locale's separator."""
    try:
        _, factor, unit = quantity.getUserPreferred()
        if factor and unit:
            return "%s %s" % (repr(quantity.Value / factor), unit)
    except Exception:
        pass
    return quantity.UserString


def _sheetName(label, taken):
    name = re.sub(r"[^A-Za-z0-9_]", "_", label)[:31] or "Sheet"
    candidate = name
    number = 1
    while candidate.lower() in taken:
        number += 1
        suffix = "_%d" % number
        candidate = name[: 31 - len(suffix)] + suffix
    taken.add(candidate.lower())
    return candidate


def exportSheets(sheets, filename):
    """Writes the spreadsheets to an XLSX file, one worksheet each."""
    styles = _Styles()
    worksheets = []
    taken = set()
    definedNames = []
    for sheet in sheets:
        name = _sheetName(sheet.Label, taken)
        sheetXml, aliases = _worksheetXml(sheet, styles)
        # Aliases belong to their sheet: sheet-scoped names, so that sheets
        # may use the same alias (workbook names must be unique)
        for alias, address in sorted(aliases.items()):
            col, row = _cellNumbers(address)
            definedNames.append(
                '<definedName name=%s localSheetId="%d">%s!$%s$%d</definedName>'
                % (_xmlQuote(alias), len(worksheets), _sheetReference(name), columnName(col), row)
            )
        worksheets.append((name, sheetXml))

    contentTypes = [
        _xmlHeader,
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbookRels = [_xmlHeader, '<Relationships xmlns="%s">' % _pkgRelNS]
    workbook = [
        _xmlHeader,
        '<workbook xmlns="%s" xmlns:r="%s"><sheets>' % (_mainNS, _relNS),
    ]
    for i, (name, _) in enumerate(worksheets, start=1):
        contentTypes.append(
            '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i
        )
        workbookRels.append(
            '<Relationship Id="rId%d" Type="%s/worksheet" Target="worksheets/sheet%d.xml"/>'
            % (i, _relNS, i)
        )
        workbook.append('<sheet name=%s sheetId="%d" r:id="rId%d"/>' % (_xmlQuote(name), i, i))
    contentTypes.append("</Types>")
    workbookRels.append(
        '<Relationship Id="rId%d" Type="%s/styles" Target="styles.xml"/></Relationships>'
        % (len(worksheets) + 1, _relNS)
    )
    workbook.append("</sheets>")
    if definedNames:
        workbook.append("<definedNames>%s</definedNames>" % "".join(definedNames))
    # Excel recomputes the formulas when it opens the file
    workbook.append('<calcPr fullCalcOnLoad="1"/></workbook>')

    rootRels = (
        _xmlHeader + '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>' % (_pkgRelNS, _relNS)
    )

    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(contentTypes))
        z.writestr("_rels/.rels", rootRels)
        z.writestr("xl/workbook.xml", "".join(workbook))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(workbookRels))
        z.writestr("xl/styles.xml", styles.xml())
        for i, (_, sheetXml) in enumerate(worksheets, start=1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, sheetXml)


def export(exportList, filename):
    """Exports the spreadsheets among the given objects to an XLSX file."""
    sheets = [obj for obj in exportList if obj.isDerivedFrom("Spreadsheet::Sheet")]
    if not sheets:
        App.Console.PrintError("XLSX export: select one or more spreadsheets\n")
        return
    exportSheets(sheets, filename)
