# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw.makeCanonicalPoint raises TypeError for wrong arguments.

It returned None with the argument error still set, so the call failed with
SystemError ("returned a result with an exception set").
"""

import unittest

import FreeCAD
import TechDraw


class DrawMakeCanonicalPointTest(unittest.TestCase):
    def testWrongArgumentsRaiseTypeError(self):
        for args in ((), (None,), (None, FreeCAD.Vector()), ([], FreeCAD.Vector(), True)):
            with self.subTest(args=args):
                with self.assertRaises(TypeError):
                    TechDraw.makeCanonicalPoint(*args)


if __name__ == "__main__":
    unittest.main()
