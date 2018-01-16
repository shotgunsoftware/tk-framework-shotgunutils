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
        # This Bundle method was introduced in tk-core > v0.18.124
        # Check the existence of the attribute to not introduce a dependency
        # on tk-core release.
        if not hasattr(self, "_remove_old_cached_data"):
            return
        # Cleaning up data can be slow if a lot of old data is present. As a
        # safety measure, we only post it when running from tk-desktop, which
        # allows us to not trigger the clean up every single time this framework
        # is loaded.
        if self.engine.instance_name != "tk-desktop":
            return

        try:
            self.log_info(
                "Posting old cached data clean up for engine %s...." % self.engine.instance_name
            )
            # Qt might not be yet available at this stage (e.g. in tk-desktop),
            # so use regular Python Thread to post the clean up in the background.
            self._bg_cleanup_thread = threading.Thread(
                target=self._remove_old_cached_data,
                name="%s Clean Up" % self.name
            )
            self._bg_cleanup_thread.start()
        except Exception as e:
            self.log_warning("Unable to post data clean up: %s" % e)
            pass
