// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2022 Abdullah Tahiri <abdullah.tahiri.yo@gmail.com>     *
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

#include <string>

#include <App/Datums.h>
#include <Mod/Part/App/DatumFeature.h>

#include <Gui/Application.h>
#include <Gui/Document.h>
#include <Gui/Notifications.h>
#include <Gui/ViewProviderDocumentObject.h>
#include <Gui/Selection/SelectionFilter.h>
#include <Gui/Command.h>
#include <Gui/CommandT.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>
#include <Gui/MDIView.h>

#include <Mod/Sketcher/App/SketchObject.h>

#include "DrawSketchHandler.h"
#include "Utils.h"
#include "ViewProviderSketch.h"
#include <Mod/Part/App/Datums.h>
#include "SnapManager.h"


namespace SketcherGui
{

// Top-down design (#17951): while a sketch is edited in place inside a parent tree (e.g. an
// assembly), the other components can be referenced through that tree, see
// SketchObject::addExternalInContext(). Returns the root of the tree and the path of the
// sketch in it.
inline bool getInPlaceEditContext(
    Sketcher::SketchObject* sketch,
    App::DocumentObject*& root,
    std::string& sketchPath
)
{
    root = nullptr;
    auto editDoc = Gui::Application::Instance->editDocument();
    if (!editDoc) {
        return false;
    }
    Gui::ViewProviderDocumentObject* parentVp = nullptr;
    editDoc->getInEdit(&parentVp, &sketchPath);
    if (!parentVp || !parentVp->getObject() || parentVp->getObject() == sketch
        || sketchPath.size() < 2 || sketchPath.back() != '.'
        || parentVp->getObject()->getSubObject(sketchPath.c_str()) != sketch) {
        return false;  // not edited in place inside a parent tree
    }
    root = parentVp->getObject();
    return true;
}

// Elements of other bodies, parts or documents that addExternalInContext() may reference
inline bool isContextReason(Sketcher::SketchObject::eReasonList reason)
{
    return reason == Sketcher::SketchObject::rlOtherDoc
        || reason == Sketcher::SketchObject::rlOtherPart
        || reason == Sketcher::SketchObject::rlOtherBody;
}

inline bool isExternalElement(const char* sSubName)
{
    if (Base::Tools::isNullOrEmpty(sSubName)) {
        return false;
    }
    std::string element(sSubName);
    return (element.size() > 4 && element.substr(0, 4) == "Edge")
        || (element.size() > 6 && element.substr(0, 6) == "Vertex")
        || (element.size() > 4 && element.substr(0, 4) == "Face");
}

class ExternalSelection: public Gui::SelectionFilterGate
{
    App::DocumentObject* object;

public:
    explicit ExternalSelection(App::DocumentObject* obj)
        : Gui::SelectionFilterGate(nullPointer())
        , object(obj)
    {}

