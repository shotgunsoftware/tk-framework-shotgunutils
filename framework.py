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
import threading
import datetime
import os

class ShotgunUtilsFramework(sgtk.platform.Framework):
    
    ##########################################################################################
    # init and destroy
            
    def init_framework(self):
        self.log_debug("%s: Initializing..." % self)
        self._bg_cleanup_thread = None
        self._post_old_data_cleanup()
    
    def destroy_framework(self):
        self.log_debug("%s: Destroying..." % self)
        if self._bg_cleanup_thread:
            if self._bg_cleanup_thread.isAlive():
                # If the clean up is not completed yet, log why we are waiting.
                self.log_info("Waiting for old data clean up to complete...")
            self._bg_cleanup_thread.join()
    
    def _post_old_data_cleanup(self):
        """
        If the current tk-core version supports it, and running in tk-desktop,
        post a cleanup of old data in the background.
        """
        return
        try:
            self.log_info(
                "Posting old cached data clean up for engine %s...." % self.engine.instance_name
            )
            # Qt might not be yet available at this stage (e.g. in tk-desktop),
            # so we can't use a background task manager or a QThread, we use
            # regular Python Thread to post the clean up in the background.
            self._bg_cleanup_thread = threading.Thread(
                target=self._remove_old_cached_data,
                name="%s Clean Up" % self.name
            )
            self._bg_cleanup_thread.start()
        except Exception as e:
            self.log_warning("Unable to post data clean up: %s" % e)
            pass

    def _remove_old_cached_data(self, grace_period=7):
        """
        Remove data old files cached by this bundle.

        A file is considered old if it was not modified in the last number of days
        specified by the `grace_period` value.

        The `grace_period` value must be at least 1 (one day).

        It is the responsability of the bundle implementation to ensure that
        modification times for the files which should be kept are recent.
        Typically, when re-using a cached file, the bundle should use
        `os.utime(cached_file_path, None)` to update the modification time to the
        current time.

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
