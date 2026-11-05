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

#include <limits>
#include <Inventor/sensors/SoNodeSensor.h>
#include <Inventor/nodes/SoAnnotation.h>
#include <Inventor/nodes/SoOrthographicCamera.h>
#include <Inventor/nodes/SoTransform.h>
#include <Inventor/nodes/SoSwitch.h>
#include <Inventor/nodes/SoEventCallback.h>
#include <Inventor/nodes/SoPickStyle.h>
#include <Inventor/events/SoMouseButtonEvent.h>
#include <Inventor/SoPickedPoint.h>
#include <Inventor/SoPath.h>

#include <algorithm>

#include <QEvent>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QPixmap>
#include <QRegularExpression>
#include <QLabel>
#include <QLineEdit>
#include <QHBoxLayout>
#include <QString>
#include <QTimer>
#include <QToolTip>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ObjectIdentifier.h>
#include <App/UserParameters.h>
#include <Base/Quantity.h>
#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>

#include "EditableDatumLabel.h"
#include "ExpressionCompleter.h"
#include "Base/Console.h"
#include "Gui/QuantitySpinBox.h"


using namespace Gui;


struct NodeData
{
    EditableDatumLabel* label;
};

EditableDatumLabel::EditableDatumLabel(
    View3DInventorViewer* view,
    const Base::Placement& plc,
    bool autoDistance,
    bool avoidMouseCursor
)
    : isSet(false)
    , hasFinishedEditing(false)
    , autoDistance(autoDistance)
    , autoDistanceReverse(false)
    , avoidMouseCursor(avoidMouseCursor)
    , value(0.0)
    , viewer(view)
    , spinBox(nullptr)
    , lockIconLabel(nullptr)
    , cameraSensor(nullptr)
    , pickStyle(nullptr)
    , function(Function::Positioning)
    , editStartValue(0.0)
{
    // NOLINTBEGIN
    initColors();

    root = new SoSwitch;
    root->ref();

    annotation = new SoAnnotation;
    annotation->ref();
    annotation->renderCaching = SoSeparator::OFF;
    root->addChild(annotation);

    transform = new SoTransform();
    transform->ref();
    annotation->addChild(transform);

    eventCallback = new SoEventCallback;
    eventCallback->ref();
    eventCallback->addEventCallback(SoMouseButtonEvent::getClassTypeId(), eventCallbackF, this);
    annotation->addChild(eventCallback);
    pickStyle = new SoPickStyle;
    pickStyle->ref();
    pickStyle->style = SoPickStyle::UNPICKABLE;
    annotation->addChild(pickStyle);

    label = new SoDatumLabel();
    label->ref();
    label->string = " ";
    setDeactivatedColor();
    label->size.setValue(17);
    label->lineWidth = 2.0;
    label->useAntialiasing = false;
    label->datumtype = SoDatumLabel::DISTANCE;
    label->param1 = 0.;
    label->param2 = 0.;
    label->param3 = 0.;
    if (autoDistance) {
        setLabelRecommendedDistance();
    }
    annotation->addChild(label);

    setPlacement(plc);
    // NOLINTEND

    static_cast<SoSeparator*>(viewer->getSceneGraph())->addChild(root);  // NOLINT

    if (view) {
        connect(view, &View3DInventorViewer::cameraChanged, this, [this]() {
            if (this->label) {
                // 1. Re-attach the sensor to the NEW camera object
                if (this->cameraSensor && this->viewer && this->viewer->getCamera()) {
                    this->cameraSensor->detach();
                    this->cameraSensor->attach(this->viewer->getCamera());
                }

                if (this->autoDistance) {
                    this->setLabelRecommendedDistance();
                }
                this->label->touch();

                if (this->isInEdit()) {
                    this->positionSpinbox();
                }
            }
        });
    }
}

EditableDatumLabel::~EditableDatumLabel()
{
    deactivate();
    transform->unref();
    annotation->unref();
    eventCallback->unref();
    pickStyle->unref();
    root->unref();
    label->unref();
}

