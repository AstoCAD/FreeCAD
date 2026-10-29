# SPDX-License-Identifier: LGPL-2.1-or-later
"""Face highlight and selection pixels must not depend on earlier overlays.

Regression coverage for https://github.com/FreeCAD/FreeCAD/issues/30889.
Requires an explicitly selected disposable profile and an initialized GUI
process, but creates no document, window, or preference changes.
"""

import importlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest


_SIZE = 256
# Interior rectangles for the fixed camera and geometry below. Bounds are
# [left, top, right-exclusive, bottom-exclusive] in QImage coordinates.
_SMALL_INTERIOR = (56, 128, 76, 145)
_RIGHT_INTERIOR = (150, 90, 178, 118)


def _plain_path(path):
    for component in (path, *path.parents):
        try:
            if component.is_symlink():
                return False
            is_junction = getattr(component, "is_junction", None)
            if is_junction is not None and is_junction():
                return False
            attributes = getattr(component.lstat(), "st_file_attributes", 0)
            if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                return False
        except FileNotFoundError:
            continue
        except OSError:
            return False
    return True


def _owned_profile():
    selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
    configured = os.environ.get("FREECAD_USER_HOME")
    if not selected or not configured:
        raise unittest.SkipTest("Requires an explicitly selected disposable test profile")
    selected_path = Path(selected)
    configured_path = Path(configured)
    for path in (selected_path, configured_path):
        if not path.is_absolute() or not _plain_path(path):
            raise unittest.SkipTest("Disposable profile paths must be absolute and free of links")
    try:
        profile = selected_path.resolve(strict=True)
        same_home = configured_path.resolve(strict=True) == profile
    except OSError:
        raise unittest.SkipTest("The disposable test profile must already exist")
    if not profile.is_dir() or not same_home:
        raise unittest.SkipTest("FREECAD_USER_HOME must select the disposable test profile")
    return profile


def _runtime(profile):
    # Environment admission precedes all CAD, GUI, Coin, and Qt runtime imports.
    App = importlib.import_module("FreeCAD")
    if not App.GuiUp:
        raise unittest.SkipTest("Face overlay rendering requires a GUI test process")

    active_paths = {
        "UserParameter": Path(App.ConfigGet("UserParameter")),
        "UserAppData": Path(App.getUserAppDataDir()),
    }
    system_parameter = App.ConfigGet("SystemParameter")
    if system_parameter:
        active_paths["SystemParameter"] = Path(system_parameter)
    for name, path in active_paths.items():
        if not path.is_absolute() or not _plain_path(path):
            raise unittest.SkipTest(f"Active {name} must be absolute and free of links")
        if not path.resolve().is_relative_to(profile):
            raise unittest.SkipTest(f"Active {name} is outside the disposable test profile")
    if active_paths["UserParameter"].resolve() != profile / "user.cfg":
        raise unittest.SkipTest("Active user configuration is not the disposable user.cfg")
    if "SystemParameter" in active_paths:
        if active_paths["SystemParameter"].resolve() != profile / "system.cfg":
            raise unittest.SkipTest("Active system configuration is not the disposable system.cfg")

    if sys.platform.startswith("linux"):
        display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
        if not display and platform not in {"offscreen", "minimal", "eglfs", "linuxfb", "vnc"}:
            raise unittest.SkipTest("A display or explicitly configured Qt platform is required")

    Gui = importlib.import_module("FreeCADGui")
    QtGui = importlib.import_module("PySide.QtGui")
    if QtGui.QGuiApplication.instance() is None:
        raise unittest.SkipTest("Requires an initialized Qt GUI application")
    importlib.import_module("PartGui")
    coin = importlib.import_module("pivy.coin")
    return Gui, coin, QtGui


def _is_overlay(rgb, mode):
    red, green, blue = rgb
    if mode == "highlight":
        return red >= 180 and green <= 70 and blue <= 70
    return green >= 120 and red <= 70 and blue <= 70


def _is_grey(rgb):
    return 80 <= min(rgb) <= max(rgb) <= 200 and max(rgb) - min(rgb) <= 5


def _count_region(image, rectangle, predicate):
    left, top, right, bottom = rectangle
    count = 0
    for y in range(top, bottom):
        for x in range(left, right):
            color = image.pixelColor(x, y)
            count += bool(predicate((color.red(), color.green(), color.blue())))
    return count


