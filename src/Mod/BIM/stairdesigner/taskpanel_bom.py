# SPDX-License-Identifier: LGPL-2.1-or-later

"""Bill-of-materials task-panel page: the timber stock to order.

Two sub-tabs: the dimensions of each member, the smallest rectangle of
stock it is cut from, exported as a list or as dimensioned drawings; and
the stock layout, the members laid out on the planks or panels of their
materials, counting the stock to order, previewing each plank or panel
and exporting it to DXF.
"""

import os

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

from .stair_bom import (
    MEMBER_KINDS,
    Material,
    default_materials,
    flat_pieces,
    kind_label,
    material_names,
    set_stair_materials,
    stair_layout,
    stair_materials,
    stair_stock,
    stock_csv,
    stock_totals,
)
from .stair_drawing import DRAWN_KINDS, PAPER_SIZES, DrawingSettings, make_stair_drawings
from .stair_dxf import stock_dxf
from .stair_sketch import make_stock_sketch, stock_sketch
from .taskpanel_position import _PARAMETERS, _selection_path
from .taskpanel_widgets import _CheckableComboBox

translate = FreeCAD.Qt.translate

_DRAWING_KINDS = "StairDesignerDrawingKinds"
_DRAWING_PAPER = "StairDesignerDrawingPaper"
_DRAWING_STANDARD_SCALE = "StairDesignerDrawingStandardScale"
_DRAWING_HIDDEN_EDGES = "StairDesignerDrawingHiddenEdges"

_PIECE_ROLE = QtCore.Qt.UserRole
# Identity of a materials table row: kinds follow their row when rows
# above it are deleted or it is renamed.
_ROW_ROLE = QtCore.Qt.UserRole + 1


def _kinds_label(kind):
    return {
        "Stringer": translate("BIM", "Stringers"),
        "Tread": translate("BIM", "Treads"),
        "Riser": translate("BIM", "Risers"),
        "Wedge": translate("BIM", "Wedges"),
    }[kind]


def _number(value):
    return f"{value:.0f}"


class _MaterialTableWidget(QtGui.QTableWidget):
    """Materials table that deletes the current row with the Delete key."""

    def __init__(self, delete_callback, parent=None):
        super().__init__(0, 4, parent)
        self._delete_callback = delete_callback

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Delete and self.state() != self.EditingState:
            self._delete_callback()
            event.accept()
            return
        super().keyPressEvent(event)


def _stock_size(found):
    """Return the stock size of a material layout: thickness, length, width."""

    sizes = [found.material.length, found.material.width]
    if found.thickness > 0.0:
        sizes.insert(0, found.thickness)
    return " × ".join(_number(size) for size in sizes)


def _stock_name(found):
    """Return the name of a material layout's stock, with its thickness."""

    if found.thickness > 0.0:
        return f"{found.material.name} {_number(found.thickness)}"
    return found.material.name


def _stored_drawing_settings():
    """Return the drawing settings last used, the default ones at first."""

    parameters = FreeCAD.ParamGet(_PARAMETERS)
    default = DrawingSettings()
    kinds = parameters.GetString(_DRAWING_KINDS, ",".join(default.kinds)).split(",")
    paper = parameters.GetString(_DRAWING_PAPER, default.paper)
    return DrawingSettings(
        tuple(kind for kind in DRAWN_KINDS if kind in kinds),
        paper if paper in PAPER_SIZES else default.paper,
        parameters.GetBool(_DRAWING_STANDARD_SCALE, default.standard_scale),
        parameters.GetBool(_DRAWING_HIDDEN_EDGES, default.hidden_edges),
    )


def _store_drawing_settings(settings):
    parameters = FreeCAD.ParamGet(_PARAMETERS)
    parameters.SetString(_DRAWING_KINDS, ",".join(settings.kinds))
    parameters.SetString(_DRAWING_PAPER, settings.paper)
    parameters.SetBool(_DRAWING_STANDARD_SCALE, settings.standard_scale)
    parameters.SetBool(_DRAWING_HIDDEN_EDGES, settings.hidden_edges)


