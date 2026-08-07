/***************************************************************************
 *   Copyright (c) 2020 WandererFan <wandererfan@gmail.com>                *
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
 ***************************************************************************/

#pragma once

#include <memory>
#include <string>

#include <Base/Vector3D.h>
#include <Gui/TaskView/TaskDialog.h>
#include <Gui/TaskView/TaskView.h>
#include <Mod/TechDraw/TechDrawGlobal.h>

namespace App
{
class Document;
}

namespace TechDraw
{
class DrawPage;
class DrawViewDetail;
class DrawViewPart;
}

namespace TechDrawGui
{
class QGVPage;
class Ui_TaskDetail;

class TaskDetail : public QWidget
{
    Q_OBJECT

public:
    TaskDetail(TechDraw::DrawPage* page, QGVPage* graphicsView);
    explicit TaskDetail(TechDraw::DrawViewDetail* detailFeat);
    ~TaskDetail() override;

    bool accept();
    bool reject();

    TechDraw::DrawViewDetail* getDetailFeat() const;
    QGVPage* graphicsView() const;
    bool isCreateMode() const;
    bool isCreated() const;
    double referenceAngle() const;

    void setInteractiveBase(TechDraw::DrawViewPart* base);
    void createDetail(const Base::Vector3d& anchor, double radius);
    void setInteractiveGeometry(const Base::Vector3d& anchor, double radius);
    void setReferenceAngle(double angle);
    void saveButtons(QPushButton* btnOK, QPushButton* btnCancel);

private Q_SLOTS:
    void onIdentifierEdit();
    void onConnectChanged(bool checked);
    void onScaleTypeEdit();
    void onScaleEdit();

private:
    void setupUi();
    void setUiFromFeature();
    void updateScale();
    void saveDetailState();
    void restoreDetailState();

    std::unique_ptr<Ui_TaskDetail> ui;
    TechDraw::DrawPage* m_page{nullptr};
    QGVPage* m_graphicsView{nullptr};
    TechDraw::DrawViewDetail* m_detailFeat{nullptr};
    TechDraw::DrawViewPart* m_baseFeat{nullptr};
    App::Document* m_doc{nullptr};
    std::string m_detailName;
    Base::Vector3d m_saveAnchor;
    double m_saveRadius{0.0};
    double m_saveScale{1.0};
    long m_saveScaleType{0};
    std::string m_saveReference;
    bool m_saveConnect{false};
    double m_saveReferenceAngle{0.0};
    bool m_createMode{true};
    bool m_created{false};
    bool m_blockUpdate{false};
    QPushButton* m_btnOK{nullptr};
    QPushButton* m_btnCancel{nullptr};
};

class TaskDlgDetail : public Gui::TaskView::TaskDialog
{
    Q_OBJECT

public:
    TaskDlgDetail(TechDraw::DrawPage* page, QGVPage* graphicsView);
    explicit TaskDlgDetail(TechDraw::DrawViewDetail* detailFeat);
    ~TaskDlgDetail() override;

    void open() override;
    bool accept() override;
    bool reject() override;
    bool isAllowedAlterDocument() const override { return false; }
    void modifyStandardButtons(QDialogButtonBox* box) override;
    std::string getDetailName() const;

private:
    TaskDetail* widget{nullptr};
    Gui::TaskView::TaskBox* taskbox{nullptr};
    QGVPage* m_graphicsView{nullptr};
};

}  // namespace TechDrawGui
