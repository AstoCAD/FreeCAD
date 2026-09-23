# Sketcher visual annotations

Implemented on AstoCAD, separately from the layer commits. Annotations are persistent visual data owned by a sketch, independent of its geometry, constraints, solver, and modeling Shape. Dimensions remain outside this milestone.

## Using annotations

Edit a sketch and use the **Cosmetics** toolbar, or **Sketch → Cosmetics**. The commands are **Cosmetic Text**, **Hatch**, and **Leader Line**; their tool widgets are titled after them. The **Show cosmetics** setting in the Edit controls settings menu hides the Cosmetics task panel and toolbar; cosmetics stay visible in the 3D view.

- **Text:** click to place the text's top-left corner and type directly in the view, as in TechDraw's rich annotation. A formatting toolbar above the text sets font, size, bold, italic, underline, strikethrough, color, and alignment. The tool widget sets text height, wrapping width (0 does not wrap), and rotation, remembered for the next text. Click elsewhere, press Escape, or press Ctrl+Enter to finish; an empty text is discarded. Double-click a text in the view or in the Cosmetics list (or use Edit in its context menu) to edit it the same way; clearing its content deletes it. Text has no edit dialog. The existing geometry-producing text tool remains available.
- **Hatch:** activate the tool and click one edge of each closed loop to hatch; preselected edges contribute their loops too. The whole loop is selected and the hatch previews as it grows. Click a hatched loop again to remove it. Loops inside another loop become holes, so an outer and an inner rectangle hatch only the frame. An edge on no closed loop (open wire or standalone edge) is refused with a warning; edges dangling from a loop are ignored. The tool widget sets pattern, spacing, and angle, which are remembered for the next hatch; the construction toggle decides construction mode as for geometry. Press Enter or right-click to create the hatch; Esc cancels.
- **Leader Line:** click the arrowhead point, then each bend; Ctrl snaps the angle of the segment being placed, as in the line tool. The preview shows the leader with its arrowhead. The tool widget sets the arrowhead style (filled or open arrow, tick, dot, open circle, fork, filled triangle, none — TechDraw's names, so linked pages match) and size, remembered for the next leader. Press Enter or right-click to create it; Esc cancels. Edit coordinates, arrowhead style and size in the editor; drag a point or the whole leader in the viewport.

Double-click a cosmetic in the list to open its editor, which provides a name, layer, and construction setting; the hatch editor also changes pattern, spacing, angle, and pattern origin. Text is edited in the view instead. Its numeric fields are unit
aware: they follow the active unit schema and accept expressions, and leader coordinates
accept an explicit length such as `0.5 in`. Construction annotations appear only in sketch edit mode. Normal annotations also appear outside edit and in linked TechDraw views. New annotations use the active layer and construction mode. Preview changes are discarded on Cancel. Creation, editing, dragging, and deletion support undo/redo.

Double-click a cosmetic in the list to edit it. Text and leaders can also be selected in the viewport, except where a sketch point, edge, or constraint lies under the cursor: geometry wins, so it stays selectable under a cosmetic. Hatches are deliberately unpickable in the viewport so boundary points, edges, and overlapping content remain accessible. Select a cosmetic in the taskbox; use Delete or the context menu to remove it. The existing Layer context menu moves annotation selections between layers. The layer removal dialog includes annotations in its move/delete decision.

Layer visibility and locking apply to annotations. Disabling Show layers displays annotations on all layers. Locked operations are ignored by GUI tools, which say why in the status bar and the report view rather than failing silently or interrupting with a dialog; the App API validates and rejects them. Constraint participation and solved-state colors have no effect on annotations. Normal annotation strokes inherit layer color, pattern, and fixed screen line width; rich text can override its text color. Selected and preselected annotations use the selection and preselection colors, including text, whose selection is checked against the edited object path so sketches inside a Body highlight too. Construction annotations use the construction color and normal sketch line width.

## App data and API

`Sketcher::Annotation` and `PropertyAnnotationList` provide a typed, versioned, transactional value model. Each record has a stable ID, type, label, layer, construction flag, and typed payload. The allocator retains its highest ID across undo and save/reopen, so new annotations cannot adopt an old TechDraw identity. `Sketch.Annotations` returns independent Python dictionary snapshots. Mutation uses:

```python
note = sketch.addAnnotation({
    "Type": "Text", "Html": "<b>Inspection note</b>",
    "Position": (10, 20, 0), "TextSize": 3.5,
})
sketch.updateAnnotation(note, {"Construction": True})
sketch.delAnnotations([note])
```

Types are `Text`, `Hatch`, and `Leader`. A hatch `Pattern` names one of the built-in PAT patterns; `getAnnotationPattern(id)` returns its line families (origin, direction, offset, dashes) in sketch millimetres. Positions and leader `Points` accept FreeCAD vectors or coordinate tuples. Hatch `Boundary` values are stable `GeometryFacadeList[index].Id` values, not current geometry indexes. `getAnnotationFace(id)` and `getAnnotationStrokes(id)` return transient rendering data without adding modeling geometry. `Annotation<ID>` is the stable selection subelement.

Hatches retain their boundary IDs when geometry indexes change. Deleted or invalid boundaries suppress the hatch and expose an error in the taskbox; they do not silently attach to another face. Undo restores valid references. Open boundaries are rejected. Excessively dense hatches are suppressed with a spacing error.

Copying the complete sketch copies annotations and their IDs with its geometry. Carbon copy, geometry duplication, and geometry-producing tools do not copy annotations. HTML uses Qt's rich-text subset, not a browser engine. Leader points are free sketch-local positions, not geometric attachments. This version supports the leader arrowheads listed above and the hatch patterns listed below.

## Hatch patterns

Patterns are PAT line families (angle, origin, offset, dashes), the format TechDraw and other CAD programs exchange, so the TechDraw counterpart embeds exactly what the sketch draws. No SVG is involved. Spacing scales every pattern by the same factor: it is the pitch of the general-use ANSI31 lines, and the other drafting patterns keep their proportions relative to it. Angle turns the pattern as defined, so 0° gives the standard 45° section lines.

- **Standard section lining** (ANSI Y14.2 material symbols as distributed in acad.pat): ANSI31 general use and cast iron, ANSI32 steel, ANSI33 bronze/brass/copper, ANSI34 plastic/rubber, ANSI35 refractory, ANSI36 marble/slate/glass, ANSI37 lead/zinc/magnesium/insulation (crosshatch), ANSI38 aluminium. ISO 128-3 (which replaced ISO 128-50) specifies the ANSI31 thin 45° lines for general use and leaves material symbols to be explained on the drawing or by other standards.
- **Common drafting conventions** from acad.pat, not standards: square grid, brick, earth, herringbone, crosses, honeycomb, insulation, dots, concrete (AR-CONC), and sand (AR-SAND).

Files saved before named patterns load as ANSI31 (or ANSI37 for crosshatch) with the angle adjusted, so they draw unchanged. An unknown pattern name in a file falls back to ANSI31.

## Gui implementation

`AnnotationManager` owns a shared Coin scene used inside and outside sketch edit. The scene has exactly one parent at a time, moving between the view provider's annotation node and the edit root, so nothing is drawn or picked twice. Rendering and picking are separate from geometry and constraint Coin indexes. Text is laid out with QTextDocument and cached as an adaptive-resolution transparent texture; the camera only re-rasters text whose resolution no longer fits, and never rebuilds the scene or the task box. Hatch strokes are cached by annotation value and re-clipped in one boolean operation; a boundary edit re-clips immediately and then waits for the geometry to settle, so dragging geometry does not re-clip per frame. Editor and drag previews never mutate persistent data until accepted.

The Cosmetics taskbox uses a list with per-item visibility checkboxes, type icons, and names. Its filter checkbox enables filters for type and layer; filtering changes only the list, not scene visibility. Right-click the list for Show All and Hide All, which affect all cosmetics regardless of the list filters. When Show layers is enabled, editable layer comboboxes appear in both Cosmetics and Elements. Hidden cosmetic IDs persist in the view provider and follow undo/redo and linked TechDraw visibility. Each creation tool has a dedicated cursor icon copied from TechDraw. The in-view text editor is a QGraphicsTextItem on the viewer's Quarter graphics scene, mapped onto the sketch by projecting the text frame through the camera (so it follows pan, zoom, rotation, and wrapping), with its toolbar as a proxy widget above it. While it has focus it receives all keys, so neither Coin nor application shortcuts see them, and the scene hides the stored raster of the edited text. The dialog editor handles hatch settings and leader points. Construction types and broken hatches have visible list indicators/tooltips. Refusals (a locked layer, an open loop, an invalid pattern) are explained in the status bar and report view; a tool keeps its picked loops or points when a save is refused. UI texts follow FreeCAD's FEP-0007 guideline: Title Case for commands, menus, buttons, and window titles; sentence case elsewhere; tooltips start with a verb; input hints start with the input. The hatch tool previews through the same scene with a scene-only annotation and reports problems as translated warnings in the status bar and report view instead of dialogs or exceptions. While a tool is active the construction toggle always switches the creation mode, even though the hatch tool keeps its loops selected.

## Linked TechDraw objects

TechDraw's `SketchAnnotations.py` adapter creates native `DrawRichAnno`, `DrawGeomHatch`, and `DrawLeaderLine` counterparts when a direct SketchObject source is included in a page's DrawViewPart. The adapter arms itself the first time a document contains a drawing page, so sessions without one pay nothing for it. SourceSketch, SourceAnnotationId, and AnnotationView persist their identities. Source edits, placement, view scale/rotation/direction, construction, layer visibility, deletion, undo/redo, and restore reconcile the same counterparts. GUI updates are queued until projection is ready, with a bounded number of retries before deferring to the next change; headless updates run at recompute boundaries or through `SketchAnnotations.synchronize(document)`.

Source-owned content is read-only in the native editors. `PageOffset` provides an additional page-space offset in millimetres without changing the sketch. Native TechDraw line weights remain page settings. Explicit layer colors carry to the page; the default page color is black.

Hatches match complete projected faces by area and overlap, including holes. Ambiguous or edge-on projections report an unresolved status and remain unhatched. Projected PAT definitions are embedded through TechDraw's included-file property, so saved files do not depend on a temporary PAT file. Construction annotations and missing sources suppress native content, including exports; undo can restore the links.

The adapter currently supports direct sketch sources in DrawViewPart. Automatic traversal of Body/Link sources and projection groups, geometry-attached leaders, arbitrary PAT pattern editing, and annotation dimensions are later extensions. PDF and SVG exports use the native TechDraw elements.

## Regression coverage

Tests cover App validation, snapshots, stable IDs/subelements, copying, save/reopen, undo/redo, solver/model separation, locking, and associative hatch holes and broken references. Native GUI tests exercise creation commands, rich-text edits, selection, dragging/locking, cancellation, construction/layer visibility, and annotation-only layer removal. TechDraw tests cover native types, scale/placement/projection, multiple views, offsets, persistence, broken boundaries, source/view deletion and undo, live layer visibility/color updates, unchanged synchronization, and PDF/SVG export.