class _DrawingSettingsDialog(QtGui.QDialog):
    """Asks what the exported drawings show and the pages they are scaled to."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("BIM", "Export Drawings"))
        layout = QtGui.QVBoxLayout(self)
        parts = QtGui.QGroupBox(translate("BIM", "Parts"))
        parts.setToolTip(translate("BIM", "Kinds of parts drawn, one page per distinct shape"))
        parts_layout = QtGui.QHBoxLayout(parts)
        self.kinds = {}
        for kind in DRAWN_KINDS:
            box = QtGui.QCheckBox(_kinds_label(kind))
            box.setChecked(kind in settings.kinds)
            box.toggled.connect(self._kinds_changed)
            parts_layout.addWidget(box)
            self.kinds[kind] = box
        layout.addWidget(parts)

        form = QtGui.QFormLayout()
        self.paper = QtGui.QComboBox()
        for name in PAPER_SIZES:
            self.paper.addItem(name, name)
        self.paper.setCurrentIndex(max(self.paper.findData(settings.paper), 0))
        form.addRow(translate("BIM", "Paper size"), self.paper)
        self.scale = QtGui.QComboBox()
        self.scale.addItem(translate("BIM", "Fit to page"), False)
        self.scale.addItem(translate("BIM", "Standard scale"), True)
        self.scale.setCurrentIndex(1 if settings.standard_scale else 0)
        self.scale.setToolTip(
            translate(
                "BIM",
                "Draws each part as large as its page allows, or at the "
                "largest of 1:1, 1:2, 1:5, 1:10 and so on that fits it",
            )
        )
        form.addRow(translate("BIM", "Scale"), self.scale)
        layout.addLayout(form)
        self.hidden_edges = QtGui.QCheckBox(translate("BIM", "Show hidden edges"))
        self.hidden_edges.setChecked(settings.hidden_edges)
        self.hidden_edges.setToolTip(
            translate(
                "BIM",
                "Draws the edges hidden under the face shown, such as the "
                "tenon cheeks cut from the underside",
            )
        )
        layout.addWidget(self.hidden_edges)

        self.buttons = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._kinds_changed()

    def _kinds_changed(self, *args):
        # Nothing to draw without a kind of part.
        self.buttons.button(QtGui.QDialogButtonBox.Ok).setEnabled(bool(self.settings().kinds))

    def settings(self):
        return DrawingSettings(
            tuple(kind for kind, box in self.kinds.items() if box.isChecked()),
            self.paper.currentData(),
            bool(self.scale.currentData()),
            self.hidden_edges.isChecked(),
        )


def _fit_columns(tree):
    """Stretch a tree's first column; the others fit their contents."""

    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QtGui.QHeaderView.Stretch)
    for column in range(1, tree.columnCount()):
        header.setSectionResizeMode(column, QtGui.QHeaderView.ResizeToContents)


