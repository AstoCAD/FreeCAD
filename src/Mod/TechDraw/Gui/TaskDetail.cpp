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

#include <algorithm>
#include <cmath>
#include <limits>

#include <QBrush>
#include <QGraphicsEllipseItem>
#include <QGraphicsPathItem>
#include <QGraphicsScene>
#include <QGraphicsSceneMouseEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainterPath>
#include <QPainterPathStroker>
#include <QPen>
#include <QTimer>

#include <App/Document.h>
#include <Base/Console.h>
#include <Base/Exception.h>
#include <Base/Tools.h>
#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Command.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/InputHint.h>
#include <Gui/MainWindow.h>
#include <Gui/Selection/Selection.h>
#include <Gui/ViewProvider.h>
#include <Mod/TechDraw/App/DrawPage.h>
#include <Mod/TechDraw/App/DrawViewDetail.h>
#include <Mod/TechDraw/App/DrawViewPart.h>

#include "ui_TaskDetail.h"
#include "QGIEdge.h"
#include "QGIHighlight.h"
#include "QGIVertex.h"
#include "QGIViewPart.h"
#include "QGSPage.h"
#include "QGVPage.h"
#include "Rez.h"
#include "TaskDetail.h"
#include "TechDrawHandler.h"
#include "ViewProviderPage.h"
#include "ViewProviderViewPart.h"

using namespace Gui;
using namespace TechDraw;
using namespace TechDrawGui;

namespace
{

constexpr double DefaultRadius = 10.0;
constexpr double HandleDistancePixels = 9.0;

class DetailDragCapture final : public QGraphicsItem
{
public:
    DetailDragCapture()
    {
        setAcceptedMouseButtons(Qt::LeftButton);
        setCursor(Qt::OpenHandCursor);
    }

    void setHitShape(const QPainterPath& shape)
    {
        prepareGeometryChange();
        m_shape = shape;
    }

    QRectF boundingRect() const override
    {
        return m_shape.boundingRect();
    }

    QPainterPath shape() const override
    {
        return m_shape;
    }

    void paint(QPainter*, const QStyleOptionGraphicsItem*, QWidget*) override {}

protected:
    void mousePressEvent(QGraphicsSceneMouseEvent* event) override
    {
        setCursor(Qt::ClosedHandCursor);
        event->accept();
    }

    void mouseMoveEvent(QGraphicsSceneMouseEvent* event) override
    {
        event->accept();
    }

    void mouseReleaseEvent(QGraphicsSceneMouseEvent* event) override
    {
        setCursor(Qt::OpenHandCursor);
        event->accept();
    }

private:
    QPainterPath m_shape;
};

class DetailViewHandler final : public TechDrawHandler
{
public:
    explicit DetailViewHandler(TaskDetail* task) : m_task(task) {}

    ~DetailViewHandler() override
    {
        clearPreview();
        selectBase(nullptr);
    }

    void mouseMoveEvent(QMouseEvent* event) override
    {
        if (!viewPage || !m_task) {
            return;
        }

        const QPointF scenePoint = viewPage->mapToScene(event->pos());
        if (m_mode == Mode::SeekCenter) {
            QGIViewPart* hovered = findView(event->pos());
            if (hovered != m_baseItem) {
                selectBase(hovered);
                m_base = hovered
                    ? dynamic_cast<DrawViewPart*>(hovered->getViewObject())
                    : nullptr;
                m_task->setInteractiveBase(m_base);
            }
            if (!m_baseItem || !m_base) {
                clearPreview();
                return;
            }

            m_center = m_baseItem->mapFromScene(scenePoint);
            if (!event->modifiers().testFlag(Qt::ControlModifier)) {
                m_center = snapPoint(event->pos(), m_center);
            }
            m_radius = Rez::guiX(DefaultRadius * m_base->getScale());
            updatePreview();
            event->accept();
            return;
        }

        if (!m_baseItem || !m_base) {
            return;
        }
        const QPointF localPoint = m_baseItem->mapFromScene(scenePoint);
        if (m_mode == Mode::SeekRadius) {
            m_radius = std::max(1.0, distance(localPoint, m_center));
            updatePreview();
            event->accept();
            return;
        }

        if (m_drag == Drag::Center) {
            m_center = event->modifiers().testFlag(Qt::ControlModifier)
                ? localPoint
                : snapPoint(event->pos(), localPoint);
            updatePreview();
            updateFeature();
            event->accept();
        }
        else if (m_drag == Drag::Radius) {
            m_radius = std::max(1.0, distance(localPoint, m_center));
            updatePreview();
            updateFeature();
            event->accept();
        }
        else if (m_drag == Drag::Reference) {
            const QPointF delta = localPoint - m_center;
            if (distance(localPoint, m_center) > 1.0e-9) {
                double angle = Base::toDegrees(std::atan2(-delta.y(), delta.x()));
                if (angle < 0.0) {
                    angle += 360.0;
                }
                m_task->setReferenceAngle(angle);
                updatePreview();
            }
            event->accept();
        }
        else {
            updatePreview();
        }
    }