    bool allow(App::Document* pDoc, App::DocumentObject* pObj, const char* sSubName) override
    {
        Sketcher::SketchObject* sketch = static_cast<Sketcher::SketchObject*>(object);

        this->notAllowedReason = "";
        Sketcher::SketchObject::eReasonList msg;
        if (!sketch->isExternalAllowed(pDoc, pObj, &msg)) {
            App::DocumentObject* root = nullptr;
            std::string sketchPath;
            if (isContextReason(msg) && isExternalElement(sSubName)
                && getInPlaceEditContext(sketch, root, sketchPath)) {
                // referenced through the edit root, see addExternalInContext()
                return true;
            }
            switch (msg) {
                case Sketcher::SketchObject::rlCircularReference:
                    this->notAllowedReason = QT_TR_NOOP("Linking this will cause circular dependency.");
                    break;
                case Sketcher::SketchObject::rlOtherDoc:
                    this->notAllowedReason = QT_TR_NOOP("This object is in another document.");
                    break;
                case Sketcher::SketchObject::rlOtherBody:
                    this->notAllowedReason = QT_TR_NOOP(
                        "This object belongs to another body, can't link."
                    );
                    break;
                case Sketcher::SketchObject::rlOtherPart:
                    this->notAllowedReason = QT_TR_NOOP(
                        "This object belongs to another part, can't link."
                    );
                    break;
                default:
                    break;
            }
            return false;
        }

        // Note: its better to search the support of the sketch in case the sketch support is a base
        // plane
        // Part::BodyBase* body = Part::BodyBase::findBodyOf(sketch);
        // if ( body && body->hasFeature ( pObj ) && body->isAfter ( pObj, sketch ) ) {
        // Don't allow selection after the sketch in the same body
        // NOTE: allowness of features in other bodies is handled by
        // SketchObject::isExternalAllowed()
        // TODO may be this should be in SketchObject::isExternalAllowed() (2015-08-07, Fat-Zer)
        // return false;
        //}

        if (pObj->isDerivedFrom<Part::DatumLine>() || pObj->isDerivedFrom<Part::DatumPoint>()
            || pObj->isDerivedFrom<App::Line>() || pObj->isDerivedFrom<App::Point>()) {
            return true;
        }

        if (pObj->isDerivedFrom<App::Plane>() || pObj->isDerivedFrom<Part::Datum>()) {
            return true;
        }

        if (Base::Tools::isNullOrEmpty(sSubName)) {
            return false;
        }

        std::string element(sSubName);
        if ((element.size() > 4 && element.substr(0, 4) == "Edge")
            || (element.size() > 6 && element.substr(0, 6) == "Vertex")
            || (element.size() > 4 && element.substr(0, 4) == "Face")) {
            return true;
        }

        return false;
    }
};

class DrawSketchHandlerExternal: public DrawSketchHandler
{
    Q_DECLARE_TR_FUNCTIONS(SketcherGui::DrawSketchHandlerExternal)

public:
    DrawSketchHandlerExternal(bool alwaysReference, bool intersection)
        : alwaysReference {alwaysReference}
        , intersection {intersection}
    {}
    ~DrawSketchHandlerExternal() override
    {
        Gui::Selection().rmvSelectionGate();
    }

    void mouseMove(SnapManager::SnapHandle snapHandle) override
    {
        Q_UNUSED(snapHandle);
        if (Gui::Selection().getPreselection().pObjectName) {
            applyCursor();
        }
    }

    bool pressButton(Base::Vector2d onSketchPos) override
    {
        Q_UNUSED(onSketchPos);
        return true;
    }

    bool releaseButton(Base::Vector2d onSketchPos) override
    {
        Q_UNUSED(onSketchPos);
        /* this is ok not to call to purgeHandler
         * in continuous creation mode because the
         * handler is destroyed by the quit() method on pressing the
         * right button of the mouse */
        return true;
    }

    bool acceptsOtherDocumentSelection() const override
    {
        return true;  // components of an assembly the sketch is edited in, see addInContext()
    }

