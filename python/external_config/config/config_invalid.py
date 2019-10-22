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

logger = sgtk.platform.get_logger(__name__)


class InvalidExternalConfiguration(ExternalConfiguration):
    """
    Represents an external configuration that is invalid, and cannot be used
    as a source for requesting commands.
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
        status=ExternalConfiguration.CONFIGURATION_INACCESSIBLE,
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
        :param int status: The status of the configuration as an enum defined by
            :class:`ExternalConfiguration`.
        """
        super(InvalidExternalConfiguration, self).__init__(
            parent=parent,
            bg_task_manager=bg_task_manager,
            plugin_id=plugin_id,
            engine_name=engine_name,
            interpreter=interpreter,
            software_hash=software_hash,
            pipeline_config_uri=None,
            status=status,
        )

        self._pipeline_configuration_id = pipeline_config_id

    def __repr__(self):
        """
        String representation
        """
        return "<InvalidExternalConfiguration id %d, status %d>" % (
            self._pipeline_configuration_id,
            self.status,
        )

    @property
    def is_valid(self):
        """
        Returns ``False``, which indicates that this is an invalid configuration
        and is inaccessible for some reason.
        """
        return False

    @property
    def pipeline_configuration_id(self):
        """
        The associated PipelineConfiguration entity id.
        """
        return self._pipeline_configuration_id

    def request_commands(self, *args, **kwargs):
        """
        This implementation raises an exception, as it's not possible to
        request commands from an invalid configuration.

        :raises: RuntimeError
        """
        logger.debug("Commands were requested from an invalid configuration: %r", self)
        raise RuntimeError(
            "It is not possible to request commands from an invalid configuration."
        )
