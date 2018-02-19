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
import sys
import cPickle
import traceback
import copy

LOGGER_NAME = "tk-framework-shotgunutils.multi_context.cache_script"
ENGINE_INIT_ERROR_EXIT_CODE = 77

def main(
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
    Bootstraps into an engine and caches commands to file.

    :param str cache_path: Path to write cached data to
    :param str configuration_uri: URI to bootstrap (for when pipeline config id is unknown).
    :param int pipeline_config_id: Associated pipeline config id
    :param str plugin_id: Plugin id to use for bootstrap
    :param str engine_name: Engine name to launch
    :param str entity_type: Entity type to launch
    :param str entity_id: Entity id to launch
    :param list bundle_cache_fallback_paths: List of bundle cache paths to include.
    """
    # import modules from shotgun-utils fw for serialization
    import file_cache
    import remote_command
    import constants

    try:
        # log to file.
        sgtk.LogManager().initialize_base_file_handler(engine_name)
        logger = sgtk.LogManager.get_logger(LOGGER_NAME)
        logger.debug("")
        logger.debug("-=" * 60)
        logger.debug("Preparing ToolkitManager for command cache bootstrap.")

        # Setup the bootstrap manager.
        manager = sgtk.bootstrap.ToolkitManager()
        manager.plugin_id = plugin_id
        manager.bundle_cache_fallback_paths = bundle_cache_fallback_paths

        if pipeline_config_id:
            # we have a pipeline config id to launch.
            manager.do_shotgun_config_lookup = True
            manager.pipeline_configuration = pipeline_config_id
        else:
            # launch a base uri. no need to look in sg for overrides.
            manager.do_shotgun_config_lookup = False
            manager.base_configuration = configuration_uri

        logger.debug("Starting %s using entity %s %s", engine_name, entity_type, entity_id)
        engine = manager.bootstrap_engine(
            engine_name,
            entity={"type": entity_type, "id": entity_id}
        )
        logger.debug("Engine %s started using entity %s %s", engine, entity_type, entity_id)

    except Exception:
        # We need to give the server a way to know that this failed due
        # to an engine initialization issue. That will allow it to skip
        # this config gracefully and log appropriately.
        logger.exception("Could not bootstrap configuration")
        print traceback.format_exc()
        sys.exit(constants.EXTERNAL_PROCESS_ENGINE_INIT_EXIT_CODE)

    # Note that from here on out, we have to use the legacy log_* methods
    # that the engine provides. This is because we're now operating in the
    # tk-core that is configured for the project, which means we can't
    # guarantee that it is v0.18+.
    engine.log_debug("Processing engine commands...")
    commands = []

    for cmd_name, data in engine.commands.iteritems():
        engine.log_debug("Processing command: %s" % cmd_name)

        commands.append(
            remote_command.RemoteCommand.serialize_command(
                {"type": entity_type, "id": entity_id},
                engine_name,
                cmd_name,
                data["properties"]
            )
        )

    engine.log_debug("Engine commands processed.")
    file_cache.write_cache_file(cache_path, commands)
    engine.log_debug("Cache complete.")
    engine.destroy()

if __name__ == "__main__":
    """
    Main script entry point
    """

    # unpack file with arguments payload
    arg_data_file = sys.argv[1]
    with open(arg_data_file, "rb") as fh:
        arg_data = cPickle.load(fh)

    # prepend sgtk to sys.path to make sure
    # know exactly what version of sgtk we are running.
    original_sys_path = copy.copy(sys.path)
    sys.path = [arg_data["core_path"]] + sys.path
    import sgtk

    # now add the external config module
    # so that we later can import serialization logic.
    utils_folder = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..",)
    )
    sys.path.insert(0, utils_folder)

    main(
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
