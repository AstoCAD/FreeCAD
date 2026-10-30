# SPDX-License-Identifier: LGPL-2.1-or-later
"""Project Utility extracts archives whose entries share a sub-directory."""

import os
import shutil
import tempfile
import unittest
import zipfile

from freecad import project_utility


class TestProjectUtility(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fc_project_utility_")
        self.archive = os.path.join(self.tmpdir, "Sample.FCStd")
        with zipfile.ZipFile(self.archive, "w") as zfile:
            zfile.writestr("Document.xml", "<Document/>")
            zfile.writestr("sub/first.brp", "first")
            zfile.writestr("sub/second.brp", "second")
            zfile.writestr("thumbnails/Thumbnail.png", "png")
        self.outdir = os.path.join(self.tmpdir, "out")
        os.mkdir(self.outdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read(self, *parts):
        with open(os.path.join(self.outdir, *parts), "rb") as stream:
            return stream.read()

    def test_extract_entries_sharing_a_directory(self):
        project_utility.extractDocument(self.archive, self.outdir)
        self.assertEqual(self._read("sub", "first.brp"), b"first")
        self.assertEqual(self._read("sub", "second.brp"), b"second")

    def test_extract_into_folder_with_existing_directory(self):
        # e.g. a second project extracted into the same folder (both have thumbnails/)
        os.mkdir(os.path.join(self.outdir, "thumbnails"))
        project_utility.extractDocument(self.archive, self.outdir)
        self.assertEqual(self._read("thumbnails", "Thumbnail.png"), b"png")
        self.assertEqual(self._read("Document.xml"), b"<Document/>")
