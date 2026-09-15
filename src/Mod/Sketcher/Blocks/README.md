# Sketcher Blocks

Each `.txt` file is a geometry snapshot in the format produced by Sketcher's
**Copy Elements** command. To create a block, select at least two edges while
editing a sketch, then choose **Create Block** from the right-click menu or
the Blocks menu. In the tool widget, optionally enable **Fixed Size** as the
block's insertion default, then click in the sketch to choose the block origin.
For adjustable blocks, click a second point to define the end of the line handle.
The two points must differ. Fixed-size blocks need only the origin click.
Choose a name in the save dialog, which starts in the default block library folder.
Geometry is saved relative to the chosen origin. Internal constraints are kept;
constraints anchoring the selection to the source sketch axes are omitted.
The sketch and clipboard remain unchanged.
Alternatively, save Copy Elements clipboard text as UTF-8. Insert Block can browse to that file.
Files in the user's `Mod/Sketcher/Blocks` directory also appear in the library;
subdirectories preserve the folder hierarchy. Each library has a separate root,
so entries with the same name remain available in their respective folders.

The loader accepts the geometry-building statements emitted by Copy Elements.
It preserves construction geometry. Copied constraints are accepted as part of
the format; the inserted geometry is a snapshot controlled by a Group handle.
The loader does not execute arbitrary Python scripts.

The Group constraint stores its source in `File` metadata and the chosen width
or height mode in `FileHeight`. Select the Group in the constraints list and
choose **Reload From File** to update it. Reload retains the handle, its
dimensions, the Group's name and its place in a nested group. It replaces all
members, so constraints attached directly to those old members are removed.
The stored geometry remains usable when the source file is unavailable.

SVG import uses **File → Import** while a sketch is in edit, with the SVG geometry
importer selected. It imports at native size and position into a Group, with the
same reload action. SVG parsing belongs to the SVG importer; Blocks do not load it.

The nine bundled entries were converted from the previous Sketcher SVG library
using the SVG importer and Copy Elements. Their geometry and names are preserved.

## Placement

**Fixed Size** defaults to unchecked for stock blocks and Copy Elements files.
Create Block saves its checkbox choice in a `# Sketcher block fixed size: true`
or `false` comment. Insert Block loads that default whenever a file is selected.
You can override it for an insertion, and the block editor preserves the saved setting.
Adjustable blocks created with two points store a `# Sketcher block handle: x y`
comment: the handle endpoint relative to the origin. Its length and direction
control placement and reload independently of the geometry's bounding box.
The block editor preserves this handle. Older files retain width/height placement.

The first click places the source origin, including for scaled blocks.
With **Fixed Size** checked, dimensions stay at source size and the second click
sets orientation. **Fixed Orientation** preserves the source orientation; with
both checked, one click places the block. With only Fixed Orientation checked,
the second click sets size. Uncheck both to set size and orientation together.
Fixed-size blocks have a point handle at the source origin. Moving this point
translates the block without changing its size. Reload keeps the placement rotation.

## Editing a block

Select a block handle, one of its edges, or its constraint and choose **Edit Block**
from the right-click menu. A temporary **Block Edit** document opens the source
geometry at its original coordinates. Closing the sketch saves the text file,
updates matching instances in every open document, and closes the temporary document.
Each affected document receives an undo transaction. If saving or updating fails,
the source and instances remain unchanged and the editor stays open for recovery.

## Block libraries

Insert Block has a folder tree with **Built-in Blocks**, **User Blocks**, and any
folders added with **Add Folder**. Expand folders to browse their actual hierarchy.
Added folders and the last selected block are remembered between sessions.
**Refresh** reads changes made on disk. **Remove Folder** removes a custom folder
from the list without deleting any files. **Choose File** can also insert a text
file directly. Text has its own command; the **Blocks** command group contains
Insert Block, Create Block, Edit Block, and Reload From File.
