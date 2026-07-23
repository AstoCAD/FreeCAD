# SPDX-License-Identifier: LGPL-2.1-or-later

"""Shared Stair Designer task-panel widgets and editors."""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

translate = FreeCAD.Qt.translate


def _load_task_form(resource, owner, widget_names):
    """Load a Designer form with an explicit, Python-owned outer widget.

    ``PySideUic.loadUi()`` ignores its nominal ``base`` argument in FreeCAD's
    implementation. Use ``UiLoader.load()`` directly so the loaded root is
    created with *form* as its Qt and Shiboken parent from the beginning.
    """

    form = QtGui.QWidget()
    content = FreeCADGui.UiLoader().load(resource, form)
    if content is None:
        raise RuntimeError(f"Cannot load task form {resource}")
    layout = QtGui.QVBoxLayout(form)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(content)
    form.setWindowTitle(content.windowTitle())
    form.ui = content
    owner.__dict__.setdefault("_ui_forms", []).append((form, content))
    for name in widget_names:
        setattr(owner, name, getattr(content, name))
    return form


def _value(quantity):
    return float(quantity.Value) if hasattr(quantity, "Value") else float(quantity)


def _length_spin(value=0.0, minimum=0.0, maximum=1000000.0):
    spin = QtGui.QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setRange(minimum, maximum)
    spin.setSuffix(" mm")
    spin.setValue(value)
    return spin


def _float_spin(value=0.0, minimum=0.0, maximum=1000.0, decimals=3):
    spin = QtGui.QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    return spin


def _percent_spin(value=50):
    spin = QtGui.QSpinBox()
    spin.setRange(0, 100)
    spin.setSuffix(" %")
    spin.setValue(int(round(_value(value))))
    return spin


class _ItemEditorGuard(QtCore.QObject):
    """Keep a view's embedded editors from reacting to passing input.

    The wheel over an unfocused editor scrolls the view instead of focusing
    the editor and changing its value. Typed keys that an editor leaves
    unused reach the view, whose type-to-search would move its current row.
    """

    NAME = "stair_designer_item_editor_guard"

    def __init__(self, view):
        super().__init__(view)
        self.setObjectName(self.NAME)
        self._view = view

    def eventFilter(self, watched, event):
        if watched is self._view:
            if (
                event.type() == QtCore.QEvent.KeyPress
                and event.text().isprintable()
                and event.text()
                and not event.modifiers()
                & (QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier)
            ):
                return True
            return False
        if event.type() == QtCore.QEvent.Wheel and not watched.hasFocus():
            QtCore.QCoreApplication.sendEvent(self._view.viewport(), event)
            return True
        return False


def _prepare_item_editor(view, widget):
    """Prepare ``widget`` to be embedded in the item ``view``.

    The editor only takes focus when clicked or tabbed to, and a typed value
    applies once validated (Enter, Tab, focus out): every value rebuilds the
    stair, and the intermediate values of a number being typed are not meant.
    """

    guard = view.findChild(QtCore.QObject, _ItemEditorGuard.NAME)
    if guard is None:
        guard = _ItemEditorGuard(view)
        view.installEventFilter(guard)
    widget.setFocusPolicy(QtCore.Qt.StrongFocus)
    widget.installEventFilter(guard)
    if isinstance(widget, QtGui.QAbstractSpinBox):
        widget.setKeyboardTracking(False)


class _FlightTreeWidget(QtGui.QTreeWidget):
    """Flight tree that owns and consumes its Delete-key action."""

    def __init__(self, delete_callback, parent=None):
        super().__init__(parent)
        self._delete_callback = delete_callback

    def setItemWidget(self, item, column, widget):
        _prepare_item_editor(self, widget)
        super().setItemWidget(item, column, widget)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Delete:
            self._delete_callback()
            event.accept()
            return
        super().keyPressEvent(event)


