# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2019 sliptonic <shopinthewoods@gmail.com>               *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import os
import unittest

import FreeCAD
import Path
import CAMTests.PathTestUtils as PathTestUtils


class TestPathPreferences(PathTestUtils.PathTestBase):
    def test00(self):
        """There is at least one search path."""

        paths = Path.Preferences.searchPaths()
        self.assertGreater(len(paths), 0)

    def test01(self):
        """Path/Post is part of the posts search path."""
        paths = Path.Preferences.searchPathsPost()
        self.assertEqual(len([p for p in paths if p.endswith("/Path/Post/")]), 1)

    def test02(self):
        """Path/Post/scripts is part of the posts search path."""
        paths = Path.Preferences.searchPathsPost()
        self.assertEqual(len([p for p in paths if p.endswith("/Path/Post/scripts/")]), 1)

    def test03(self):
        """Available post processors include linuxcnc, generic and opensbp."""
        posts = Path.Preferences.allAvailablePostProcessors()
        self.assertIn("linuxcnc", posts)
        self.assertIn("generic", posts)
        self.assertIn("opensbp", posts)

    def test10_addon_post_path_registered(self):
        """A path added via addAddonPostPath() appears in searchPathsPost().

        Given: a temporary directory
        When: addAddonPostPath() is called with that directory
        Then: the directory is included in the list returned by searchPathsPost()
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            Path.Preferences.addAddonPostPath(tmpdir)
            paths = Path.Preferences.searchPathsPost()
            self.assertIn(tmpdir, paths)
            # Cleanup
            Path.Preferences._extra_post_paths.remove(tmpdir)

    def test11_addon_post_path_no_duplicates(self):
        """Calling addAddonPostPath() twice with the same path adds it only once.

        Given: a temporary directory
        When: addAddonPostPath() is called twice with the same path
        Then: searchPathsPost() contains the path exactly once
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            Path.Preferences.addAddonPostPath(tmpdir)
            Path.Preferences.addAddonPostPath(tmpdir)
            paths = Path.Preferences.searchPathsPost()
            self.assertEqual(paths.count(tmpdir), 1)
            Path.Preferences._extra_post_paths.remove(tmpdir)

    def test12_addon_asset_path_registers_posts_and_machines(self):
        """addAddonAssetPath() registers both the posts and machines subdirectories.

        Given: a temporary addon root with posts/ and machines/ subdirectories
        When: addAddonAssetPath() is called with the root
        Then: the posts dir appears in searchPathsPost() and the machines dir
              is registered in MachineFactory._addon_machine_dirs
        """
        import tempfile
        import os
        import pathlib
        from Machine.models.machine import MachineFactory

        with tempfile.TemporaryDirectory() as addon_root:
            posts_dir = os.path.join(addon_root, "posts")
            machines_dir = os.path.join(addon_root, "machines")
            os.makedirs(posts_dir)
            os.makedirs(machines_dir)

            Path.Preferences.addAddonAssetPath(addon_root)

            self.assertIn(posts_dir, Path.Preferences.searchPathsPost())
            registered_paths = [d for _, d in MachineFactory._addon_machine_dirs]
            self.assertIn(pathlib.Path(machines_dir), registered_paths)

            # Cleanup
            Path.Preferences._extra_post_paths.remove(posts_dir)
            mp = pathlib.Path(machines_dir)
            MachineFactory._addon_machine_dirs[:] = [
                (ns, d) for ns, d in MachineFactory._addon_machine_dirs if d != mp
            ]

    def test10(self):
        """Default paths for tools are resolved correctly"""

        self.assertEqual(
            Path.Preferences.getDefaultAssetPath().parts[-1],
            "CamAssets",
            str(Path.Preferences.getDefaultAssetPath()),
        )
        self.assertEqual(
            Path.Preferences.getBuiltinAssetPath().parts[-2:],
            ("CAM", "Tools"),
            str(Path.Preferences.getBuiltinAssetPath()),
        )
        self.assertEqual(
            Path.Preferences.getBuiltinShapePath().parts[-3:],
            ("CAM", "Tools", "Shape"),
            str(Path.Preferences.getBuiltinShapePath()),
        )
        self.assertEqual(Path.Preferences.getToolBitPath().name, "Bit")


def _isEmptyGroup(group):
    return not group.GetGroups() and not group.GetContents()


class TestPreferenceGroupRename(unittest.TestCase):
    """The start-up code of the workbench (Init.py) renames the preference group of the
    former Path workbench to "CAM". It must not leave an empty "Path" group behind."""

    def setUp(self):
        self.prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod")
        self.hadPath = self.prefs.HasGroup("Path")
        if self.hadPath and not _isEmptyGroup(self.prefs.GetGroup("Path")):
            self.skipTest("the user preferences hold settings in the old 'Path' group")
        self.prefs.RemGroup("Path")
        # The settings were renamed already, which is the usual case at start-up.
        self.createdCam = not self.prefs.HasGroup("CAM")
        self.prefs.GetGroup("CAM")
        self.unitTests = list(FreeCAD.__unit_test__)

    def tearDown(self):
        FreeCAD.__unit_test__[:] = self.unitTests
        if self.prefs.HasGroup("Path"):
            self.prefs.GetGroup("Path")  # RemGroup needs the group handle
            self.prefs.RemGroup("Path")
        if self.hadPath:
            self.prefs.GetGroup("Path")  # restore the empty group found at setUp
        if self.createdCam:
            self.prefs.RemGroup("CAM")

    def runStartupCode(self):
        camDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        initPy = os.path.join(camDir, "Init.py")
        with open(initPy, encoding="utf-8") as f:
            code = compile(f.read(), initPy, "exec")
        exec(code, {"App": FreeCAD, "FreeCAD": FreeCAD})

    def test_no_path_group_created(self):
        """Starting the workbench does not create a 'Path' preference group."""
        self.runStartupCode()
        self.assertFalse(self.prefs.HasGroup("Path"))

    def test_empty_path_group_removed(self):
        """An empty 'Path' group left behind by earlier versions is removed."""
        self.prefs.GetGroup("Path")
        self.runStartupCode()
        self.assertFalse(self.prefs.HasGroup("Path"))

    def test_path_group_with_settings_kept(self):
        """A 'Path' group that still holds settings is left alone once 'CAM' exists."""
        self.prefs.GetGroup("Path").SetBool("TestPreferenceGroupRename", True)
        self.runStartupCode()
        self.assertTrue(self.prefs.HasGroup("Path"))
        self.assertTrue(self.prefs.GetGroup("Path").GetBool("TestPreferenceGroupRename", False))
