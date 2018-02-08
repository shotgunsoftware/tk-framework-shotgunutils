# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from sgtk.util import filesystem

import threading
import datetime
import os
import time

class ShotgunUtilsFramework(sgtk.platform.Framework):
    
    # List of top folders in the cache which should be considered for old
    # data clean up.
    _CLEANUP_FOLDERS = [
        "sg",
        "sg_nav",
        "thumbs",
        "multi_context"
    ]
    # Number of days a file without modification should be kept around
    # before being considered for clean up.
    _CLEANUP_GRACE_PERIOD = 60

    ##########################################################################################
    # init and destroy
            
    def init_framework(self):
        """
        Init this framework.

        Post an old cached data cleanup in the background
        """
        self.log_debug("%s: Initializing..." % self)
        self._stop_cleanup = False
        self._bg_cleanup_thread = None
        self._post_old_data_cleanup()
    
    def destroy_framework(self):
        """
        Destroy this framework.

        If an old cached data cleanup was posted in the background, stop it
        immediately.
        """
        self.log_debug("%s: Destroying..." % self)
        # Please note that we are modifying a member which is read in another
        # thread which should be fine in Python with the GIL protecting its access.
        self._stop_cleanup = True
        if self._bg_cleanup_thread:
            if self._bg_cleanup_thread.isAlive():
                # If the clean up is not completed yet, log why we are waiting.
                self.log_info("Waiting for old data clean up to complete...")
            self._bg_cleanup_thread.join()
    
    def _post_old_data_cleanup(self):
        """
        Post a cleanup of old cached data in the background.
        """
        try:
            self.log_debug(
                "Posting old cached data clean up..."
            )
            self._stop_cleanup = False
            # Qt might not be yet available at this stage (e.g. in tk-desktop),
            # so we can't use a background task manager or a QThread, use instead
            # regular Python Thread to post the clean up in the background.
            self._bg_cleanup_thread = threading.Thread(
                target=self._remove_old_cached_data,
                name="%s Clean Up" % self.name
            )
            self._bg_cleanup_thread.start()
        except Exception as e:
            self.log_warning("Unable to post data clean up: %s" % e)

    def _remove_old_cached_data(self):
        """
        Remove old data files cached by this bundle.

        A file is considered old if it was not modified in the last number of days
        specified by the `_CLEANUP_GRACE_PERIOD` class member value, which must
        be at least 1 (one day).

        It is the responsability of the implementation to ensure that modification
        times for the files which should be kept are recent.
        Typically, when re-using a cached file, the framework should use
        `os.utime(cached_file_path, None)` to update the modification time to the
        current time.

        The list of top folders to consider for clean up is explicitly defined in
        the `_CLEANUP_FOLDERS` class member list, anything outside of those will
        never be removed by the clean up.

        :raises: ValueError if the grace period is smaller than 1.
        """
        grace_period = self._CLEANUP_GRACE_PERIOD
        if grace_period < 1:
            raise ValueError(
                "Invalid grace period value %d, it must be a least 1" % grace_period
            )
        now_timestamp = time.time()
        now = datetime.datetime.now()
        delta = datetime.timedelta(days=grace_period)
        # Datetime total_seconds was introduced in Python 2.7, so compute the
        # value ourself.
        grace_in_seconds = (
            delta.microseconds + (delta.seconds + delta.days * 24 * 3600) * 10**6
        ) / 10**6

        # Clean up the site cache and the project cache locations, only consider
        # folders specified in _CLEANUP_FOLDERS
        cache_locations = [
            os.path.join(self.site_cache_location, folder) for folder in self._CLEANUP_FOLDERS
        ]
        cache_locations.extend([
            os.path.join(self.cache_location, folder) for folder in self._CLEANUP_FOLDERS
        ])
        self.logger.debug(
            "Cleaning all files with a modification date older than %s under locations "
            "%s" % ((now - delta), ", ".join(cache_locations))
        )
        # Check if we should stop and bail out immediately if so.
        if self._stop_cleanup:
            return
        for cache_location in cache_locations:
            # Go bottom up in the hierarchy and delete old files
            for folder, dirs, files in os.walk(cache_location, topdown=False):
                for name in files:
                    # Check if we should stop and bail out immediately if so.
                    if self._stop_cleanup:
                        return
                    file_path = os.path.join(folder, name)
                    try:
                        file_stats = os.stat(file_path)
                        # Is it old enough to be removed?
                        if now_timestamp - file_stats.st_mtime > grace_in_seconds:
                            filesystem.safe_delete_file(file_path)
                    except Exception as e:
                        # Log the error for debug purpose
                        self.logger.debug(
                            "Warning: couldn't check %s for removal: %s" % (
                                file_path, e
                            ),
                            exc_info=True,
                        )

                for name in dirs:
                    # Check if we should stop and bail out immediately if so.
                    if self._stop_cleanup:
                        return
                    # Try to remove empty directories
                    dir_path = os.path.join(folder, name)
                    try:
                        if not os.listdir(dir_path):
                            filesystem.safe_delete_folder(dir_path)
                    except Exception as e:
                        # Log the error for debug purpose
                        self.logger.debug(
                            "Warning: couldn't check %s for removal: %s" % (
                                dir_path, e
                            ),
                            exc_info=True,
                        )
                        # And ignore it
                        pass
        self.logger.debug(
            "Old data cleanup completed in %s" % (datetime.datetime.now() - now)
        )