    void mousePressEvent(QMouseEvent* event) override
    {
        if (event->button() != Qt::LeftButton || !m_baseItem || !m_base) {
            return;
        }

        if (m_mode == Mode::SeekCenter) {
            m_mode = Mode::SeekRadius;
            updateHint();
            event->accept();
            return;
        }
        if (m_mode == Mode::SeekRadius) {
            if (m_radius <= 1.0) {
                event->accept();
                return;
            }
            m_task->createDetail(toAnchor(m_center), toRadius(m_radius));
            if (m_task->isCreated()) {
                m_mode = Mode::Adjust;
                updatePreview();
                updateHint();
            }
            event->accept();
            return;
        }

        const QPointF localPoint = m_baseItem->mapFromScene(
            viewPage->mapToScene(event->pos()));
        const QPointF scenePoint = viewPage->mapToScene(event->pos());
        const double centerPixels = viewportDistance(localPoint, m_center);
        const double edgePixels = std::abs(
            viewportDistance(localPoint, m_center)
            - viewportDistance(m_center + QPointF(m_radius, 0.0), m_center));
        if (centerPixels <= HandleDistancePixels) {
            m_drag = Drag::Center;
        }
        else if (referenceHit(scenePoint)) {
            m_drag = Drag::Reference;
        }
        else if (edgePixels <= HandleDistancePixels) {
            m_drag = Drag::Radius;
        }
        if (m_drag != Drag::None) {
            event->accept();
        }
    }

    void mouseReleaseEvent(QMouseEvent* event) override
    {
        if (event->button() == Qt::RightButton) {
            if (m_mode == Mode::SeekRadius) {
                m_mode = Mode::SeekCenter;
                selectBase(nullptr);
                m_base = nullptr;
                m_task->setInteractiveBase(nullptr);
                clearPreview();
                updateHint();
            }
            else if (m_mode == Mode::SeekCenter) {
                QTimer::singleShot(
                    0, Gui::getMainWindow(),
                    []() { Gui::Control().closeDialog(); });
            }
            event->accept();
            return;
        }
        if (event->button() == Qt::LeftButton) {
            m_drag = Drag::None;
            if (viewPage->getScene()) {
                viewPage->getScene()->clearSelection();
            }
            event->accept();
            return;
        }
        TechDrawHandler::mouseReleaseEvent(event);
    }

    void keyPressEvent(QKeyEvent* event) override
    {
        if (event->key() == Qt::Key_Escape) {
            QTimer::singleShot(
                0, Gui::getMainWindow(),
                []() { Gui::Control().closeDialog(); });
            event->accept();
        }
    }

    void deactivate() override
    {
        clearPreview();
        selectBase(nullptr);
        TechDrawHandler::deactivate();
    }

    void initializeFromFeature()
    {
        DrawViewDetail* detail = m_task ? m_task->getDetailFeat() : nullptr;
        if (!detail) {
            return;
        }
        m_base = dynamic_cast<DrawViewPart*>(detail->BaseView.getValue());
        if (!m_base) {
            return;
        }
        m_baseItem = findViewItem(m_base);
        if (!m_baseItem) {
            return;
        }
        const Base::Vector3d anchor = detail->AnchorPoint.getValue();
        const double scale = m_base->getScale();
        m_center = QPointF(
            Rez::guiX(anchor.x * scale),
            Rez::guiX(-anchor.y * scale));
        m_radius = Rez::guiX(detail->Radius.getValue() * scale);
        m_mode = Mode::Adjust;
        updatePreview();
        updateHint();
    }

private:
    enum class Mode
    {
        SeekCenter,
        SeekRadius,
        Adjust
    };

