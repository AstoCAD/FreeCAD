/***************************************************************************
 *   Copyright (c) 2016 WandererFan <wandererfan@gmail.com>                *
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

#include <Mod/TechDraw/TechDrawGlobal.h>

#include <QColor>
#include <QFont>
#include <QGraphicsEllipseItem>
#include <QGraphicsPathItem>
#include <QGraphicsScene>
#include <QMetaObject>
#include <QPointF>

#include "QGCustomText.h"
#include "QGCustomRect.h"
#include "QGIDecoration.h"
#include "QGIUserTypes.h"


namespace TechDrawGui
{

class QGIArrow;
class QGIView;

class TechDrawGuiExport QGIHighlight : public QGIDecoration
{
public:
    explicit QGIHighlight();
    ~QGIHighlight() override;

    enum {Type = UserType::QGIHighlight};
    int type() const override { return Type;}

    void paint(QPainter * painter,
               const QStyleOptionGraphicsItem * option,
               QWidget * widget = nullptr ) override;

    void setBounds(double x1, double y1, double x2, double y2);
    void setReference(const char* sym);
    void setFont(QFont f, double fsize);
    void draw() override;
    void setInteractive(bool state);
    void setFeatureName(std::string name) { m_featureName = name; }
    std::string getFeatureName() { return m_featureName; }
    void setReferenceAngle(double angle) { m_referenceAngle = angle; }
    QRectF referenceSceneBoundingRect() const;
    void setConnector(QGIView* source, QGIView* target, double targetRadius);

    void onDragFinished() override;

    void setLinePen(QPen isoPen);

protected:
    QColor getHighlightColor();
    void makeHighlight();
    void makeReference();
    void makeConnector();
    void setTools();
    int getHoleStyle();

private:
    QString            m_refText;
    QGraphicsEllipseItem* m_circle;
    QGCustomRect*      m_rect;
    QGCustomText*      m_reference;
    QGraphicsPathItem* m_connectorLine;
    QGIArrow*          m_connectorArrow;
    QGIView*           m_connectorSource{nullptr};
    QGIView*           m_connectorTarget{nullptr};
    double             m_connectorTargetRadius{0.0};
    QMetaObject::Connection m_sourcePositionConnection;
    QMetaObject::Connection m_targetPositionConnection;
    QMetaObject::Connection m_targetDestroyedConnection;
    std::string        m_refFontName;
    QFont              m_refFont;
    double             m_refSize;
    QPointF            m_start;
    QPointF            m_end;
    std::string        m_featureName;
    double             m_referenceAngle;
};

}
