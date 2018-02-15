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
import os
import logging
import base64
import functools
import copy


# NOTE: Inheriting from both Formatter and object here because, before
# Python 2.7, logging.Formatter was an old-style class. This means that
# super() can't be used with it if you only subclass from it. Mixing in
# object resolves the issue and causes no side effects in 2.7 to my
# knowledge.
#
# https://stackoverflow.com/questions/1713038/super-fails-with-error-typeerror-argument-1-must-be-type-not-classobj
class _Formatter(logging.Formatter, object):
    """
    Custom logging formatter that base64 encodes all log messages.
    """
    def format(self, *args, **kwargs):
        """
        Encodes log messages as base64. This allows us to collapse multiline
        log messages into a single line of text. Before presenting the log
        messages to a user, the caller of execute_command.py will be required
        to decode the message. Every message is tag at its head with "SGTK:",
        making output from a logger using this formatter easily identifiable.
        """
        result = super(_Formatter, self).format(*args, **kwargs)
        return "%s%s" % (LOGGING_PREFIX, base64.b64encode(result))

def pre_engine_start_callback(logger, context):
    """
    The pre-engine-start callback that's given to the bootstrap API.
    This callback handles attaching a custom logger to SGTK prior to
    the Shotgun engine being initialized. This allows us to customize
    the output of the logger in such a way that it is easily identified
    and filtered before going back to the client for display.

    :param logger: The logger to inject into the sgtk api instance.
    :param context: The context object being used during the bootstrap
        process.
    """
    context.sgtk.log = logger

def bootstrap(config, base_configuration, entity, engine_name, bundle_cache_fallback_paths):
    """
    Executes an engine command in the desired environment.

    :param dict config: The pipeline configuration entity.
    :param dict entity: The entity to give to the bootstrap manager when
        bootstrapping the engine.
    :param str base_configuration: The desired base pipeline configuration's
        uri.
    :param str engine_name: The name of the engine to bootstrap into. This
        is most likely going to be "tk-shotgun"

    :returns: The bootstrapped engine instance.
    """
    sgtk.LogManager().initialize_base_file_handler(engine_name)

    # Note that we don't have enough information here to determine the
    # name of the environment. As such, we just have to hardcode
    # that as "project", which isn't necessarily going to be true. For
    # tk-config-basic it will be, but when we're dealing with classic
    # configs it often won't be. We have to live with it, though, and
    # in the end it matters little.
    logger = sgtk.LogManager.get_logger("env.project.%s" % (engine_name))

    # We need to make sure messages from this logger end up going to
    # stdout. We'll be trapping stdout from the RPC API, which will
    # give us the output that gets sent back to the client when the
    # command is completed.
    handler = logging.StreamHandler(sys.stdout)
    sgtk.LogManager().initialize_custom_handler(handler)

    # Give it an easily-identifiable format. We'll use this in the RPC API
    # when filtering stdout before passing it up to the client. This custom
    # formatter also base64 encodes the raw log message before adding the
    # "SGTK:" tag at its head. This will mean that multi-line log messages
    # are collapsed into a single line of text, which can then be decoded
    # by the caller of execute_command.py to get the original log message.
    handler.setFormatter(_Formatter())

    # Setup the bootstrap manager.
    logger.debug("Preparing ToolkitManager for bootstrap.")
    manager = sgtk.bootstrap.ToolkitManager()

    # Not allowing config resolution to be overridden by environment
    # variables. This is here mostly for dev environment purposes, as
    # we'll use the env var to point to a dev config, but we don't
    # want that to then override everything else, like PipelineConfiguration
    # entities associated with the project.
    manager.allow_config_overrides = False
    manager.plugin_id = "basic.shotgun"
    manager.base_configuration = base_configuration
    manager.bundle_cache_fallback_paths = bundle_cache_fallback_paths

    # By building a partial object, we can go ahead and attach the logger
    # to the callback function, where it will become the first argument
    # at call time.
    manager.pre_engine_start_callback = functools.partial(
        pre_engine_start_callback,
        logger,
    )

    if config:
        manager.pipeline_configuration = config.get("id")

    engine = manager.bootstrap_engine(engine_name, entity=entity)
    logger.debug("Engine %s started using entity %s", engine, entity)

    return engine