class _CurrentPageTabWidget(QtGui.QTabWidget):
    """A tab widget whose height follows only its current page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._current_page_changed)

    def _hint_for_current_page(self, minimum=False):
        base_hint = (
            super().minimumSizeHint()
            if minimum
            else super().sizeHint()
        )
        current = self.currentWidget()
        if current is None:
            return base_hint

        page_hints = []
        for index in range(self.count()):
            page = self.widget(index)
            page_hints.append(
                page.minimumSizeHint() if minimum else page.sizeHint()
            )
        if not page_hints:
            return base_hint

        current_hint = (
            current.minimumSizeHint() if minimum else current.sizeHint()
        )
        tallest_page = max(hint.height() for hint in page_hints)
        chrome_height = max(0, base_hint.height() - tallest_page)
        return QtCore.QSize(
            base_hint.width(),
            current_hint.height() + chrome_height,
        )

    def sizeHint(self):
        return self._hint_for_current_page()

    def minimumSizeHint(self):
        return self._hint_for_current_page(minimum=True)

    def _current_page_changed(self, _index):
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()


class _CheckableComboBox(QtGui.QComboBox):
    """Combo box whose items are ticked: any number of them, or none.

    It shows the texts of the ticked items, ``empty_text`` without any, and
    stays open while items are ticked or unticked.
    """

    checkedChanged = QtCore.Signal()

    def __init__(self, empty_text="", parent=None):
        super().__init__(parent)
        self._empty_text = empty_text
        self._pressed = None
        self.setModel(QtGui.QStandardItemModel(self))
        # A combo box's own delegate draws no tick boxes under a style sheet.
        self.setItemDelegate(QtGui.QStyledItemDelegate(self))
        self.view().viewport().installEventFilter(self)
        self.view().installEventFilter(self)

    def set_items(self, items, checked=()):
        """Show ``items``, each a text and its data, with those whose data
        is among ``checked`` ticked."""

        model = self.model()
        items = list(items)
        shown = [model.item(row).data(QtCore.Qt.UserRole) for row in range(model.rowCount())]
        if shown != [data for _text, data in items]:
            model.clear()
            for _text, data in items:
                item = QtGui.QStandardItem()
                item.setFlags(
                    QtCore.Qt.ItemIsEnabled
                    | QtCore.Qt.ItemIsSelectable
                    | QtCore.Qt.ItemIsUserCheckable
                )
                item.setData(data, QtCore.Qt.UserRole)
                model.appendRow(item)
        # The same items are kept: an open list stays where it is.
        for row, (text, data) in enumerate(items):
            item = model.item(row)
            item.setText(text)
            item.setCheckState(QtCore.Qt.Checked if data in checked else QtCore.Qt.Unchecked)
        self.update()

    def _checked_items(self):
        model = self.model()
        items = (model.item(row) for row in range(model.rowCount()))
        return [item for item in items if item.checkState() == QtCore.Qt.Checked]

    def checked_data(self):
        """Return the data of the ticked items, in the order they are shown."""

        return [item.data(QtCore.Qt.UserRole) for item in self._checked_items()]

    def checked_text(self):
        """Return what the box shows: the ticked items' texts, or its empty text."""

        return ", ".join(item.text() for item in self._checked_items()) or self._empty_text

    def toggle(self, row):
        """Tick the item of ``row``, or untick it."""

        item = self.model().item(row)
        if item is None:
            return
        item.setCheckState(
            QtCore.Qt.Unchecked if item.checkState() == QtCore.Qt.Checked else QtCore.Qt.Checked
        )
        self.update()
        self.checkedChanged.emit()

    def showPopup(self):
        self._pressed = None
        super().showPopup()

    def wheelEvent(self, event):
        # The wheel scrolls the panel: there is no current item to change.
        event.ignore()

    def eventFilter(self, watched, event):
        view = self.view()
        if watched is view.viewport():
            if event.type() == QtCore.QEvent.MouseButtonPress:
                self._pressed = view.indexAt(event.pos()).row()
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                # A click ticks its item and leaves the list open; the
                # release of the click that opened the list does nothing.
                row = view.indexAt(event.pos()).row()
                pressed, self._pressed = self._pressed, None
                if row >= 0 and row == pressed:
                    self.toggle(row)
                return True
        elif watched is view and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Space:
                self.toggle(view.currentIndex().row())
                return True
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        painter = QtGui.QStylePainter(self)
        option = QtGui.QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentIcon = QtGui.QIcon()
        option.currentText = ""
        painter.drawComplexControl(QtGui.QStyle.CC_ComboBox, option)
        room = self.style().subControlRect(
            QtGui.QStyle.CC_ComboBox, option, QtGui.QStyle.SC_ComboBoxEditField, self
        )
        option.currentText = self.fontMetrics().elidedText(
            self.checked_text(), QtCore.Qt.ElideRight, max(room.width() - 4, 0)
        )
        painter.drawControl(QtGui.QStyle.CE_ComboBoxLabel, option)
