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

class ShotgunUtilsFramework(sgtk.platform.Framework):
    
    # A list of file names which should never be deleted when cleaning up old
    # cached data.
    _ALWAYS_KEEP_CACHED_FILES = [
        "sg_schema.pickle",
        "sg_status.pickle",
    ]
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

    def _remove_old_cached_data(self, grace_period=7):
        """
        Remove old data files cached by this bundle.

        A file is considered old if it was not modified in the last number of days
        specified by the `grace_period` value, which must be at least 1 (one day).

        It is the responsability of the implementation to ensure that modification
        times for the files which should be kept are recent.
        Typically, when re-using a cached file, the bundle should use
        `os.utime(cached_file_path, None)` to update the modification time to the
        current time.

        If some files should never be deleted, their name should be added to the
        `_ALWAYS_KEEP_CACHED_FILES` class member.

        :param int grace_period: The number of days files without any modification
                                 should be kept around before being deleted.
        :raises: ValueError if the grace_period is smaller than 1.
        """
        if grace_period < 1:
            raise ValueError(
                "Invalid grace period value %d, it must be a least 1" % grace_period
            )
        self.logger.debug("Starting old data cleanup...")
        now = datetime.datetime.now()
        grace_period_delta = datetime.timedelta(days=grace_period)
        # Clean up the site cache and the project cache locations.
        for cache_location in [self.site_cache_location, self.cache_location]:
            # Go bottom up in the hierarchy and delete old files
            for folder, dirs, files in os.walk(cache_location, topdown=False):
                for name in files:
                    # Check if we should stop and bail out immediately if so.
                    if self._stop_cleanup:
                        return
                    if name in self._ALWAYS_KEEP_CACHED_FILES:
                        continue
                    file_path = os.path.join(folder, name)
                    try:
                        file_stats = os.stat(file_path)
                        # Convert the timestamp to a datetime
                        last_modif_time = datetime.datetime.fromtimestamp(
                            int(file_stats.st_mtime)
                        )
                        # Is it old enough to be removed?
                        if now - last_modif_time > grace_period_delta:
                            filesystem.safe_delete_file(file_path)
                    except Exception as e:
                        # Log the error for debug purpose
                        self.logger.debug(
                            "Warning: couldn't check %s for removal: %s" % (
                                file_path, e
                            ),
                            exc_info=True,
                        )
                        # And ignore it
                        pass

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
