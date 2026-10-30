# SPDX-License-Identifier: LGPL-2.1-or-later
"""Project Utility extracts archives whose entries share a sub-directory."""

import os
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch

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

    def _make_project_dir(self):
        srcdir = os.path.join(self.tmpdir, "src")
        os.mkdir(srcdir)
        with open(os.path.join(srcdir, "Document.xml"), "w") as stream:
            stream.write('<Document><Property file="Box.Shape.brp"/></Document>')
        with open(os.path.join(srcdir, "Box.Shape.brp"), "w") as stream:
            stream.write("shape")
        return os.path.join(srcdir, "Document.xml")

    def test_create_and_extract_round_trip(self):
        target = os.path.join(self.tmpdir, "Repacked.FCStd")
        project_utility.createDocument(self._make_project_dir(), target)
        with zipfile.ZipFile(target) as zfile:
            self.assertEqual(sorted(zfile.namelist()), ["Box.Shape.brp", "Document.xml"])
        project_utility.extractDocument(target, self.outdir)
        self.assertEqual(self._read("Box.Shape.brp"), b"shape")

    def test_failed_create_releases_output_file(self):
        # A failed repack must not keep the archive open (it could not be deleted on Windows)
        target = os.path.join(self.tmpdir, "Failed.FCStd")
        error = None
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("write failed")):
            try:
                project_utility.createDocument(self._make_project_dir(), target)
            except OSError as exc:
                error = exc  # keeps the traceback alive, like the Python console does
        self.assertIsNotNone(error)
        os.remove(target)
        self.assertFalse(os.path.exists(target))

    def test_failed_extract_releases_source_file(self):
        # Make the extraction fail by blocking a directory with a plain file
        with open(os.path.join(self.outdir, "sub"), "w") as stream:
            stream.write("not a directory")
        error = None
        try:
            project_utility.extractDocument(self.archive, self.outdir)
        except OSError as exc:
            error = exc  # keeps the traceback alive, like the Python console does
        self.assertIsNotNone(error)
        os.remove(self.archive)
        self.assertFalse(os.path.exists(self.archive))
