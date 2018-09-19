# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from .config_base import ExternalConfiguration
from .. import file_cache

logger = sgtk.platform.get_logger(__name__)


class RemoteExternalConfiguration(ExternalConfiguration):
    """
    Represents a Shotgun pipeline configuration
    linked to an remote descriptor such as app_store,
    git or shotgun.
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
            status=ExternalConfiguration.CONFIGURATION_READY
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
        """
        super(RemoteExternalConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            engine_name,
            interpreter,
            software_hash,
            pipeline_config_uri,
            status
        )

        self._pipeline_configuration_id = pipeline_config_id
        self._pipeline_config_name = pipeline_config_name

        # is our config uri tracking the latest version?
        self._tracking_latest = sgtk.descriptor.is_descriptor_version_missing(
            pipeline_config_uri
        )


    def __repr__(self):
        """
        String representation
        """
        return "<RemoteExternalConfiguration id %d@%s>" % (
            self._pipeline_configuration_id,
            self.descriptor_uri
        )

    @property
    def pipeline_configuration_id(self):
        """
        The associated pipeline configuration id or ``None`` if not defined.
        """
        return self._pipeline_configuration_id

    @property
    def pipeline_configuration_name(self):
        """
        The name of the associated pipeline configuration or ``None`` if not defined.
        """
        return self._pipeline_config_name

    @property
    def tracking_latest(self):
        """
        Returns True if this configuration is tracking an external 'latest version'.
        """
        return self._tracking_latest

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
        return {
            file_cache.FOLDER_PREFIX_KEY: "id_%s" % self.pipeline_configuration_id,
            "engine_name": self.engine_name,
            "uri": self.descriptor_uri,
            "software_hash": self.software_hash,
            "type": entity_type,
            "link_type": link_entity_type,
        }


