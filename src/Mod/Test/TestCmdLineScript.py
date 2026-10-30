# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

"""Tests of running a Python script given on the FreeCADCmd command line.

FreeCAD/FreeCAD#31734: the script was imported as a module, so code under
'if __name__ == "__main__":' never ran, and a script raising an exception was
executed a second time.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import FreeCAD as App


SCRIPT = """\
import os
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "runs.txt"), "a") as f:
    f.write(__name__ + "\\n")
if __name__ == "__main__":
    with open(os.path.join(here, "main.txt"), "w") as f:
        f.write("ok")
if os.path.exists(os.path.join(here, "raise.flag")):
    raise RuntimeError("script error")
"""


def _freecadcmd():
    bindir = os.path.join(App.getHomePath(), "bin")
    for name in ("FreeCADCmd.exe", "FreeCADCmd", "freecadcmd"):
        path = os.path.join(bindir, name)
        if os.path.isfile(path):
            return path
    return None


class TestCmdLineScript(unittest.TestCase):
    def setUp(self):
        self.exe = _freecadcmd()
        if not self.exe:
            self.skipTest("FreeCADCmd executable not found")
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.script = os.path.join(self.tmpdir, "fc_cmdline_script.py")
        with open(self.script, "w") as f:
            f.write(SCRIPT)

    def _run(self):
        cmd = [self.exe, "--user-cfg", os.path.join(self.tmpdir, "user.cfg"), self.script]
        subprocess.run(cmd, cwd=self.tmpdir, capture_output=True, timeout=300)
        runs_file = os.path.join(self.tmpdir, "runs.txt")
        if not os.path.exists(runs_file):
            return []
        with open(runs_file) as f:
            return f.read().split()

    def testScriptRunsAsMain(self):
        """The script runs once, as __main__, like with the Python executable."""
        self.assertEqual(self._run(), ["__main__"])
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "main.txt")))

    def testFailingScriptRunsOnce(self):
        """A script raising an exception is not executed a second time."""
        open(os.path.join(self.tmpdir, "raise.flag"), "w").close()
        self.assertEqual(self._run(), ["__main__"])
