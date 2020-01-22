# Copyright (c) 2018 Shotgun Software Inc.
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
import hashlib
from .config_base import ExternalConfiguration
from .. import file_cache
from tank_vendor import six


logger = sgtk.platform.get_logger(__name__)


class LiveExternalConfiguration(ExternalConfiguration):
    """
    Represents an external configuration which is linked to
    a mutable descriptor and a location on disk.

    This class of configurations are 'classic' shotgun
    configurations which have been set up with the
    Shotgun project setup wizard.
    """

    def __init__(
        self,
        parent,
        bg_task_manager,
        plugin_id,
        engine_name,
        interpreter,
        software_hash,
        pipeline_config_id,
        pipeline_config_name,
        pipeline_config_uri,
        pipeline_config_folder,
        status=ExternalConfiguration.CONFIGURATION_READY,
    ):
        """
        .. note:: This class is constructed by :class:`ExternalConfigurationLoader`.
            Do not construct objects by hand.

        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param str plugin_id: Associated bootstrap plugin id
        :param str engine_name: Associated engine name
        :param str interpreter: Associated Python interpreter
        :param str software_hash: Hash representing the state of the Shotgun software entity
        :param id pipeline_config_id: Pipeline Configuration id
        :param are pipeline_config_name: Pipeline Configuration name
        :param str pipeline_config_uri: Descriptor URI string for the config
        :param str pipeline_config_folder: Folder where the configuration is located
        """
        super(LiveExternalConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            engine_name,
            interpreter,
            software_hash,
            pipeline_config_uri,
            status,
        )

        self._pipeline_configuration_id = pipeline_config_id
        self._pipeline_config_name = pipeline_config_name
        self._pipeline_config_folder = pipeline_config_folder

    def __repr__(self):
        """
        String representation
        """
        return "<LiveExternalConfiguration id %d@%s>" % (
            self._pipeline_configuration_id,
            self.descriptor_uri,
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

    @property
    def path(self):
        """
        The path on disk to where this configuration is located.
        """
        return self._pipeline_config_folder

    def _compute_config_hash_keys(self, entity_type, entity_id, link_entity_type):
        """
        Generates a hash to uniquely identify the configuration.

        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where caching it per linked type can be beneficial.
        :returns: dictionary of values to use for hash computation
        """
        cache_key = {
            file_cache.FOLDER_PREFIX_KEY: "id_%s" % self.pipeline_configuration_id,
            "engine_name": self.engine_name,
            "software_hash": self.software_hash,
            "uri": self.descriptor_uri,
            "type": entity_type,
            "link_type": link_entity_type,
            # because this cache is mutable, we need to look deeper to calculate its uniqueness.
            "env_mtime_hash": self._get_environment_hash(),
        }

        return cache_key

    @sgtk.LogManager.log_timing
    def _get_environment_hash(self):
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

        :returns: checksum string representing the state of the environment files.
        :rtype: str
        """
        env_hash = hashlib.md5()
        env_path = os.path.join(self._pipeline_config_folder, "env")

        # We do a deep scan of from the config's "env" root down to
        # its bottom.
        logger.debug("Looking for env files in %s" % env_path)
        num_files = 0
        for root, dir_names, file_names in os.walk(env_path):
            for file_name in fnmatch.filter(file_names, "*.yml"):
                full_path = os.path.join(root, file_name)
                # stash the filename and the mod date into the hash
                num_files += 1
                env_hash.update(six.ensure_binary(full_path))
                env_hash.update(six.ensure_binary(str(os.path.getmtime(full_path))))

        logger.debug("Checked %d files" % num_files)
        return env_hash.hexdigest()
