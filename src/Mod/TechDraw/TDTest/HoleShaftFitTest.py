# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Hole/Shaft Fit tool gives the ISO 286 limits of the n shaft field.

The n deviation table had a single row for 120-180 mm and for 180-250 mm while
the nominal ranges are split in three there, so every value from 160 mm on was
read one or two rows too far (n6 at 170 mm gave +60/+35 instead of +52/+27) and
an H7/n6 fit above 400 mm raised IndexError.
"""

import importlib.util
import os
import unittest


def loadIso286():
    # TechDrawTools/__init__ registers Gui commands, so load the module file on its own
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "TechDrawTools",
        "TaskHoleShaftFit.py",
    )
    spec = importlib.util.spec_from_file_location("TDTestTaskHoleShaftFit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ISO286


class HoleShaftFitTest(unittest.TestCase):
    def setUp(self):
        self.iso = loadIso286()()

    def limits(self, value, field):
        self.iso.calculate(value, field[0], int(field[1:]))
        return (self.iso.upperValue, self.iso.lowerValue)

    def testN6Limits(self):
        # ISO 286-2 n6 limits in micrometres, one value per nominal range
        expected = [
            (2, (10, 4)),
            (5, (16, 8)),
            (8, (19, 10)),
            (12, (23, 12)),
            (16, (23, 12)),
            (20, (28, 15)),
            (26, (28, 15)),
            (35, (33, 17)),
            (45, (33, 17)),
            (55, (39, 20)),
            (70, (39, 20)),
            (90, (45, 23)),
            (110, (45, 23)),
            (130, (52, 27)),
            (150, (52, 27)),
            (170, (52, 27)),
            (190, (60, 31)),
            (210, (60, 31)),
            (240, (60, 31)),
            (260, (66, 34)),
            (300, (66, 34)),
            (330, (73, 37)),
            (380, (73, 37)),
            (420, (80, 40)),
            (480, (80, 40)),
        ]
        for value, limits in expected:
            with self.subTest(value=value):
                self.assertEqual(self.limits(value, "n6"), limits)

    def testOtherFieldsAt170(self):
        # controls: neighbouring fields of the same range were already right
        self.assertEqual(self.limits(170, "k6"), (28, 3))
        self.assertEqual(self.limits(170, "r6"), (93, 68))
        self.assertEqual(self.limits(170, "s6"), (133, 108))
        self.assertEqual(self.limits(170, "N7"), (-12, -52))
        self.assertEqual(self.limits(170, "H7"), (40, 0))


if __name__ == "__main__":
    unittest.main()
