# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2023 Werner Mayer
# SPDX-FileNotice: Part of the FreeCAD project.

__title__="Document handling module"
__author__ = "Werner Mayer"
__url__ = "https://www.freecad.org"
__doc__ = "Tools for extracting or creating project files"


import os
import xml.sax
import xml.sax.handler
import xml.sax.xmlreader
import zipfile

# SAX handler to parse the Document.xml
class DocumentHandler(xml.sax.handler.ContentHandler):
    """ Parse content of Document.xml or GuiDocument.xml """
    def __init__(self, dirname):
        """ Init parser """
        super().__init__()
        self.files = []
        self.dirname = dirname

    def startElement(self, name, attrs):
        item = attrs.get("file")
        if item is not None:
            self.files.append(os.path.join(self.dirname, str(item)))

    def characters(self, content):
        return

    def endElement(self, name):
        return

def _entryName(info):
    """ Name of an archive entry as FreeCAD stores it

    FreeCAD writes the entry names in UTF-8 without setting the UTF-8 flag of
    the zip format, so the zipfile module decodes them as CP437.
    """
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except UnicodeError:
        return info.filename

def extractDocument(filename, outpath):
    """ Extract files from project archive """
    with zipfile.ZipFile(filename) as zfile:
        for info in zfile.infolist():
            i = _entryName(info)
            data = zfile.read(info)
            dirs = i.split("/")
            if len(dirs) > 1:
                dirs.pop()
                curpath = outpath
                for j in dirs:
                    curpath = curpath + "/" + j
                    os.makedirs(curpath, exist_ok=True)
            with open(outpath + "/"+i, 'wb') as output:
                output.write(data)

def createDocument(filename, outpath):
    """ Create project archive """
    files = getFilesList(filename)
    dirname = os.path.dirname(filename)
    guixml = os.path.join(dirname, "GuiDocument.xml")
    if os.path.exists(guixml):
        files.extend(getFilesList(guixml))
    with zipfile.ZipFile(outpath, 'w', zipfile.ZIP_DEFLATED) as compress:
        for file in files:
            if os.path.isfile(file):
                path_in_archive = os.path.relpath(path=file, start=dirname)
                compress.write(file, path_in_archive, zipfile.ZIP_DEFLATED)

def getFilesList(filename):
    """ Determine list of files referenced in a Document.xml or GuiDocument.xml """
    dirname = os.path.dirname(filename)
    handler = DocumentHandler(dirname)
    parser = xml.sax.make_parser()
    parser.setContentHandler(handler)
    parser.parse(filename)

    files = []
    files.append(filename)
    files.extend(iter(handler.files))
    return files
