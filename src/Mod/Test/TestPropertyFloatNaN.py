# SPDX-License-Identifier: LGPL-2.1-or-later
"""Float and quantity properties reject NaN from Python and expressions, but still load it."""

import io
import math
import re
import unittest
import zipfile
from uuid import uuid4

import FreeCAD as App


def restoreValueAsFromFile(obj, prop, value):
    """Set a float or quantity property the way a saved document does.

    A document may hold a NaN written before NaN was rejected. Restoring must
    still load it, and features must still fail cleanly on it, so tests of those
    features use this instead of an assignment.
    """
    data = obj.dumpPropertyContent(prop, Compression=0)
    source = zipfile.ZipFile(io.BytesIO(bytes(data)))
    xml = source.read("Persistence.xml").decode()
    xml, count = re.subn(r'value="[^"]*"', 'value="%r"' % float(value), xml, count=1)
    if count != 1:
        raise ValueError("No value attribute in the XML of " + prop)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for name in source.namelist():
            target.writestr(name, xml if name == "Persistence.xml" else source.read(name))
    obj.restorePropertyContent(prop, buffer.getvalue())


class TestPropertyFloatNaN(unittest.TestCase):
    TYPES = (
        "App::PropertyFloat",
        "App::PropertyFloatConstraint",
        "App::PropertyPrecision",
        "App::PropertyQuantity",
        "App::PropertyQuantityConstraint",
        "App::PropertyDistance",
        "App::PropertyLength",
        "App::PropertyAngle",
    )

    def setUp(self):
        self.doc = App.newDocument("FloatNaN_" + uuid4().hex[:10])
        self.obj = self.doc.addObject("App::FeaturePython", "Obj")
        for index, typeName in enumerate(self.TYPES):
            self.obj.addProperty(typeName, "P%d" % index, "Values")
            setattr(self.obj, "P%d" % index, 2.5)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _value(self, prop):
        value = getattr(self.obj, prop)
        return getattr(value, "Value", value)

    def testAssigningNaNRaisesAndKeepsTheValue(self):
        nan = float("nan")
        for index, typeName in enumerate(self.TYPES):
            prop = "P%d" % index
            values = [nan, -nan]
            if "Quantity" in typeName or index >= 5:
                values.append(App.Units.Quantity(nan, App.Units.Unit()))
            for value in values:
                with self.subTest(type=typeName, value=value):
                    with self.assertRaises(ValueError):
                        setattr(self.obj, prop, value)
                    self.assertEqual(self._value(prop), 2.5)

    def testNaNInAConstraintTupleRaises(self):
        nan = float("nan")
        for value in ((nan, 0.0, 10.0, 1.0), (1.0, nan, 10.0, 1.0), (1.0, 0.0, nan, 1.0),
                      (1.0, 0.0, 10.0, nan)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.obj.P1 = value
                self.assertEqual(self.obj.P1, 2.5)

    def testFiniteAndInfiniteValuesUnchanged(self):
        self.obj.P0 = float("inf")
        self.assertEqual(self.obj.P0, float("inf"))
        self.obj.P0 = -3
        self.assertEqual(self.obj.P0, -3.0)
        self.obj.P5 = "4 mm"
        self.assertEqual(self.obj.P5.Value, 4.0)
        # the constraint of a length still clamps
        self.obj.P6 = -1
        self.assertEqual(self.obj.P6.Value, 0.0)

    def testExpressionGivingNaNFailsTheRecompute(self):
        for prop in ("P0", "P3", "P6"):
            with self.subTest(prop=prop):
                self.obj.setExpression(prop, "sqrt(-1)")
                self.doc.recompute()
                self.assertIn("Invalid", self.obj.State)
                self.assertEqual(self._value(prop), 2.5)
                self.obj.setExpression(prop, None)
                self.doc.recompute()

    def testNaNFromAFileStillLoads(self):
        for index, typeName in enumerate(self.TYPES):
            prop = "P%d" % index
            with self.subTest(type=typeName):
                restoreValueAsFromFile(self.obj, prop, float("nan"))
                self.assertTrue(math.isnan(self._value(prop)))

    def testNaNSurvivesSaveAndReload(self):
        restoreValueAsFromFile(self.obj, "P0", float("nan"))
        path = App.getTempPath() + self.doc.Name + ".FCStd"
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.obj = self.doc.getObject("Obj")
        self.assertTrue(math.isnan(self.obj.P0))
        self.assertEqual(self.obj.P1, 2.5)


if __name__ == "__main__":
    unittest.main()
