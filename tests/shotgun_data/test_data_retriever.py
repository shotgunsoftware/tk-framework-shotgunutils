# Copyright 2017 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#

import sys
import os
import time
import shutil

from mock import patch
from tank_test.tank_test_base import setUpModule  # noqa

# import the test base class
test_python_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "python")
)
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

    @patch("sgtk.util.download_url")
    def test_thumbnail_cache(self, patched):
        """
        Test thumbnail caching
        """
        dummy_thumb_path = os.path.join(
            self.fixtures_root, "resources", "thumbnail.png"
        )
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

        # Stop all threads now to avoid some QThread: Destroyed while thread
        # is still running errors on exit.
        #
        # As documented inside the ResultsDispatcher thread, the manager
        # does not actually wait for the thread to avoid a deadlock. In a real
        # software it doesn't matter because there's always a QApplication,
        # but here it will sometime get destroyed before a thread may end,
        # which will cause a crash. So we'll wait for the thread to finish
        # before going on with the test.
        task_manager = retriever._task_manager
        retriever.stop()
        for i in range(5):
            if task_manager._results_dispatcher.isRunning() is False:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Thread did not finalize in time.")

        # We run tasks which usually run on a background task manager directly
        # here for the ease of testing.
        result = retriever._task_download_thumbnail(
            None, "https:://foo/bar/blah.png", "Asset", 1, None, False
        )
        thumb_path = result["thumb_path"]
        self.assertIsNotNone(thumb_path)
        self.assertTrue(os.path.exists(thumb_path))
        result = retriever._task_check_thumbnail("https:://foo/bar/blah.png", False)
        self.assertEqual(result["thumb_path"], thumb_path)
        # Reset the access and modification time on the cached file to the epoch
        os.utime(thumb_path, (0, 0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        # Checking the thumbnail should refresh its modification time to now
        # Convert to int to avoid precision problems with floats
        now = int(time.time())
        result = retriever._task_check_thumbnail("https:://foo/bar/blah.png", False)
        self.assertGreaterEqual(os.path.getmtime(thumb_path), now)
        # Cause download attempts to raise an error and try other methods updating
        # thumbnails and check that the modification time is updated.
        patched.side_effect = RuntimeError
        os.utime(thumb_path, (0, 0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        self.assertEqual(
            retriever.download_thumbnail("https:://foo/bar/blah.png", self.framework),
            thumb_path,
        )
        self.assertGreaterEqual(os.path.getmtime(thumb_path), now)
        os.utime(thumb_path, (0, 0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        self.assertEqual(
            retriever._task_check_attachment(
                {
                    "this_file": {
                        "url": "https:://foo/bar/blah.png",
                        "name": os.path.basename(thumb_path),
                    }
                }
            )["file_path"],
            thumb_path,
        )
        self.assertGreaterEqual(os.path.getmtime(thumb_path), now)
        # download_thumbnail_source seems to have a slightly different logic
        # for the file name, do a faked download first and check updates.
        patched.side_effect = _download_url
        thumb_path = retriever.download_thumbnail_source("Asset", 1, self.framework)
        os.utime(thumb_path, (0, 0))
        self.assertEqual(int(os.path.getmtime(thumb_path)), 0)
        patched.side_effect = RuntimeError
        self.assertEqual(
            retriever.download_thumbnail_source("Asset", 1, self.framework), thumb_path
        )
        self.assertGreaterEqual(os.path.getmtime(thumb_path), now)

    def test_cleaning_cached_data(self):
        """
        Test cleaning up cached data.
        """
        bundle = self.framework
        # Create dummy cached data
        top_cleanup_folders = []
        for folder in bundle._CLEANUP_FOLDERS:
            top_cleanup_folders.append(os.path.join(bundle.site_cache_location, folder))
            os.mkdir(top_cleanup_folders[-1])
            top_cleanup_folders.append(os.path.join(bundle.cache_location, folder))
            os.mkdir(top_cleanup_folders[-1])

        dummy_files = []
        for folder in top_cleanup_folders:
            dummy_files.extend(
                [
                    os.path.join(folder, "foo.txt"),
                    os.path.join(folder, "blah.txt"),
                    os.path.join(folder, "test", "foo.txt"),
                    os.path.join(folder, "test", "blah.txt"),
                ]
            )
        os.mkdir(os.path.join(bundle.site_cache_location, "test"))
        preserved_files = [
            os.path.join(bundle.site_cache_location, "test", "foo.txt"),
            os.path.join(bundle.site_cache_location, "blah.txt"),
            os.path.join(bundle.cache_location, "test", "foo.txt"),
            os.path.join(bundle.cache_location, "blah.txt"),
        ]
        for dummy_file in dummy_files + preserved_files:
            self.create_file(dummy_file)
        # Test we can't use bad values
        with self.assertRaisesRegex(ValueError, "Invalid grace period value"):
            bundle._remove_old_cached_data(-1, *top_cleanup_folders)
        # One day grace period clean up shouldn't delete anything
        bundle._remove_old_cached_data(1, *top_cleanup_folders)
        for dummy_file in dummy_files:
            self.assertTrue(os.path.exists(dummy_file))
        # Change the modification time for a file and clean it up
        dummy_file = dummy_files.pop()

        # Go back a full day and a second to trigger deletion.
        offset = (24 * 3600) + 1

        day_before_timestamp = time.time() - offset
        os.utime(dummy_file, (day_before_timestamp, day_before_timestamp))
        bundle._remove_old_cached_data(1, *top_cleanup_folders)
        # It should be gone, but all the others kept
        self.assertFalse(os.path.exists(dummy_file))
        for dummy_file in dummy_files:
            self.assertTrue(os.path.exists(dummy_file))
        # Test that cleaning up all files work but keep the files we should never
        # delete.
        for dummy_file in dummy_files + preserved_files:
            os.utime(dummy_file, (day_before_timestamp, day_before_timestamp))
        bundle._remove_old_cached_data(1, *top_cleanup_folders)
        for dummy_file in dummy_files:
            self.assertFalse(os.path.exists(dummy_file))
        # Preserved files should be still here, whatever the modification time
        for dummy_file in preserved_files:
            self.assertTrue(os.path.exists(dummy_file))