void EditableDatumLabel::activate()
{
    if (!viewer || isActive()) {
        return;
    }

    root->whichChild = 0;

    // track camera movements to update spinbox position.
    auto info = new NodeData {this};
    cameraSensor = new SoNodeSensor(
        [](void* data, SoSensor* sensor) {
            Q_UNUSED(sensor);
            auto info = static_cast<NodeData*>(data);
            info->label->positionSpinbox();
            if (info->label->autoDistance) {
                info->label->setLabelRecommendedDistance();
            }
        },
        info
    );
    cameraSensor->attach(viewer->getCamera());
}

void EditableDatumLabel::deactivate()
{
    stopEdit();

    if (cameraSensor) {
        auto data = static_cast<NodeData*>(cameraSensor->getData());
        delete data;
        cameraSensor->detach();
        delete cameraSensor;
        cameraSensor = nullptr;
    }

    root->whichChild = SO_SWITCH_NONE;
}

void EditableDatumLabel::startEdit(double val, QObject* eventFilteringObj, bool visibleToMouse)
{
    if (isInEdit()) {
        return;
    }

    // Reset locked state when starting to edit
    this->resetLockedState();
    clearUserExpression();

    QWidget* mdi = viewer->parentWidget();

    label->string = " ";

    spinBox = new QuantitySpinBox(mdi);
    spinBox->setUnit(Base::Unit::Length);
    spinBox->setMinimum(-std::numeric_limits<int>::max());
    spinBox->setMaximum(std::numeric_limits<int>::max());
    spinBox->setButtonSymbols(QAbstractSpinBox::NoButtons);
    spinBox->setFocusPolicy(Qt::ClickFocus);  // prevent passing focus with tab.
    spinBox->setAutoNormalize(false);
    spinBox->setKeyboardTracking(true);
    spinBox->installEventFilter(this);
    spinBox->setAutoAdjustWidth(true);
    spinBox->setMaxExpectedDigits(16);
    spinBox->setValue(Base::Quantity(val, Base::Unit::Length));
    value = val;
    editStartValue = val;

    lockIconLabel = new QLabel(spinBox);
    lockIconLabel->setObjectName(QStringLiteral("onViewParameterLockIcon"));
    lockIconLabel->setAttribute(Qt::WA_TransparentForMouseEvents, true);

    // load icon and scale it to fit in spinbox
    QPixmap lockIcon = Gui::BitmapFactory().pixmap("Constraint_Lock");
    const QFontMetrics fm(spinBox->fontMetrics());
    int iconSize = fm.height();
    QPixmap scaledIcon
        = lockIcon.scaled(iconSize, iconSize, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    lockIconLabel->setPixmap(scaledIcon);
    lockIconLabel->setVisible(false);

    if (eventFilteringObj) {
        spinBox->installEventFilter(eventFilteringObj);
    }

    if (!visibleToMouse) {
        setSpinboxVisibleToMouse(visibleToMouse);
    }

    spinBox->show();
    if (auto* edit = spinBox->findChild<QLineEdit*>()) {
        updateGeometry(edit);
        positionSpinbox();
    }
    setFocusToSpinbox();
    QTimer::singleShot(0, this, [this]() {
        if (!spinBox) {
            return;
        }
        positionSpinbox();
        setFocusToSpinbox();
    });

    connect(
        spinBox,
        qOverload<double>(&QuantitySpinBox::valueChanged),
        this,
        &EditableDatumLabel::handleSpinBoxValueChanged
    );
    connect(spinBox, &QuantitySpinBox::inputCleared, this, &EditableDatumLabel::handleSpinBoxInputCleared);
    if (auto* edit = spinBox->findChild<QLineEdit*>()) {
        connect(edit, &QLineEdit::textChanged, this, [this, edit]() { this->updateGeometry(edit); });
        // A new input replaces an accepted user parameter expression.
        connect(edit, &QLineEdit::textEdited, this, [this]() { clearUserExpression(); });
        setupUserParameterCompleter(edit);
    }
}

// Names typed in the field (`= height`, `2*height`, `w = height/2`) are completed like in the
// formula dialog: user parameters by their bare name, objects and properties by their path.
void EditableDatumLabel::setupUserParameterCompleter(QLineEdit* edit)
{
    if (!userParameterOwner || !userParameterOwner->isAttachedToDocument()) {
        return;
    }
    auto* completer = new ExpressionCompleter(userParameterOwner, spinBox);
    completer->setWidget(edit);
    completer->setCaseSensitivity(Qt::CaseInsensitive);
    if (!ExpressionParameter::instance()->isExactMatch()) {
        completer->setFilterMode(Qt::MatchContains);
    }
    connect(edit, &QLineEdit::textEdited, completer, [completer, edit](const QString& text) {
        // Numbers and units keep their usual input; complete only once a name is being typed.
        const bool name = std::any_of(text.begin(), text.end(), [](QChar c) {
            return c.isLetter() || c == QLatin1Char('_');
        });
        if (name) {
            completer->slotUpdate(text, edit->cursorPosition());
        }
        else if (completer->popup()) {
            completer->popup()->hide();
        }
    });
    const auto complete = [completer, edit](const QString& completion) {
        int start = 0;
        int end = 0;
        completer->getPrefixRange(start, end);
        const QString before = edit->text().left(start) + completion;
        const QString after = edit->text().mid(end);
        edit->setText(before + after);
        edit->setCursorPosition(static_cast<int>(before.size()));
        completer->updatePrefixEnd(static_cast<int>(before.size()));
    };
    connect(completer, qOverload<const QString&>(&QCompleter::activated), edit, complete);
}

void EditableDatumLabel::setUserParameterOwner(App::DocumentObject* owner)
{
    userParameterOwner = owner;
}

bool EditableDatumLabel::hasUserExpression() const
{
    return isSet && userExpression;
}

double EditableDatumLabel::getUserExpressionValue() const
{
    return userExpressionValue;
}

const std::string& EditableDatumLabel::getUserParameterName() const
{
    return userParameterName;
}

std::shared_ptr<App::Expression> EditableDatumLabel::getUserExpression() const
{
    return userExpression;
}

const Base::Unit& EditableDatumLabel::getUserExpressionUnit() const
{
    return userExpressionUnit;
}

void EditableDatumLabel::clearUserExpression()
{
    userParameterName.clear();
    userExpression.reset();
    userExpressionUnit = Base::Unit();
    userExpressionValue = 0.0;
}

// Accepts `name = expression`, `= expression` and expressions that are only valid with the names
// of the owner's document (`2*myVar`). Values and expressions valid without the document are left
// to the usual handling (NotApplicable), so their meaning does not change.
EditableDatumLabel::UserInput EditableDatumLabel::acceptUserExpressionInput()
{
    if (!userParameterOwner || !spinBox || !userParameterOwner->isAttachedToDocument()) {
        return UserInput::NotApplicable;
    }

    std::string input = spinBox->text().trimmed().toUtf8().toStdString();
    bool explicitExpression = false;
    if (input.size() > 1 && input[0] == '=' && input[1] != '=') {
        explicitExpression = true;
        input = QString::fromStdString(input.substr(1)).trimmed().toUtf8().toStdString();
    }

    std::string name;
    std::string rhs;
    const bool assignment = App::UserParameters::splitAssignment(input, name, rhs);
    if (!assignment && !explicitExpression && spinBox->hasValidInput()) {
        return UserInput::NotApplicable;
    }

    const auto reject = [this](const QString& message) {
        QToolTip::showText(spinBox->mapToGlobal(QPoint(0, spinBox->height())), message, spinBox);
        return UserInput::Rejected;
    };

    Base::Quantity quantity;
    QString error;
    const auto expression = spinBox->interpretExpression(
        QString::fromStdString(assignment ? rhs : input),
        App::ObjectIdentifier(userParameterOwner->Label),
        quantity,
        error
    );
    if (!expression) {
        if (!assignment && !explicitExpression) {
            return UserInput::NotApplicable;
        }
        return reject(error);
    }

    if (assignment) {
        const auto status = App::UserParameters::checkName(
            userParameterOwner->getDocument(),
            name,
            userParameterOwner
        );
        if (status != App::UserParameters::NameStatus::Available) {
            return reject(
                QString::fromStdString(App::UserParameters::nameStatusMessage(status, name))
            );
        }
    }

    const Base::Unit unit = spinBox->unit();
    {
        QSignalBlocker blocker(spinBox);
        spinBox->setValue(quantity);
    }

    clearUserExpression();
    // `= 30 mm` is a plain value.
    if (assignment || !expression->getIdentifiers().empty()) {
        userParameterName = assignment ? name : std::string();
        userExpression = expression;
        userExpressionUnit = unit;
        userExpressionValue = spinBox->rawValue();
    }
    return UserInput::Accepted;
}

bool EditableDatumLabel::syncValueFromSpinBox(bool emitParameterUnset)
{
    if (!spinBox) {
        return false;
    }

    if (!spinBox->hasValidInput()) {
        if (emitParameterUnset) {
            resetLockedState();
            Q_EMIT parameterUnset();
        }
        return false;
    }

    value = spinBox->rawValue();
    isSet = true;

    if (hasFinishedEditing) {
        setLockedAppearance(true);
    }

    return true;
}

void EditableDatumLabel::handleSpinBoxValueChanged()
{
    if (syncValueFromSpinBox()) {
        Q_EMIT valueChanged(value);
    }
}

void EditableDatumLabel::handleSpinBoxInputCleared()
{
    if (!isSet && !hasFinishedEditing) {
        return;
    }

    // Clearing an OVP removes its provisional parameter; it does not create a new numeric value.
    // Keep the committed value intact so Escape and cancellation can still restore it.
    isSet = false;
    resetLockedState();
    Q_EMIT parameterUnset();
}

bool EditableDatumLabel::eventFilter(QObject* watched, QEvent* event)
{
    if (event->type() == QEvent::KeyPress) {
        auto* keyEvent = static_cast<QKeyEvent*>(event);
        // `= expression`: '=' typed over the shown value and unit starts an empty expression,
        // so that the unit does not end up behind the names ("= height mm").
        if (keyEvent->text() == QLatin1String("=") && qobject_cast<QAbstractSpinBox*>(watched)
            && spinBox) {
            if (auto* edit = spinBox->findChild<QLineEdit*>()) {
                QString rest = edit->text();
                if (edit->hasSelectedText()) {
                    rest.remove(edit->selectionStart(), edit->selectedText().size());
                }
                // Only a number and/or the unit the field shows: nothing typed that the
                // expression would need. Anything else ("h", "height") is a name being typed
                // and is kept, even when it is also a unit symbol (h = hour).
                const QString shown = QString::fromStdString(spinBox->value().getUserString());
                static const QRegularExpression lastDigit(QStringLiteral(R"(\d)"));
                const QString unit = shown.mid(shown.lastIndexOf(lastDigit) + 1).trimmed();
                QString remaining = rest.trimmed();
                if (!unit.isEmpty() && remaining.endsWith(unit)) {
                    remaining.chop(unit.size());
                }
                static const QRegularExpression number(QStringLiteral(R"(^[-+]?[\d.,\s]*$)"));
                if (number.match(remaining).hasMatch()) {
                    edit->setText(QStringLiteral("="));
                    clearUserExpression();
                    return true;
                }
            }
        }
        if (keyEvent->key() == Qt::Key_Escape) {
            if (qobject_cast<QAbstractSpinBox*>(watched)) {
                this->value = this->editStartValue;
                this->isSet = false;
                this->hasFinishedEditing = false;
                this->clearUserExpression();
                this->setLockedAppearance(false);
                this->setSpinboxValue(this->editStartValue);
                this->stopEdit();
                Q_EMIT this->editingCanceled(this->value);
                return true;
            }
        }
        if (keyEvent->key() == Qt::Key_Return || keyEvent->key() == Qt::Key_Enter
            || keyEvent->key() == Qt::Key_Tab) {

            if (qobject_cast<QAbstractSpinBox*>(watched)) {
                // a user parameter input is accepted as a typed value
                const UserInput userInput = acceptUserExpressionInput();
                if (userInput == UserInput::Rejected) {
                    return true;
                }
                const bool userValue = userInput == UserInput::Accepted;

                // if tab has been pressed and user did not type anything previously,
                // then just cycle but don't lock anything, otherwise we lock the label
                if (keyEvent->key() == Qt::Key_Tab && !this->isSet && !userValue) {
                    if (!this->spinBox->hasValidInput()) {
                        syncValueFromSpinBox();
                        return true;
                    }
                    return false;
                }

                // for ctrl + enter we accept values as they are
                if (keyEvent->modifiers() & Qt::ControlModifier) {
                    if (userValue) {
                        syncValueFromSpinBox();
                    }
                    Q_EMIT this->finishEditingOnAllOVPs();
                    return true;
                }
                else {
                    // regular enter or tab with edited input accepts the current value.
                    this->hasFinishedEditing = true;

                    if (!syncValueFromSpinBox()) {
                        return true;
                    }

                    const double finishedValue = value;
                    Q_EMIT this->editingFinished(finishedValue);
                    return true;
                }
            }
        }
        else if (this->hasFinishedEditing && keyEvent->key() != Qt::Key_Tab) {
            this->resetLockedState();
            return false;
        }
    }
    else if (event->type() == QEvent::FocusIn) {
        // Emit focusGained whenever the spinbox or its child QLineEdit receives focus
        Q_EMIT focusGained();
    }
    else if (event->type() == QEvent::FocusOut) {
        if (watched == spinBox) {
            Q_EMIT focusLost();
        }
    }

    return QObject::eventFilter(watched, event);
}

void EditableDatumLabel::stopEdit(bool writeChanges)
{
    if (spinBox) {
        if (writeChanges) {
            // write the spinbox value in the label.
            Base::Quantity quantity = spinBox->value();
            std::string valueStr = quantity.getUserString();
            label->string = SbString(valueStr.c_str());
        }
        else {
            Base::Quantity quantity(editStartValue, spinBox->unit());
            label->string = quantity.getUserString().c_str();
        }

        spinBox->deleteLater();
        spinBox = nullptr;

        // Lock icon will be automatically destroyed as it's a child of spinbox
        lockIconLabel = nullptr;
    }
}

bool EditableDatumLabel::isActive() const
{
    return cameraSensor != nullptr;
}

bool EditableDatumLabel::isInEdit() const
{
    return spinBox != nullptr;
}


double EditableDatumLabel::getValue() const
{
    // We use value rather than spinBox->rawValue() in case edit stopped.
    return value;
}

void EditableDatumLabel::setSpinboxValue(double val, const Base::Unit& unit)
{
    value = val;

    if (!spinBox) {
        Base::Quantity quantity(val, unit);
        double factor {};
        std::string unitStr;
        std::string valueStr = quantity.getUserString(factor, unitStr);
        label->string = SbString(valueStr.c_str());
        return;
    }

    QSignalBlocker block(spinBox);
    spinBox->setValue(Base::Quantity(val, unit));
    positionSpinbox();

    if (spinBox->hasFocus()) {
        spinBox->selectNumber();
    }
}

void EditableDatumLabel::setFocusToSpinbox()
{
    if (!spinBox) {
        return;
    }
    if (!spinBox->hasFocus()) {
        spinBox->setFocus();
        spinBox->selectNumber();
    }
}

void EditableDatumLabel::clearSelection()
{
    if (!spinBox) {
        return;
    }

    if (auto* edit = spinBox->findChild<QLineEdit*>()) {
        edit->deselect();
    }
}

void EditableDatumLabel::positionSpinbox()
{
    if (!spinBox) {
        return;
    }

    if (spinBox->hasFocus()) {
        spinBox->raise();
    }

    QSize wSize = spinBox->size();
    QWidget* parent = spinBox->parentWidget();
    QSize vSize = parent ? parent->size() : viewer->size();
    QPoint pxCoord = viewer->toQPoint(viewer->getPointOnViewport(getTextCenterPoint()));
    if (parent && parent != viewer) {
        pxCoord = viewer->mapTo(parent, pxCoord);
    }

    int posX = std::min(std::max(pxCoord.x() - wSize.width() / 2, 0), vSize.width() - wSize.width());
    int posY = std::min(std::max(pxCoord.y() - wSize.height() / 2, 0), vSize.height() - wSize.height());

    if (avoidMouseCursor) {
        QPoint cursorPos = viewer->mapFromGlobal(QCursor::pos());
        int margin = static_cast<int>(wSize.height() * 0.7);  // NOLINT
        if ((cursorPos.x() > posX - margin && cursorPos.x() < posX + wSize.width() + margin)
            && (cursorPos.y() > posY - margin && cursorPos.y() < posY + wSize.height() + margin)) {
            posY = cursorPos.y()
                + ((cursorPos.y() > pxCoord.y()) ? -wSize.height() - margin : margin);
        }
    }

    pxCoord.setX(posX);
    pxCoord.setY(posY);
    spinBox->move(pxCoord);
}

SbVec3f EditableDatumLabel::getTextCenterPoint() const
{
    // Here we need the 3d point and not the 2d point as are the SoLabel points.
    //  First we get the 2D point (on the sketch/image plane) of the middle of the text label.
    SbVec3f point2D = label->getLabelTextCenter();
    // Get the translation and rotation values from the transform
    SbVec3f translation = transform->translation.getValue();
    SbRotation rotation = transform->rotation.getValue();

    // Calculate the inverse transformation
    SbVec3f invTranslation = -translation;
    SbRotation invRotation = rotation.inverse();

    // Transform the 2D coordinates to 3D
    // Plane form
    SbVec3f RX(1, 0, 0);
    SbVec3f RY(0, 1, 0);

    // move to position of Sketch
    invRotation.multVec(RX, RX);
    invRotation.multVec(RY, RY);
    invRotation.multVec(invTranslation, invTranslation);

    // we use invTranslation as the Base because in setPlacement we set transform->translation using
    // placement.getPosition() to fix the Zoffset. But this applies the X & Y translation too.
    Base::Vector3d pos(invTranslation[0], invTranslation[1], invTranslation[2]);
    Base::Vector3d RXb(RX[0], RX[1], RX[2]);
    Base::Vector3d RYb(RY[0], RY[1], RY[2]);
    Base::Vector3d P2D(point2D[0], point2D[1], point2D[2]);
    P2D.TransformToCoordinateSystem(pos, RXb, RYb);

    return {float(P2D.x), float(P2D.y), float(P2D.z)};
}

void EditableDatumLabel::setPlacement(const Base::Placement& plc)
{
    double x {}, y {}, z {}, w {};  // NOLINT
    plc.getRotation().getValue(x, y, z, w);
    transform->rotation.setValue(x, y, z, w);  // NOLINT

    Base::Vector3d pos = plc.getPosition();
    transform->translation.setValue(float(pos.x), float(pos.y), float(pos.z));

    Base::Vector3d RN(0, 0, 1);
    RN = plc.getRotation().multVec(RN);
    label->norm.setValue(SbVec3f(float(RN.x), float(RN.y), float(RN.z)));
}

void EditableDatumLabel::updateGeometry()
{
    if (!spinBox) {
        return;
    }
    updateGeometry(spinBox->findChild<QLineEdit*>());
}

void EditableDatumLabel::updateGeometry(QLineEdit* edit)
{
    if (!spinBox || !edit) {
        return;
    }
    // Workaround: adjustSize() causes the cursor to jump to the end and selections to clear
    // Save the state beforehand and restore it after the geometry update
    int pos = edit->cursorPosition();
    int selStart = edit->selectionStart();
    int selEnd = edit->selectionEnd();
    spinBox->adjustSize();
    edit->setCursorPosition(pos);
    if (selStart != -1 && selEnd != -1) {
        edit->setSelection(selStart, selEnd - selStart);
    }
}

// NOLINTNEXTLINE
void EditableDatumLabel::setColor(SbColor color)
{
    label->textColor = color;
}

void EditableDatumLabel::setActivatedColor()
{
    label->textColor = dimConstrColor;
}

void EditableDatumLabel::setDeactivatedColor()
{
    label->textColor = dimConstrDeactivatedColor;
}

void EditableDatumLabel::initColors()
{
    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/View"
    );

    dimConstrColor = SbColor(1.0f, 0.149f, 0.0f);           // NOLINT
    dimConstrDeactivatedColor = SbColor(0.5f, 0.5f, 0.5f);  // NOLINT

    float transparency = 0.f;
    unsigned long color = (unsigned long)(dimConstrColor.getPackedValue());
    color = hGrp->GetUnsigned("ConstrainedDimColor", color);
    dimConstrColor.setPackedValue((uint32_t)color, transparency);

    color = (unsigned long)(dimConstrDeactivatedColor.getPackedValue());
    color = hGrp->GetUnsigned("DeactivatedConstrDimColor", color);
    dimConstrDeactivatedColor.setPackedValue((uint32_t)color, transparency);
}

