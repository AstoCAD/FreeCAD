// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *   Copyright (c) 2025 AstoCAD                                             *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it    *
 *   under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the  *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   FreeCAD is distributed in the hope that it will be useful, but        *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
 *   Lesser General Public License for more details.                       *
 *                                                                         *
 *   You should have received a copy of the GNU Lesser General Public      *
 *   License along with FreeCAD. If not, see                               *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 **************************************************************************/

#include "PreCompiled.h"

#ifndef _PreComp_
#endif

#include <App/Document.h>

#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Command.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/FileDialog.h>
#include <Gui/ActiveObjectList.h>
#include <Gui/TaskView/TaskView.h>

#include "TaskNewObject.h"
#include "ui_TaskNewObject.h"

using namespace Gui;

/* TRANSLATOR Gui::TaskNewObject */

TaskBoxNewObject::TaskBoxNewObject(std::string type, QWidget* parent)
    : QWidget(parent)
    , ui(new Ui_TaskNewObject)
    , type(type)
{
    ui->setupUi(this);

    ui->saveFile->onRestore();
    ui->addInNewFile->onRestore();

    // We don't save the file if we are not creating a new file.
    ui->saveFile->setEnabled(ui->addInNewFile->isChecked());
    QObject::connect(ui->addInNewFile, &QCheckBox::toggled, [this](bool checked) {
        ui->saveFile->setEnabled(checked);
    });

    if (type == "App::Part") {
        ui->nameLine->setPlaceholderText(QObject::tr("Part"));
        ui->createBody->onRestore();
    }
    else {
        ui->createBody->hide();
        ui->nameLine->setPlaceholderText(QObject::tr("Assembly"));
    }
}

bool TaskBoxNewObject::accept()
{
    ui->saveFile->onSave();
    ui->addInNewFile->onSave();

    if (type == "App::Part") {
        ui->createBody->onSave();
        Command::openCommand(QT_TRANSLATE_NOOP("Command", "Create new part"));
    }
    else {
        Command::openCommand(QT_TRANSLATE_NOOP("Command", "Create new assembly"));
    }

    std::string name = ui->nameLine->text().toStdString();
    if (name.empty()) {
        name = ui->nameLine->placeholderText().toStdString();
    }

    // Create a new document unless the current doc is empty or useCurrent option used.
    auto doc = App::GetApplication().getActiveDocument();
    if (doc->countObjects() != 0 && ui->addInNewFile->isChecked()) {
        Command::doCommand(Command::Doc, "App.newDocument('%s')", name.c_str());
    }

    Command::doCommand(Command::Doc, "obj = App.ActiveDocument.addObject('%s', '%s')", type.c_str(), name.c_str());
    Command::doCommand(Command::Doc, "obj.Label = '%s'", name.c_str());

    if (type == "App::Part") {
        Command::doCommand(Gui::Command::Gui, "Gui.activeView().setActiveObject('%s', obj)", PARTKEY);

        // Step 3: Optionally create a body
        if (ui->createBody->isChecked()) {
            Command::doCommand(Command::Doc, "body = obj.newObject('PartDesign::Body', 'Body')");
            Command::doCommand(Gui::Command::Gui, "Gui.activeView().setActiveObject('%s', body)", PDBODYKEY);

            // assure the PartDesign workbench
            if (App::GetApplication().GetParameterGroupByPath("User parameter:BaseApp/Preferences/Mod/PartDesign")->GetBool("SwitchToWB", true)) {
                Gui::Command::assureWorkbench("PartDesignWorkbench");
            }
        }
    }
    else {
        Command::doCommand(Gui::Command::Gui, "obj.Type = 'Assembly'");
        Command::doCommand(Gui::Command::Gui, "obj.newObject('Assembly::JointGroup', 'Joints')");
        Command::doCommand(Gui::Command::Gui, "Gui.ActiveDocument.setEdit(obj)");

        // assure the Assembly workbench
        if (App::GetApplication().GetParameterGroupByPath("User parameter:BaseApp/Preferences/Mod/Assembly")->GetBool("SwitchToWB", true)) {
            Gui::Command::assureWorkbench("AssemblyWorkbench");
        }
    }

    if (ui->addInNewFile->isChecked() && ui->saveFile->isChecked()) {
        Command::doCommand(Command::Gui, "Gui.SendMsgToActiveView(\"Save\")");
    }

    Command::commitCommand();

    return true;
}

bool TaskBoxNewObject::reject()
{
    return true;
}

/* TRANSLATOR Gui::TaskNewObject */

TaskNewObject::TaskNewObject(std::string type)
    : widget{ new TaskBoxNewObject(type) }
{
    if (type == "App::Part") {
        widget->setWindowTitle(QObject::tr("Create new part"));
        addTaskBox(Gui::BitmapFactory().pixmap("Geofeaturegroup"), widget);
    }
    else {
        widget->setWindowTitle(QObject::tr("Create new assembly"));
        addTaskBox(Gui::BitmapFactory().pixmap("Geoassembly"), widget);
    }

    // if no document we must create one or the taskbox does not show.
    auto* doc = App::GetApplication().getActiveDocument();
    if (!doc) {
        App::GetApplication().newDocument();
    }
}

bool TaskNewObject::accept()
{
    return widget->accept();
}

bool TaskNewObject::reject()
{
    return widget->reject();
}

#include "moc_TaskNewObject.cpp"