class _StockView(QtGui.QGraphicsView):
    """Preview of one plank or panel with the parts laid on it."""

    def __init__(self):
        super().__init__()
        self.setScene(QtGui.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setMinimumHeight(140)
        # Always fitted: nothing to scroll to.
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # Y up, as in the drawing.
        self.scale(1.0, -1.0)

    def show_stock(self, stock):
        scene = self.scene()
        scene.clear()
        self._stock_rect = None
        if stock is None:
            scene.setSceneRect(QtCore.QRectF())
            return
        self._stock_rect = QtCore.QRectF(0.0, 0.0, stock.length, stock.width)
        # The scene rect would otherwise only grow, from stock to stock.
        scene.setSceneRect(self._stock_rect.adjusted(-20, -20, 20, 20))
        palette = self.palette()
        text_color = palette.color(QtGui.QPalette.Text)
        scene.addRect(
            QtCore.QRectF(0.0, 0.0, stock.length, stock.width),
            QtGui.QPen(text_color, 0),
            QtGui.QBrush(palette.color(QtGui.QPalette.AlternateBase)),
        )
        part_brush = QtGui.QBrush(QtGui.QColor(196, 150, 100))
        pocket_brush = QtGui.QBrush(QtGui.QColor(140, 95, 55))
        for placed in stock.placed:
            polygon = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in placed.outline])
            scene.addPolygon(polygon, QtGui.QPen(text_color, 0), part_brush)
            for _depth, outline in placed.part.pockets:
                pocket = QtGui.QPolygonF(
                    [QtCore.QPointF(x, y) for x, y in placed.map(outline)]
                )
                scene.addPolygon(pocket, QtGui.QPen(QtCore.Qt.NoPen), pocket_brush)
            # Cut from the underside: outlined only.
            back_pen = QtGui.QPen(QtGui.QColor(140, 95, 55), 0, QtCore.Qt.DashLine)
            for _depth, outline in placed.part.back_pockets:
                pocket = QtGui.QPolygonF(
                    [QtCore.QPointF(x, y) for x, y in placed.map(outline)]
                )
                scene.addPolygon(pocket, back_pen)
            label = scene.addSimpleText(
                translate("BIM", "{} (flipped)").format(placed.part.label)
                if placed.flipped
                else placed.part.label
            )
            label.setFlag(QtGui.QGraphicsItem.ItemIgnoresTransformations)
            text = label.boundingRect()
            label.setTransform(
                QtGui.QTransform.fromTranslate(-text.width() / 2.0, -text.height() / 2.0)
            )
            label.setPos(polygon.boundingRect().center())
        self.fit()

    def fit(self):
        rect = getattr(self, "_stock_rect", None)
        if rect is not None and not rect.isEmpty():
            self.fitInView(rect.adjusted(-20, -20, 20, 20), QtCore.Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()


class BomPanelMixin:
    """Task-panel methods grouped by responsibility."""

    def _make_bom_panel(self):
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.bom_tabs = QtGui.QTabWidget()
        layout.addWidget(self.bom_tabs)

        # Component dimensions
        components = QtGui.QWidget()
        components_layout = QtGui.QVBoxLayout(components)
        self.bom_tabs.addTab(components, translate("BIM", "Component dimensions"))

        # Stock layout
        self.bom_layout_page = QtGui.QWidget()
        box = QtGui.QVBoxLayout(self.bom_layout_page)
        self.bom_tabs.addTab(self.bom_layout_page, translate("BIM", "Stock layout"))
        self.bom_tabs.setTabToolTip(
            1,
            translate(
                "BIM",
                "Lays the members out on planks or panels of their materials and "
                "counts how many to order",
            ),
        )
        self.bom_materials = _MaterialTableWidget(self._remove_bom_material)
        self.bom_materials.setHorizontalHeaderLabels(
            [
                translate("BIM", "Material"),
                translate("BIM", "Length"),
                translate("BIM", "Width"),
                translate("BIM", "Spacing"),
            ]
        )
        self.bom_materials.horizontalHeaderItem(3).setToolTip(
            translate(
                "BIM",
                "Spacing left between parts on the stock: saw kerf or cutter diameter",
            )
        )
        self.bom_materials.setToolTip(
            translate(
                "BIM",
                "Planks or panels the members are cut from, in mm, as thick as "
                "the parts: parts of another thickness get stock of their own. "
                "Treads wider than their planks are glued up from strips laid "
                "from the nosing. Right-click to add or delete a material",
            )
        )
        self.bom_materials.verticalHeader().setVisible(False)
        header = self.bom_materials.horizontalHeader()
        header.setSectionResizeMode(0, QtGui.QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QtGui.QHeaderView.ResizeToContents)
        self.bom_materials.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.bom_materials.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.bom_materials.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.bom_materials.customContextMenuRequested.connect(self._show_bom_material_menu)
        # Tall enough for the three default materials.
        self.bom_materials.setFixedHeight(
            header.sizeHint().height()
            + 3 * self.bom_materials.verticalHeader().defaultSectionSize()
            + 2 * self.bom_materials.frameWidth()
        )
        box.addWidget(self.bom_materials)

        # Two kinds per row, to keep the panel short.
        form = QtGui.QGridLayout()
        self.bom_assignment = {}
        for index, kind in enumerate(MEMBER_KINDS):
            combo = _CheckableComboBox(translate("BIM", "None"))
            combo.setToolTip(
                translate(
                    "BIM",
                    "Materials these parts may be cut from. With several ticked, "
                    "they are cut from the first one they fit, and go to another "
                    "only where that saves a plank or panel",
                )
            )
            self.bom_assignment[kind] = combo
            row, column = divmod(index, 2)
            form.addWidget(QtGui.QLabel(_kinds_label(kind)), row, 2 * column)
            form.addWidget(combo, row, 2 * column + 1)
            combo.checkedChanged.connect(self._bom_materials_changed)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        box.addLayout(form)
        self.bom_flip = QtGui.QCheckBox(translate("BIM", "Flip parts to save stock"))
        self.bom_flip.setToolTip(
            translate(
                "BIM",
                "Lets parts without housings be turned over, laid on their other "
                "face, where they fit better that way. Untick for stock with one "
                "finished face",
            )
        )
        self.bom_flip.setChecked(bool(getattr(self.stair, "BomFlipParts", True)))
        box.addWidget(self.bom_flip)

        self.bom_totals = QtGui.QTreeWidget()
        self.bom_totals.setHeaderLabels(
            [translate("BIM", "Stock"), translate("BIM", "Quantity"), translate("BIM", "Used")]
        )
        self.bom_totals.setToolTip(
            translate(
                "BIM",
                "Planks or panels to order per material. Select one to preview "
                "how the parts are laid on it",
            )
        )
        _fit_columns(self.bom_totals)
        box.addWidget(self.bom_totals)
        self.bom_warnings = QtGui.QLabel()
        self.bom_warnings.setWordWrap(True)
        self.bom_warnings.setVisible(False)
        box.addWidget(self.bom_warnings)
        self.bom_preview = _StockView()
        box.addWidget(self.bom_preview)
        layout_buttons = QtGui.QHBoxLayout()
        self.bom_export_dxf = QtGui.QPushButton(translate("BIM", "Export DXF…"))
        self.bom_export_dxf.setToolTip(
            translate(
                "BIM",
                "Saves the selected plank or panel, or all of the selected "
                "material's, with the parts' outlines and housing pockets",
            )
        )
        self.bom_edit_sketch = QtGui.QPushButton(translate("BIM", "Edit Panels in Sketch"))
        self.bom_edit_sketch.setToolTip(
            translate(
                "BIM",
                "Draws the planks or panels with their parts in a sketch and "
                "opens it, to move the parts by hand: each one slides as a "
                "whole when dragged. This panel closes, keeping its changes",
            )
        )
        layout_buttons.addStretch(1)
        layout_buttons.addWidget(self.bom_edit_sketch)
        layout_buttons.addWidget(self.bom_export_dxf)
        box.addLayout(layout_buttons)

        self.bom_tree = QtGui.QTreeWidget()
        self.bom_tree.setRootIsDecorated(False)
        self.bom_tree.setAlternatingRowColors(True)
        self.bom_tree.setHeaderLabels(
            [
                translate("BIM", "Part"),
                translate("BIM", "Qty"),
                translate("BIM", "Thickness"),
                translate("BIM", "Length"),
                translate("BIM", "Width"),
                translate("BIM", "Items"),
            ]
        )
        self.bom_tree.setToolTip(
            translate(
                "BIM",
                "Smallest rectangle of stock each part is cut from, in mm. Treads "
                "are measured along their nosing, the grain direction. Select a "
                "row to select its parts in the document",
            )
        )
        self.bom_tree.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        components_layout.addWidget(self.bom_tree)
        self.bom_sections = QtGui.QTreeWidget()
        self.bom_sections.setRootIsDecorated(False)
        self.bom_sections.setHeaderLabels(
            [translate("BIM", "Plank section"), translate("BIM", "Total length")]
        )
        self.bom_sections.setToolTip(
            translate(
                "BIM",
                "Plank length to order per section, end to end, without saw kerf "
                "or offcut allowance",
            )
        )
        _fit_columns(self.bom_sections)
        components_layout.addWidget(self.bom_sections)
        component_buttons = QtGui.QHBoxLayout()
        drawings = QtGui.QPushButton(translate("BIM", "Export Drawings…"))
        drawings.setToolTip(
            translate(
                "BIM",
                "Makes a TechDraw page with a dimensioned view of each distinct "
                "part, and saves them all to one PDF, to ask for quotes",
            )
        )
        export = QtGui.QPushButton(translate("BIM", "Export CSV…"))
        component_buttons.addStretch(1)
        component_buttons.addWidget(drawings)
        component_buttons.addWidget(export)
        components_layout.addLayout(component_buttons)

        buttons = QtGui.QHBoxLayout()
        refresh = QtGui.QPushButton(translate("BIM", "Refresh"))
        refresh.setToolTip(translate("BIM", "Measures the members again"))
        buttons.addStretch(1)
        buttons.addWidget(refresh)
        layout.addLayout(buttons)

        self.bom_rows = []
        self.bom_pieces = None
        self.bom_signature = None
        self.bom_layouts = []
        self._bom_filling = False
        self._fill_bom_materials()
        refresh.clicked.connect(self._refresh_bom_pieces)
        export.clicked.connect(self._export_bom)
        drawings.clicked.connect(self._export_bom_drawings)
        self.bom_export_dxf.clicked.connect(self._export_bom_dxf)
        self.bom_edit_sketch.clicked.connect(self._edit_bom_sketch)
        self.bom_materials.itemChanged.connect(self._bom_materials_changed)
        self.bom_flip.toggled.connect(self._bom_flip_changed)
        self.bom_tree.itemSelectionChanged.connect(self._bom_rows_selected)
        self.bom_tabs.currentChanged.connect(self._bom_tab_shown)
        self.bom_totals.currentItemChanged.connect(self._bom_stock_selected)
        self.section_tabs.currentChanged.connect(self._bom_tab_shown)
        return widget

    # Materials

    def _fill_bom_materials(self):
        self._bom_filling = True
        try:
            materials, assignment = stair_materials(self.stair)
            self.bom_materials.setRowCount(0)
            for material in materials:
                self._append_bom_material_row(material)
            self._fill_bom_assignment(assignment)
        finally:
            self._bom_filling = False

    def _append_bom_material_row(self, material):
        row = self.bom_materials.rowCount()
        self.bom_materials.insertRow(row)
        self._bom_row_ids = getattr(self, "_bom_row_ids", 0) + 1
        name = QtGui.QTableWidgetItem(material.name)
        name.setData(_ROW_ROLE, self._bom_row_ids)
        self.bom_materials.setItem(row, 0, name)
        for column, value in enumerate(
            (material.length, material.width, material.spacing), start=1
        ):
            # Spacing may be fractional: a 3.2 mm saw kerf.
            item = QtGui.QTableWidgetItem(f"{value:g}" if column == 3 else _number(value))
            item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.bom_materials.setItem(row, column, item)

    def _table_materials(self):
        materials = []
        for row in range(self.bom_materials.rowCount()):
            name_item = self.bom_materials.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            values = []
            for column in range(1, 4):
                item = self.bom_materials.item(row, column)
                try:
                    values.append(max(0.0, float(item.text().replace(",", "."))))
                except (AttributeError, ValueError):
                    values.append(0.0)
            materials.append(Material(name or f"{row + 1}", *values))
        return materials

    def _bom_row_id(self, row):
        item = self.bom_materials.item(row, 0)
        return item.data(_ROW_ROLE) if item is not None else None

    def _fill_bom_assignment(self, assignment):
        names = [material.name for material in self._table_materials()]
        ids = [self._bom_row_id(row) for row in range(len(names))]
        for kind, combo in self.bom_assignment.items():
            wanted = material_names(assignment.get(kind))
            combo.set_items(
                list(zip(names, ids)),
                [row_id for name, row_id in zip(names, ids) if name in wanted],
            )

    def _show_bom_material_menu(self, position):
        clicked = self.bom_materials.itemAt(position)
        if clicked is not None:
            self.bom_materials.setCurrentItem(clicked)
        menu = QtGui.QMenu(self.bom_materials)
        add_action = menu.addAction(
            QtGui.QIcon(":/icons/Arch_Add.svg"),
            translate("BIM", "Add Material"),
        )
        add_action.triggered.connect(self._add_bom_material)
        if clicked is not None:
            menu.addSeparator()
            delete_action = menu.addAction(
                QtGui.QIcon(":/icons/Arch_Remove.svg"),
                translate("BIM", "Delete Material"),
            )
            delete_action.triggered.connect(self._remove_bom_material)
        menu.exec_(self.bom_materials.viewport().mapToGlobal(position))

    def _add_bom_material(self, *args):
        materials = self._table_materials()
        name = translate("BIM", "Material {}").format(len(materials) + 1)
        self._bom_filling = True
        try:
            self._append_bom_material_row(Material(name, 2500.0, 1250.0))
        finally:
            self._bom_filling = False
        self._bom_materials_changed()

    def _remove_bom_material(self, *args):
        row = self.bom_materials.currentRow()
        if row < 0:
            return
        self._bom_filling = True
        try:
            self.bom_materials.removeRow(row)
        finally:
            self._bom_filling = False
        self._bom_materials_changed()

    def _bom_materials_changed(self, *args):
        if self._loading or self._bom_filling:
            return
        materials = self._table_materials()
        # Keep each kind on the rows it chose, renamed or moved up by a
        # deletion; a deleted row is no longer among its kinds' materials.
        names = {
            self._bom_row_id(row): material.name for row, material in enumerate(materials)
        }
        assignment = {
            kind: [names[row_id] for row_id in combo.checked_data() if row_id in names]
            for kind, combo in self.bom_assignment.items()
        }
        self._fill_bom_assignment(assignment)
        set_stair_materials(self.stair, materials, assignment)
        self._refresh_bom()

    def _bom_flip_changed(self, checked):
        if self._loading or self._bom_filling:
            return
        self.stair.BomFlipParts = bool(checked)
        self._refresh_bom()

    def _default_bom_materials(self):
        """Give a stair without materials the default ones, sized from its parts."""

        if self._loading or self._bom_filling or self.bom_materials.rowCount():
            return
        if self.bom_pieces is not None:
            materials, assignment = default_materials(self.stair, self.bom_pieces)
            self._bom_filling = True
            try:
                for material in materials:
                    self._append_bom_material_row(material)
                self._fill_bom_assignment(assignment)
            finally:
                self._bom_filling = False
            set_stair_materials(self.stair, materials, assignment)

    def _stock_layout_shown(self):
        return (
            self.section_tabs.currentWidget() is self.section_widgets.get("bom")
            and self.bom_tabs.currentWidget() is self.bom_layout_page
        )

    # Pieces and layout

    def _bom_signature(self):
        """Return what the list depends on, cheap to compare."""

        return tuple(
            (part.Name, round(part.Shape.Volume, 3), tuple(part.Placement.Base))
            for group in (self.stair.StringersGroup, self.stair.StepsGroup)
            if group
            for part in group.Group
            if not part.Shape.isNull()
        )

    def _bom_tab_shown(self, *args):
        # Measure the members again only when they changed.
        if self.section_tabs.currentWidget() is self.section_widgets.get("bom"):
            if self.bom_pieces is None or self.bom_signature != self._bom_signature():
                self._refresh_bom_pieces()
            elif self._stock_layout_shown() and not self.bom_materials.rowCount():
                self._refresh_bom()

    def _refresh_bom_pieces(self, *args):
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.bom_pieces = flat_pieces(self.stair)
        finally:
            QtGui.QApplication.restoreOverrideCursor()
        self.bom_signature = self._bom_signature()
        self._refresh_bom()

    def _refresh_bom(self, *args):
        if self.bom_pieces is None:
            return
        if self._stock_layout_shown():
            self._default_bom_materials()
        self.bom_rows = stair_stock(self.stair, 0.0, self.bom_pieces)
        self._fill_bom_rows()
        self.bom_sections.clear()
        for thickness, width, length in stock_totals(self.bom_rows):
            item = QtGui.QTreeWidgetItem(
                [f"{thickness:.0f} × {width:.0f} mm", f"{length / 1000.0:.2f} m"]
            )
            item.setTextAlignment(1, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.bom_sections.addTopLevelItem(item)

        materials, assignment = stair_materials(self.stair)
        self.bom_totals.clear()
        self.bom_layouts, unassigned = stair_layout(
            materials, assignment, self.bom_pieces, self.bom_flip.isChecked()
        )
        self._fill_bom_layouts()
        warnings = []
        loose_wedges = [piece for piece in unassigned if piece.kind == "Wedge"]
        unassigned = [piece for piece in unassigned if piece.kind != "Wedge"]
        if unassigned:
            warnings.append(
                translate("BIM", "No material: {}").format(
                    ", ".join(sorted({piece.label for piece in unassigned}))
                )
            )
        if loose_wedges:
            warnings.append(
                translate("BIM", "No material for {} wedges: cut them from offcuts").format(
                    len(loose_wedges)
                )
            )
        for found in self.bom_layouts:
            too_large = [piece for piece in found.unplaced if piece.kind != "Wedge"]
            offcuts = [piece for piece in found.unplaced if piece.kind == "Wedge"]
            if too_large:
                warnings.append(
                    translate("BIM", "Too large for {}: {}").format(
                        found.material.name,
                        ", ".join(piece.label for piece in too_large),
                    )
                )
            if offcuts:
                warnings.append(
                    translate("BIM", "No room left on {} for {} wedges: cut them from offcuts").format(
                        found.material.name, len(offcuts)
                    )
                )
        self.bom_warnings.setText("\n".join(warnings))
        self.bom_warnings.setVisible(bool(warnings))
        self.bom_export_dxf.setEnabled(bool(self.bom_layouts))
        self.bom_edit_sketch.setEnabled(any(found.stocks for found in self.bom_layouts))
        self.bom_preview.show_stock(None)
        if self.bom_totals.topLevelItemCount():
            first = self.bom_totals.topLevelItem(0)
            self.bom_totals.setCurrentItem(first.child(0) if first.childCount() else first)

    def _fill_bom_rows(self):
        # Emptying the list is no choice of the user's: the selection in
        # the document stays as it is.
        self.bom_tree.blockSignals(True)
        try:
            self._fill_bom_tree()
        finally:
            self.bom_tree.blockSignals(False)

    def _fill_bom_tree(self):
        self.bom_tree.clear()
        for index, row in enumerate(self.bom_rows):
            item = QtGui.QTreeWidgetItem(
                [
                    kind_label(row["kind"]),
                    str(row["quantity"]),
                    _number(row["thickness"]),
                    _number(row["length"]),
                    _number(row["width"]),
                    ", ".join(row["parts"]),
                ]
            )
            for column in range(1, 5):
                item.setTextAlignment(column, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            item.setData(0, _PIECE_ROLE, index)
            self.bom_tree.addTopLevelItem(item)
        for column in range(5):
            self.bom_tree.resizeColumnToContents(column)

    def _bom_rows_selected(self):
        """Select the parts of the selected rows in the document, which
        shows them in the view. Wedges are no parts of their own."""

        items = self.bom_tree.selectedItems()
        if self._loading or not items:
            return
        document = self.stair.Document
        parts = []
        for item in items:
            index = item.data(0, _PIECE_ROLE)
            if index is None or not 0 <= index < len(self.bom_rows):
                continue
            for part in self.bom_rows[index]["sources"]:
                try:
                    # A part measured before the stair was rebuilt may be gone.
                    found = document.getObject(part.Name)
                except ReferenceError:
                    continue
                if found is not None and found not in parts:
                    parts.append(found)
        FreeCADGui.Selection.clearSelection()
        for part in parts:
            # The stair shows its parts within itself: the view only
            # highlights one selected by its path from the stair.
            root, path = _selection_path(part, "")
            FreeCADGui.Selection.addSelection(root.Document.Name, root.Name, path)

    def _fill_bom_layouts(self):
        for found in self.bom_layouts:
            material = found.material
            used = (
                sum(stock.used for stock in found.stocks) / len(found.stocks)
                if found.stocks
                else 0.0
            )
            top = QtGui.QTreeWidgetItem(
                [
                    f"{material.name}: {_stock_size(found)} mm",
                    str(len(found.stocks)),
                    f"{used * 100.0:.0f} %",
                ]
            )
            top.setData(0, _PIECE_ROLE, ("material", found))
            for index, stock in enumerate(found.stocks, start=1):
                child = QtGui.QTreeWidgetItem(
                    [
                        translate("BIM", "{} {}").format(_stock_name(found), index),
                        str(len(stock.placed)),
                        f"{stock.used * 100.0:.0f} %",
                    ]
                )
                child.setData(0, _PIECE_ROLE, ("stock", found, stock))
                top.addChild(child)
            self.bom_totals.addTopLevelItem(top)
            top.setExpanded(True)

    def _bom_stock_selected(self, current, *args):
        data = current.data(0, _PIECE_ROLE) if current is not None else None
        stock = None
        if data and data[0] == "stock":
            stock = data[2]
        elif data and data[0] == "material" and data[1].stocks:
            stock = data[1].stocks[0]
        self.bom_preview.show_stock(stock)

    # Export

    def _export_bom(self, *args):
        if self.bom_pieces is None or self.bom_signature != self._bom_signature():
            self._refresh_bom_pieces()
        path, _filter = QtGui.QFileDialog.getSaveFileName(
            self.form,
            translate("BIM", "Export bill of materials"),
            f"{self.stair.Label}.csv",
            translate("BIM", "CSV files (*.csv)"),
        )
        if not path:
            return
        self._write_bom_file(path, stock_csv(self.bom_rows))

    def _export_bom_drawings(self, *args):
        if self.bom_pieces is None or self.bom_signature != self._bom_signature():
            self._refresh_bom_pieces()
        dialog = _DrawingSettingsDialog(_stored_drawing_settings(), self.form)
        if not dialog.exec_():
            return
        settings = dialog.settings()
        _store_drawing_settings(settings)
        title = translate("BIM", "Export Drawings")
        pages = []
        failure = None
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            pages = make_stair_drawings(self.stair, self.bom_pieces, settings)
        except (OSError, ValueError, RuntimeError) as error:
            failure = str(error)
        finally:
            QtGui.QApplication.restoreOverrideCursor()
        if failure:
            QtGui.QMessageBox.warning(self.form, title, failure)
            return
        if not pages:
            QtGui.QMessageBox.information(
                self.form, title, translate("BIM", "The stair has none of the selected parts")
            )
            return
        # The pages stay in the document, whether saved to a file or not.
        path, _filter = QtGui.QFileDialog.getSaveFileName(
            self.form, title, f"{self.stair.Label}.pdf", translate("BIM", "PDF files (*.pdf)")
        )
        if not path:
            return
        import TechDrawGui

        if os.path.exists(path):
            # A file TechDraw cannot replace is left as it was: tell so.
            before = os.stat(path).st_mtime_ns
        else:
            before = None
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            TechDrawGui.exportPagesAsPdf(pages, path)
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            failure = str(error)
        finally:
            QtGui.QApplication.restoreOverrideCursor()
        if failure is None and (
            not os.path.exists(path) or os.stat(path).st_mtime_ns == before
        ):
            failure = translate("BIM", "The file could not be written: {}").format(path)
        if failure:
            QtGui.QMessageBox.warning(self.form, title, failure)

    def _export_bom_dxf(self, *args):
        current = self.bom_totals.currentItem()
        data = current.data(0, _PIECE_ROLE) if current is not None else None
        if not data:
            QtGui.QMessageBox.information(
                self.form,
                translate("BIM", "Export DXF"),
                translate("BIM", "Select a material, or one of its planks or panels"),
            )
            return
        found = data[1]
        stocks = [data[2]] if data[0] == "stock" else found.stocks
        name = (
            f"{self.stair.Label} {current.text(0)}"
            if data[0] == "stock"
            else f"{self.stair.Label} {_stock_name(found)}"
        )
        path, _filter = QtGui.QFileDialog.getSaveFileName(
            self.form,
            translate("BIM", "Export DXF"),
            f"{name}.dxf",
            translate("BIM", "DXF files (*.dxf)"),
        )
        if not path:
            return
        # DXF R12 text is in the drawing's code page, not UTF-8.
        self._write_bom_file(path, stock_dxf(stocks), "cp1252")

    def _bom_sketch(self):
        """Return the sketch of the stock layout to edit, made anew or the
        one the stair has, as the user chooses; ``None`` if they give up."""

        sketch = stock_sketch(self.stair)
        if sketch is not None:
            box = QtGui.QMessageBox(self.form)
            box.setIcon(QtGui.QMessageBox.Question)
            box.setWindowTitle(translate("BIM", "Edit Panels in Sketch"))
            box.setText(
                translate(
                    "BIM",
                    "The stair already has a sketch of its stock layout. Open it, "
                    "with its parts where they were moved, or replace it by the "
                    "layout as it is now?",
                )
            )
            keep = box.addButton(translate("BIM", "Open"), QtGui.QMessageBox.AcceptRole)
            replace = box.addButton(
                translate("BIM", "Replace"), QtGui.QMessageBox.DestructiveRole
            )
            box.addButton(QtGui.QMessageBox.Cancel)
            box.setDefaultButton(keep)
            box.exec_()
            if box.clickedButton() is keep:
                return sketch
            if box.clickedButton() is not replace:
                return None
        return make_stock_sketch(self.stair, self.bom_layouts)

    def _edit_bom_sketch(self, *args):
        sketch = self._bom_sketch()
        if sketch is None:
            return
        name = sketch.Name
        document = self.stair.Document

        def edit():
            # A sketch is edited in a panel of its own: this one closes
            # first, its changes kept as with OK.
            self.accept()
            FreeCADGui.Control.closeDialog()
            found = document.getObject(name)
            if found is not None:
                FreeCADGui.getDocument(document.Name).setEdit(name)
                FreeCADGui.activateWorkbench("SketcherWorkbench")

        # Once the click is dealt with: closing the panel deletes its button.
        QtCore.QTimer.singleShot(0, edit)

    def _write_bom_file(self, path, text, encoding="utf-8"):
        try:
            with open(path, "w", encoding=encoding, errors="replace", newline="") as stream:
                stream.write(text)
        except OSError as error:
            QtGui.QMessageBox.warning(self.form, translate("BIM", "Export"), str(error))