class TestBrepFaceOverlayHistory(unittest.TestCase):
    def setUp(self):
        self.profile = _owned_profile()  # First active step, before runtime imports.
        self.Gui, self.coin, self.QtGui = _runtime(self.profile)
        temporary = tempfile.TemporaryDirectory(prefix="brep-face-overlay-", dir=str(self.profile))
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self._roots = []
        # Cleanup is LIFO: release scene references before removing their images.
        self.addCleanup(self._roots.clear)

    def _make_scene(self, mode):
        coin = self.coin
        node_type = coin.SoType.fromName("SoBrepFaceSet")
        self.assertFalse(node_type.isBad(), "PartGui did not register SoBrepFaceSet")
        faces = node_type.createInstance()
        self.assertIsNotNone(faces)
        root = coin.SoSeparator()
        self._roots.append(root)
        camera = coin.SoOrthographicCamera()
        camera.position.setValue(0.0, 0.0, 5.0)
        camera.height.setValue(2.4)
        camera.aspectRatio.setValue(1.0)
        camera.nearDistance.setValue(1.0)
        camera.farDistance.setValue(10.0)
        root.addChild(camera)
        light = coin.SoLightModel()
        light.model.setValue(coin.SoLightModel.BASE_COLOR)
        root.addChild(light)
        material = coin.SoMaterial()
        material.diffuseColor.setValue(0.6, 0.6, 0.6)
        material.transparency.setValue(0.0)
        root.addChild(material)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(0, 7, [
            coin.SbVec3f(-0.85, -0.25, 0.0),
            coin.SbVec3f(-0.35, -0.25, 0.0),
            coin.SbVec3f(-0.60, 0.30, 0.0),
            coin.SbVec3f(0.10, -0.55, 0.0),
            coin.SbVec3f(0.85, -0.55, 0.0),
            coin.SbVec3f(0.85, 0.55, 0.0),
            coin.SbVec3f(0.10, 0.55, 0.0),
        ])
        root.addChild(coordinates)
        # Part 0 is one isolated triangle on the left; part 1 is two triangles
        # forming a square on the right. The camera and base geometry stay fixed.
        faces.coordIndex.setValues(0, 12, [0, 1, 2, -1, 3, 4, 5, -1, 3, 5, 6, -1])
        faces.partIndex.setValues(0, 2, [1, 2])
        faces.highlightPartIndex.setNum(0)
        faces.selectionPartIndex.setNum(0)
        faces.highlightColor.setValue(1.0, 0.0, 0.0)
        faces.selectionColor.setValue(0.0, 0.75, 0.0)
        root.addChild(faces)
        field = faces.highlightPartIndex if mode == "highlight" else faces.selectionPartIndex
        # Selecting either part needs one input index, so this field never shrinks.
        field.setValues(0, 1, [0])
        return root, field

    def _capture(self, root, mode, stage):
        # A fresh renderer supplies independent GL/FBO cache identifiers while
        # the same scene node retains its internally owned overlay geometry.
        renderer = self.Gui.SoQtOffscreenRenderer(_SIZE, _SIZE)
        renderer.setNumPasses(0)
        renderer.setBackgroundColor(1.0, 1.0, 1.0, 1.0)
        renderer.setInternalTextureFormat(0x8058)  # GL_RGBA8, opaque capture.
        self.assertTrue(renderer.render(root), "Qt offscreen rendering failed")
        path = self.directory / f"{mode}-{stage}.png"
        renderer.writeToImage(str(path))
        del renderer
        image = self.QtGui.QImage(str(path))
        self.assertFalse(image.isNull(), "Offscreen image was not written")
        self.assertEqual((image.width(), image.height()), (_SIZE, _SIZE))
        pixels = [image.pixel(x, y) for y in range(_SIZE) for x in range(_SIZE)]
        metrics = {
            "small_overlay": _count_region(image, _SMALL_INTERIOR, lambda rgb: _is_overlay(rgb, mode)),
            "small_grey": _count_region(image, _SMALL_INTERIOR, _is_grey),
            "right_overlay": _count_region(image, _RIGHT_INTERIOR, lambda rgb: _is_overlay(rgb, mode)),
            "right_grey": _count_region(image, _RIGHT_INTERIOR, _is_grey),
        }
        self.assertGreater(
            sum((pixel & 0xFFFFFF) != 0xFFFFFF for pixel in pixels),
            1000,
            f"{stage}: renderer produced a blank or insufficiently populated image",
        )
        return pixels, metrics

    def _assert_history(self, mode):
        root, field = self._make_scene(mode)
        captures = []
        for stage, part in (("small-first", 0), ("large-first", 1), ("small-again", 0), ("large-again", 1)):
            field.set1Value(0, part)
            self.assertEqual(field.getNum(), 1)
            captures.append(self._capture(root, mode, stage))
        (small_pixels, small), (large_pixels, large), (again_pixels, again), (expanded_pixels, expanded) = captures

        # Hard positive controls precede history assertions: neither blank images
        # nor an uncolored base mesh can establish a rendering regression.
        self.assertGreater(small["small_overlay"], 200)
        self.assertGreater(small["right_grey"], 500)
        self.assertEqual(small["right_overlay"], 0)
        self.assertGreater(large["right_overlay"], 500)
        self.assertGreater(large["small_grey"], 200)
        self.assertEqual(large["small_overlay"], 0)
        self.assertGreater(again["small_overlay"], 200)
        self.assertGreater(expanded["right_overlay"], 500)
        self.assertGreater(expanded["small_grey"], 200)
        self.assertEqual(expanded["small_overlay"], 0)

        with self.subTest(check="small-image-history"):
            self.assertEqual(
                sum(before != after for before, after in zip(small_pixels, again_pixels)),
                0,
                "Returning to the same small overlay must restore every initial pixel",
            )
        with self.subTest(check="unselected-right-face"):
            self.assertEqual(again["right_overlay"], 0, "A previous face remains colored after shrinking")
            self.assertGreater(again["right_grey"], 500)
        with self.subTest(check="large-reexpansion"):
            self.assertEqual(
                sum(before != after for before, after in zip(large_pixels, expanded_pixels)),
                0,
                "Growing the overlay again must restore every initial large-overlay pixel",
            )

    def test_highlight_history(self):
        self._assert_history("highlight")

    def test_selection_history(self):
        self._assert_history("selection")


if __name__ == "__main__":
    unittest.main()
