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
from .config_base import RemoteConfiguration
from .. import file_cache

logger = sgtk.platform.get_logger(__name__)


class FallbackRemoteConfiguration(RemoteConfiguration):
    """
    Class representing a config which does not have
    an associated pipeline configuration id.
    """

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            engine,
            interpreter,
            pipeline_config_uri,
    ):
        """
        .. note:: This class is constructed by :class:`RemoteConfigurationLoader`.
            Do not construct objects by hand.

        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param str plugin_id: Associated bootstrap plugin id
        :param str engine: Associated engine name
        :param str interpreter: Associated python interpreter
        :param str pipeline_config_uri: Descriptor URI string for the config
        """
        super(FallbackRemoteConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            engine,
            interpreter,
        )
        self._pipeline_config_uri = pipeline_config_uri

    def __repr__(self):
        """
        Low level string representation
        """
        return "<FallbackRemoteConfiguration %s>" % self._pipeline_config_uri

    @property
    def descriptor_uri(self):
        """
        The descriptor uri associated with this pipeline configuration.
        """
        return self._pipeline_config_uri

    def _compute_config_hash(self, entity_type, entity_id, link_entity_type):
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
            file_cache.FOLDER_PREFIX_KEY: "base",
            "engine": self.engine,
            "uri": self.descriptor_uri,
            "type": entity_type,
            "link_type": link_entity_type,
        }

        return cache_key

