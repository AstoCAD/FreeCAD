/****************************************************************************
 *   Copyright (c) 2025 AstoCAD                                             *
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

#ifndef GUI_TASKNEWOBJECT_H
#define GUI_TASKNEWOBJECT_H

#include <Gui/TaskView/TaskDialog.h>


namespace Gui {

class Ui_TaskNewObject;
class TaskBoxNewObject : public QWidget
{
    Q_OBJECT
    Q_DISABLE_COPY(TaskBoxNewObject)

public:
    explicit TaskBoxNewObject(std::string type, QWidget* parent = nullptr);

    bool accept();
    bool reject();

private:
    std::unique_ptr<Ui_TaskNewObject> ui;
    std::string type;
};

class TaskNewObject : public TaskView::TaskDialog
{
    Q_OBJECT

public:
    explicit TaskNewObject(std::string type);

public:
    bool accept() override;
    bool reject() override;

    QDialogButtonBox::StandardButtons getStandardButtons() const override
    { return QDialogButtonBox::Ok|QDialogButtonBox::Cancel; }

private:
    TaskBoxNewObject* widget;
};

} //namespace Gui

#endif // GUI_TASKNEWOBJECT_H
