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

LOGGER_NAME = "tk-framework-shotgunutils.multi_context.external_runner"

# first ensure that we have the right path to sgtk loaded
# this is explicitly passed down from the caller
sgtk_path = sys.argv[1]

# prepend sgtk to sys.path to make sure
# know exactly what version of sgtk we are running.
sys.path.insert(0, sgtk_path)

import sgtk

# we should now be able to import QT - this is a
# requirement for the external config module
qt_importer = sgtk.util.qt_importer.QtImporter()



# now add the external config module
# so that we later can import serialization logic.
utils_folder = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", )
)
sys.path.insert(0, utils_folder)


class QtTaskRunner(qt_importer.QtCore.QObject):
    """
    Wrapper class which allowing us to run a single operation
    """
    completed = qt_importer.QtCore.Signal()

    def __init__(self, callback):
        qt_importer.QtCore.QObject.__init__(self)
        self._callback = callback

    def execute_command(self):
        # execute the callback

        # note that because pyside has its own exception wrapper around
        # exec we need to catch and log any exceptions here.
        try:
            self._callback()

        finally:
            # broadcast that we have finished this command
            self.completed.emit()

class EngineStartupFailure(RuntimeError):
    """
    Raised when the engine fails to start.
    """


def start_engine(
    configuration_uri,
    pipeline_config_id,
    plugin_id,
    engine_name,
    entity_type,
    entity_id,
    bundle_cache_fallback_paths

):
    """
    Bootstraps into an engine.

    :param str configuration_uri: URI to bootstrap (for when pipeline config id is unknown).
    :param int pipeline_config_id: Associated pipeline config id
    :param str plugin_id: Plugin id to use for bootstrap
    :param str engine_name: Engine name to launch
    :param str entity_type: Entity type to launch
    :param str entity_id: Entity id to launch
    :param list bundle_cache_fallback_paths: List of bundle cache paths to include.
    :raises: EngineStartupFailure on failure
    """
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

    except Exception as e:
        # We need to give the server a way to know that this failed due
        # to an engine initialization issue. That will allow it to skip
        # this config gracefully and log appropriately.
        logger.exception("Could not bootstrap configuration")

        # print to our logger so it's picked up by the main process
        print traceback.format_exc()
        raise EngineStartupFailure(e)

    return engine


def cache_commands(engine, entity_type, entity_id, cache_path):
    """
    Caches registered commands for the given engine.

    :param str entity_type: Entity type
    :param str entity_id: Entity id
    :param engine: Engine instance.
    :param str cache_path: Path to write cached data to
    """
    # import modules from shotgun-utils fw for serialization
    import file_cache
    import external_command

    # Note that from here on out, we have to use the legacy log_* methods
    # that the engine provides. This is because we're now operating in the
    # tk-core that is configured for the project, which means we can't
    # guarantee that it is v0.18+.
    engine.log_debug("Processing engine commands...")
    commands = []

    for cmd_name, data in engine.commands.iteritems():
        engine.log_debug("Processing command: %s" % cmd_name)

        commands.append(
            external_command.ExternalCommand.serialize_command(
                entity_type,
                cmd_name,
                data["properties"]
            )
        )

    engine.log_debug("Engine commands processed.")
    file_cache.write_cache_file(cache_path, commands)
    engine.log_debug("Cache complete.")


def main(arg_data):

    try:
        engine = start_engine(
            arg_data["configuration_uri"],
            arg_data["pipeline_config_id"],
            arg_data["plugin_id"],
            arg_data["engine_name"],
            arg_data["entity_type"],
            arg_data["entity_id"],
            arg_data["bundle_cache_fallback_paths"]
        )

        action = arg_data["action"]

        if action == "cache_actions":
            cache_commands(
                engine,
                arg_data["entity_type"],
                arg_data["entity_id"],
                arg_data["cache_path"]
            )

        elif action == "execute_command":
            callback_name = arg_data["callback_name"]
            engine.commands[callback_name]["callback"]()

        else:
            raise RuntimeError("Unknown action '%s'" % action)

    finally:
        # make sure we have a clean shutdown
        if engine:
            engine.destroy()



if __name__ == "__main__":
    """
    Main script entry point
    """
    # unpack file with arguments payload
    arg_data_file = sys.argv[2]
    with open(arg_data_file, "rb") as fh:
        arg_data = cPickle.load(fh)

    task_runner = QtTaskRunner(main)

    # start up our QApp now
    qt_application = qt_importer.QtGui.QApplication([])

    # TODO - add icon
    #qt_application.setWindowIcon(qt_importer.QtGui.QIcon(self.icon_256))

    # when the QApp starts, initialize our task code
    qt_importer.QtCore.QTimer.singleShot(0, task_runner.execute_command)

    # and ask the main app to exit when the task emits its finished signal
    task_runner.completed.connect(qt_application.quit)

    # start the application loop. This will block the process until the task
    # has completed - this is either triggered by a main window closing or
    # byt the finished signal being called from the task class above.
    qt_application.exec_()

    sys.exit(0)
