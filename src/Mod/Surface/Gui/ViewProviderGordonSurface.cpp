// SPDX-License-Identifier: LGPL-2.1-or-later

#include <QCheckBox>
#include <QDoubleSpinBox>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QSpinBox>
#include <QVBoxLayout>
#include <App/Document.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/InputHint.h>
#include <Gui/MainWindow.h>
#include <Gui/Selection/Selection.h>
#include <Gui/Selection/SelectionObject.h>
#include <Gui/TaskView/TaskDialog.h>
#include <Gui/TreeItemMode.h>
#include <Mod/Surface/App/FeatureGordonSurface.h>
#include "ViewProviderGordonSurface.h"

using namespace SurfaceGui;
PROPERTY_SOURCE(SurfaceGui::ViewProviderGordonSurface, PartGui::ViewProviderSpline)

namespace
{
class GordonPanel: public QWidget
{
public:
    explicit GordonPanel(ViewProviderGordonSurface* provider)
        : vp(provider)
        , feature(static_cast<Surface::GordonSurface*>(vp->getObject()))
    {
        setWindowTitle(tr("Gordon surface"));
        setObjectName(QStringLiteral("GordonSurfaceEditor"));
        auto layout = new QVBoxLayout(this);
        group(layout, tr("Profiles"), "profiles", feature->Profiles);
        group(layout, tr("Guides"), "guides", feature->Guides);
        layout->addWidget(new QLabel(tr("Tolerance (mm)")));
        auto tolerance = new QDoubleSpinBox;
        tolerance->setObjectName(QStringLiteral("tolerance"));
        tolerance->setDecimals(7);
        tolerance->setRange(1e-7, 1e3);
        tolerance->setValue(feature->Tolerance.getValue());
        tolerance->setSingleStep(0.001);
        layout->addWidget(tolerance);
        connect(tolerance, qOverload<double>(&QDoubleSpinBox::valueChanged), this, [this](double value) {
            feature->Tolerance.setValue(value);
        });
        layout->addWidget(new QLabel(tr("Maximum samples per direction")));
        auto samples = new QSpinBox;
        samples->setRange(8, 512);
        samples->setValue(static_cast<int>(feature->MaxSamples.getValue()));
        layout->addWidget(samples);
        connect(samples, qOverload<int>(&QSpinBox::valueChanged), this, [this](int value) {
            feature->MaxSamples.setValue(value);
        });
        auto flip = new QCheckBox(tr("Flip normal"));
        flip->setChecked(feature->FlipNormal.getValue());
        layout->addWidget(flip);
        connect(flip, &QCheckBox::toggled, this, [this](bool value) {
            feature->FlipNormal.setValue(value);
        });
        auto preview = new QPushButton(tr("Update preview"));
        preview->setObjectName(QStringLiteral("updatePreview"));
        layout->addWidget(preview);
        connect(preview, &QPushButton::clicked, this, [this] { updatePreview(); });
        status = new QLabel;
        status->setWordWrap(true);
        layout->addWidget(status);
    }

    bool updatePreview()
    {
        const bool success = feature->recomputeFeature();
        status->setText(
            success ? tr("Measured fitting error: %1 mm")
                          .arg(feature->ApproximationError.getValue(), 0, 'g', 4)
                    : QString::fromUtf8(feature->getStatusString())
        );
        return success;
    }

private:
    ViewProviderGordonSurface* vp;
    Surface::GordonSurface* feature;
    QLabel* status;

    static void fill(QListWidget* list, App::PropertyLinkSubList& property)
    {
        list->clear();
        const auto objects = property.getValues();
        const auto names = property.getSubValues();
        for (size_t i = 0; i < objects.size(); ++i) {
            if (!objects[i]) {
                continue;
            }
            list->addItem(
                QString::fromUtf8(objects[i]->Label.getValue())
                + (names[i].empty() ? QString()
                                    : QStringLiteral(" — ") + QString::fromStdString(names[i]))
            );
        }
    }

