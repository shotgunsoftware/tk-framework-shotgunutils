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
    callback_name,
    configuration_uri,
    pipeline_config_id,
    plugin_id,
    engine_name,
    entity_type,
    entity_id,
    bundle_cache_fallback_paths

):
    """
    """
    try:
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
            # we have a pipeline config id to launch
            manager.do_shotgun_config_lookup = True
            manager.pipeline_configuration = pipeline_config_id
        else:
            # launch a base uri. no need to look up in sg.
            manager.do_shotgun_config_lookup = False
            manager.base_configuration = configuration_uri # sgtk:descriptor:baked=path/to/viewmaster/baked

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
        logger.exception("could not bootstrap configuration")
        print traceback.format_exc()
        sys.exit(ENGINE_INIT_ERROR_EXIT_CODE)

    # Note that from here on out, we have to use the legacy log_* methods
    # that the engine provides. This is because we're now operating in the
    # tk-core that is configured for the project, which means we can't
    # guarantee that it is v0.18+.
    engine.log_debug("Processing engine commands...")

    engine.commands[callback_name]["callback"]()

    logger.debug("Execution complete. Exiting with code 0")


if __name__ == "__main__":
    arg_data_file = sys.argv[1]

    with open(arg_data_file, "rb") as fh:
        arg_data = cPickle.load(fh)

    # The RPC api has given us the path to its tk-core to prepend
    # to our sys.path prior to importing sgtk. We'll prepent the
    # the path, import sgtk, and then clean up after ourselves.
    original_sys_path = copy.copy(sys.path)
    try:
        sys.path = [arg_data["core_path"]] + sys.path
        import sgtk
    finally:
        sys.path = original_sys_path

    # now add shotgun utils
    utils_folder = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..",)
    )
    sys.path.insert(0, utils_folder)

    main(
        arg_data["callback_name"],
        arg_data["configuration_uri"],
        arg_data["pipeline_config_id"],
        arg_data["plugin_id"],
        arg_data["engine_name"],
        arg_data["entity_type"],
        arg_data["entity_id"],
        arg_data["bundle_cache_fallback_paths"]
    )

    sys.exit(0)
