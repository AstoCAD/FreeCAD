/***************************************************************************
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                       *
 *   This file is part of FreeCAD.                                         *
 ***************************************************************************/

#include <QDoubleSpinBox>
#include <QGraphicsEllipseItem>
#include <QGraphicsItem>
#include <QGraphicsPathItem>
#include <QGraphicsScene>
#include <QGraphicsSceneMouseEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPainterPathStroker>
#include <QPen>
#include <QPushButton>
#include <QPolygonF>
#include <QTimer>

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include <App/Document.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Control.h>
#include <Gui/InputHint.h>
#include <Gui/MainWindow.h>
#include <Gui/Selection/Selection.h>
#include <Gui/TaskView/TaskView.h>
#include <Mod/TechDraw/App/DrawPage.h>
#include <Mod/TechDraw/App/DrawViewBrokenOutSection.h>
#include <Mod/TechDraw/App/DrawViewPart.h>

#include "ui_TaskBrokenOutSection.h"
#include "BrokenOutSectionUtils.h"
#include "QGIViewPart.h"
#include "QGSPage.h"
#include "QGVPage.h"
#include "Rez.h"
#include "TaskBrokenOutSection.h"
#include "TechDrawHandler.h"
#include "ZVALUE.h"

using namespace TechDraw;
using namespace TechDrawGui;

namespace
{

constexpr double HandleRadius = 4.0;
constexpr double HitDistancePixels = 12.0;

QPainterPath periodicSplinePath(const std::vector<QPointF>& points)
{
    return TechDrawGui::periodicBSplinePath(points);
}

class BrokenOutOutlineItem final : public QGraphicsPathItem
{
public:
    explicit BrokenOutOutlineItem(QGraphicsItem* parent)
        : QGraphicsPathItem(parent)
    {}

    QPainterPath shape() const override
    {
        QPainterPathStroker stroker;
        stroker.setWidth(std::max(6.0, pen().widthF()));
        return stroker.createStroke(path());
    }
};

class BrokenOutPointHandle final : public QGraphicsEllipseItem
{
public:
    BrokenOutPointHandle()
        : QGraphicsEllipseItem(
              -HandleRadius, -HandleRadius,
              2.0 * HandleRadius, 2.0 * HandleRadius)
    {
        setFlag(QGraphicsItem::ItemIgnoresTransformations);
        setAcceptedMouseButtons(Qt::LeftButton);
        setAcceptHoverEvents(true);
        setCursor(Qt::OpenHandCursor);
        setZValue(1007.0);
    }

    QRectF boundingRect() const override
    {
        return {-HitDistancePixels, -HitDistancePixels,
                2.0 * HitDistancePixels, 2.0 * HitDistancePixels};
    }

    QPainterPath shape() const override
    {
        QPainterPath hitShape;
        hitShape.addEllipse(QPointF(), HitDistancePixels, HitDistancePixels);
        return hitShape;
    }

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
};

class BrokenOutSectionHandler final : public TechDrawHandler
{
public:
    BrokenOutSectionHandler(TaskBrokenOutSection* task,
                            DrawViewBrokenOutSection* section = nullptr,
                            DrawViewPart* base = nullptr)
        : m_task(task), m_base(base), m_section(section),
          m_editingExisting(section != nullptr)
    {
        m_depthConnection = QObject::connect(
            task, &TaskBrokenOutSection::depthChanged, task,
            [this](double depth) { updateDepth(depth); });
        m_resetConnection = QObject::connect(
            task, &TaskBrokenOutSection::resetOutlineRequested, task,
            [this]() { resetOutline(); });
    }

    ~BrokenOutSectionHandler() override
    {
        QObject::disconnect(m_depthConnection);
        QObject::disconnect(m_resetConnection);
        clearGraphics();
        selectBase(nullptr);
    }

    void initializeFromFeature()
    {
        if (!m_section || !m_base || !viewPage || !viewPage->getScene()) {
            return;
        }
        for (QGraphicsItem* item : viewPage->getScene()->items()) {
            auto* view = dynamic_cast<QGIViewPart*>(item);
            if (view && view->getViewObject() == m_base) {
                selectBase(view);
                break;
            }
        }
        if (!m_baseItem) {
            return;
        }
        for (const Base::Vector3d& point : m_section->Outline.getValues()) {
            const Base::Vector3d displayed = m_base->mapPointToBrokenView(point);
            m_points.emplace_back(Rez::guiX(displayed.x), -Rez::guiX(displayed.y));
        }
        m_task->setDepth(m_section->Depth.getValue());
        m_task->setOutlineComplete(true);
        m_mode = Mode::Adjust;
        makeGraphics();
        updateGraphics();
        updateHint();
    }

