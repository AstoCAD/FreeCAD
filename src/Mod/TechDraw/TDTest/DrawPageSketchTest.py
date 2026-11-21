# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2026 AstoCAD <hello@astocad.com>                         *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# **************************************************************************/

import unittest

import FreeCAD

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawPageSketchTest(unittest.TestCase):
    def setUp(self):
        FreeCAD.newDocument("TDPageSketch")
        self.document = FreeCAD.ActiveDocument
        self.page = createPageWithSVGTemplate(self.document)
        self.sketch = self.document.addObject("Sketcher::SketchObject", "Sketch")

    def tearDown(self):
        FreeCAD.closeDocument("TDPageSketch")

    def testSketchCanBeAddedAndRemoved(self):
        self.page.addView(self.sketch)

        self.assertIn(self.sketch, self.page.Views)
        self.assertNotIn(self.sketch, self.page.getViews())

        self.page.removeView(self.sketch)
        self.assertNotIn(self.sketch, self.page.Views)
        self.assertIsNotNone(self.document.getObject("Sketch"))

    def testSketchCanBelongToViewPart(self):
        view = self.document.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        self.page.addView(self.sketch)

        view.Sketches = [self.sketch]

        self.assertIn(self.sketch, self.page.Views)
        self.assertIn(self.sketch, view.Sketches)

        view.Sketches = []
        self.assertIn(self.sketch, self.page.Views)
        self.assertNotIn(self.sketch, view.Sketches)


    def _pageWithAnnotation(self, python_page):
        class PageProxy:
            def __init__(self):
                self.executed = []
                self.changed = []
                self.wrapper_ids = []

            def execute(self, page):
                self.executed.append(page.Name)
                self.wrapper_ids.append(id(page))
                return False  # Run the native Page container implementation.

            def onChanged(self, page, prop):
                self.changed.append((page.Name, prop))
                self.wrapper_ids.append(id(page))

        kind = "TechDraw::DrawPagePython" if python_page else "TechDraw::DrawPage"
        page = self.document.addObject(kind, "ApiPage")
        proxy = PageProxy() if python_page else None
        if proxy is not None:
            page.Proxy = proxy
        # addView centers new annotations, so provide native dimensions without
        # relying on an SVG resource or a GUI renderer for these API checks.
        template = self.document.addObject("TechDraw::DrawTemplate", "ApiTemplate")
        template.Width = 200
        template.Height = 100
        template.Orientation = "Landscape"
        page.Template = template
        annotation = self.document.addObject("TechDraw::DrawViewAnnotation", "ApiAnnotation")
        annotation.Text = ["page-api"]
        annotation.TextSize = 3
        annotation.ScaleType = "Page"
        page.Views = [annotation]
        page.Scale = 2
        self.document.recompute()
        self.assertTrue(page.isValid())
        self.assertIn("Up-to-date", page.State)
        self.assertEqual(page.Template, template)
        self.assertEqual(page.Views, [annotation])
        self.assertIs(page.Views[0], annotation)
        self.assertEqual(annotation.Scale, 2)
        self.assertEqual(annotation.Text, ["page-api"])
        self.assertIs(self.document.getObject(page.Name), page)
        self.assertIs(next(obj for obj in self.document.Objects if obj.Name == page.Name), page)
        if proxy is not None:
            self.assertGreater(len(proxy.executed), 0)
            self.assertIn((page.Name, "Views"), proxy.changed)
            self.assertIn((page.Name, "Scale"), proxy.changed)
            self.assertIs(page.Proxy, proxy)
            self.assertTrue(all(value == id(page) for value in proxy.wrapper_ids))

            def marker(obj):
                return obj.Name, len(obj.Views)

            # FeaturePython binds Python functions to the cached wrapper.
            # Delete the bound method while the object is still alive.
            page.pageApiMarker = marker
            try:
                self.assertEqual(page.pageApiMarker(), (page.Name, 1))
                self.assertIs(page.pageApiMarker.__self__, page)
                self.assertIs(self.document.getObject(page.Name), page)
            finally:
                del page.pageApiMarker
            self.assertFalse(hasattr(page, "pageApiMarker"))
            page.addProperty("App::PropertyString", "ApiMarker", "Page API")
            page.ApiMarker = "owned-page-api"
            self.assertEqual(page.ApiMarker, "owned-page-api")
            self.assertIn((page.Name, "ApiMarker"), proxy.changed)
            calls = len(proxy.executed)
            page.touch()
            self.document.recompute()
            self.assertGreater(len(proxy.executed), calls)
            self.assertIn("Up-to-date", page.State)
            self.assertIs(page.Proxy, proxy)
            self.assertIs(self.document.getObject(page.Name), page)
        return page, annotation, proxy

    def _checkNativePageViewApi(self, page, annotation):
        missing = []
        for name in ("addView", "removeView", "getViews", "getAllViews",
                     "PageWidth", "PageHeight", "PageOrientation"):
            try:
                value = getattr(page, name)
            except AttributeError:
                missing.append(name)
            else:
                if name in ("addView", "removeView", "getViews", "getAllViews"):
                    self.assertTrue(callable(value), name)
        for name in missing:
            with self.subTest(native_attribute=name):
                self.fail("Page must expose native DrawPage attribute: " + name)
        if missing:
            return

        self.assertEqual(page.PageWidth, 200)
        self.assertEqual(page.PageHeight, 100)
        self.assertEqual(page.PageOrientation, "Landscape")
        self.assertEqual([item.Name for item in page.getViews()], [annotation.Name])
        self.assertEqual([item.Name for item in page.getAllViews()], [annotation.Name])
        self.assertEqual(page.removeView(annotation), 0)
        self.assertEqual(page.Views, [])
        self.assertEqual(page.getViews(), [])
        self.assertEqual(page.getAllViews(), [])
        self.assertIsNotNone(self.document.getObject(annotation.Name))
        self.assertEqual(page.addView(annotation), 1)
        self.assertEqual(page.Views, [annotation])
        self.assertEqual(annotation.X.Value, 100)
        self.assertEqual(annotation.Y.Value, 50)
        self.assertEqual(annotation.Scale, page.Scale)
        self.assertEqual([item.Name for item in page.getViews()], [annotation.Name])
        self.assertEqual([item.Name for item in page.getAllViews()], [annotation.Name])
        self.assertEqual(page.removeView(annotation), 0)
        self.assertEqual(page.Views, [])
        self.assertEqual(page.getViews(), [])
        self.assertEqual(page.getAllViews(), [])
        self.assertEqual(annotation.Text, ["page-api"])
        self.assertIs(self.document.getObject(page.Name), page)

    def testPlainPageRetainsNativeViewApi(self):
        page, annotation, _proxy = self._pageWithAnnotation(False)
        self._checkNativePageViewApi(page, annotation)

    def testPythonPageProxyRetainsNativeScaleAndIdentity(self):
        page, annotation, proxy = self._pageWithAnnotation(True)
        self.assertEqual(page.Views, [annotation])
        self.assertIs(page.Proxy, proxy)

    def testPythonPageRetainsNativeViewApi(self):
        page, annotation, proxy = self._pageWithAnnotation(True)
        self._checkNativePageViewApi(page, annotation)
        self.assertIs(page.Proxy, proxy)


if __name__ == "__main__":
    unittest.main()
