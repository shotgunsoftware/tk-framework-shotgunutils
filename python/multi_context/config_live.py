# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sgtk
import fnmatch
from sgtk.platform.qt import QtCore, QtGui
from . import file_cache
from .config_base import BaseConfiguration

logger = sgtk.platform.get_logger(__name__)



class LiveConfiguration(BaseConfiguration):
    """
    Class for loading and caching registered commands for a given
    """

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            project_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_interpreter,
            local_path,
    ):
        """
        :param parent:
        :param bg_task_manager:
        :param plugin_id:
        :param project_id:
        :param pipeline_config_id:
        :param pipeline_config_name:
        :param pipeline_config_uri:
        :param pipeline_config_interpreter:
        :param local_path:
        """
        super(LiveConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            project_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_interpreter,
            local_path,
        )

    def _compute_config_hash(self, engine, entity_type, entity_id, link_entity_type):
        """
        Returns a cache key
        """
        cache_key = {
            "config_id": self.id,
            "engine": engine,
            "uri": self.descriptor_uri,
            "type": entity_type,
            "link_type": link_entity_type,
        }

        # because this cache is mutable, we need to look deeper to calculate its uniqueness.
        cache_key.update(self._get_yml_file_data())

        return cache_key

    @sgtk.LogManager.log_timing
    def _get_yml_file_data(self):
        """
        Gets environment yml file paths and their associated mtimes for the
        given pipeline configuration descriptor object. The data will be looked
        up once per unique wss connection and cached.

        ..Example:
            {
                "/shotgun/my_project/config": {
                    "/shotgun/my_project/config/env/project.yml": 1234567,
                    ...
                },
                ...
            }

        :param config_descriptor: The descriptor object for the config to get
            yml file data for.

        :returns: A dictionary keyed by yml file path, set to the file's mtime
            at the time the data was cached.
        :rtype: dict
        """
        env_path = os.path.join(self.path, "config", "env")
        logger.debug("Looking for env files in %s" % env_path)

        yml_files = {}
        # We do a deep scan of from the config's "env" root down to
        # its bottom.
        for root, dir_names, file_names in os.walk(env_path):
            for file_name in fnmatch.filter(file_names, "*.yml"):
                full_path = os.path.join(root, file_name)
                yml_files[full_path] = os.path.getmtime(full_path)

        logger.debug("Checked %d files" % len(yml_files))
        return yml_files


