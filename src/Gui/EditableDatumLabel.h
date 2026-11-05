/// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2023 Ondsel <development@ondsel.com>                     *
 *                                                                          *
 *   This file is part of FreeCAD.                                          *
 *                                                                          *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, either version 2.1 of the   *
 *   License, or (at your option) any later version.                        *
 *                                                                          *
 *   FreeCAD is distributed in the hope that it will be useful, but         *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of             *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
 *   Lesser General Public License for more details.                        *
 *                                                                          *
 *   You should have received a copy of the GNU Lesser General Public       *
 *   License along with FreeCAD. If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                       *
 *                                                                          *
 ***************************************************************************/

#pragma once

#include <memory>
#include <string>

#include <QObject>
#include <QPointer>
#include <QLabel>
#include <Base/Unit.h>
#include <Gui/QuantitySpinBox.h>

#include "SoDatumLabel.h"

#include <FCGlobal.h>

class SoNodeSensor;
class SoTransform;
class SoAnnotation;
class SoSwitch;
class SoEventCallback;
class SoPickStyle;
class QLineEdit;

namespace App
{
class DocumentObject;
class Expression;
}  // namespace App

namespace Gui
{

class View3DInventorViewer;


class GuiExport EditableDatumLabel: public QObject
{
    Q_OBJECT
    Q_DISABLE_COPY(EditableDatumLabel)

public:
    enum class Function
    {
        Positioning,
        Dimensioning,
        Forced
    };

    EditableDatumLabel(
        View3DInventorViewer* view,
        const Base::Placement& plc,
        bool autoDistance = false,
        bool avoidMouseCursor = false
    );

    ~EditableDatumLabel() override;

    void activate();
    void deactivate();

    void startEdit(double val, QObject* eventFilteringObj = nullptr, bool visibleToMouse = false);
    void stopEdit(bool writeChanges = true);
    bool isActive() const;
    bool isInEdit() const;
    double getValue() const;
    void setSpinboxValue(double val, const Base::Unit& unit = Base::Unit::Length);
    void setPlacement(const Base::Placement& plc);
    void setColor(SbColor color);
    void setActivatedColor();
    void setDeactivatedColor();
    void setFocus();
    void setPoints(SbVec3f p1, SbVec3f p2);
    void setPoints(Base::Vector3d p1, Base::Vector3d p2);
    void setFocusToSpinbox();
    void clearSelection();  ///< Clears text selection in the spinbox
    void setLabelType(SoDatumLabel::Type type, Function function = Function::Positioning);
    void setLabelDistance(double val);
    void setLabelStartAngle(double val);
    void setLabelRange(double val);
    void setLabelRecommendedDistance();
    void setLabelAutoDistanceReverse(bool val);
    void setSpinboxVisibleToMouse(bool val);
    void setPickable(bool val);
    void setLockedAppearance(bool locked);  ///< Sets visual appearance to indicate locked state
                                            ///< (finished editing)
    void resetLockedState();  ///< Resets both hasFinishedEditing flag and locked appearance
    void updateGeometry();
    void updateGeometry(QLineEdit* edit);

    Function getFunction();

    /** @name User parameters (App/UserParameters.h)
     * When an owner is set, accepting the input `name = expression`, `= expression` or an
     * expression that is only valid with names of the owner's document (`2*myVar`) sets the
     * value of the label and keeps the expression, so that the caller can bind the property it
     * creates from the value (and create the user parameter `name` on the owner), and '='
     * typed over the shown value starts an empty expression. Any other input keeps its usual
     * meaning; without an owner the label behaves as before. */
    //@{
    void setUserParameterOwner(App::DocumentObject* owner);
    /// True when the label was set from such an expression.
    bool hasUserExpression() const;
    /// The value of the expression when it was accepted (in internal units).
    double getUserExpressionValue() const;
    /// The name of the user parameter to create, empty for `= expression`.
    const std::string& getUserParameterName() const;
    /// The expression (parsed on the owner) giving the value of the label.
    std::shared_ptr<App::Expression> getUserExpression() const;
    /// The unit of the field when the expression was accepted.
    const Base::Unit& getUserExpressionUnit() const;
    /// Forget the expression once it has been bound (tools that bind at every step).
    void clearUserExpression();
    //@}

    // NOLINTBEGIN
    SoDatumLabel* label;
    bool isSet;  ///< used to differentiate when user has started typing inside the label
    bool hasFinishedEditing;  ///< flag to know when user has finished editing, i.e. pressed enter
    bool autoDistance;
    bool autoDistanceReverse;
    bool avoidMouseCursor;
    double value;
    // NOLINTEND

Q_SIGNALS:
    void valueChanged(double val);
    void editingFinished(double val);
    void editingCanceled(double val);
    void parameterUnset();
    void finishEditingOnAllOVPs();  ///< Emitted when Ctrl+Enter is pressed to finish editing on all
                                    ///< visible OVPs
    void clicked(EditableDatumLabel* label);  ///< Emitted when the label is clicked in the 3D view.
    void rightClicked(EditableDatumLabel* label, const QPoint& globalPos);
    void editFinished(double value);  ///< Emitted when editing is confirmed (e.g., Enter pressed).
    void focusLost();                 ///< Emitted when the spinbox looses focus.
    void focusGained();               ///< Emitted when the spinbox gains focus.

protected:
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    enum class UserInput
    {
        NotApplicable,
        Accepted,
        Rejected
    };
    /// Whether an owner is set (setUserParameterOwner()) and the expressions can name its document.
    bool acceptsUserExpressions() const;
    UserInput acceptUserExpressionInput();
    void setupUserParameterCompleter(QLineEdit* edit);
    bool syncValueFromSpinBox(bool emitParameterUnset = true);
    void handleSpinBoxValueChanged();
    void handleSpinBoxInputCleared();
    void positionSpinbox();
    SbVec3f getTextCenterPoint() const;
    void initColors();

    void handleEvent(SoEventCallback* cb);
    static void eventCallbackF(void* userData, SoEventCallback* cb);

private:
    SoSwitch* root;
    SoAnnotation* annotation;
    SoTransform* transform;
    QPointer<View3DInventorViewer> viewer;
    QuantitySpinBox* spinBox;
    QLabel* lockIconLabel;  ///< Label to display lock icon next to spinbox
    SoNodeSensor* cameraSensor;
    SbVec3f midpos;

    SbColor dimConstrColor, dimConstrDeactivatedColor;
    SoEventCallback* eventCallback;
    SoPickStyle* pickStyle;

    Function function;
    double editStartValue;

    App::DocumentObject* userParameterOwner {nullptr};
    std::string userParameterName;
    std::shared_ptr<App::Expression> userExpression;
    Base::Unit userExpressionUnit;
    double userExpressionValue {0.0};
};

}  // namespace Gui
