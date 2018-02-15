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

logger = sgtk.platform.get_logger(__name__)


class ImmutableRemoteConfiguration(RemoteConfiguration):
    """
    Represents a Shotgun pipeline configuration
    linked to an immutable descriptor.
    """

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_interpreter,
    ):
        """
        .. note:: This class is constructed by :class:`RemoteConfigurationLoader`.
            Do not construct objects by hand.

        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param str plugin_id: Associated bootstrap plugin id
        :param id pipeline_config_id: Pipeline Configuration id
        :param are pipeline_config_name: Pipeline Configuration name
        :param str pipeline_config_uri: Descriptor URI string for the config
        :param pipeline_config_interpreter: Path to the python interpreter
            associated with the config
        """
        super(ImmutableRemoteConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            pipeline_config_interpreter,
        )

        self._pipeline_configuration_id = pipeline_config_id
        self._pipeline_config_name = pipeline_config_name
        self._pipeline_config_uri = pipeline_config_uri

    def __repr__(self):
        """
        String representation
        """
        return "<ImmutableRemoteConfiguration id %d@%s>" % (
            self._pipeline_configuration_id,
            self._pipeline_config_uri
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

    def _compute_config_hash(self, engine, entity_type, entity_id, link_entity_type):
        """
        Generates a hash to uniquely identify the configuration.

        :param str engine: Engine to run
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where caching it per linked type can be beneficial.
        :returns: dictionary of values to use for hash computation
        """
        return {
            "prefix": "id_%s" % self.pipeline_configuration_id,
            "engine": engine,
            "uri": self.descriptor_uri,
            "type": entity_type,
            "link_type": link_entity_type,
        }