    bool onSelectionChanged(const Gui::SelectionChanges& msg) override
    {
        if (msg.Type == Gui::SelectionChanges::AddSelection) {
            if (addInContext(msg)) {
                return true;
            }
            if (App::GetApplication().getDocument(msg.pDocName)
                != sketchgui->getObject()->getDocument()) {
                return false;  // only referenced through addInContext()
            }
            App::DocumentObject* obj = sketchgui->getObject()->getDocument()->getObject(
                msg.pObjectName
            );
            if (!obj) {
                throw Base::ValueError("Sketcher: External geometry: Invalid object in selection");
            }
            std::string subName(msg.pSubName);

            if (obj->isDerivedFrom<App::Plane>() || obj->isDerivedFrom<Part::Datum>()
                || obj->isDerivedFrom<Part::DatumLine>() || obj->isDerivedFrom<Part::DatumPoint>()
                || obj->isDerivedFrom<App::Line>() || obj->isDerivedFrom<App::Point>()
                || (subName.size() > 4 && subName.substr(0, 4) == "Edge")
                || (subName.size() > 6 && subName.substr(0, 6) == "Vertex")
                || (subName.size() > 4 && subName.substr(0, 4) == "Face")) {
                try {
                    openCommand(QT_TRANSLATE_NOOP("Command", "Add external geometry"));
                    Gui::cmdAppObjectArgs(
                        sketchgui->getObject(),
                        "addExternal(\"%s\",\"%s\", %s, %s)",
                        msg.pObjectName,
                        msg.pSubName,
                        alwaysReference || isConstructionMode() ? "False" : "True",
                        intersection ? "True" : "False"
                    );

                    commitCommand();

                    // adding external geometry does not require a solve() per se (the DoF is the
                    // same), however a solve is required to update the amount of solver geometry,
                    // because we only redraw a changed Sketch if the solver geometry amount is the
                    // same as the SkethObject geometry amount (as this avoids other issues). This
                    // solver is a very low cost one anyway (there is actually nothing to solve).
                    tryAutoRecomputeIfNotSolve(sketchgui->getObject<Sketcher::SketchObject>());

                    Gui::Selection().clearSelection();
                    /* this is ok not to call to purgeHandler
                     * in continuous creation mode because the
                     * handler is destroyed by the quit() method on pressing the
                     * right button of the mouse */
                }
                catch (const Base::Exception&) {
                    Gui::NotifyError(
                        sketchgui,
                        QT_TRANSLATE_NOOP("Notifications", "Error"),
                        QT_TRANSLATE_NOOP("Notifications", "Failed to add external geometry")
                    );
                    Gui::Selection().clearSelection();
                    abortCommand();
                }
                return true;
            }
        }
        updateHint();

        return false;
    }

private:
    // Handles a pick of another component while the sketch is edited in place (#17951): the
    // element is referenced through the edit root, see SketchObject::addExternalInContext().
    // Returns false if the selection is not such a pick.
    bool addInContext(const Gui::SelectionChanges& msg)
    {
        auto sketch = sketchgui->getObject<Sketcher::SketchObject>();
        App::Document* pickDoc = App::GetApplication().getDocument(msg.pDocName);
        App::DocumentObject* picked = pickDoc ? pickDoc->getObject(msg.pObjectName) : nullptr;
        Sketcher::SketchObject::eReasonList reason = Sketcher::SketchObject::rlAllowed;
        if (!picked || sketch->isExternalAllowed(picked->getDocument(), picked, &reason)
            || !isContextReason(reason) || !isExternalElement(msg.pSubName)) {
            return false;
        }
        App::DocumentObject* root = nullptr;
        std::string sketchPath;
        if (!msg.pOriginalMsg || !getInPlaceEditContext(sketch, root, sketchPath)) {
            return false;
        }

        auto fail = [this](const char* text) {
            Gui::NotifyError(sketchgui, QT_TRANSLATE_NOOP("Notifications", "Error"), text);
            Gui::Selection().clearSelection();
        };

        // The pick must lie in the tree the sketch is edited from
        const Gui::SelectionChanges& original = *msg.pOriginalMsg;
        App::Document* rootDoc = App::GetApplication().getDocument(original.pDocName);
        if (!rootDoc || rootDoc->getObject(original.pObjectName) != root
            || Base::Tools::isNullOrEmpty(original.pSubName)) {
            fail(QT_TRANSLATE_NOOP(
                "Notifications",
                "This object is not part of the tree the sketch is edited in."
            ));
            return true;
        }

        try {
            openCommand(QT_TRANSLATE_NOOP("Command", "Add external geometry"));
            Gui::cmdAppObjectArgs(
                sketch,
                "addExternalInContext(%s, '%s', '%s', %s, %s)",
                Gui::Command::getObjectCmd(root).c_str(),
                sketchPath.c_str(),
                original.pSubName,
                alwaysReference || isConstructionMode() ? "False" : "True",
                intersection ? "True" : "False"
            );
            commitCommand();
            tryAutoRecomputeIfNotSolve(sketch);
            Gui::Selection().clearSelection();
        }
        catch (const Base::Exception&) {
            abortCommand();
            fail(QT_TRANSLATE_NOOP("Notifications", "Failed to add external geometry"));
        }
        return true;
    }

    void activated() override
    {
        setAxisPickStyle(false);
        Gui::MDIView* mdi = Gui::Application::Instance->activeDocument()->getActiveView();
        Gui::View3DInventorViewer* viewer;
        viewer = static_cast<Gui::View3DInventor*>(mdi)->getViewer();
        viewer->setSelectionEnabled(true);

        Gui::Selection().clearSelection();
        Gui::Selection().rmvSelectionGate();
        Gui::Selection().addSelectionGate(new ExternalSelection(sketchgui->getObject()));
    }

    QString getCrosshairCursorSVGName() const override
    {
        if (intersection) {
            return QStringLiteral("Sketcher_Pointer_External_Intersection");
        }

        return QStringLiteral("Sketcher_Pointer_External");
    }

    void deactivated() override
    {
        Q_UNUSED(sketchgui);
        setAxisPickStyle(true);
    }

    bool alwaysReference;
    bool intersection;

public:
    std::list<Gui::InputHint> getToolHints() const override
    {
        return {
            {tr("%1 pick external geometry", "Sketcher External: hint"),
             {Gui::InputHint::UserInput::MouseLeft}},
        };
    }
};

}  // namespace SketcherGui
