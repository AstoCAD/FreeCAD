/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *   This file is part of FreeCAD.                                         *
 ***************************************************************************/

#include "ViewProviderBrokenOutSection.h"

#include <QMessageBox>

#include <Gui/Application.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/MainWindow.h>
#include <Gui/Selection/Selection.h>
#include <Mod/TechDraw/App/DrawPage.h>
#include <Mod/TechDraw/App/DrawViewBrokenOutSection.h>
#include <Mod/TechDraw/App/DrawViewPart.h>

#include "QGVPage.h"
#include "TaskBrokenOutSection.h"
#include "ViewProviderPage.h"

using namespace TechDrawGui;

PROPERTY_SOURCE(TechDrawGui::ViewProviderBrokenOutSection, Gui::ViewProviderDocumentObject)

ViewProviderBrokenOutSection::ViewProviderBrokenOutSection()
{
    sPixmap = "actions/TechDraw_BrokenOutSectionView";
    Gui::ViewProviderSuppressibleExtension::initExtension(this);
}

bool ViewProviderBrokenOutSection::setEdit(int mode)
{
    if (mode != Gui::ViewProvider::Default) {
        return Gui::ViewProviderDocumentObject::setEdit(mode);
    }
    if (Gui::Control().activeDialog()) {
        return false;
    }

    auto* section = dynamic_cast<TechDraw::DrawViewBrokenOutSection*>(getObject());
    TechDraw::DrawViewPart* base = nullptr;
    if (section) {
        for (App::DocumentObject* parent : section->getInList()) {
            base = dynamic_cast<TechDraw::DrawViewPart*>(parent);
            if (base) {
                break;
            }
        }
    }
    TechDraw::DrawPage* page = base ? base->findParentPage() : nullptr;
    Gui::Document* guiDocument = page
        ? Gui::Application::Instance->getDocument(page->getDocument())
        : nullptr;
    auto* pageProvider = guiDocument
        ? dynamic_cast<ViewProviderPage*>(guiDocument->getViewProvider(page))
        : nullptr;
    if (pageProvider) {
        pageProvider->switchToMdiViewPage();
    }
    QGVPage* graphicsView = pageProvider ? pageProvider->getQGVPage() : nullptr;
    if (!section || !base || !graphicsView) {
        QMessageBox::warning(
            Gui::getMainWindow(), QObject::tr("No active drawing page"),
            QObject::tr("The drawing page containing this broken-out section could not be opened."));
        return false;
    }

    Gui::Selection().clearSelection();
    Gui::Control().showDialog(
        new TaskDlgBrokenOutSection(section, base, graphicsView));
    return true;
}

bool ViewProviderBrokenOutSection::doubleClicked()
{
    setEdit(Gui::ViewProvider::Default);
    return true;
}

Gui::MDIView* ViewProviderBrokenOutSection::getMDIView() const
{
    auto* section =
        dynamic_cast<TechDraw::DrawViewBrokenOutSection*>(getObject());
    if (!section) {
        return nullptr;
    }
    TechDraw::DrawViewPart* base = nullptr;
    for (App::DocumentObject* parent : section->getInList()) {
        base = dynamic_cast<TechDraw::DrawViewPart*>(parent);
        if (base) {
            break;
        }
    }
    TechDraw::DrawPage* page = base ? base->findParentPage() : nullptr;
    Gui::Document* guiDocument = page
        ? Gui::Application::Instance->getDocument(page->getDocument())
        : nullptr;
    auto* pageProvider = guiDocument
        ? dynamic_cast<ViewProviderPage*>(guiDocument->getViewProvider(page))
        : nullptr;
    return pageProvider ? pageProvider->getMDIView() : nullptr;
}
