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

from .config_immutable import ImmutableExternalConfiguration
from .config_live import LiveExternalConfiguration
from .config_fallback import FallbackExternalConfiguration
from .config_unversioned_descriptor import UnversionedDescriptorExternalConfiguration
from ..errors import ExternalConfigParseError, ExternalConfigNotAccessibleError

logger = sgtk.platform.get_logger(__name__)

# file format magic number
CONFIGURATION_GENERATION = 9


def create_from_pipeline_configuration_data(parent, bg_task_manager, config_loader, configuration_data):
    """
    Creates a :class`ExternalConfiguration` subclass given
    a set of input data, as returned by ToolkitManager.get_pipeline_configurations()

    :param parent: QT parent object.
    :type parent: :class:`~PySide.QtGui.QObject`
    :param bg_task_manager: Background task manager to use for any asynchronous work.
    :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
    :param config_loader: Associated configuration Loader
    :type config_loader: :class:`ExternalConfigurationLoader`
    :param configuration_data: Dictionary entry on the form
        returned by ToolkitManager.get_pipeline_configurations()
    :returns: :class:`ExternalConfiguration`
    :raises: :class:`ExternalConfigNotAccessibleError` if the configuration
        data could not be accessed.
    """
    descriptor = configuration_data["descriptor"]

    # for configurations which were resolved directly from a
    # descriptor, we also have a descriptor_uri set
    descriptor_uri = configuration_data["descriptor_uri"]

    if descriptor is None:
        # the config is not accessible
        raise ExternalConfigNotAccessibleError(
            "The descriptor for Pipeline Configuration '%s' (id %s) "
            "could not be resolved" % (
                configuration_data["name"],
                configuration_data["id"]
            )
        )

    elif descriptor_uri and sgtk.descriptor.is_descriptor_version_missing(descriptor_uri):
        # this is a pipeline configuration defined via the descriptor field in
        # Shotgun which doesn't have a version number, e.g. something like
        # sgtk:descriptor:app_store?name=tk-config-basic

        return UnversionedDescriptorExternalConfiguration(
            parent,
            bg_task_manager,
            config_loader.plugin_id,
            config_loader.engine_name,
            config_loader.interpreter,
            configuration_data["id"],
            configuration_data["name"],
            descriptor_uri,
        )

    elif descriptor.is_immutable():
        # this is a pipeline configuration defined in Shotgun pointing
        # at an immutable descriptor, e.g. a uploaded zip, app store,
        # git etc.
        return ImmutableExternalConfiguration(
            parent,
            bg_task_manager,
            config_loader.plugin_id,
            config_loader.engine_name,
            config_loader.interpreter,
            configuration_data["id"],
            configuration_data["name"],
            descriptor.get_uri(),
        )

    else:
        # this is a pipeline configuration pointing at a location on
        # disk where the configuration can change at any point. This
        # includes path and dev descriptors as well as classic
        # toolkit setups.

        # check that it exists on disk
        if descriptor.get_path() is None:
            raise ExternalConfigNotAccessibleError(
                "Pipeline Configuration '%s' (id %s) "
                "does not have a path on disk." % (
                    configuration_data["name"],
                    configuration_data["id"]
                )
            )

        return LiveExternalConfiguration(
            parent,
            bg_task_manager,
            config_loader.plugin_id,
            config_loader.engine_name,
            config_loader.interpreter,
            configuration_data["id"],
            configuration_data["name"],
            descriptor.get_uri(),
            descriptor.get_config_folder(),
        )


def create_fallback_configuration(parent, bg_task_manager, config_loader):
    """
    Creates a :class`ExternalConfiguration` subclass given a config
    URI with no particular pipeline configuration association.

    :param parent: QT parent object.
    :type parent: :class:`~PySide.QtGui.QObject`
    :param bg_task_manager: Background task manager to use for any asynchronous work.
    :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
    :param config_loader: Associated configuration Loader
    :type config_loader: :class:`ExternalConfigurationLoader`
    :returns: :class:`ExternalConfiguration`
    """
    return FallbackExternalConfiguration(
        parent,
        bg_task_manager,
        config_loader.plugin_id,
        config_loader.engine_name,
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
        "engine_name": config_object.engine_name,
        "interpreter": config_object.interpreter,
        "pipeline_config_id": config_object.pipeline_configuration_id,
        "pipeline_config_name": config_object.pipeline_configuration_name,
        "config_uri": config_object.descriptor_uri,
        "class_name": config_object.__class__.__name__
    }

    if isinstance(config_object, LiveExternalConfiguration):
        data["config_path"] = config_object.path

    return data


def deserialize(parent, bg_task_manager, data):
    """
    Creates a :class:`ExternalConfiguration` given serialized data.

    :param parent: QT parent object.
    :type parent: :class:`~PySide.QtGui.QObject`
    :param bg_task_manager: Background task manager to use for any asynchronous work.
    :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
    :param data: Data created with :meth:`serialize`.
    :returns: :class:`ExternalConfiguration`
    :raises: :class:`ExternalConfigParseError` on error
    """
    if data.get("GENERATION") != CONFIGURATION_GENERATION:
        raise ExternalConfigParseError(
            "Serialized format is version %s. Required version is %s" % (
                data.get("GENERATION"),
                CONFIGURATION_GENERATION
            )
        )

    if data["class_name"] == "ImmutableExternalConfiguration":
        return ImmutableExternalConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine_name"],
            data["interpreter"],
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
        )
    elif data["class_name"] == "UnversionedDescriptorExternalConfiguration":
        return UnversionedDescriptorExternalConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine_name"],
            data["interpreter"],
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
        )
    elif data["class_name"] == "LiveExternalConfiguration":
        return LiveExternalConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine_name"],
            data["interpreter"],
            data["pipeline_config_id"],
            data["pipeline_config_name"],
            data["config_uri"],
            data["config_path"],
        )
    elif data["class_name"] == "FallbackExternalConfiguration":
        return FallbackExternalConfiguration(
            parent,
            bg_task_manager,
            data["plugin_id"],
            data["engine_name"],
            data["interpreter"],
            data["config_uri"],
        )
    else:
        raise ExternalConfigParseError("Don't know how to deserialize class %s" % data["class_name"])