void EditableDatumLabel::eventCallbackF(void* userData, SoEventCallback* cb)
{
    auto* self = static_cast<EditableDatumLabel*>(userData);
    self->handleEvent(cb);
}

void EditableDatumLabel::handleEvent(SoEventCallback* cb)
{
    const auto* event = cb->getEvent();
    if (!event->isOfType(SoMouseButtonEvent::getClassTypeId())) {
        return;
    }

    const auto* mouseEvent = static_cast<const SoMouseButtonEvent*>(event);

    const SoPickedPoint* pickedPoint = cb->getPickedPoint();
    if (!pickedPoint || !pickedPoint->getPath()->containsNode(this->annotation)) {
        return;
    }

    if (mouseEvent->getButton() == SoMouseButtonEvent::BUTTON1) {
        if (mouseEvent->getState() == SoMouseButtonEvent::UP) {
            cb->setHandled();
            Q_EMIT clicked(this);
        }
    }
    else if (mouseEvent->getButton() == SoMouseButtonEvent::BUTTON2) {
        cb->setHandled();
        if (mouseEvent->getState() == SoMouseButtonEvent::UP) {
            Q_EMIT rightClicked(this, QCursor::pos());
        }
    }
}

void EditableDatumLabel::setPickable(bool val)
{
    pickStyle->style = val ? SoPickStyle::SHAPE_ON_TOP : SoPickStyle::UNPICKABLE;
}