    void mouseMoveEvent(QMouseEvent* event) override
    {
        if (!viewPage || !m_task) {
            return;
        }
        if (m_mode == Mode::FindView) {
            QGIViewPart* hovered = findView(event->pos());
            if (hovered != m_baseItem) {
                selectBase(hovered);
                m_base = hovered
                    ? dynamic_cast<DrawViewPart*>(hovered->getViewObject())
                    : nullptr;
            }
            event->accept();
            return;
        }
        if (!m_baseItem || !m_base) {
            return;
        }

        const QPointF local = localPoint(event->pos());
        if (m_mode == Mode::Draw) {
            m_cursorPoint = local;
            updateGraphics();
            event->accept();
        }
        else if (m_dragIndex >= 0) {
            m_points[static_cast<size_t>(m_dragIndex)] = local;
            updateGraphics();
            updateObject();
            event->accept();
        }
    }

    void mousePressEvent(QMouseEvent* event) override
    {
        if (event->button() != Qt::LeftButton || !m_baseItem || !m_base) {
            return;
        }
        const QPointF local = localPoint(event->pos());
        if (m_mode == Mode::FindView) {
            m_mode = Mode::Draw;
            m_points.push_back(local);
            m_cursorPoint = local;
            makeGraphics();
            updateGraphics();
            updateHint();
            event->accept();
            return;
        }
        if (m_mode == Mode::Draw) {
            if (m_points.size() >= 3
                && viewportDistance(local, m_points.front()) <= HitDistancePixels) {
                completeOutline();
            }
            else {
                m_points.push_back(local);
                m_cursorPoint = local;
                updateGraphics();
            }
            event->accept();
            return;
        }

        m_selectedIndex = nearestPoint(local);
        m_dragIndex = m_selectedIndex;
        updateGraphics();
        event->accept();
    }

    void mouseDoubleClickEvent(QMouseEvent* event) override
    {
        if (event->button() != Qt::LeftButton || m_mode != Mode::Adjust
            || !m_baseItem) {
            return;
        }
        const QPointF local = localPoint(event->pos());
        if (distanceToOutline(local) > HitDistancePixels) {
            return;
        }
        const size_t insertAt = nearestSegment(local) + 1;
        m_points.insert(m_points.begin() + static_cast<std::ptrdiff_t>(insertAt), local);
        m_selectedIndex = static_cast<int>(insertAt);
        updateGraphics();
        updateObject();
        event->accept();
    }

    void mouseReleaseEvent(QMouseEvent* event) override
    {
        if (event->button() == Qt::RightButton) {
            if (m_mode == Mode::Draw) {
                if (m_editingExisting) {
                    m_points.clear();
                    m_selectedIndex = -1;
                    m_dragIndex = -1;
                    clearGraphics();
                    makeGraphics();
                    updateHint();
                }
                else {
                    resetDrawing();
                }
            }
            else if (m_mode == Mode::FindView) {
                QTimer::singleShot(0, Gui::getMainWindow(),
                                   []() { Gui::Control().closeDialog(); });
            }
            event->accept();
            return;
        }
        if (event->button() == Qt::LeftButton) {
            m_dragIndex = -1;
            if (viewPage->getScene()) {
                viewPage->getScene()->clearSelection();
            }
            Gui::Selection().clearSelection();
            event->accept();
            return;
        }
        TechDrawHandler::mouseReleaseEvent(event);
    }

    void keyPressEvent(QKeyEvent* event) override
    {
        if ((event->key() == Qt::Key_Delete || event->key() == Qt::Key_Backspace)
            && m_mode == Mode::Adjust && m_selectedIndex >= 0
            && m_points.size() > 3) {
            m_points.erase(m_points.begin() + m_selectedIndex);
            m_selectedIndex = -1;
            updateGraphics();
            updateObject();
            event->accept();
            return;
        }
        if (event->key() == Qt::Key_Escape) {
            if (m_mode == Mode::Draw) {
                resetDrawing();
            }
            else {
                QTimer::singleShot(0, Gui::getMainWindow(),
                                   []() { Gui::Control().closeDialog(); });
            }
            event->accept();
        }
    }

    void deactivate() override
    {
        clearGraphics();
        selectBase(nullptr);
        TechDrawHandler::deactivate();
    }

private:
    enum class Mode { FindView, Draw, Adjust };

