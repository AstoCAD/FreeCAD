# SPDX-License-Identifier: LGPL-2.1-or-later
"""Float, quantity, vector, placement, rotation and matrix properties reject NaN from Python
and expressions, but still load it."""

import io
import math
import re
import unittest
import zipfile
from uuid import uuid4

import FreeCAD as App


def _rotationAttributes(rotation):
    axis = rotation.RawAxis
    return {"A": rotation.Angle, "Ox": axis.x, "Oy": axis.y, "Oz": axis.z}


def _xmlAttributes(value):
    """The XML attributes a property of the type of value saves it in."""
    if isinstance(value, App.Vector):
        return {"valueX": value.x, "valueY": value.y, "valueZ": value.z}
    if isinstance(value, App.Rotation):
        return _rotationAttributes(value)
    if isinstance(value, App.Placement):
        attributes = {"Px": value.Base.x, "Py": value.Base.y, "Pz": value.Base.z}
        attributes.update(("Q%d" % index, q) for index, q in enumerate(value.Rotation.Q))
        attributes.update(_rotationAttributes(value.Rotation))
        return attributes
    if isinstance(value, App.Matrix):
        return {
            "a%d%d" % (row, col): getattr(value, "A%d%d" % (row, col))
            for row in range(1, 5)
            for col in range(1, 5)
        }
    return {"value": value}


def restoreValueAsFromFile(obj, prop, value):
    """Set a float, quantity, vector, placement or matrix property the way a saved document does.

    A document may hold a NaN written before NaN was rejected. Restoring must
    still load it, and features must still fail cleanly on it, so tests of those
    features use this instead of an assignment.
    """
    data = obj.dumpPropertyContent(prop, Compression=0)
    source = zipfile.ZipFile(io.BytesIO(bytes(data)))
    xml = source.read("Persistence.xml").decode()
    for name, number in _xmlAttributes(value).items():
        xml, count = re.subn(
            r'\b%s="[^"]*"' % name, '%s="%r"' % (name, float(number)), xml, count=1
        )
        if count != 1:
            raise ValueError("No %s attribute in the XML of %s" % (name, prop))
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


def _hasNaN(value):
    if isinstance(value, (list, tuple)):
        return any(_hasNaN(item) for item in value)
    if isinstance(value, App.Vector):
        return any(math.isnan(number) for number in value)
    if isinstance(value, App.Rotation):
        return _hasNaN(list(value.Q)) or math.isnan(value.Angle) or _hasNaN(value.RawAxis)
    if isinstance(value, App.Placement):
        return _hasNaN(value.Base) or _hasNaN(value.Rotation)
    if isinstance(value, App.Matrix):
        return any(math.isnan(number) for number in value.A)
    return math.isnan(value)


