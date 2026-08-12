/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *   This file is part of FreeCAD.                                         *
 ***************************************************************************/

#pragma once

#include <QDialogButtonBox>
#include <QWidget>

#include <memory>

#include <Gui/TaskView/TaskDialog.h>
#include <Mod/TechDraw/TechDrawGlobal.h>

class Ui_TaskBrokenOutSection;

namespace Gui::TaskView
{
class TaskBox;
}

namespace TechDraw
{
class DrawPage;
class DrawViewBrokenOutSection;
class DrawViewPart;
}

namespace TechDrawGui
{
class QGVPage;

class TechDrawGuiExport TaskBrokenOutSection : public QWidget
{
    Q_OBJECT

public:
    explicit TaskBrokenOutSection(QWidget* parent = nullptr);
    ~TaskBrokenOutSection() override;

    double depth() const;
    void setDepth(double depth);
    void setOutlineComplete(bool complete);
    bool hasCompleteOutline() const { return m_outlineComplete; }

Q_SIGNALS:
    void depthChanged(double depth);
    void resetOutlineRequested();
    void outlineCompleteChanged(bool complete);

private:
    std::unique_ptr<Ui_TaskBrokenOutSection> ui;
    bool m_outlineComplete{false};
};

class TechDrawGuiExport TaskDlgBrokenOutSection : public Gui::TaskView::TaskDialog
{
public:
    TaskDlgBrokenOutSection(TechDraw::DrawPage* page, QGVPage* graphicsView);
    TaskDlgBrokenOutSection(TechDraw::DrawViewBrokenOutSection* section,
                            TechDraw::DrawViewPart* base,
                            QGVPage* graphicsView);
    ~TaskDlgBrokenOutSection() override;

    void open() override;
    bool accept() override;
    bool reject() override;
    void modifyStandardButtons(QDialogButtonBox* buttonBox) override;
    QDialogButtonBox::StandardButtons getStandardButtons() const override
    {
        return QDialogButtonBox::Ok | QDialogButtonBox::Cancel;
    }
    bool isAllowedAlterSelection() const override { return true; }
    bool isAllowedAlterDocument() const override { return true; }

private:
    TechDraw::DrawPage* m_page{nullptr};
    TechDraw::DrawViewBrokenOutSection* m_section{nullptr};
    TechDraw::DrawViewPart* m_base{nullptr};
    QGVPage* m_graphicsView{nullptr};
    TaskBrokenOutSection* m_widget{nullptr};
    Gui::TaskView::TaskBox* m_taskBox{nullptr};
    bool m_transactionOpen{false};
};
} // namespace TechDrawGui