    enum class Drag
    {
        None,
        Center,
        Radius,
        Reference
    };

    std::list<Gui::InputHint> getToolHints() const override
    {
        using enum Gui::InputHint::UserInput;
        if (m_mode == Mode::SeekCenter) {
            return {
                {QObject::tr("%1 place detail center"), {MouseLeft}},
                {QObject::tr("%1 move without snapping"), {{ModifierCtrl, MouseMove}}},
                {QObject::tr("%1 close detail view tool"), {MouseRight}},
            };
        }
        if (m_mode == Mode::SeekRadius) {
            return {
                {QObject::tr("%1 set detail radius"), {MouseLeft}},
                {QObject::tr("%1 restart detail placement"), {MouseRight}},
            };
        }
        return {
            {QObject::tr("%1 drag center, circle, or identifier"), {{MouseLeft, MouseMove}}},
            {QObject::tr("%1 move center without snapping"), {{ModifierCtrl, MouseMove}}},
        };
    }

    QString getCrosshairCursorSVGName() const override
    {
        return QStringLiteral("TechDraw_DetailView");
    }

    QGIViewPart* findView(const QPoint& viewportPoint)
    {
        const QList<QGraphicsItem*> items = viewPage->items(viewportPoint);
        for (QGraphicsItem* item : items) {
            for (QGraphicsItem* parent = item; parent; parent = parent->parentItem()) {
                auto* view = dynamic_cast<QGIViewPart*>(parent);
                auto* object = view
                    ? dynamic_cast<DrawViewPart*>(view->getViewObject())
                    : nullptr;
                if (view && view->isVisible() && object
                    && object->findParentPage() == getPage()) {
                    return view;
                }
            }
        }
        return nullptr;
    }

    QGIViewPart* findViewItem(DrawViewPart* object) const
    {
        if (!viewPage || !viewPage->getScene()) {
            return nullptr;
        }
        for (QGraphicsItem* item : viewPage->getScene()->items()) {
            auto* view = dynamic_cast<QGIViewPart*>(item);
            if (view && view->getViewObject() == object) {
                return view;
            }
        }
        return nullptr;
    }

    QGIHighlight* findHighlight() const
    {
        DrawViewDetail* detail = m_task ? m_task->getDetailFeat() : nullptr;
        if (!m_baseItem || !detail) {
            return nullptr;
        }

        QList<QGraphicsItem*> pending = m_baseItem->childItems();
        while (!pending.empty()) {
            QGraphicsItem* item = pending.takeLast();
            if (auto* highlight = dynamic_cast<QGIHighlight*>(item)) {
                if (highlight->getFeatureName() == detail->getNameInDocument()) {
                    return highlight;
                }
            }
            pending.append(item->childItems());
        }
        return nullptr;
    }

    void selectBase(QGIViewPart* base)
    {
        if (m_baseItem && m_baseItem != base) {
            m_baseItem->setSelected(false);
        }
        m_baseItem = base;
        if (m_baseItem) {
            m_baseItem->setSelected(true);
        }
    }

    static double distance(const QPointF& first, const QPointF& second)
    {
        return std::hypot(first.x() - second.x(), first.y() - second.y());
    }

    double viewportDistance(const QPointF& first, const QPointF& second) const
    {
        const QPoint firstViewport = viewPage->mapFromScene(m_baseItem->mapToScene(first));
        const QPoint secondViewport = viewPage->mapFromScene(m_baseItem->mapToScene(second));
        return std::hypot(
            firstViewport.x() - secondViewport.x(),
            firstViewport.y() - secondViewport.y());
    }

    QPointF nearestPointOnEdge(QGIEdge* edge, const QPointF& point) const
    {
        QPointF best = point;
        double bestDistanceSquared = std::numeric_limits<double>::max();
        const QList<QPolygonF> polygons = edge->path().toSubpathPolygons();
        for (const QPolygonF& polygon : polygons) {
            for (qsizetype index = 1; index < polygon.size(); ++index) {
                const QPointF first =
                    m_baseItem->mapFromItem(edge, polygon[index - 1]);
                const QPointF second =
                    m_baseItem->mapFromItem(edge, polygon[index]);
                const QPointF segment = second - first;
                const double lengthSquared = QPointF::dotProduct(segment, segment);
                if (lengthSquared <= 1.0e-12) {
                    continue;
                }
                const double parameter = std::clamp(
                    QPointF::dotProduct(point - first, segment) / lengthSquared,
                    0.0,
                    1.0);
                const QPointF candidate = first + segment * parameter;
                const QPointF delta = candidate - point;
                const double distanceSquared = QPointF::dotProduct(delta, delta);
                if (distanceSquared < bestDistanceSquared) {
                    bestDistanceSquared = distanceSquared;
                    best = candidate;
                }
            }
        }
        return best;
    }

