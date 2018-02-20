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

from .config_immutable import ImmutableRemoteConfiguration
from .config_live import LiveRemoteConfiguration
from .config_fallback import FallbackRemoteConfiguration
from ..errors import RemoteConfigParseError, RemoteConfigNotAccessibleError

logger = sgtk.platform.get_logger(__name__)

# file format magic number
CONFIGURATION_GENERATION = 6


def create_from_pipeline_configuration_data(parent, bg_task_manager, config_loader, configuration_data):
    """
    Creates a :class`RemoteConfiguration` subclass given
    a set of input data, as returned by ToolkitManager.get_pipeline_configurations()

    :param parent: QT parent object.
    :type parent: :class:`~PySide.QtGui.QObject`
    :param bg_task_manager: Background task manager to use for any asynchronous work.
    :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
    :param config_loader: Associated configuration Loader
    :type config_loader: :class:`RemoteConfigurationLoader`
    :param configuration_data: Dictionary entry on the form
        returned by ToolkitManager.get_pipeline_configurations()
    :returns: :class:`RemoteConfiguration`
    :raises: :class:`RemoteConfigNotAccessibleError` if the configuration data could not
    """

    descriptor = configuration_data["descriptor"]

    if descriptor is None:
        # the config is not accessible
        raise RemoteConfigNotAccessibleError(
            "Configuration %s could not be resolved" % configuration_data["name"]
        )

    if descriptor.is_immutable():
        return ImmutableRemoteConfiguration(
            parent,
            bg_task_manager,
            config_loader.plugin_id,
            config_loader.engine,
            config_loader.interpreter,
            configuration_data["id"],
            configuration_data["name"],
            descriptor.get_uri(),
        )

    else:
        # check that it exists on disk
        if descriptor.get_path() is None:
            raise RemoteConfigNotAccessibleError(
                "Configuration %s does not have a path on disk." % configuration_data["name"]
            )

        return LiveRemoteConfiguration(
            parent,
            bg_task_manager,
            config_loader.plugin_id,
            config_loader.engine,
            config_loader.interpreter,
            configuration_data["id"],
            configuration_data["name"],
            descriptor.get_uri(),
            descriptor.get_config_folder(),
        )


def create_default(parent, bg_task_manager, config_loader):
    """
    Creates a :class`RemoteConfiguration` subclass given a config
    URI with no particular pipeline configuration association.

    :param parent: QT parent object.
    :type parent: :class:`~PySide.QtGui.QObject`
    :param bg_task_manager: Background task manager to use for any asynchronous work.
    :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
    :param config_loader: Associated configuration Loader
    :type config_loader: :class:`RemoteConfigurationLoader`
    :returns: :class:`RemoteConfiguration`
    """
    return FallbackRemoteConfiguration(
        parent,
        bg_task_manager,
        config_loader.plugin_id,
        config_loader.engine,
        config_loader.interpreter,
        config_loader.base_config_uri,
    )


def serialize(config_object):
    """
    Create a chunk of data that can be included in json, yaml or pickle.

    To be used in conjunction with :meth:`deserialize`.

    :returns: Simple dictionary based data structure.
    """
    data = {
        "GENERATION": CONFIGURATION_GENERATION,
        "plugin_id": config_object.plugin_id,
        "engine": config_object.engine,
        "interpreter": config_object.interpreter,
        "pipeline_config_id": config_object.pipeline_configuration_id,
        "pipeline_config_name": config_object.pipeline_configuration_name,
        "config_uri": config_object.descriptor_uri,
        "class_name": config_object.__class__.__name__
    }

    if isinstance(config_object, LiveRemoteConfiguration):
        data["config_path"] = config_object.path

    return data


def deserialize(parent, bg_task_manager, data):
    """
    Creates a :class:`RemoteConfiguration` given serialized data.

    :param parent: QT parent object.
    :type parent: :class:`~PySide.QtGui.QObject`
    :param bg_task_manager: Background task manager to use for any asynchronous work.
    :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
    :param data: Data created with :meth:`serialize`.
    :returns: :class:`RemoteConfiguration`
    :raises: :class:`RemoteConfigParseError` on error
    """
    if data.get("GENERATION") != CONFIGURATION_GENERATION:
        raise RemoteConfigParseError(
            "Serialized format is version %s. Required version is %s" % (
                data.get("GENERATION"),
                CONFIGURATION_GENERATION
            )
        )

    if data["class_name"] == "ImmutableRemoteConfiguration":
        return ImmutableRemoteConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine"],
            data["interpreter"],
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
        )
    elif data["class_name"] == "LiveRemoteConfiguration":
        return LiveRemoteConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine"],
            data["interpreter"],
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
            data["config_path"],
        )
    elif data["class_name"] == "FallbackRemoteConfiguration":
        return FallbackRemoteConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine"],
            data["interpreter"],
            data["config_uri"],
        )
    else:
        raise RemoteConfigParseError("Don't know how to deserialize class %s" % data["class_name"])


