# Copyright 2017 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sys
import os
import time

import sgtk
import shutil

from mock import patch
from tank_test.tank_test_base import *

# import the test base class
test_python_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "python"))
sys.path.append(test_python_path)
from base_test import TestShotgunUtilsFramework


class TestDataRetriever(TestShotgunUtilsFramework):
    """
    Tests for the data handler low level io
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestDataRetriever, self).setUp()
        self.shotgun_data = self.framework.import_module("shotgun_data")

    @skip_if_pyside_missing
    @patch("sgtk.util.download_url")
    def test_thumbnail_cache(self, patched):
        """
        Test thumbnail caching
        """
        dummy_thumb_path = os.path.join(self.fixtures_root, "resources", "thumbnail.png")
        extension = "png"

        def _download_url(sg, url, location, use_url_extension=False):
            """Copy our dummy thumbnail where it should be cached"""
            if use_url_extension:
                # Make sure the disk location has the same extension as the url path.
                # This is needed for thumbnail existence checking
                location = "%s.%s" % (location, extension)
            shutil.copyfile(dummy_thumb_path, location)
            return location

        patched.side_effect = _download_url

        retriever = self.shotgun_data.ShotgunDataRetriever()
        # Stop all threads now to avoid some QThread: Destroyed while thread is still running
        # errors on exit.
        retriever.stop()
        # We run tasks which usually run on a background task manager directly
        # here for the ease of testing.
        result = retriever._task_download_thumbnail(
            None,
            "https:://foo/bar/blah.png",
            "Asset", 1, None, False
        )
        thumb_path = result["thumb_path"]
        self.assertIsNotNone(thumb_path)
        self.assertTrue(os.path.exists(thumb_path))
        result = retriever._task_check_thumbnail("https:://foo/bar/blah.png", False)
        self.assertEqual(result["thumb_path"], thumb_path)
        # Reset the access and modification time on the cached file to the epoch
        os.utime(thumb_path, (0,0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        # Checking the thumbnail should refresh its modification time to now
        now = time.time()
        result = retriever._task_check_thumbnail("https:://foo/bar/blah.png", False)
        # Temporary test to display values in case of failure of the test.
        if os.path.getmtime(thumb_path) < now:
            raise RuntimeError(
                "Modification time timestamp %s is smaller than %s" % (
                    os.path.getmtime(thumb_path),
                    now
                )
            )
        self.assertTrue(
            os.path.getmtime(thumb_path) >= now
        )
        # Cause download attempts to raise an error and try other methods updating
        # thumbnails and check that the modification time is updated.
        patched.side_effect = RuntimeError
        os.utime(thumb_path, (0,0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        self.assertEqual(
            retriever.download_thumbnail("https:://foo/bar/blah.png", self.framework),
            thumb_path
        )
        self.assertTrue(
            os.path.getmtime(thumb_path) >= now
        )
        os.utime(thumb_path, (0,0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        self.assertEqual(
            retriever._task_check_attachment({
                "this_file": {
                    "url": "https:://foo/bar/blah.png",
                    "name": os.path.basename(thumb_path)
                }
            })["file_path"],
            thumb_path
        )
        self.assertTrue(
            os.path.getmtime(thumb_path) >= now
        )
        # download_thumbnail_source seems to have a slightly different logic
        # for the file name, do a first faked download first and check updates.
        patched.side_effect = _download_url
        thumb_path = retriever.download_thumbnail_source("Asset", 1, self.framework)
        os.utime(thumb_path, (0,0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        patched.side_effect = RuntimeError
        self.assertEqual(
            retriever.download_thumbnail_source("Asset", 1, self.framework),
            thumb_path
        )
        self.assertTrue(
            os.path.getmtime(thumb_path) >= now
        )