def execute(config, project, name, entities, base_configuration, engine_name, bundle_cache_fallback_paths):
    """
    Executes an engine command in the desired environment.

    :param dict config: The pipeline configuration entity.
    :param dict project: The project entity.
    :param str name: The name of the engine command to execute.
    :param list entities: The list of entities selected in the web UI when the
        command action was triggered.
    :param str base_configuration: The desired base pipeline configuration's
        uri.
    :param str engine_name: The name of the engine to bootstrap into. This
        is most likely going to be "tk-shotgun"
    """
    # We need a single, representative entity when we bootstrap. The fact that
    # we might have gotten multiple entities from the client due to a
    # multiselection is only relevant later on when we're actually executing
    # the engine command. As such, pull the first entity off of the list.
    if entities:
        entity = entities[0]
    else:
        entity = project

    engine = bootstrap(
        config, base_configuration, entity, engine_name, bundle_cache_fallback_paths
    )

    # Handle the "special" commands that aren't tied to any registered engine
    # commands.
    if name == CORE_INFO_COMMAND:
        core_info(engine)
        sys.exit(0)
    elif name == UPGRADE_CHECK_COMMAND:
        app_upgrade_info(engine)
        sys.exit(0)

    # Import sgtk here after the bootstrap. That will ensure that we get the
    # core that was swapped in during the bootstrap.
    import sgtk

    # We need to make sure that sgtk is accessible to any process that the
    # command execution spawns. We'll look up the path to the pipeline
    # config's install location and set PYTHONPATH such that core is
    # importable.
    core_root = os.path.join(
        engine.sgtk.pipeline_configuration.get_install_location(),
        "install",
        "core",
        "python"
    )

    # We need to make sure that we're not introducing unicode into the
    # environment. This cropped up with some studio-team apps that ended
    # up causing some hangs on launch.
    if isinstance(core_root, unicode):
        core_root = core_root.encode("utf-8")

    sgtk.util.prepend_path_to_env_var(
        "PYTHONPATH",
        core_root,
    )

    command = engine.commands.get(name)

    if not command:
        msg = "Unable to find engine command: %s" % name
        engine.log_error(msg)
        raise sgtk.TankError(msg)

    # We need to know whether this command is allowed to be run when multiple
    # entities are selected. We can look for the special flag in the command's
    # properties to know whether that's the case.
    try:
        ms_flag = sgtk.platform.constants.LEGACY_MULTI_SELECT_ACTION_FLAG
    except AttributeError:
        # If the constant doesn't exist, it's because we're in a 0.16.x core.
        # In that case, we just hardcode it to what we know the value to have
        # been at that time. It's the best we can do.
        ms_flag = "supports_multiple_selection"

    props = command["properties"]
    old_style = ms_flag in props

    # Desktop sets this to the site configuration path. That will cause
    # problems for us in DCCs if it's allowed to persist, as it's checked
    # during a routine that ensures the current config matches what's
    # expected for an open work file. As such, we need to change it to
    # match the project's config path instead.
    config_path = engine.sgtk.pipeline_configuration.get_path()

    # We need to make sure that we don't introduce unicode into the
    # environment. This appears to happen at times, likely due to some
    # component of the path built by pipeline_configuration "infecting"
    # the resulting aggregate path.
    if isinstance(config_path, unicode):
        config_path = config_path.encode("utf-8")

    os.environ["TANK_CURRENT_PC"] = config_path

    if old_style:
        entity_ids = [e["id"] for e in entities]
        entity_type = entity["type"]
        engine.execute_old_style_command(name, entity_type, entity_ids)
    else:
        engine.execute_command(name)

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

    LOGGING_PREFIX = arg_data["logging_prefix"]

    execute(
        arg_data["config"],
        arg_data["project"],
        arg_data["name"],
        arg_data["entities"],
        arg_data["base_configuration"],
        arg_data["engine_name"],
        arg_data["bundle_cache_fallback_paths"]
    )

    sys.exit(0)