    QPointF snapPoint(const QPoint& viewportPoint, const QPointF& point) const
    {
        QGIEdge* preselectedEdge = nullptr;
        const QList<QGraphicsItem*> items = viewPage->items(viewportPoint);
        auto belongsToBase = [this](QGraphicsItem* item) {
            for (QGraphicsItem* parent = item; parent; parent = parent->parentItem()) {
                if (parent == m_baseItem) {
                    return true;
                }
            }
            return false;
        };

        for (QGraphicsItem* item : items) {
            if (!belongsToBase(item)) {
                continue;
            }
            if (auto* vertex = dynamic_cast<QGIVertex*>(item)) {
                return m_baseItem->mapFromScene(
                    vertex->mapToScene(vertex->boundingRect().center()));
            }
            if (!preselectedEdge) {
                preselectedEdge = dynamic_cast<QGIEdge*>(item);
            }
        }

        if (preselectedEdge) {
            return nearestPointOnEdge(preselectedEdge, point);
        }
        return point;
    }

    Base::Vector3d toAnchor(const QPointF& point) const
    {
        const double scale = m_base ? m_base->getScale() : 1.0;
        return Base::Vector3d(
            Rez::appX(point.x()) / scale,
            -Rez::appX(point.y()) / scale,
            0.0);
    }

    double toRadius(double radius) const
    {
        const double scale = m_base ? m_base->getScale() : 1.0;
        return Rez::appX(radius) / scale;
    }

    void makePreview()
    {
        if (m_circle || !viewPage || !viewPage->getScene()) {
            return;
        }
        QPen pen(QColor(35, 95, 210));
        pen.setStyle(Qt::DashLine);
        pen.setWidthF(1.5);
        pen.setCosmetic(true);
        m_circle = viewPage->getScene()->addEllipse({}, pen, QBrush(Qt::NoBrush));
        m_circle->setZValue(10000.0);
        m_circle->setAcceptedMouseButtons(Qt::LeftButton);
        m_circle->setFlag(QGraphicsItem::ItemIsMovable, false);
        m_circle->setFlag(QGraphicsItem::ItemIsSelectable, false);

        const QColor centerColor(35, 95, 210);
        QPen centerPen(centerColor);
        centerPen.setWidthF(1.5);
        centerPen.setCosmetic(true);
        m_centerMarker =
            viewPage->getScene()->addEllipse({}, centerPen, QBrush(centerColor));
        m_centerMarker->setZValue(10001.0);
        m_centerMarker->setAcceptedMouseButtons(Qt::LeftButton);
        m_centerMarker->setFlag(QGraphicsItem::ItemIsMovable, false);
        m_centerMarker->setFlag(QGraphicsItem::ItemIsSelectable, false);

        m_centerCapture = new DetailDragCapture();
        m_centerCapture->setZValue(10003.0);
        viewPage->getScene()->addItem(m_centerCapture);
        m_radiusCapture = new DetailDragCapture();
        m_radiusCapture->setZValue(10002.0);
        viewPage->getScene()->addItem(m_radiusCapture);
        m_referenceCapture = new DetailDragCapture();
        m_referenceCapture->setZValue(10004.0);
        viewPage->getScene()->addItem(m_referenceCapture);
    }