    std::list<Gui::InputHint> getToolHints() const override
    {
        using enum Gui::InputHint::UserInput;
        if (m_mode == Mode::FindView) {
            return {{QObject::tr("%1 choose a view and place the first point"), {MouseLeft}},
                    {QObject::tr("%1 close broken-out section tool"), {MouseRight}}};
        }
        if (m_mode == Mode::Draw) {
            return {{QObject::tr("%1 add spline point; click first point to close"), {MouseLeft}},
                    {QObject::tr("%1 restart outline"), {MouseRight}}};
        }
        return {{QObject::tr("%1 drag a spline point"), {{MouseLeft, MouseMove}}},
                {QObject::tr("%1 double-click outline to add a point"), {MouseLeft}},
                {QObject::tr("%1 select point and press Delete to remove it"), {KeyDelete}}};
    }

    QString getCrosshairCursorSVGName() const override
    {
        return QStringLiteral("TechDraw_BrokenOutSectionView_Pointer");
    }

    QGIViewPart* findView(const QPoint& viewportPoint)
    {
        const QList<QGraphicsItem*> items = viewPage->items(viewportPoint);
        for (QGraphicsItem* item : items) {
            for (QGraphicsItem* parent = item; parent; parent = parent->parentItem()) {
                auto* view = dynamic_cast<QGIViewPart*>(parent);
                auto* object = view
                    ? dynamic_cast<DrawViewPart*>(view->getViewObject()) : nullptr;
                if (view && view->isVisible() && object
                    && object->findParentPage() == getPage()) {
                    return view;
                }
            }
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

    QPointF localPoint(const QPoint& viewportPoint) const
    {
        return m_baseItem->mapFromScene(viewPage->mapToScene(viewportPoint));
    }

    double viewportDistance(const QPointF& first, const QPointF& second) const
    {
        const QPoint a = viewPage->mapFromScene(m_baseItem->mapToScene(first));
        const QPoint b = viewPage->mapFromScene(m_baseItem->mapToScene(second));
        return std::hypot(a.x() - b.x(), a.y() - b.y());
    }

    int nearestPoint(const QPointF& point) const
    {
        int result = -1;
        double best = HitDistancePixels;
        for (size_t i = 0; i < m_points.size(); ++i) {
            const double distance = viewportDistance(point, m_points[i]);
            if (distance <= best) {
                best = distance;
                result = static_cast<int>(i);
            }
        }
        return result;
    }

    size_t nearestSegment(const QPointF& point) const
    {
        size_t result = 0;
        double best = std::numeric_limits<double>::max();
        for (size_t i = 0; i < m_points.size(); ++i) {
            const QPointF first = m_points[i];
            const QPointF second = m_points[(i + 1) % m_points.size()];
            const QPointF segment = second - first;
            const double lengthSquared = QPointF::dotProduct(segment, segment);
            const double parameter = lengthSquared > 1.0e-12
                ? std::clamp(QPointF::dotProduct(point - first, segment) / lengthSquared,
                             0.0, 1.0) : 0.0;
            const QPointF candidate = first + segment * parameter;
            const QPointF delta = candidate - point;
            const double distance = QPointF::dotProduct(delta, delta);
            if (distance < best) {
                best = distance;
                result = i;
            }
        }
        return result;
    }

    double distanceToOutline(const QPointF& point) const
    {
        const QPainterPath path = periodicSplinePath(m_points);
        double best = std::numeric_limits<double>::max();
        for (const QPolygonF& polygon : path.toSubpathPolygons()) {
            for (qsizetype i = 1; i < polygon.size(); ++i) {
                const QPointF first = polygon[i - 1];
                const QPointF segment = polygon[i] - first;
                const double lengthSquared = QPointF::dotProduct(segment, segment);
                const double parameter = lengthSquared > 1.0e-12
                    ? std::clamp(QPointF::dotProduct(point - first, segment) / lengthSquared,
                                 0.0, 1.0) : 0.0;
                const QPointF candidate = first + segment * parameter;
                best = std::min(best, viewportDistance(point, candidate));
            }
        }
        return best;
    }

    void makeGraphics()
    {
        if (m_outline || !viewPage || !viewPage->getScene()) {
            return;
        }
        QPen pen(QColor(35, 95, 210), 2.0, Qt::SolidLine,
                 Qt::RoundCap, Qt::RoundJoin);
        pen.setCosmetic(true);
        m_outline = new BrokenOutOutlineItem(m_baseItem);
        m_outline->setPen(pen);
        m_outline->setZValue(ZVALUE::EDGE + 0.5);
        m_outline->setCursor(viewPage->viewport()->cursor());
        m_outline->setAcceptHoverEvents(true);
        m_outline->setAcceptedMouseButtons(Qt::NoButton);
    }

    void updateGraphics()
    {
        makeGraphics();
        QPainterPath localPath;
        if (m_mode == Mode::Adjust) {
            localPath = periodicSplinePath(m_points);
        }
        else if (!m_points.empty()) {
            localPath.moveTo(m_points.front());
            for (size_t i = 1; i < m_points.size(); ++i) {
                localPath.lineTo(m_points[i]);
            }
            localPath.lineTo(m_cursorPoint);
        }
        m_outline->setPath(localPath);

        while (m_handles.size() > m_points.size()) {
            delete m_handles.back();
            m_handles.pop_back();
        }
        while (m_handles.size() < m_points.size()) {
            auto* handle = new BrokenOutPointHandle();
            viewPage->getScene()->addItem(handle);
            m_handles.push_back(handle);
        }
        for (size_t i = 0; i < m_points.size(); ++i) {
            const QPointF scene = m_baseItem->mapToScene(m_points[i]);
            BrokenOutPointHandle* handle = m_handles[i];
            handle->setPos(scene);
            const bool selected = static_cast<int>(i) == m_selectedIndex;
            const QColor color = selected ? QColor(220, 70, 40) : QColor(35, 95, 210);
            handle->setPen(QPen(color, 1.0));
            handle->setBrush(color);
        }
    }

    void clearGraphics()
    {
        delete m_outline;
        m_outline = nullptr;
        for (auto* handle : m_handles) {
            delete handle;
        }
        m_handles.clear();
    }

    std::vector<Base::Vector3d> modelPoints() const
    {
        std::vector<Base::Vector3d> result;
        result.reserve(m_points.size());
        const double scale = m_base->getScale();
        for (const QPointF& point : m_points) {
            const Base::Vector3d displayed(
                Rez::appX(point.x()) / scale,
                -Rez::appX(point.y()) / scale,
                0.0);
            result.push_back(m_base->mapPointFromBrokenView(displayed));
        }
        return result;
    }

    void completeOutline()
    {
        if (m_section && m_editingExisting) {
            m_section->Outline.setValues(modelPoints());
            m_section->Depth.setValue(m_task->depth());
        }
        else {
            m_section = m_base->addBrokenOutSection(modelPoints(), m_task->depth());
        }
        if (!m_section) {
            return;
        }
        m_mode = Mode::Adjust;
        m_selectedIndex = -1;
        m_task->setOutlineComplete(true);
        updateGraphics();
        recompute();
        updateHint();
    }

    void updateObject()
    {
        if (!m_section) {
            return;
        }
        m_section->Outline.setValues(modelPoints());
        recompute();
    }

    void updateDepth(double depth)
    {
        if (!m_section) {
            return;
        }
        m_section->Depth.setValue(depth);
        recompute();
    }

    void recompute()
    {
        if (!m_base) {
            return;
        }
        m_base->recomputeFeature();
        m_base->requestPaint();
    }

    void resetDrawing()
    {
        m_points.clear();
        m_selectedIndex = -1;
        m_dragIndex = -1;
        clearGraphics();
        selectBase(nullptr);
        m_base = nullptr;
        m_mode = Mode::FindView;
        updateHint();
    }

    void resetOutline()
    {
        if (m_section && m_editingExisting) {
            m_section->Outline.setValues(std::vector<Base::Vector3d>{});
            m_points.clear();
            m_selectedIndex = -1;
            m_dragIndex = -1;
            clearGraphics();
            makeGraphics();
            m_mode = Mode::Draw;
            m_task->setOutlineComplete(false);
            recompute();
            updateHint();
            return;
        }
        if (m_section && m_section->getDocument()) {
            App::Document* document = m_section->getDocument();
            document->removeObject(m_section->getNameInDocument());
        }
        m_section = nullptr;
        recompute();
        m_task->setOutlineComplete(false);
        resetDrawing();
        if (viewPage && viewPage->getScene()) {
            viewPage->getScene()->update();
        }
    }

    TaskBrokenOutSection* m_task{nullptr};
    QGIViewPart* m_baseItem{nullptr};
    DrawViewPart* m_base{nullptr};
    DrawViewBrokenOutSection* m_section{nullptr};
    QGraphicsPathItem* m_outline{nullptr};
    std::vector<BrokenOutPointHandle*> m_handles;
    std::vector<QPointF> m_points;
    QPointF m_cursorPoint;
    int m_selectedIndex{-1};
    int m_dragIndex{-1};
    Mode m_mode{Mode::FindView};
    QMetaObject::Connection m_depthConnection;
    QMetaObject::Connection m_resetConnection;
    bool m_editingExisting{false};
};

} // namespace

TaskBrokenOutSection::TaskBrokenOutSection(QWidget* parent)
    : QWidget(parent), ui(new Ui_TaskBrokenOutSection)
{
    ui->setupUi(this);
    connect(ui->depthSpin, qOverload<double>(&QDoubleSpinBox::valueChanged),
            this, &TaskBrokenOutSection::depthChanged);
    connect(ui->resetButton, &QPushButton::clicked,
            this, &TaskBrokenOutSection::resetOutlineRequested);
}

TaskBrokenOutSection::~TaskBrokenOutSection() = default;

double TaskBrokenOutSection::depth() const
{
    return ui->depthSpin->value();
}

void TaskBrokenOutSection::setOutlineComplete(bool complete)
{
    if (m_outlineComplete == complete) {
        return;
    }
    m_outlineComplete = complete;
    ui->resetButton->setVisible(complete);
    Q_EMIT outlineCompleteChanged(complete);
}

void TaskBrokenOutSection::setDepth(double depth)
{
    ui->depthSpin->setValue(depth);
}

TaskDlgBrokenOutSection::TaskDlgBrokenOutSection(DrawPage* page, QGVPage* graphicsView)
    : m_page(page), m_graphicsView(graphicsView)
{
    m_widget = new TaskBrokenOutSection();
    m_taskBox = new Gui::TaskView::TaskBox(
        Gui::BitmapFactory().pixmap("actions/TechDraw_BrokenOutSectionView"),
        m_widget->windowTitle(), true, nullptr);
    m_taskBox->groupLayout()->addWidget(m_widget);
    Content.push_back(m_taskBox);
}

TaskDlgBrokenOutSection::TaskDlgBrokenOutSection(
    DrawViewBrokenOutSection* section,
    DrawViewPart* base,
    QGVPage* graphicsView)
    : TaskDlgBrokenOutSection(base ? base->findParentPage() : nullptr, graphicsView)
{
    m_section = section;
    m_base = base;
}

TaskDlgBrokenOutSection::~TaskDlgBrokenOutSection()
{
    if (m_graphicsView && m_graphicsView->isHandlerActive()) {
        m_graphicsView->deactivateHandler();
    }
    if (m_transactionOpen) {
        App::Document* document = m_base ? m_base->getDocument()
                                         : (m_page ? m_page->getDocument() : nullptr);
        if (document) {
            document->abortTransaction();
        }
    }
}

void TaskDlgBrokenOutSection::open()
{
    App::Document* document = m_base ? m_base->getDocument()
                                     : (m_page ? m_page->getDocument() : nullptr);
    if (document && !m_transactionOpen) {
        document->openTransaction(
            QT_TRANSLATE_NOOP("Command", "Create or edit broken-out section"));
        m_transactionOpen = true;
    }
    if (m_graphicsView) {
        auto* handler = new BrokenOutSectionHandler(m_widget, m_section, m_base);
        m_graphicsView->activateHandler(handler);
        handler->initializeFromFeature();
    }
}

bool TaskDlgBrokenOutSection::accept()
{
    if (!m_widget->hasCompleteOutline()) {
        return false;
    }
    App::Document* document = m_base ? m_base->getDocument()
                                     : (m_page ? m_page->getDocument() : nullptr);
    if (document && m_transactionOpen) {
        document->commitTransaction();
        m_transactionOpen = false;
    }

    if (document) {
        document->recompute();
    }
    return true;
}

void TaskDlgBrokenOutSection::modifyStandardButtons(QDialogButtonBox* buttonBox)
{
    if (QPushButton* okButton = buttonBox->button(QDialogButtonBox::Ok)) {
        okButton->setEnabled(m_widget->hasCompleteOutline());
        connect(m_widget, &TaskBrokenOutSection::outlineCompleteChanged,
                okButton, &QPushButton::setEnabled);
    }
}

bool TaskDlgBrokenOutSection::reject()
{
    App::Document* document = m_base ? m_base->getDocument()
                                     : (m_page ? m_page->getDocument() : nullptr);
    if (document && m_transactionOpen) {
        document->abortTransaction();
        m_transactionOpen = false;
        document->recompute();
    }
    if (m_base) {
        m_base->recomputeFeature();
        m_base->requestPaint();
    }
    return true;
}

#include <Mod/TechDraw/Gui/moc_TaskBrokenOutSection.cpp>