    void group(QVBoxLayout* layout, const QString& title, const char* name, App::PropertyLinkSubList& property)
    {
        layout->addWidget(new QLabel(title));
        auto list = new QListWidget;
        list->setObjectName(QString::fromLatin1(name));
        list->setToolTip(
            tr("Assign at least two curves in each direction. Every profile must cross "
               "every guide once. Curves may be unordered or reversed; split closed "
               "networks at their seams.")
        );
        list->setSelectionMode(QAbstractItemView::ExtendedSelection);
        list->setMaximumHeight(110);
        layout->addWidget(list);
        fill(list, property);
        auto row = new QHBoxLayout;
        auto add = new QPushButton(tr("Add selected"));
        add->setObjectName(QString::fromLatin1(name) + QStringLiteral("Add"));
        row->addWidget(add);
        auto remove = new QPushButton(tr("Remove"));
        row->addWidget(remove);
        layout->addLayout(row);
        connect(add, &QPushButton::clicked, this, [this, list, &property] {
            auto objects = property.getValues();
            auto names = property.getSubValues();
            for (auto selected : Gui::Selection().getSelectionEx()) {
                auto object = selected.getObject();
                if (object == feature || !Part::Feature::hasShapeOwner(object)) {
                    continue;
                }
                auto subs = selected.getSubNames();
                if (subs.empty()) {
                    subs.emplace_back();
                }
                for (const auto& sub : subs) {
                    bool duplicate = false;
                    for (size_t i = 0; i < objects.size(); ++i) {
                        duplicate |= objects[i] == object && names[i] == sub;
                    }
                    if (!duplicate) {
                        objects.push_back(object);
                        names.push_back(sub);
                    }
                }
            }
            property.setValues(objects, names);
            fill(list, property);
            Gui::Selection().clearSelection();
        });
        connect(remove, &QPushButton::clicked, this, [list, &property] {
            auto objects = property.getValues();
            auto names = property.getSubValues();
            for (int i = list->count() - 1; i >= 0; --i) {
                if (list->item(i)->isSelected()) {
                    objects.erase(objects.begin() + i);
                    names.erase(names.begin() + i);
                }
            }
            property.setValues(objects, names);
            fill(list, property);
        });
    }
};

class TaskGordonSurface: public Gui::TaskView::TaskDialog
{
public:
    explicit TaskGordonSurface(ViewProviderGordonSurface* provider)
        : vp(provider)
        , panel(new GordonPanel(vp))
    {
        addTaskBox(Gui::BitmapFactory().pixmap("Surface_GordonSurface"), panel);
        setDocumentName(vp->getObject()->getDocument()->getName());
        setAutoCloseOnTransactionChange(false);
    }
    bool accept() override
    {
        if (!panel->updatePreview()) {
            return false;
        }
        auto doc = vp->getDocument();
        doc->resetEdit();
        doc->getDocument()->recompute();
        doc->commitCommand();
        return true;
    }
    bool reject() override
    {
        auto doc = vp->getDocument();
        doc->abortCommand();
        doc->resetEdit();
        doc->getDocument()->recompute();
        return true;
    }
    void activate() override
    {
        using enum Gui::InputHint::UserInput;
        Gui::getMainWindow()->showHints({
            {.message = QObject::tr("%1 select curves, then Add selected to Profiles or Guides"),
             .sequences = {MouseLeft}},
            {.message = QObject::tr("%1 extend selection"), .sequences = {{ModifierCtrl, MouseLeft}}},
        });
    }
    void deactivate() override
    {
        Gui::getMainWindow()->hideHints();
    }
    bool isAllowedAlterSelection() const override
    {
        return true;
    }

private:
    ViewProviderGordonSurface* vp;
    GordonPanel* panel;
};
}  // namespace

QIcon ViewProviderGordonSurface::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Surface_GordonSurface");
}
bool ViewProviderGordonSurface::doubleClicked()
{
    startDefaultEditMode();
    return true;
}
bool ViewProviderGordonSurface::setEdit(int mode)
{
    if (mode != Default) {
        return ViewProviderSpline::setEdit(mode);
    }
    if (Gui::Control().activeDialog()) {
        return false;
    }
    if (!getDocument()->hasPendingCommand()) {
        getDocument()->openCommand(QT_TRANSLATE_NOOP("Command", "Edit Gordon surface"));
    }
    Gui::Control().showDialog(new TaskGordonSurface(this));
    signalChangeHighlight(true, Gui::HighlightMode::Bold);
    return true;
}
void ViewProviderGordonSurface::unsetEdit(int mode)
{
    if (mode != Default) {
        ViewProviderSpline::unsetEdit(mode);
        return;
    }
    signalChangeHighlight(false, Gui::HighlightMode::Bold);
    Gui::Control().closeDialog();
}