    void updatePreview()
    {
        if (!m_baseItem) {
            clearPreview();
            return;
        }
        makePreview();
        const QPointF centerScene = m_baseItem->mapToScene(m_center);
        const QPointF radiusScene = m_baseItem->mapToScene(
            m_center + QPointF(m_radius, 0.0));
        const double sceneRadius = distance(centerScene, radiusScene);
        const QRectF circleRect(
            centerScene.x() - sceneRadius,
            centerScene.y() - sceneRadius,
            2.0 * sceneRadius,
            2.0 * sceneRadius);
        m_circle->setRect(circleRect);

        const double zoom = std::max(std::abs(viewPage->transform().m11()), 1.0e-6);
        const double markerRadius = 4.0 / zoom;
        m_centerMarker->setRect(
            centerScene.x() - markerRadius,
            centerScene.y() - markerRadius,
            2.0 * markerRadius,
            2.0 * markerRadius);

        if (m_mode == Mode::Adjust) {
            m_circle->hide();
        }
        else {
            m_circle->show();
        }

        QPainterPath centerShape;
        centerShape.addEllipse(centerScene,
                               HandleDistancePixels / zoom,
                               HandleDistancePixels / zoom);
        m_centerCapture->setHitShape(centerShape);

        QPainterPath circlePath;
        circlePath.addEllipse(circleRect);
        QPainterPathStroker circleStroker;
        circleStroker.setWidth(2.0 * HandleDistancePixels / zoom);
        m_radiusCapture->setHitShape(circleStroker.createStroke(circlePath));

        QPainterPath referenceShape;
        if (QGIHighlight* highlight = findHighlight()) {
            const double margin = HandleDistancePixels / zoom;
            referenceShape.addRect(
                highlight->referenceSceneBoundingRect().adjusted(
                    -margin, -margin, margin, margin));
        }
        m_referenceCapture->setHitShape(referenceShape);
    }

    bool referenceHit(const QPointF& scenePoint) const
    {
        if (!m_referenceCapture) {
            return false;
        }
        return m_referenceCapture->shape().contains(scenePoint);
    }

    void updateFeature()
    {
        if (m_task) {
            m_task->setInteractiveGeometry(toAnchor(m_center), toRadius(m_radius));
        }
    }

    void clearPreview()
    {
        delete m_circle;
        delete m_centerMarker;
        delete m_centerCapture;
        delete m_radiusCapture;
        delete m_referenceCapture;
        m_circle = nullptr;
        m_centerMarker = nullptr;
        m_centerCapture = nullptr;
        m_radiusCapture = nullptr;
        m_referenceCapture = nullptr;
    }

    TaskDetail* m_task{nullptr};
    QGIViewPart* m_baseItem{nullptr};
    DrawViewPart* m_base{nullptr};
    QGraphicsEllipseItem* m_circle{nullptr};
    QGraphicsEllipseItem* m_centerMarker{nullptr};
    DetailDragCapture* m_centerCapture{nullptr};
    DetailDragCapture* m_radiusCapture{nullptr};
    DetailDragCapture* m_referenceCapture{nullptr};
    QPointF m_center;
    double m_radius{0.0};
    Mode m_mode{Mode::SeekCenter};
    Drag m_drag{Drag::None};
};

}  // namespace

TaskDetail::TaskDetail(DrawPage* page, QGVPage* graphicsView)
    : ui(new Ui_TaskDetail)
    , m_page(page)
    , m_graphicsView(graphicsView)
    , m_doc(page ? page->getDocument() : nullptr)
{
    setupUi();
    setWindowTitle(tr("Create Detail View"));
    if (m_page) {
        m_blockUpdate = true;
        ui->leIdentifier->setText(
            QString::fromStdString(m_page->getNextViewIdentifier(false)));
        ui->cbScaleType->setCurrentIndex(0);
        ui->qsbScale->setValue(m_page->Scale.getValue());
        ui->qsbScale->setEnabled(false);
        m_blockUpdate = false;
    }
}

TaskDetail::TaskDetail(DrawViewDetail* detailFeat)
    : ui(new Ui_TaskDetail)
    , m_page(detailFeat ? detailFeat->findParentPage() : nullptr)
    , m_detailFeat(detailFeat)
    , m_baseFeat(detailFeat
          ? dynamic_cast<DrawViewPart*>(detailFeat->BaseView.getValue())
          : nullptr)
    , m_doc(detailFeat ? detailFeat->getDocument() : nullptr)
    , m_detailName(detailFeat ? detailFeat->getNameInDocument() : "")
    , m_createMode(false)
    , m_created(detailFeat != nullptr)
{
    setupUi();
    setWindowTitle(tr("Edit Detail View"));
    if (!m_detailFeat || !m_baseFeat || !m_page) {
        Base::Console().error("TaskDetail - invalid detail view or base view\n");
        return;
    }

    Gui::Document* guiDocument = Gui::Application::Instance->getDocument(m_doc);
    auto* viewProvider = guiDocument
        ? dynamic_cast<ViewProviderPage*>(guiDocument->getViewProvider(m_page))
        : nullptr;
    m_graphicsView = viewProvider ? viewProvider->getQGVPage() : nullptr;
    saveDetailState();
    setUiFromFeature();
}

