/****************************************************************************
 *   Copyright (c) 2024 Ondsel <development@ondsel.com>                     *
 *                                                                          *
 *   This file is part of the FreeCAD CAx development system.               *
 *                                                                          *
 *   This library is free software; you can redistribute it and/or          *
 *   modify it under the terms of the GNU Library General Public            *
 *   License as published by the Free Software Foundation; either           *
 *   version 2 of the License, or (at your option) any later version.       *
 *                                                                          *
 *   This library  is distributed in the hope that it will be useful,       *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of         *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          *
 *   GNU Library General Public License for more details.                   *
 *                                                                          *
 *   You should have received a copy of the GNU Library General Public      *
 *   License along with this library; see the file COPYING.LIB. If not,     *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,          *
 *   Suite 330, Boston, MA  02111-1307, USA                                 *
 *                                                                          *
 ****************************************************************************/


#include <memory>


#include <App/Document.h>
#include <App/UserParameters.h>
#include <App/VarSet.h>

#include "Application.h"
#include "Document.h"
#include "MainWindow.h"
#include "ViewProviderVarSet.h"

using namespace Gui;
using namespace Gui::Dialog;

PROPERTY_SOURCE(Gui::ViewProviderVarSet, Gui::ViewProviderDocumentObject)

ViewProviderVarSet::ViewProviderVarSet()
{
    setToggleVisibility(ToggleVisibilityMode::NoToggleVisibility);
    sPixmap = "VarSet";
}

bool ViewProviderVarSet::doubleClicked()
{
    if (!dialog) {
        dialog = std::make_unique<DlgAddProperty>(getMainWindow(), this);
    }

    // Do not use exec() here because it blocks and prevents command Std_VarSet
    // to commit the autotransaction.  This in turn prevents the dialog to
    // handle transactions well.
    dialog->setWindowModality(Qt::ApplicationModal);
    dialog->show();
    dialog->raise();
    dialog->activateWindow();

    return true;
}

void ViewProviderVarSet::onFinished(int /*result*/)
{
    dialog = nullptr;
}

// The object holding the user parameters of a document (App::UserParameters::holder()) is created
// on demand, when the user types `name = value` in an input: it is not shown in the tree unless
// the user asks for it (ShowInTree, "Toggle Visibility in Tree View" in the tree). It is hidden
// once, when the GUI first knows it; from then on ShowInTree is the choice of the user, which is
// saved with the document.

void ViewProviderVarSet::attach(App::DocumentObject* obj)
{
    ViewProviderDocumentObject::attach(obj);

    if (!App::UserParameters::isHolder(obj)) {
        return;
    }
    // Only a holder that is created now: one that is loaded, pasted or brought back by undo or
    // redo gets its saved view properties, see finishRestoring().
    const App::Document* doc = obj->getDocument();
    if (!doc || doc->testStatus(App::Document::Restoring) || doc->isPerformingTransaction()) {
        return;
    }
    // Not a view provider that is attached without being the one of the document
    // (Gui.subgraphFromObject()).
    const Gui::Document* guiDoc = Application::Instance->getDocument(doc);
    if (guiDoc && guiDoc->getViewProvider(obj) == this) {
        ShowInTree.setValue(false);
    }
}

void ViewProviderVarSet::Restore(Base::XMLReader& reader)
{
    viewPropertiesRestored = true;
    ViewProviderDocumentObject::Restore(reader);
}

void ViewProviderVarSet::finishRestoring()
{
    ViewProviderDocumentObject::finishRestoring();

    // A document saved without the GUI has no view properties: its holder is new to the GUI.
    if (!viewPropertiesRestored && App::UserParameters::isHolder(getObject())) {
        ShowInTree.setValue(false);
    }
    viewPropertiesRestored = false;
}
