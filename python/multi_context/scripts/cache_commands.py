# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sys
import cPickle
import glob
import os
import contextlib
import traceback
import copy

LOGGER_NAME = "tk-framework-shotgunutils.multi_context.cache_script"
ENGINE_INIT_ERROR_EXIT_CODE = 77

def bootstrap(data, base_configuration, engine_name, config_data, bundle_cache_fallback_paths):
    """
    Bootstraps into sgtk and returns the resulting engine instance.

    :param dict data: The raw payload send down by the client.
    :param str base_configuration: The desired base pipeline configuration's
        uri.
    :param str engine_name: The name of the engine to bootstrap into. This
        is most likely going to be "tk-shotgun"
    :param dict config_data: All relevant pipeline configuration data. This
        dict is keyed by pipeline config entity id, each containing a dict
        that contains, at a minimum, "entity", "lookup_hash", and
        "contents_hash" keys.

    :returns: Bootstrapped engine instance.
    """
    sgtk.LogManager().initialize_base_file_handler("tk-shotgun")

    logger = sgtk.LogManager.get_logger(LOGGER_NAME)
    logger.debug("Preparing ToolkitManager for bootstrap.")

    entity = dict(
        type=data["entity_type"],
        id=data["entity_id"],
        project=dict(
            type="Project",
            id=data["project_id"],
        ),
    )

    # Setup the bootstrap manager.
    manager = sgtk.bootstrap.ToolkitManager()
    manager.caching_policy = manager.CACHE_FULL
    manager.allow_config_overrides = False
    manager.plugin_id = "basic.shotgun"
    manager.base_configuration = base_configuration
    manager.pipeline_configuration = config_data["entity"]["id"]
    manager.bundle_cache_fallback_paths = bundle_cache_fallback_paths

    logger.debug("Starting %s using entity %s", engine_name, entity)
    engine = manager.bootstrap_engine(engine_name, entity=entity)
    logger.debug("Engine %s started using entity %s", engine, entity)

    return engine

def cache(
    cache_path,
    configuration_uri,
    pipeline_config_id,
    plugin_id,
    engine_name,
    entity_type,
    entity_id,
    bundle_cache_fallback_paths
):
    """
    Populates the sqlite cache with a row representing the desired pipeline
    configuration and entity type. If an entry already exists, it is updated.

    :param str cache_file: The path to the sqlite cache file on disk.
    :param dict data: The raw payload send down by the client.
    :param str base_configuration: The desired base pipeline configuration's
        uri.
    :param str engine_name: The name of the engine to bootstrap into. This
        is most likely going to be "tk-shotgun"
    :param dict config_data: All relevant pipeline configuration data. This
        dict is keyed by pipeline config entity id, each containing a dict
        that contains, at a minimum, "entity", "lookup_hash", and
        "contents_hash" keys.
    :param bool config_is_mutable: Whether the pipeline config is mutable. If
        it is, then we include the __core_info and __upgrade_check commands.
    """
    try:
        engine = bootstrap(
            data,
            base_configuration,
            engine_name,
            config_data,
            bundle_cache_fallback_paths,
        )
    except Exception:
        # We need to give the server a way to know that this failed due
        # to an engine initialization issue. That will allow it to skip
        # this config gracefully and log appropriately.
        print traceback.format_exc()
        sys.exit(ENGINE_INIT_ERROR_EXIT_CODE)

    # Note that from here on out, we have to use the legacy log_* methods
    # that the engine provides. This is because we're now operating in the
    # tk-core that is configured for the project, which means we can't
    # guarantee that it is v0.18+.
    engine.log_debug("Raw payload from client: %s" % data)

    lookup_hash = config_data["lookup_hash"]
    contents_hash = config_data["contents_hash"]

    engine.log_debug("Processing engine commands...")
    commands = []

    for cmd_name, data in engine.commands.iteritems():
        engine.log_debug("Processing command: %s" % cmd_name)
        props = data["properties"]
        app = props.get("app")

        if app:
            app_name = app.name
        else:
            app_name = None

        commands.append(
            dict(
                name=cmd_name,
                title=props.get("title", cmd_name),
                deny_permissions=props.get("deny_permissions", []),
                supports_multiple_selection=props.get(
                    "supports_multiple_selection",
                    False
                ),
                app_name=app_name,
                group=props.get("group"),
                group_default=props.get("group_default"),
                engine_name=props.get("engine_name"),
            ),
        )

    engine.log_debug("Engine commands processed.")


    # Tear down the engine. This is both good practice before we exit
    # this process, but also necessary if there are multiple pipeline
    # configs that we're iterating over.
    engine.log_debug("Shutting down engine...")
    engine.destroy()

if __name__ == "__main__":
    arg_data_file = sys.argv[1]

    with open(arg_data_file, "rb") as fh:
        arg_data = cPickle.load(fh)

    # The RPC api has given us the path to its tk-core to prepend
    # to our sys.path prior to importing sgtk. We'll prepent the
    # the path, import sgtk, and then clean up after ourselves.
    original_sys_path = copy.copy(sys.path)
    try:
        sys.path = [arg_data["sys_path"]] + sys.path
        import sgtk
    finally:
        sys.path = original_sys_path

    cache(
        arg_data["cache_path"],
        arg_data["configuration_uri"],
        arg_data["pipeline_config_id"],
        arg_data["plugin_id"],
        arg_data["engine_name"],
        arg_data["entity_type"],
        arg_data["entity_id"],
        arg_data["bundle_cache_fallback_paths"]
    )

    sys.exit(0)