TaskDetail::~TaskDetail() = default;

void TaskDetail::setupUi()
{
    ui->setupUi(this);
    connect(ui->leIdentifier,
            &QLineEdit::editingFinished,
            this,
            &TaskDetail::onIdentifierEdit);
    connect(ui->cbConnect,
            &QCheckBox::toggled,
            this,
            &TaskDetail::onConnectChanged);
    connect(ui->cbScaleType,
            qOverload<int>(&QComboBox::currentIndexChanged),
            this,
            &TaskDetail::onScaleTypeEdit);
    connect(ui->qsbScale,
            qOverload<double>(&QDoubleSpinBox::valueChanged),
            this,
            &TaskDetail::onScaleEdit);
}

void TaskDetail::setUiFromFeature()
{
    if (!m_detailFeat) {
        return;
    }
    m_blockUpdate = true;
    ui->leIdentifier->setText(
        QString::fromUtf8(m_detailFeat->Reference.getValue()));
    ui->cbConnect->setChecked(m_detailFeat->Connect.getValue());
    ui->cbScaleType->setCurrentIndex(m_detailFeat->getScaleType());
    ui->qsbScale->setValue(m_detailFeat->getScale());
    ui->qsbScale->setEnabled(m_detailFeat->ScaleType.isValue("Custom"));
    m_blockUpdate = false;
}

void TaskDetail::setInteractiveBase(DrawViewPart* base)
{
    if (m_created || base == m_baseFeat) {
        return;
    }
    m_baseFeat = base;
    if (!base) {
        return;
    }
    m_blockUpdate = true;
    ui->cbScaleType->setCurrentIndex(base->getScaleType());
    ui->qsbScale->setValue(base->getScale());
    ui->qsbScale->setEnabled(base->getScaleType() == 2);
    m_blockUpdate = false;
}

void TaskDetail::createDetail(const Base::Vector3d& anchor, double radius)
{
    if (m_created || !m_baseFeat || !m_page || !m_doc) {
        return;
    }

    const int transaction = Gui::Command::openActiveDocumentCommand(
        QT_TRANSLATE_NOOP("Command", "Create Detail View"));
    const std::string objectName{"Detail"};
    m_detailName = m_doc->getUniqueObjectName(objectName.c_str());
    Gui::Command::doCommand(
        Command::Doc,
        "App.activeDocument().addObject('TechDraw::DrawViewDetail', '%s')",
        m_detailName.c_str());

    m_detailFeat = dynamic_cast<DrawViewDetail*>(
        m_doc->getObject(m_detailName.c_str()));
    if (!m_detailFeat) {
        Gui::Command::abortCommand(transaction);
        throw Base::RuntimeError("TaskDetail - new detail view not found");
    }

    const std::string identifier = ui->leIdentifier->text().toStdString();
    const std::string escapedIdentifier = Base::Tools::escapeEncodeString(identifier);
    const std::string baseName = m_baseFeat->getNameInDocument();
    const std::string pageName = m_page->getNameInDocument();
    Gui::Command::doCommand(
        Command::Doc,
        "App.activeDocument().%s.Reference = '%s'",
        m_detailName.c_str(),
        escapedIdentifier.c_str());
    Gui::Command::doCommand(
        Command::Doc,
        "App.activeDocument().%s.BaseView = App.activeDocument().%s",
        m_detailName.c_str(),
        baseName.c_str());
    Gui::Command::doCommand(
        Command::Doc,
        "App.activeDocument().%s.Direction = App.activeDocument().%s.Direction",
        m_detailName.c_str(),
        baseName.c_str());
    Gui::Command::doCommand(
        Command::Doc,
        "App.activeDocument().%s.XDirection = App.activeDocument().%s.XDirection",
        m_detailName.c_str(),
        baseName.c_str());
    Gui::Command::doCommand(
        Command::Doc,
        "App.activeDocument().%s.addView(App.activeDocument().%s)",
        pageName.c_str(),
        m_detailName.c_str());

    m_detailFeat->Source.setValues(m_baseFeat->Source.getValues());
    m_detailFeat->AnchorPoint.setValue(anchor);
    m_detailFeat->Radius.setValue(radius);
    m_detailFeat->Connect.setValue(ui->cbConnect->isChecked());
    m_detailFeat->ScaleType.setValue(ui->cbScaleType->currentIndex());
    m_detailFeat->Scale.setValue(ui->qsbScale->value());
    if (identifier == m_page->getNextViewIdentifier(false)) {
        m_page->getNextViewIdentifier();
    }
    m_created = true;

    Gui::Command::updateActive();
    Gui::Command::commitCommand(transaction);
    m_detailFeat->recomputeFeature();
    m_baseFeat->requestPaint();
    if (m_btnOK) {
        m_btnOK->setEnabled(true);
    }
}

