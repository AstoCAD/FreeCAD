# Sketcher Blocks

Each `.txt` file is a geometry snapshot in the format produced by Sketcher's
**Copy Elements** command. To create a block, select at least two edges while
editing a sketch, then choose **Create Block** from the right-click menu or
the Sketcher tools menu. Choose a name in the save dialog, which starts in the
default block library folder. The sketch and clipboard remain unchanged.
Alternatively, save Copy Elements clipboard text as UTF-8. Insert Block can browse to that file.
Files in the user's `Mod/Sketcher/Blocks` directory also appear in the library;
subdirectories provide categories. User entries take precedence over bundled
entries with the same relative name.

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
