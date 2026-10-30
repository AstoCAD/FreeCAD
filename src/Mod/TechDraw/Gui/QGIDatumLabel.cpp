// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2013 Luke Parry <l.parry@warwick.ac.uk>                 *
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

#include <QApplication>
#include <QGraphicsSceneMouseEvent>

#include <Gui/Application.h>
#include <Mod/TechDraw/App/DimensionFormatter.h>
#include <Mod/TechDraw/App/DimensionGeometry.h>
#include <Mod/TechDraw/App/DrawViewDimension.h>
#include <Mod/TechDraw/App/Preferences.h>

#include "PreferencesGui.h"
#include "QGCustomText.h"
#include "QGIDatumLabel.h"
#include "QGIViewDimension.h"
#include "TaskSelectLineAttributes.h"
#include "ViewProviderDimension.h"


#define NORMAL 0
#define PRE 1
#define SEL 2

using namespace TechDraw;
using Format = DimensionFormatter::Format;

namespace TechDrawGui {

QGIDatumLabel::QGIDatumLabel() : m_dragState(DragState::NoDrag)
{
    verticalSep = false;

    parent = nullptr;

    setCacheMode(QGraphicsItem::NoCache);
    setFlag(ItemSendsGeometryChanges, true);
    setFlag(ItemIsMovable, true);
    setSelectability(true);
    setFiltersChildEvents(true);

    m_textItems = new QGraphicsItemGroup();
    m_textItems->setParentItem(this);
    m_dimText = new QGCustomText();
    m_dimText->setTightBounding(true);
    m_dimText->setParentItem(m_textItems);
    m_tolTextOver = new QGCustomText();
    m_tolTextOver->setTightBounding(true);
    m_tolTextOver->setParentItem(m_textItems);
    m_tolTextUnder = new QGCustomText();
    m_tolTextUnder->setTightBounding(true);
    m_tolTextUnder->setParentItem(m_textItems);
    m_unitText = new QGCustomText();
    m_unitText->setTightBounding(true);
    m_unitText->setParentItem(m_textItems);

    m_frame = new QGraphicsRectItem();
    QPen framePen;
    framePen.setWidthF(Rez::guiX(0.5));
    framePen.setColor(m_dimText->defaultTextColor());
    framePen.setJoinStyle(Qt::MiterJoin);
    m_frame->setPen(framePen);

    m_ctrl = false;
}

void QGIDatumLabel::setFramed(bool framed)
{
    if(framed) {
        m_frame->setVisible(true);
        m_frame->setParentItem(this);
    }
    else {
        m_frame->setVisible(false);
        m_frame->setParentItem(nullptr);
    }
}

QVariant QGIDatumLabel::itemChange(GraphicsItemChange change, const QVariant& value)
{
    if (change == ItemSelectedHasChanged && scene()) {
        if (isSelected()) {
            setPrettySel();
        }
        else {
            setPrettyNormal();
            if (m_dragState == DragState::Dragging) {
                //stop the drag if we are no longer selected.
                m_dragState = DragState::NoDrag;
                Q_EMIT dragFinished();
            }
        }
    }
    else if (change == ItemPositionHasChanged && scene()) {
        if (!(QApplication::keyboardModifiers() & Qt::AltModifier)) {
            QPointF newPos = value.toPointF();    //position within parent!
            if (!m_inhibitSnapOnPosChange) {
                // we don't want to snap if snap caused this position change
                snapPosition(newPos);
            }
            m_inhibitSnapOnPosChange = false;
        }

        m_dragState = DragState::Dragging;
        Q_EMIT dragging(m_ctrl);
    }

    return QGraphicsItem::itemChange(change, value);
}

void QGIDatumLabel::snapPosition(QPointF& pos)
{
    auto* qgivd = dynamic_cast<QGIViewDimension*>(parentItem());
    if (!qgivd) {
        return;
    }
    auto* dim(dynamic_cast<TechDraw::DrawViewDimension*>(qgivd->getViewObject()));
    if (!dim) {
        return;
    }

    auto* vp = freecad_cast<ViewProviderDimension*>(Gui::Application::Instance->getViewProvider(dim));
    if (!vp || !vp->AllowSnap.getValue()) {
        return;
    }

    // Each kind of dimension has its own snapping rules
    std::string type = dim->Type.getValueAsString();
    bool snapped = false;
    if (type == "Distance" || type == "DistanceX" || type == "DistanceY") {
        snapped = snapDistance(pos, dim, qgivd);
    }
    else if (type == "Radius" || type == "Diameter") {
        snapped = snapRadial(pos, dim, qgivd, vp);
    }
    else if (type == "Angle" || type == "Angle3Pt") {
        snapped = snapAngle(pos, dim, qgivd);
    }
    if (!snapped) {
        return;
    }

    // block itemChange from calling snapPosition again
    m_inhibitSnapOnPosChange = true;
    setPos(pos);
}

//! Snap a linear dimension label to the middle of its dimension line, and in line or one
//! spacing apart from the labels of parallel dimensions (chained or cascaded dimensions).
bool QGIDatumLabel::snapDistance(QPointF& pos, TechDraw::DrawViewDimension* dim,
                                 QGIViewDimension* qgivd)
{
    std::string type = dim->Type.getValueAsString();
    bool snapped = false;
    qreal snapTextPercent = Preferences::SnapDimensionsTextFactor();
    double dimSpacing = Rez::guiX(activeDimAttributes.getCascadeSpacing());

    // 1 - We try to snap the label to its center position.
    pointPair pp = dim->getLinearPoints();
    if (pp.first().IsEqual(pp.second(), EWTOLERANCE)) {
        // probably a broken dim
        return false;
    }
    Base::Vector3d p1_3d = Rez::guiX(pp.first());
    Base::Vector3d p2_3d = Rez::guiX(pp.second());
    Base::Vector2d p1 = Base::Vector2d(p1_3d.x, p1_3d.y);
    Base::Vector2d p2 = Base::Vector2d(p2_3d.x, p2_3d.y);
    if (type == "DistanceX") {
        p2 = Base::Vector2d(p2.x, p1.y);
    }
    else if (type == "DistanceY") {
        p2 = Base::Vector2d(p1.x, p2.y);
    }
    Base::Vector2d mid = (p1 + p2) * 0.5;
    Base::Vector2d dir = p2 - p1;
    Base::Vector2d normal = Base::Vector2d(-dir.y, dir.x);

    Base::Vector2d toCenter = getPosToCenterVec();

    Base::Vector2d posV = Base::Vector2d(pos.x(), pos.y()) + toCenter;

    Base::Vector2d projPnt;
    projPnt.ProjectToLine(posV - mid, normal);
    projPnt = projPnt + mid;

    if ((projPnt - posV).Length() < dimSpacing * snapTextPercent) {
        posV = projPnt;
        pos.setX(posV.x - toCenter.x);
        pos.setY(posV.y - toCenter.y);
        snapped = true;
    }

    // 2 - We check for coord/chain dimensions to offer proper snapping
    double snapChainPercent = Preferences::SnapDimensionsChainFactor();
    auto* qgiv = dynamic_cast<QGIView*>(qgivd->parentItem());
    if (qgiv) {
        auto* dvp = dynamic_cast<TechDraw::DrawViewPart*>(qgiv->getViewObject());
        if (dvp) {
            std::vector<TechDraw::DrawViewDimension*> dims = dvp->getDimensions();
            for (auto& d : dims) {
                if (d == dim) { continue; }

                std::string typei = d->Type.getValueAsString();
                if (typei != "Distance" && typei != "DistanceX" && typei != "DistanceY") {
                    continue;
                }

                pp = d->getLinearPoints();
                Base::Vector3d ip1_3d = Rez::guiX(pp.first());
                Base::Vector3d ip2_3d = Rez::guiX(pp.second());

                Base::Vector2d ip1 = Base::Vector2d(ip1_3d.x, ip1_3d.y);
                Base::Vector2d ip2 = Base::Vector2d(ip2_3d.x, ip2_3d.y);
                if (typei == "DistanceX") {
                    ip2 = Base::Vector2d(ip2.x, ip1.y);
                }
                else if (typei == "DistanceY") {
                    ip2 = Base::Vector2d(ip1.x, ip2.y);
                }

                Base::Vector2d idir = ip2 - ip1;

                if (fabs(dir.x * idir.y - dir.y * idir.x) > Precision::Confusion()) {
                    //dimensions not parallel
                    continue;
                }

                auto* vp = freecad_cast<ViewProviderDimension*>(Gui::Application::Instance->getViewProvider(d));
                if (!vp) { continue; }
                auto* qgivDi(dynamic_cast<QGIViewDimension*>(vp->getQView()));
                if (!qgivDi) { continue; }
                auto labeli = qgivDi->getDatumLabel();
                if (!labeli) { continue; }
                QPointF posi = labeli->pos();
                Base::Vector2d toCenteri = labeli->getPosToCenterVec();
                Base::Vector2d posVi = Base::Vector2d(posi.x(), posi.y()) + toCenteri;

                Base::Vector2d projPnt2;
                projPnt2.ProjectToLine(posV - posVi, idir);
                projPnt2 = projPnt2 + posVi;

                if ((projPnt2 - posV).Length() < dimSpacing * snapChainPercent) {
                    posV = projPnt2;
                    pos.setX(posV.x - toCenter.x);
                    pos.setY(posV.y - toCenter.y);
                    snapped = true;
                    break;
                }
                else if (fabs((projPnt2 - posV).Length() - fabs(dimSpacing)) < dimSpacing * snapChainPercent) {
                    posV = projPnt2 + (posV - projPnt2).Normalize() * dimSpacing;
                    pos.setX(posV.x - toCenter.x);
                    pos.setY(posV.y - toCenter.y);
                    snapped = true;
                    break;
                }
            }
        }
    }

    return snapped;
}

//! Snap a radius label to the middle of the radius line, and a diameter label to the center
//! of the diameter line. Only the styles where the label follows the line are concerned.
bool QGIDatumLabel::snapRadial(QPointF& pos, TechDraw::DrawViewDimension* dim,
                               QGIViewDimension* qgivd, ViewProviderDimension* vp)
{
    int style = vp->StandardAndStyle.getValue();
    bool isoOriented = style == ViewProviderDimension::STD_STYLE_ISO_ORIENTED;
    if (!isoOriented && style != ViewProviderDimension::STD_STYLE_ASME_INLINED) {
        return false;
    }

    // the angle of the line as last drawn, from the center towards the arc
    std::optional<double> lineAngle = qgivd->getRadialLineAngle();
    if (!lineAngle.has_value()) {
        return false;
    }

    arcPoints arc = dim->getArcPoints();
    double radius = Rez::guiX(arc.radius);
    if (radius < Precision::Confusion()) {
        // probably a broken dim
        return false;
    }
    Base::Vector3d center3d = Rez::guiX(arc.center);
    Base::Vector2d center(center3d.x, center3d.y);

    // the line angle is measured with Y up, the label is placed with Y down
    Base::Vector2d lineDir = Base::Vector2d::FromPolar(1.0, -lineAngle.value());
    Base::Vector2d normal = lineDir.Perpendicular();
    Base::Vector2d mid = center;
    if (std::string(dim->Type.getValueAsString()) == "Radius") {
        mid += lineDir * (radius * 0.5);
    }

    Base::Vector2d toCenter = getPosToCenterVec();
    Base::Vector2d labelCenter = Base::Vector2d(pos.x(), pos.y()) + toCenter;

    // ASME centers the label on the line. ISO keeps it beside the line, on its current side,
    // at the distance used by QGIViewDimension, which measures the label before rotating it.
    // The hair more keeps the redrawn line angle defined when the label sits next to the
    // center of a diameter.
    double lineLabelDistance = 0.0;
    if (isoOriented) {
        lineLabelDistance = tightBoundingRect().height() * 0.5
            + Rez::guiX(qgivd->getIsoDimensionLineSpacing());
        lineLabelDistance *= 1.0 + 1e-6;
    }
    double side = (labelCenter - mid) * normal >= 0.0 ? 1.0 : -1.0;
    Base::Vector2d target = mid + normal * (side * lineLabelDistance);

    qreal snapTextPercent = Preferences::SnapDimensionsTextFactor();
    double dimSpacing = Rez::guiX(activeDimAttributes.getCascadeSpacing());
    if ((target - labelCenter).Length() >= dimSpacing * snapTextPercent) {
        return false;
    }

    pos.setX(target.x - toCenter.x);
    pos.setY(target.y - toCenter.y);
    return true;
}

//! Snap an angle label to the bisector of the angle, and its arc on or one spacing apart
//! from the arcs of other angle dimensions with the same vertex (chained or cascaded angles).
bool QGIDatumLabel::snapAngle(QPointF& pos, TechDraw::DrawViewDimension* dim,
                              QGIViewDimension* qgivd)
{
    anglePoints ap = dim->getAnglePoints();
    if (ap.first().IsEqual(ap.vertex(), EWTOLERANCE)
        || ap.second().IsEqual(ap.vertex(), EWTOLERANCE)) {
        // probably a broken dim
        return false;
    }
    Base::Vector3d vertex3d = Rez::guiX(ap.vertex());
    Base::Vector3d first3d = Rez::guiX(ap.first());
    Base::Vector3d second3d = Rez::guiX(ap.second());
    Base::Vector2d vertex(vertex3d.x, vertex3d.y);
    Base::Vector2d leg1 = Base::Vector2d(first3d.x, first3d.y) - vertex;
    Base::Vector2d leg2 = Base::Vector2d(second3d.x, second3d.y) - vertex;
    leg1.Normalize();
    leg2.Normalize();
    if (dim->ShowSupplementary.getValue()) {
        // as drawn by QGIViewDimension::drawAngle
        leg1.Negate();
    }

    bool snapped = false;
    qreal snapTextPercent = Preferences::SnapDimensionsTextFactor();
    double dimSpacing = Rez::guiX(activeDimAttributes.getCascadeSpacing());

    Base::Vector2d toCenter = getPosToCenterVec();
    Base::Vector2d labelCenter = Base::Vector2d(pos.x(), pos.y()) + toCenter;

    // 1 - We try to snap the label to the bisector of the angle.
    Base::Vector2d bisector = leg1 + leg2;
    if (bisector.Length() < Precision::Confusion()) {
        // straight angle
        bisector = leg1.Perpendicular();
    }
    Base::Vector2d projPnt;
    projPnt.ProjectToLine(labelCenter - vertex, bisector);
    projPnt = projPnt + vertex;
    if ((projPnt - labelCenter).Length() < dimSpacing * snapTextPercent) {
        labelCenter = projPnt;
        snapped = true;
    }

    // 2 - We check for other angles around the same vertex to align or cascade the arcs.
    std::optional<double> labelOffset = qgivd->getAngleLabelOffset();
    Base::Vector2d radial = labelCenter - vertex;
    double labelDistance = radial.Length();
    auto* qgiv = dynamic_cast<QGIView*>(qgivd->parentItem());
    auto* dvp = qgiv ? dynamic_cast<TechDraw::DrawViewPart*>(qgiv->getViewObject()) : nullptr;
    if (dvp && labelOffset.has_value() && labelDistance > Precision::Confusion()) {
        double offset = Rez::guiX(labelOffset.value());  // from the arc to the label center
        double arcRadius = labelDistance - offset;
        double snapChainPercent = Preferences::SnapDimensionsChainFactor();
        double bestGap = dimSpacing * snapChainPercent;
        std::optional<double> bestRadius;
        for (auto& d : dvp->getDimensions()) {
            if (d == dim) {
                continue;
            }
            std::string typei = d->Type.getValueAsString();
            if (typei != "Angle" && typei != "Angle3Pt") {
                continue;
            }
            if (!d->getAnglePoints().vertex().IsEqual(ap.vertex(), EWTOLERANCE)) {
                // not concentric
                continue;
            }
            auto* vpi = freecad_cast<ViewProviderDimension*>(Gui::Application::Instance->getViewProvider(d));
            if (!vpi) {
                continue;
            }
            auto* qgivdi = dynamic_cast<QGIViewDimension*>(vpi->getQView());
            if (!qgivdi || !qgivdi->getAngleArcRadius().has_value()) {
                continue;
            }
            // same arc for chained angles, one spacing inside or outside for cascaded ones
            double arcRadiusi = Rez::guiX(qgivdi->getAngleArcRadius().value());
            for (double candidate : {arcRadiusi, arcRadiusi - dimSpacing, arcRadiusi + dimSpacing}) {
                double gap = fabs(candidate - arcRadius);
                if (candidate > 0.0 && candidate + offset > Precision::Confusion()
                    && gap < bestGap) {
                    bestGap = gap;
                    bestRadius = candidate;
                }
            }
        }
        if (bestRadius.has_value()) {
            labelCenter = vertex + radial * ((bestRadius.value() + offset) / labelDistance);
            snapped = true;
        }
    }

    if (snapped) {
        pos.setX(labelCenter.x - toCenter.x);
        pos.setY(labelCenter.y - toCenter.y);
    }
    return snapped;
}

void QGIDatumLabel::mousePressEvent(QGraphicsSceneMouseEvent* event)
{
    if (event->modifiers() & Qt::ControlModifier) {
        m_ctrl = true;
    }

    QGraphicsItem::mousePressEvent(event);
}

void QGIDatumLabel::mouseReleaseEvent(QGraphicsSceneMouseEvent* event)
{
    //    Base::Console().message("QGIDL::mouseReleaseEvent()\n");
    m_ctrl = false;
    if (m_dragState == DragState::Dragging) {
        m_dragState = DragState::NoDrag;
        Q_EMIT dragFinished();
    }

    QGraphicsItem::mouseReleaseEvent(event);
}

void QGIDatumLabel::mouseDoubleClickEvent(QGraphicsSceneMouseEvent* event)
{
    QGIViewDimension* qgivDimension = dynamic_cast<QGIViewDimension*>(parentItem());
    if (!qgivDimension) {
        qWarning() << "QGIDatumLabel::mouseDoubleClickEvent: No parent item";
        return;
    }

    auto ViewProvider = freecad_cast<ViewProviderDimension*>(
        qgivDimension->getViewProvider(qgivDimension->getViewObject()));
    if (!ViewProvider) {
        qWarning() << "QGIDatumLabel::mouseDoubleClickEvent: No valid view provider";
        return;
    }

    ViewProvider->startDefaultEditMode();
    QGraphicsItem::mouseDoubleClickEvent(event);
}

void QGIDatumLabel::hoverEnterEvent(QGraphicsSceneHoverEvent* event)
{
    Q_EMIT hover(true);
    if (!isSelected()) {
        setPrettyPre();
    }
    else {
        setPrettySel();
    }
    QGraphicsItem::hoverEnterEvent(event);
}

void QGIDatumLabel::hoverLeaveEvent(QGraphicsSceneHoverEvent* event)
{
    Q_EMIT hover(false);
    if (!isSelected()) {
        setPrettyNormal();
    }
    else {
        setPrettySel();
    }

    QGraphicsItem::hoverLeaveEvent(event);
}

QRectF QGIDatumLabel::boundingRect() const
{
    return childrenBoundingRect();
}

QRectF QGIDatumLabel::tightBoundingRect() const
{
    QRectF totalRect;
    for (QGraphicsItem* item : m_textItems->childItems()) {
        auto* customText = dynamic_cast<QGCustomText*>(item);
        if (customText && !customText->toPlainText().isEmpty()) {
            QRectF itemRect = customText->alignmentRect();
            QPointF pos = customText->pos();
            itemRect.translate(pos.x(), pos.y());
            totalRect = totalRect.isNull() ? itemRect : totalRect.united(itemRect);
        }
    }
    int fontSize = m_dimText->font().pixelSize();
    int paddingLeft = fontSize * 0.2;
    int paddingTop = fontSize * 0.1;
    int paddingRight = fontSize * 0.2;
    int paddingBottom = fontSize * 0.1;
    return totalRect.adjusted(-paddingLeft, -paddingTop, paddingRight, paddingBottom);
}

void QGIDatumLabel::updateFrameRect() {
    prepareGeometryChange();
    m_frame->setRect(tightBoundingRect());
}

void QGIDatumLabel::boundingRectChanged()
{
    setTransformOriginPoint(tightBoundingRect().center());
}

void QGIDatumLabel::setLineWidth(double lineWidth)
{
    QPen pen = m_frame->pen();
    pen.setWidthF(lineWidth);
    m_frame->setPen(pen);
}

void QGIDatumLabel::setFrameColor(QColor color)
{
    QPen pen = m_frame->pen();
    pen.setColor(color);
    m_frame->setPen(pen);
}

void QGIDatumLabel::paint(QPainter* painter, const QStyleOptionGraphicsItem* option,
                          QWidget* widget)
{
    Q_UNUSED(widget);
    Q_UNUSED(painter);
    QStyleOptionGraphicsItem myOption(*option);
    myOption.state &= ~QStyle::State_Selected;

    //    painter->setPen(Qt::blue);
    //    painter->drawRect(boundingRect());          //good for debugging
}

void QGIDatumLabel::setPosFromCenter(const double& xCenter, const double& yCenter)
{
    //set label's Qt position(top, left) given boundingRect center point
    Base::Vector2d centerOffset = getPosToCenterVec();
    double xTopLeft = xCenter - centerOffset.x;
    double yTopLeft = yCenter - centerOffset.y;
    setPos(xTopLeft, yTopLeft);
    updateChildren();
}

void QGIDatumLabel::updateChildren()
{
    prepareGeometryChange();
    QString uText = m_unitText->toPlainText();
    if ((uText.size() > 0) && (uText.at(0) != QChar::fromLatin1(' '))) {
        QString vText = m_dimText->toPlainText();
        vText = vText + uText;
        m_dimText->setPlainText(vText);
        m_unitText->setPlainText(QString());
    }

    QRectF labelBox = m_dimText->alignmentRect();
    double right = labelBox.right();
    double middle = labelBox.center().y();

    //set unit position
    QRectF unitBox = m_unitText->alignmentRect();
    double unitWidth = unitBox.width();
    double unitRight = right + unitWidth;
    // Set the m_unitText font *baseline* at same height as the m_dimText font baseline
    m_unitText->setPos(right, 0.0);

    //set tolerance position
    QRectF overBox = m_tolTextOver->alignmentRect();
    double tolLeft  = unitRight;

    // Adjust for difference in tight and original bounding box sizes, note the y-coord down system
    QPointF tol_adj = m_tolTextOver->tightBoundingAdjust();
    m_tolTextOver->justifyLeftAt(tolLeft + tol_adj.x(), middle + tol_adj.y()/2.0, false);
    tol_adj = m_tolTextUnder->tightBoundingAdjust();
    m_tolTextUnder->justifyLeftAt(tolLeft + tol_adj.x(), middle + overBox.height() + tol_adj.y()/2.0, false);
}

Base::Vector2d QGIDatumLabel::getPosToCenterVec() const
{
    QPointF center = tightBoundingRect().center();
    return Base::Vector2d(center.x(), center.y());
}

void QGIDatumLabel::setFont(QFont font)
{
    prepareGeometryChange();
    m_dimText->setFont(font);
    m_unitText->setFont(font);
    QFont tFont(font);
    double fontSize = font.pixelSize();
    double tolAdj = getTolAdjust();
    tFont.setPixelSize(std::max(1, static_cast<int>(fontSize * tolAdj)));
    m_tolTextOver->setFont(tFont);
    m_tolTextUnder->setFont(tFont);
    updateFrameRect();
    boundingRectChanged();
}

void QGIDatumLabel::setDimString(QString text, qreal maxWidth)
{
    prepareGeometryChange();
    m_dimText->setPlainText(text);
    m_dimText->setTextWidth(maxWidth);
    updateFrameRect();
    boundingRectChanged();
}

void QGIDatumLabel::setToleranceString()
{
    prepareGeometryChange();
    QGIViewDimension* qgivd = dynamic_cast<QGIViewDimension*>(parentItem());
    if (!qgivd) {
        return;
    }
    const auto dim(dynamic_cast<TechDraw::DrawViewDimension*>(qgivd->getViewObject()));
    if (!dim) {
        return;
    }

    // skip regular 2 line tolerance formatting when it does not apply
    if (!dim->hasOverUnderTolerance() || dim->EqualTolerance.getValue()
             || dim->TheoreticalExact.getValue()) {
        m_tolTextOver->hide();
        m_tolTextUnder->hide();
        // we must explicitly empty the text otherwise the frame drawn for
        // TheoreticalExact would be as wide as necessary for the text
        m_tolTextOver->setPlainText(QString());
        m_tolTextUnder->setPlainText(QString());
        updateFrameRect();
        boundingRectChanged();
        return;
    }

    std::pair<std::string, std::string> labelTexts;

    if (dim->ArbitraryTolerances.getValue()) {
        labelTexts = dim->getFormattedToleranceValues(Format::FORMATTED);//copy tolerance spec
    }
    else {
        if (dim->isMultiValueSchema()) {
            labelTexts = dim->getFormattedToleranceValues(Format::UNALTERED);//don't format multis
        }
        else {
            labelTexts = dim->getFormattedToleranceValues(Format::FORMATTED);// prefix value [unit] postfix
        }
    }

    if (labelTexts.first.empty()) {
        m_tolTextUnder->hide();
    }
    else {
        if (dim->UnderTolerance.getValue() == 0 &&
            (labelTexts.first.at(0) == '+' ||
             labelTexts.first.at(0) == '-')) {
             labelTexts.first.at(0) = ' ';
        }
        m_tolTextUnder->setPlainText(QString::fromUtf8(labelTexts.first.c_str()));
        m_tolTextUnder->show();
    }

    if (labelTexts.second.empty()) {
        m_tolTextOver->hide();
    }
    else {
        if (dim->OverTolerance.getValue() == 0 &&
            (labelTexts.second.at(0) == '+' ||
             labelTexts.second.at(0) == '-')) {
             labelTexts.second.at(0) = ' ';
        }
        m_tolTextOver->setPlainText(QString::fromUtf8(labelTexts.second.c_str()));
        m_tolTextOver->show();
    }

    updateFrameRect();
    boundingRectChanged();
}



int QGIDatumLabel::getPrecision()
{
    if (Preferences::useGlobalDecimals()) {
        return Base::UnitsApi::getDecimals();
    }
    return Preferences::getPreferenceGroup("Dimensions")->GetInt("AltDecimals", 2);
}

double QGIDatumLabel::getTolAdjust()
{
    return Preferences::getPreferenceGroup("Dimensions")->GetFloat("TolSizeAdjust", 0.50);
}


void QGIDatumLabel::setPrettySel()
{
    //    Base::Console().message("QGIDL::setPrettySel()\n");
    m_dimText->setPrettySel();
    m_tolTextOver->setPrettySel();
    m_tolTextUnder->setPrettySel();
    m_unitText->setPrettySel();
    setFrameColor(PreferencesGui::selectQColor());
    Q_EMIT setPretty(SEL);
}

void QGIDatumLabel::setPrettyPre()
{
    //    Base::Console().message("QGIDL::setPrettyPre()\n");
    m_dimText->setPrettyPre();
    m_tolTextOver->setPrettyPre();
    m_tolTextUnder->setPrettyPre();
    m_unitText->setPrettyPre();
    setFrameColor(PreferencesGui::preselectQColor());
    Q_EMIT setPretty(PRE);
}

void QGIDatumLabel::setPrettyNormal()
{
    //    Base::Console().message("QGIDL::setPrettyNormal()\n");
    m_dimText->setPrettyNormal();
    m_tolTextOver->setPrettyNormal();
    m_tolTextUnder->setPrettyNormal();
    m_unitText->setPrettyNormal();
    setFrameColor(m_colNormal);
    Q_EMIT setPretty(NORMAL);
}

void QGIDatumLabel::setColor(QColor color)
{
    //    Base::Console().message("QGIDL::setColor({})\n", qPrintable(c.name()));
    m_colNormal = color;
    m_dimText->setColor(m_colNormal);
    m_tolTextOver->setColor(m_colNormal);
    m_tolTextUnder->setColor(m_colNormal);
    m_unitText->setColor(m_colNormal);
    setFrameColor(m_colNormal);
}

void QGIDatumLabel::setSelectability(bool val)
{
    setFlag(ItemIsSelectable, val);
    setAcceptHoverEvents(val);
    setAcceptedMouseButtons(val ? Qt::AllButtons : Qt::NoButton);
}

}  // namespace TechDrawGui