void EditableDatumLabel::setFocus()
{
    if (spinBox) {
        spinBox->selectNumber();
    }
}

void EditableDatumLabel::setPoints(SbVec3f p1, SbVec3f p2)
{
    label->setPoints(p1, p2);
    // TODO: here the position of the spinbox is not going to be center of p1, p2 because the point
    // given by getTextCenterPoint
    //  is not updated yet. it will be only on redraw so it is actually positioning on previous position.

    positionSpinbox();
    if (autoDistance) {
        setLabelRecommendedDistance();
    }
}

void EditableDatumLabel::setPoints(Base::Vector3d p1, Base::Vector3d p2)
{
    setPoints(
        SbVec3f(float(p1.x), float(p1.y), float(p1.z)),
        SbVec3f(float(p2.x), float(p2.y), float(p2.z))
    );
}

// NOLINTNEXTLINE
void EditableDatumLabel::setLabelType(SoDatumLabel::Type type, Function funct)
{
    label->datumtype = type;
    function = funct;
}

// NOLINTNEXTLINE
void EditableDatumLabel::setLabelDistance(double val)
{
    label->param1 = float(val);
}

// NOLINTNEXTLINE
void EditableDatumLabel::setLabelStartAngle(double val)
{
    label->param2 = float(val);
}

