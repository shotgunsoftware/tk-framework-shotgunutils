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
from .config_base import RemoteConfiguration

logger = sgtk.platform.get_logger(__name__)


class LiveRemoteConfiguration(RemoteConfiguration):
    """
    Represents a remote configuration which is which is linked to
    a mutable descriptor and a locaation on disk.
    """

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_folder,
            pipeline_config_interpreter,
    ):
        """
        :param parent: Qt parent object
        :param bg_task_manager: Background task runner instance
        :param str plugin_id: Associated bootstrap plugin id
        :param id pipeline_config_id: Pipeline Configuration id
        :param are pipeline_config_name: Pipeline Configuration name
        :param str pipeline_config_uri: Descriptor URI string for the config
        :param str pipeline_config_folder: Folder where the configuration is located
        :param pipeline_config_interpreter: Path to the python interpreter
            associated with the config
        """
        super(LiveRemoteConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            pipeline_config_interpreter,
        )

        self._pipeline_configuration_id = pipeline_config_id
        self._pipeline_config_name = pipeline_config_name
        self._pipeline_config_uri = pipeline_config_uri
        self._pipeline_config_folder = pipeline_config_folder

    def __repr__(self):
        return "<LiveRemoteConfiguration id %d@%s>" % (
            self._pipeline_configuration_id,
            self._pipeline_config_uri
        )

    @property
    def pipeline_configuration_id(self):
        """
        The associated pipeline configuration id or None if not defined.
        """
        return self._pipeline_configuration_id

    @property
    def pipeline_configuration_name(self):
        """
        The name of the associated pipeline configuration or None if not defined.
        """
        return self._pipeline_config_name

    def _compute_config_hash(self, engine, entity_type, entity_id, link_entity_type):
        """
        Generates a hash to uniquely identify the configuration.
        Implemented by subclasses.

        :param str engine: Engine to run
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where caching it per linked type can be beneficial.
        :returns: dictionary of values to use for hash computation
        """
        cache_key = {
            "prefix": "id_%s" % self.pipeline_configuration_id,
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

        :returns: A dictionary keyed by yml file path, set to the file's mtime
            at the time the data was cached.
        :rtype: dict
        """
        env_path = os.path.join(self._pipeline_config_folder, "env")
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