class TestPropertyVectorNaN(unittest.TestCase):
    """The same for the vector, placement, rotation and matrix properties."""

    VECTOR_TYPES = (
        "App::PropertyVector",
        "App::PropertyVectorDistance",
        "App::PropertyPosition",
        "App::PropertyDirection",
    )

    def setUp(self):
        self.doc = App.newDocument("VectorNaN_" + uuid4().hex[:10])
        self.obj = self.doc.addObject("App::FeaturePython", "Obj")
        for index, typeName in enumerate(self.VECTOR_TYPES):
            self.obj.addProperty(typeName, "V%d" % index, "Values")
            setattr(self.obj, "V%d" % index, App.Vector(1, 2, 3))
        self.obj.addProperty("App::PropertyVectorList", "Points", "Values")
        self.obj.Points = [App.Vector(1, 2, 3), App.Vector(4, 5, 6)]
        self.obj.addProperty("App::PropertyPlacement", "Plm", "Values")
        self.obj.Plm = self.placement()
        self.obj.addProperty("App::PropertyPlacementList", "Plms", "Values")
        self.obj.Plms = [self.placement(), App.Placement()]
        self.obj.addProperty("App::PropertyRotation", "Rot", "Values")
        self.obj.Rot = App.Rotation(App.Vector(0, 0, 1), 30)
        self.obj.addProperty("App::PropertyMatrix", "Mat", "Values")
        self.obj.Mat = self.matrix()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    @staticmethod
    def placement():
        return App.Placement(App.Vector(1, 2, 3), App.Rotation(App.Vector(0, 0, 1), 30))

    @staticmethod
    def matrix():
        matrix = App.Matrix()
        matrix.move(App.Vector(1, 2, 3))
        return matrix

    def assertUnchanged(self):
        for index in range(len(self.VECTOR_TYPES)):
            self.assertEqual(getattr(self.obj, "V%d" % index), App.Vector(1, 2, 3))
        self.assertEqual(self.obj.Points, [App.Vector(1, 2, 3), App.Vector(4, 5, 6)])
        self.assertTrue(self.obj.Plm.isSame(self.placement(), 1e-12))
        self.assertEqual(len(self.obj.Plms), 2)
        self.assertTrue(self.obj.Plms[0].isSame(self.placement(), 1e-12))
        self.assertTrue(self.obj.Plms[1].isSame(App.Placement(), 1e-12))
        self.assertTrue(self.obj.Rot.isSame(App.Rotation(App.Vector(0, 0, 1), 30), 1e-12))
        self.assertEqual(self.obj.Mat, self.matrix())

    def assertRaisesAndUnchanged(self, prop, value):
        with self.subTest(prop=prop, value=value):
            with self.assertRaises(ValueError):
                setattr(self.obj, prop, value)
            self.assertUnchanged()

    def testAssigningNaNVectorRaisesAndKeepsTheValue(self):
        nan = float("nan")
        for index in range(len(self.VECTOR_TYPES)):
            for value in (App.Vector(nan, 0, 0), App.Vector(0, 0, -nan), (0.0, nan, 0.0)):
                self.assertRaisesAndUnchanged("V%d" % index, value)

    def testNaNInAVectorListRaisesAndKeepsTheList(self):
        nan = float("nan")
        for value in (
            [App.Vector(0, 0, 0), App.Vector(nan, 0, 0)],
            [(0.0, 0.0, nan)],
            {1: App.Vector(0, nan, 0)},  # set1Value
            {2: App.Vector(0, nan, 0)},  # append
        ):
            self.assertRaisesAndUnchanged("Points", value)

    def testAssigningNaNPlacementRaisesAndKeepsTheValue(self):
        nan = float("nan")
        values = (
            App.Placement(App.Vector(nan, 0, 0), App.Rotation()),
            App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), nan)),
            App.Placement(App.Vector(), App.Rotation(nan, 0, 0, 1)),
            App.Matrix(1, 0, 0, nan, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        )
        for value in values:
            self.assertRaisesAndUnchanged("Plm", value)
            self.assertRaisesAndUnchanged("Plms", [App.Placement(), value])
            self.assertRaisesAndUnchanged("Plms", {0: value})

    def testAssigningNaNRotationRaisesAndKeepsTheValue(self):
        nan = float("nan")
        for value in (
            App.Rotation(App.Vector(0, 0, 1), nan),
            App.Rotation(nan, 0, 0, 1),
            App.Matrix(nan, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        ):
            self.assertRaisesAndUnchanged("Rot", value)

    def testAssigningNaNMatrixRaisesAndKeepsTheValue(self):
        nan = float("nan")
        values = [App.Matrix(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, nan)]
        values.append(tuple([0.0] * 15 + [nan]))
        for value in values:
            self.assertRaisesAndUnchanged("Mat", value)

    def testSettingANaNComponentKeepsTheValue(self):
        # the component is set on a copy; the error of the assignment back is not raised
        nan = float("nan")
        self.obj.V0.x = nan
        self.obj.Plm.Base.y = nan
        self.obj.Plm.Rotation.Angle = nan
        self.obj.Rot.Angle = nan
        self.obj.Mat.A14 = nan
        self.assertUnchanged()

    def testExpressionGivingNaNFailsTheRecompute(self):
        for path in (
            "V0.x",
            "V2.z",
            "Plm.Base.x",
            "Plm.Rotation.Angle",
            "Plm.Rotation.Axis.x",
            "Plm.Rotation.Yaw",
            "Plm.Rotation.Pitch",
            "Plm.Rotation.Roll",
            "Rot.Angle",
            "Rot.Axis.y",
            "Mat.A14",
        ):
            with self.subTest(path=path):
                self.obj.setExpression(path, "sqrt(-1)")
                self.doc.recompute()
                self.assertIn("Invalid", self.obj.State)
                self.assertUnchanged()
                self.obj.setExpression(path, None)
                self.doc.recompute()

    def testExpressionGivingANumberStillWorks(self):
        self.obj.setExpression("Plm.Base.x", "7")
        self.obj.setExpression("V0.y", "8")
        self.doc.recompute()
        self.assertNotIn("Invalid", self.obj.State)
        self.assertEqual(self.obj.Plm.Base.x, 7)
        self.assertEqual(self.obj.V0.y, 8)

    def testFiniteAndInfiniteValuesUnchanged(self):
        inf = float("inf")
        self.obj.V0 = App.Vector(inf, 0, 0)
        self.assertEqual(self.obj.V0.x, inf)
        self.obj.V1 = (4, 5.5, 6)
        self.assertEqual(self.obj.V1, App.Vector(4, 5.5, 6))
        self.obj.Points = {2: App.Vector(7, 8, 9)}
        self.assertEqual(self.obj.Points[2], App.Vector(7, 8, 9))
        self.obj.Plm = App.Placement(App.Vector(inf, 0, 0), App.Rotation())
        self.assertEqual(self.obj.Plm.Base.x, inf)
        self.obj.Plm = self.matrix()
        self.assertEqual(self.obj.Plm.Base, App.Vector(1, 2, 3))
        self.obj.Mat = tuple(range(16))
        self.assertEqual(self.obj.Mat.A21, 1)  # the tuple is read column by column

    def testNaNFromAFileStillLoads(self):
        nan = float("nan")
        values = {"V%d" % index: App.Vector(nan, 2, 3) for index in range(len(self.VECTOR_TYPES))}
        values["Plm"] = App.Placement(App.Vector(1, nan, 3), App.Rotation())
        values["Rot"] = App.Rotation(App.Vector(0, 0, 1), nan)
        matrix = self.matrix()
        matrix.A24 = nan
        values["Mat"] = matrix
        for prop, value in values.items():
            with self.subTest(prop=prop):
                restoreValueAsFromFile(self.obj, prop, value)
                self.assertTrue(_hasNaN(getattr(self.obj, prop)))


if __name__ == "__main__":
    unittest.main()