// NOLINTNEXTLINE
void EditableDatumLabel::setLabelRange(double val)
{
    label->param3 = float(val);
}

void EditableDatumLabel::setLabelRecommendedDistance()
{
    // Takes the 3d view size, and set the label distance to a % of that, such that the distance
    // does not depend on the zoom level.
    float width = -1.;
    float length = -1.;
    viewer->getDimensions(width, length);

    if (width == -1. || length == -1.) {
        return;
    }

    label->param1 = (autoDistanceReverse ? -1.0F : 1.0F) * (width + length) * 0.03F;  // NOLINT
}

void EditableDatumLabel::setLabelAutoDistanceReverse(bool val)
{
    autoDistanceReverse = val;
}

void EditableDatumLabel::setSpinboxVisibleToMouse(bool val)
{
    if (!spinBox) {
        return;
    }
    spinBox->setAttribute(Qt::WA_TransparentForMouseEvents, !val);
}

void EditableDatumLabel::setLockedAppearance(bool locked)
{
    if (!spinBox || !lockIconLabel) {
        return;
    }
    spinBox->addIconSpace(locked);
    lockIconLabel->setVisible(locked);
    if (auto* edit = spinBox->findChild<QLineEdit*>()) {
        updateGeometry(edit);
    }
    const QFontMetrics fm(spinBox->fontMetrics());
    int iconSize = fm.height();
    int padding = spinBox->getMargin();
    // position lock icon inside the spinbox
    QSize spinboxSize = spinBox->size();
    lockIconLabel->setGeometry(
        spinboxSize.width() - iconSize - padding,
        (spinboxSize.height() - iconSize) / 2,
        iconSize,
        iconSize
    );
}

void EditableDatumLabel::resetLockedState()
{
    hasFinishedEditing = false;
    setLockedAppearance(false);
}

EditableDatumLabel::Function EditableDatumLabel::getFunction()
{
    return function;
}

#include "moc_EditableDatumLabel.cpp"  // NOLINT
