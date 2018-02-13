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
import sys
import sgtk

from .config_immutable import ImmutableRemoteConfiguration
from .config_live import LiveRemoteConfiguration
from .config_fallback import FallbackRemoteConfiguration
from ..errors import RemoteConfigParseError, RemoteConfigNotAccessibleError

logger = sgtk.platform.get_logger(__name__)

CONFIGURATION_GENERATION = 3


def create_from_pipeline_configuration_data(parent, bg_task_manager, plugin_id, configuration_data):
    """
    Creates a :class`RemoteConfiguration` subclass given
    a set of input data, as returned by ToolkitManager.get_pipeline_configurations()

    :param parent: Qt parent object
    :param bg_task_manager: Background task runner instance
    :param str plugin_id: Associated bootstrap plugin id
    :param configuration_data: Dictionary entry on the form
        returned by ToolkitManager.get_pipeline_configurations()
    :returns: :class:`RemoteConfiguration`
    :raises: :class:`RemoteConfigNotAccessibleError` if the configuration data could not
    """

    if configuration_data["descriptor"] is None:
        # the config is not accessible
        raise RemoteConfigNotAccessibleError(
            "Configuration %s could not be accessed" % configuration_data["name"]
        )

    if configuration_data["descriptor"].is_immutable():
        return ImmutableRemoteConfiguration(
            parent,
            bg_task_manager,
            plugin_id,
            configuration_data["id"],
            configuration_data["name"],
            configuration_data["descriptor"].get_uri(),
            _get_python_interpreter(configuration_data["descriptor"])
        )

    else:
        return LiveRemoteConfiguration(
            parent,
            bg_task_manager,
            plugin_id,
            configuration_data["id"],
            configuration_data["name"],
            configuration_data["descriptor"].get_config_folder(),
            configuration_data["descriptor"].get_uri(),
            _get_python_interpreter(configuration_data["descriptor"])
        )


def create_default(parent, bg_task_manager, plugin_id, config_uri):
    """
    Creates a :class`RemoteConfiguration` subclass given a config
    URI with no particular pipeline configuration association.

    :param parent: Qt parent object
    :param bg_task_manager: Background task runner instance
    :param str plugin_id: Associated bootstrap plugin id
    :param str config_uri: Config URI to cache
    :returns: :class:`RemoteConfiguration`
    """
    return FallbackRemoteConfiguration(
        parent,
        bg_task_manager,
        plugin_id,
        config_uri,
        _get_python_interpreter(None)
    )


def serialize(config_object):
    """
    Create a chunk of data that can be included in json, yaml or pickle.
    :return: simple data structure.
    """
    data = {
        "GENERATION": CONFIGURATION_GENERATION,
        "plugin_id": config_object.plugin_id,
        "pipeline_config_id": config_object.pipeline_configuration_id,
        "config_uri": config_object.descriptor_uri,
        "python_interpreter": config_object._pipeline_config_interpreter,  # todo - fix
        "class_name": config_object.__class__.__name__
    }

    if isinstance(config_object, LiveRemoteConfiguration):
        data["config_path"] = config_object._pipeline_config_folder

    return data


def deserialize(parent, bg_task_manager, data):
    """
    Creates a :class:`RemoteConfiguration` given serialized data.

    :param bg_task_manager:
    :param parent:
    :param data:
    :returns: :class:`RemoteConfiguration`
    :raises: SerializationFormatError
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
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
            data["python_interpreter"]
        )
    elif data["class_name"] == "LiveRemoteConfiguration":
        return LiveRemoteConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
            data["config_path"],
            data["python_interpreter"]
        )
    elif data["class_name"] == "FallbackRemoteConfiguration":
        return FallbackRemoteConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["config_uri"],
            data["python_interpreter"]
        )
    else:
        raise RemoteConfigParseError("Don't know how to deserialize class %s" % data["class_name"])


def _get_python_interpreter(descriptor):
    """
    Retrieves the python interpreter from the configuration. Returns the
    current python interpreter if no interpreter was specified.
    """
    try:
        if descriptor is None:
            # use default python
            raise sgtk.TankFileDoesNotExistError()
        else:
            path_to_python = descriptor.python_interpreter
    except sgtk.TankFileDoesNotExistError:
        # note - for configurations not declaring this,
        # a perfectly valid thing to do - we just use the
        # default one
        if sys.platform == "darwin":
            path_to_python = os.path.join(sys.prefix, "bin", "python")
        elif sys.platform == "win32":
            path_to_python = os.path.join(sys.prefix, "python.exe")
        else:
            path_to_python = os.path.join(sys.prefix, "bin", "python")
    return path_to_python
