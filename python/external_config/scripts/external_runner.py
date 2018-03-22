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
import imp
import sys
import cPickle
import traceback

# handle imports
path_to_sgtk = sys.argv[1]
# prepend sgtk to sys.path to make sure
# know exactly what version of sgtk we are running.
sys.path.insert(0, path_to_sgtk)
import sgtk

# we should now be able to import QT - this is a
# requirement for the external config module
qt_importer = sgtk.util.qt_importer.QtImporter()

LOGGER_NAME = "tk-framework-shotgunutils.multi_context.external_runner"
logger = sgtk.LogManager.get_logger(LOGGER_NAME)


class QtTaskRunner(qt_importer.QtCore.QObject):
    """
    Wrapper class for a callback payload.

    This is used in conjunction with a QT event loop, allowing a
    given callback to be run inside an event loop. By the end of
    the execution, if the callback payload has not created any
    windows, a ``completed`` signal is emitted. This allows for
    a pattern where the QT event loop can be explicitly torn down
    for callback payloads which don't start up new dialogs.

    In the case of dialogs, QT defaults to a "terminate event loop
    when the last window closes", ensuring a graceful termination
    when the dialog is closed.

    Typically used like this::

        task_runner = QtTaskRunner(callback_payload)

        # start up our QApplication
        qt_application = qt_importer.QtGui.QApplication([])

        # Set up automatic execution of our task runner as soon
        # as the event loop starts up.
        qt_importer.QtCore.QTimer.singleShot(0, task_runner.execute_command)

        # and ask the main app to exit when the task emits its finished signal
        task_runner.completed.connect(qt_application.quit)

        # start the application loop. This will block the process until the task
        # has completed - this is either triggered by a main window closing or
        # byt the finished signal being called from the task class above.
        qt_application.exec_()

        # check if any errors were raised.
        if task_runner.failure_detected:
            # exit with error
            sys.exit(1)
        else:
            sys.exit(0)
    """

    # emitted when the taskrunner has completed non-ui work
    completed = qt_importer.QtCore.Signal()

    def __init__(self, callback):
        """
        :param callback: Callback to execute
        """
        qt_importer.QtCore.QObject.__init__(self)
        self._callback = callback
        self._failure_detected = False

    @property
    def failure_detected(self):
        """
        True if an execution error has been detected
        """
        return self._failure_detected

    def execute_command(self):
        """
        Execute the callback given by the constructor.
        For details and example, see the class introduction.
        """
        # note that because pyside has its own exception wrapper around
        # exec we need to catch and log any exceptions here.
        try:
            self._callback()
        except Exception as e:
            self._failure_detected = True

            # We need to give the server a way to know that this failed due
            # to an engine initialization issue. That will allow it to skip
            # this config gracefully and log appropriately.
            logger.exception("Could not bootstrap configuration")

            # push it to stdout so that the parent process will get it
            print traceback.format_exc()

        finally:
            # broadcast that we have finished this command
            qt_app = qt_importer.QtCore.QCoreApplication.instance()
            if len(qt_app.topLevelWidgets()) == 0:
                # no windows opened. we are done!
                self.completed.emit()


def _get_core_python_path():
    """
    Computes the path to the current Toolkit core.

    :returns: Path to the current core.
    """
    sgtk_file = sgtk.__file__
    tank_folder = os.path.dirname(sgtk_file)
    python_folder = os.path.dirname(tank_folder)
    return python_folder


def _import_py_file(python_path, name):
    """
    Helper which imports a Python file and returns it.

    :param str python_path: path where module is located
    :param str name: name of py file (without extension)
    :returns: Python object
    """
    mfile, pathname, description = imp.find_module(name, [python_path])
    try:
        module = imp.load_module(name, mfile, pathname, description)
    finally:
        if mfile:
            mfile.close()
    return module


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
    """
    # log to file.
    sgtk.LogManager().initialize_base_file_handler(engine_name)
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

    # add the core path to the PYTHONPATH so that downstream processes
    # can make use of it
    sgtk_path = _get_core_python_path()
    sgtk.util.prepend_path_to_env_var("PYTHONPATH", sgtk_path)

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
    utils_folder = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", )
    )
    file_cache = _import_py_file(utils_folder, "file_cache")
    external_command = _import_py_file(utils_folder, "external_command")

    logger.debug("Processing engine commands...")
    cache_data = {
        "version": external_command.ExternalCommand.FORMAT_GENERATION,
        "commands": []
    }

    for cmd_name, data in engine.commands.iteritems():
        logger.debug("Processing command: %s" % cmd_name)

        if external_command.ExternalCommand.enabled_on_current_os(data["properties"]):
            cache_data["commands"].append(
                external_command.ExternalCommand.serialize_command(
                    entity_type,
                    cmd_name,
                    data["properties"]
                )
            )

    logger.debug("Engine commands processed.")
    file_cache.write_cache_file(cache_path, cache_data)
    logger.debug("Cache complete.")


def main():
    """
    Main method, executed from inside a QT event loop.
    """
    # unpack file with arguments payload
    arg_data_file = sys.argv[2]
    with open(arg_data_file, "rb") as fh:
        arg_data = cPickle.load(fh)

    # Add application icon
    qt_application.setWindowIcon(
        qt_importer.QtGui.QIcon(arg_data["icon_path"])
    )

    engine = None

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

            # try to set the process icon to be the tk app icon
            if engine.commands[callback_name]["properties"]["app"]:
                # not every command has an associated app
                qt_application.setWindowIcon(
                    qt_importer.QtGui.QIcon(
                        engine.commands[callback_name]["properties"]["app"].icon_256
                    )
                )
            # execute the payload
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
    task_runner = QtTaskRunner(main)

    # For qt5, we may get this error:
    #
    # RuntimeError: Qt WebEngine seems to be initialized from a plugin.
    # Please set Qt::AA_ShareOpenGLContexts using QCoreApplication::setAttribute
    # before constructing QGuiApplication.
    if hasattr(qt_importer.QtCore.Qt, "AA_ShareOpenGLContexts"):
        qt_importer.QtGui.QApplication.setAttribute(
            qt_importer.QtCore.Qt.AA_ShareOpenGLContexts
        )

    # start up our QApp now
    qt_application = qt_importer.QtGui.QApplication([])

    # when the QApp starts, initialize our task code
    qt_importer.QtCore.QTimer.singleShot(0, task_runner.execute_command)

    # and ask the main app to exit when the task emits its finished signal
    task_runner.completed.connect(qt_application.quit)

    # start the application loop. This will block the process until the task
    # has completed - this is either triggered by a main window closing or
    # byt the finished signal being called from the task class above.
    qt_application.exec_()

    if task_runner.failure_detected:
        # exit with error
        sys.exit(1)
    else:
        sys.exit(0)