void TaskDetail::setInteractiveGeometry(const Base::Vector3d& anchor, double radius)
{
    if (!m_detailFeat) {
        return;
    }
    m_detailFeat->AnchorPoint.setValue(anchor);
    m_detailFeat->Radius.setValue(std::max(radius, std::numeric_limits<double>::epsilon()));
    m_detailFeat->recomputeFeature();
    if (m_baseFeat) {
        m_baseFeat->requestPaint();
    }
}

void TaskDetail::onIdentifierEdit()
{
    if (!m_detailFeat) {
        return;
    }
    m_detailFeat->Reference.setValue(ui->leIdentifier->text().toStdString());
    m_detailFeat->requestPaint();
    if (m_baseFeat) {
        m_baseFeat->requestPaint();
    }
}

void TaskDetail::onConnectChanged(bool checked)
{
    if (m_blockUpdate || !m_detailFeat) {
        return;
    }
    m_detailFeat->Connect.setValue(checked);
    if (m_baseFeat) {
        m_baseFeat->requestPaint();
    }
}

void TaskDetail::onScaleTypeEdit()
{
    if (m_blockUpdate) {
        return;
    }
    const int scaleType = ui->cbScaleType->currentIndex();
    ui->qsbScale->setEnabled(scaleType == 2);
    if (scaleType == 0 && m_page) {
        m_blockUpdate = true;
        ui->qsbScale->setValue(m_page->Scale.getValue());
        m_blockUpdate = false;
    }
    updateScale();
}

void TaskDetail::onScaleEdit()
{
    if (!m_blockUpdate) {
        updateScale();
    }
}

void TaskDetail::updateScale()
{
    if (!m_detailFeat) {
        return;
    }
    m_detailFeat->ScaleType.setValue(ui->cbScaleType->currentIndex());
    m_detailFeat->Scale.setValue(ui->qsbScale->value());
    m_detailFeat->recomputeFeature();
    m_detailFeat->requestPaint();
    if (m_baseFeat) {
        m_baseFeat->requestPaint();
    }
}

void TaskDetail::saveDetailState()
{
    if (!m_detailFeat) {
        return;
    }
    m_saveAnchor = m_detailFeat->AnchorPoint.getValue();
    m_saveRadius = m_detailFeat->Radius.getValue();
    m_saveScale = m_detailFeat->Scale.getValue();
    m_saveScaleType = m_detailFeat->ScaleType.getValue();
    m_saveReference = m_detailFeat->Reference.getValue();
    m_saveConnect = m_detailFeat->Connect.getValue();
    m_saveReferenceAngle = referenceAngle();
}

void TaskDetail::restoreDetailState()
{
    if (!m_detailFeat) {
        return;
    }
    m_detailFeat->AnchorPoint.setValue(m_saveAnchor);
    m_detailFeat->Radius.setValue(m_saveRadius);
    m_detailFeat->Scale.setValue(m_saveScale);
    m_detailFeat->ScaleType.setValue(m_saveScaleType);
    m_detailFeat->Reference.setValue(m_saveReference);
    m_detailFeat->Connect.setValue(m_saveConnect);
    setReferenceAngle(m_saveReferenceAngle);
}

void TaskDetail::saveButtons(QPushButton* btnOK, QPushButton* btnCancel)
{
    m_btnOK = btnOK;
    m_btnCancel = btnCancel;
    if (m_btnOK && m_createMode && !m_created) {
        m_btnOK->setEnabled(false);
    }
}

DrawViewDetail* TaskDetail::getDetailFeat() const
{
    if (!m_doc || m_detailName.empty()) {
        return nullptr;
    }
    return dynamic_cast<DrawViewDetail*>(m_doc->getObject(m_detailName.c_str()));
}

QGVPage* TaskDetail::graphicsView() const
{
    return m_graphicsView;
}

bool TaskDetail::isCreateMode() const
{
    return m_createMode;
}

bool TaskDetail::isCreated() const
{
    return m_created;
}

double TaskDetail::referenceAngle() const
{
    if (!m_detailFeat || !m_doc) {
        return 0.0;
    }

    Gui::Document* guiDocument = Gui::Application::Instance->getDocument(m_doc);
    auto* viewProvider = guiDocument
        ? dynamic_cast<ViewProviderViewPart*>(guiDocument->getViewProvider(m_detailFeat))
        : nullptr;
    return viewProvider ? viewProvider->HighlightAdjust.getValue() : 0.0;
}

void TaskDetail::setReferenceAngle(double angle)
{
    if (!m_detailFeat || !m_doc) {
        return;
    }

    Gui::Document* guiDocument = Gui::Application::Instance->getDocument(m_doc);
    auto* viewProvider = guiDocument
        ? dynamic_cast<ViewProviderViewPart*>(guiDocument->getViewProvider(m_detailFeat))
        : nullptr;
    if (viewProvider) {
        viewProvider->HighlightAdjust.setValue(angle);
    }
}

bool TaskDetail::accept()
{
    if (m_createMode && !m_created) {
        return false;
    }
    if (m_detailFeat) {
        m_detailFeat->recomputeFeature();
    }
    Gui::Command::doCommand(Gui::Command::Gui, "Gui.ActiveDocument.resetEdit()");
    return true;
}

bool TaskDetail::reject()
{
    if (m_createMode && m_created && m_doc->getObject(m_detailName.c_str())) {
        Gui::Command::doCommand(
            Gui::Command::Gui,
            "App.activeDocument().removeObject('%s')",
            m_detailName.c_str());
    }
    else if (!m_createMode && m_detailFeat) {
        restoreDetailState();
        m_detailFeat->recomputeFeature();
        if (m_baseFeat) {
            m_baseFeat->requestPaint();
        }
    }
    Gui::Command::doCommand(Gui::Command::Gui, "App.activeDocument().recompute()");
    Gui::Command::doCommand(Gui::Command::Gui, "Gui.ActiveDocument.resetEdit()");
    return true;
}

TaskDlgDetail::TaskDlgDetail(DrawPage* page, QGVPage* graphicsView)
    : m_graphicsView(graphicsView)
{
    widget = new TaskDetail(page, graphicsView);
    taskbox = new Gui::TaskView::TaskBox(
        Gui::BitmapFactory().pixmap("actions/TechDraw_DetailView"),
        widget->windowTitle(),
        true,
        nullptr);
    taskbox->groupLayout()->addWidget(widget);
    Content.push_back(taskbox);
}

TaskDlgDetail::TaskDlgDetail(DrawViewDetail* detailFeat)
{
    widget = new TaskDetail(detailFeat);
    m_graphicsView = widget->graphicsView();
    taskbox = new Gui::TaskView::TaskBox(
        Gui::BitmapFactory().pixmap("actions/TechDraw_DetailView"),
        widget->windowTitle(),
        true,
        nullptr);
    taskbox->groupLayout()->addWidget(widget);
    Content.push_back(taskbox);
}

TaskDlgDetail::~TaskDlgDetail()
{
    if (m_graphicsView && m_graphicsView->isHandlerActive()) {
        m_graphicsView->deactivateHandler();
    }
}

void TaskDlgDetail::open()
{
    if (!m_graphicsView) {
        return;
    }
    auto* handler = new DetailViewHandler(widget);
    m_graphicsView->activateHandler(handler);
    if (!widget->isCreateMode()) {
        handler->initializeFromFeature();
    }
}

void TaskDlgDetail::modifyStandardButtons(QDialogButtonBox* box)
{
    widget->saveButtons(
        box->button(QDialogButtonBox::Ok),
        box->button(QDialogButtonBox::Cancel));
}

std::string TaskDlgDetail::getDetailName() const
{
    DrawViewDetail* detail = widget->getDetailFeat();
    return detail ? detail->getNameInDocument() : std::string{};
}

bool TaskDlgDetail::accept()
{
    return widget->accept();
}

bool TaskDlgDetail::reject()
{
    return widget->reject();
}

#include <Mod/TechDraw/Gui/moc_TaskDetail.cpp>
