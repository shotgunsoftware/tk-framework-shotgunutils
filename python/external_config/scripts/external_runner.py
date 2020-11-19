# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from __future__ import print_function
import os
import re
import sys
import errno
import inspect
import traceback

# Until we remove the use of imp from this code,
# we must suppress the warning here as it will pop up in the Shotgun browser
# integration as a message box, when running in Python 3.4 >.
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    import imp


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


class EngineStartupError(Exception):
    """
    Indicates that bootstrapping into the engine failed.
    """


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

    # statuses
    (SUCCESS, GENERAL_ERROR, ERROR_ENGINE_NOT_STARTED) = range(3)

    def __init__(self, callback):
        """
        :param callback: Callback to execute
        """
        qt_importer.QtCore.QObject.__init__(self)
        self._callback = callback
        self._status = self.SUCCESS

    @property
    def status(self):
        """
        Status of execution
        """
        return self._status

    def execute_command(self):
        """
        Execute the callback given by the constructor.
        For details and example, see the class introduction.
        """
        # note that because pyside has its own exception wrapper around
        # exec we need to catch and log any exceptions here.
        try:
            self._callback()

        except EngineStartupError as e:
            self._status = self.ERROR_ENGINE_NOT_STARTED

            # log details to log file
            logger.exception("Could not start engine.")

            # push message to stdout
            print("Engine could not be started: %s. For details, see log files." % e)

        except Exception as e:
            self._status = self.GENERAL_ERROR

            # log details to log file
            logger.exception("Could not bootstrap configuration.")

            # push it to stdout so that the parent process will get it
            print("A general error was raised:")
            print(traceback.format_exc())

        finally:
            # broadcast that we have finished this command
            qt_app = qt_importer.QtCore.QCoreApplication.instance()

            if len(qt_app.topLevelWidgets()) == 0:
                # no windows opened. we are done!
                self.completed.emit()
            elif not [w for w in qt_app.topLevelWidgets() if w.isVisible()]:
                # There are windows, but they're all hidden, which means we should
                # be safe to shut down.
                self.completed.emit()


def _handle_qt_warnings():
    """
    This will suppress the libpng warnings, but allow any
    other warnings or errors from QT to print.
    We do this because by default warnings get printed to stderr
    and so they get displayed in the browser when running actions.
    """

    def handler(*args):
        # We handle the args this way since Qt 5 passes 3 args, type, context and message,
        # Where as Qt 4 only passes 2, type, and message.
        msg_type = args[0]
        msg_string = args[-1]

        # Suppress this warning.
        if msg_string == "libpng warning: iCCP: known incorrect sRGB profile":
            return

        if msg_type in [
            qt_importer.QtCore.QtMsgType.QtWarningMsg,
            qt_importer.QtCore.QtMsgType.QtCriticalMsg,
            qt_importer.QtCore.QtMsgType.QtFatalMsg,
        ]:
            # By default Qt would usually print these to stderr so we should do the same.
            print(msg_string, file=sys.stderr)
        else:
            # This is probably a debug or info message so just print these normally.
            print(msg_string)

    # Add a message handler so we can suppress the warnings about libpng.
    try:
        # QT 4
        qt_importer.QtCore.qInstallMsgHandler(handler)
    except AttributeError:
        # QT 5
        qt_importer.QtCore.qInstallMessageHandler(handler)


def _get_core_python_path(engine):
    """
    Computes the path to the core for a given engine.

    :param engine: Toolkit Engine to inspect
    :returns: Path to the current core.
    """
    sgtk_file = inspect.getfile(engine.sgtk.__class__)
    tank_folder = os.path.dirname(sgtk_file)
    python_folder = os.path.dirname(tank_folder)
    return python_folder


def _write_cache_file(path, data):
    """
    Writes a cache to disk given a path and some data.

    :param str path: Path to a cache file on disk.
    :param data: Data to save.
    """
    logger.debug("Saving cache to disk: %s" % path)

    old_umask = os.umask(0)
    try:
        # try to create the cache folder with as open permissions as possible
        cache_dir = os.path.dirname(path)
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir, 0o775)
            except OSError as e:
                # Race conditions are perfectly possible on some network storage setups
                # so make sure that we ignore any file already exists errors, as they
                # are not really errors!
                if e.errno != errno.EEXIST:
                    # re-raise
                    raise
        # now write the file to disk
        try:
            with open(path, "wb") as fh:
                sgtk.util.pickle.dump(data, fh)
            # and ensure the cache file has got open permissions
            os.chmod(path, 0o666)
        except Exception as e:
            logger.debug(
                "Could not write '%s'. Details: %s" % (path, e), exec_info=True
            )
        else:
            logger.debug(
                "Completed save of %s. Size %s bytes" % (path, os.path.getsize(path))
            )
    finally:
        os.umask(old_umask)


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
    user,
    configuration_uri,
    pipeline_config_id,
    plugin_id,
    engine_name,
    entity_type,
    entity_id,
    bundle_cache_fallback_paths,
    pre_cache,
):
    """
    Bootstraps into an engine.

    :param ShotgunUser user: The user that have to be used while bootstraping the engine.
    :param str configuration_uri: URI to bootstrap (for when pipeline config id is unknown).
    :param int pipeline_config_id: Associated pipeline config id
    :param str plugin_id: Plugin id to use for bootstrap
    :param str engine_name: Engine name to launch
    :param str entity_type: Entity type to launch
    :param str entity_id: Entity id to launch
    :param list bundle_cache_fallback_paths: List of bundle cache paths to include.
    :param bool pre_cache: If set to True, starting up the command
        will also include a full caching of all necessary
        dependencies for all contexts and engines.
    """
    # log to file.
    sgtk.LogManager().initialize_base_file_handler(engine_name)
    logger.debug("")
    logger.debug("-=" * 60)
    logger.debug("Preparing ToolkitManager for command cache bootstrap.")

    # Setup the bootstrap manager.
    manager = sgtk.bootstrap.ToolkitManager(user)
    manager.plugin_id = plugin_id
    manager.bundle_cache_fallback_paths = bundle_cache_fallback_paths

    if pre_cache:
        logger.debug("Will request a full environment caching before startup.")
        manager.caching_policy = manager.CACHE_FULL

    if pipeline_config_id:
        # we have a pipeline config id to launch.
        manager.do_shotgun_config_lookup = True
        manager.pipeline_configuration = pipeline_config_id
    else:
        # launch a base uri. no need to look in sg for overrides.
        manager.do_shotgun_config_lookup = False
        manager.base_configuration = configuration_uri

    logger.debug("Starting %s using entity %s %s", engine_name, entity_type, entity_id)
    try:
        engine = manager.bootstrap_engine(
            engine_name, entity={"type": entity_type, "id": entity_id}
        )

    #
    # NOTE: At this point, the core has been swapped, and can be as old
    #       as v0.15.x. Beyond this point, all sgtk operatinos need to
    #       be backwards compatible with v0.15.
    #

    except Exception as e:
        # qualify this exception and re-raise
        # note: we cannot probe for TankMissingEngineError here,
        # because older cores may not raise that exception type.
        logger.debug("Could not launch engine.", exc_info=True)
        raise EngineStartupError(e)

    logger.debug("Engine %s started using entity %s %s", engine, entity_type, entity_id)

    # add the core path to the PYTHONPATH so that downstream processes
    # can make use of it
    sgtk_path = _get_core_python_path(engine)
    sgtk.util.prepend_path_to_env_var("PYTHONPATH", sgtk_path)

    return engine


def cache_commands(engine, entity_type, entity_id, cache_path):
    """
    Caches registered commands for the given engine.
    If the engine is None, an empty list of actions is cached.

    :param str entity_type: Entity type
    :param str entity_id: Entity id
    :param engine: Engine instance or None
    :param str cache_path: Path to write cached data to
    """
    # import modules from shotgun-utils fw for serialization
    utils_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    external_command_utils = _import_py_file(utils_folder, "external_command_utils")

    cache_data = {
        "generation": external_command_utils.FORMAT_GENERATION,
        "commands": [],
    }
    if engine is None:
        logger.debug("No engine running - caching empty list of commands.")

    else:
        logger.debug("Processing engine commands...")
        for cmd_name, data in engine.commands.items():
            logger.debug("Processing command: %s" % cmd_name)

            # note: we are baking the current operating system into the cache,
            #       meaning that caches cannot be shared freely across OS platforms.
            if external_command_utils.enabled_on_current_os(data["properties"]):
                cache_data["commands"].append(
                    external_command_utils.serialize_command(
                        engine.name, entity_type, cmd_name, data["properties"]
                    )
                )
        logger.debug("Engine commands processed.")

    _write_cache_file(cache_path, cache_data)
    logger.debug("Cache complete.")


def main():
    """
    Main method, executed from inside a QT event loop.
    """
    # unpack file with arguments payload
    arg_data_file = sys.argv[2]
    with open(arg_data_file, "rb") as fh:
        arg_data = sgtk.util.pickle.load(fh)

    # Add application icon
    qt_application.setWindowIcon(qt_importer.QtGui.QIcon(arg_data["icon_path"]))

    action = arg_data["action"]
    user = sgtk.authentication.deserialize_user(arg_data["user"])
    engine = None

    user = None
    if arg_data.get("user", None):
        user = sgtk.authentication.deserialize_user(arg_data["user"])

    if action == "cache_actions":
        try:
            engine = start_engine(
                user,
                arg_data["configuration_uri"],
                arg_data["pipeline_config_id"],
                arg_data["plugin_id"],
                arg_data["engine_name"],
                arg_data["entity_type"],
                arg_data["entity_id"],
                arg_data["bundle_cache_fallback_paths"],
                arg_data.get("pre_cache") or False,
            )
        except Exception as e:
            # catch the special case where a shotgun engine has falled back
            # to its legacy mode, looking for a shotgun_entitytype.yml file
            # and cannot find it. In this case, we shouldn't handle that as
            # an error but as an indication that the given entity type and
            # entity id doesn't have any actions defined, and thus produce
            # an empty list.
            #
            # Because this operation needs to be backwards compatible, we
            # have to parse the exception message in order to extract the
            # relevant state. The error to look for is on the following form:
            # TankMissingEnvironmentFile: Missing environment file: /path/to/env/shotgun_camera.yml
            #
            if re.match(
                "^Missing environment file:.*shotgun_[a-zA-Z0-9]+\.yml$", str(e)
            ):
                logger.debug(
                    "Bootstrap returned legacy fallback exception '%s'. "
                    "An empty list of actions will be cached for the "
                    "given entity type.",
                    str(e),
                )
            else:
                # bubble the error
                raise

        cache_commands(
            engine,
            arg_data["entity_type"],
            arg_data["entity_id"],
            arg_data["cache_path"],
        )

    elif action == "execute_command":
        engine = start_engine(
            user,
            arg_data["configuration_uri"],
            arg_data["pipeline_config_id"],
            arg_data["plugin_id"],
            arg_data["engine_name"],
            arg_data["entity_type"],
            arg_data["entity_ids"][0],
            arg_data["bundle_cache_fallback_paths"],
            False,
        )

        callback_name = arg_data["callback_name"]

        # try to set the process icon to be the tk app icon
        if engine.commands[callback_name]["properties"].get("app"):
            # not every command has an associated app
            qt_application.setWindowIcon(
                qt_importer.QtGui.QIcon(
                    engine.commands[callback_name]["properties"]["app"].icon_256
                )
            )

        # Now execute the payload command payload

        # tk-shotgun apps are the only ones that supply a value for "supports_multiple_selection"
        # These apps' commands/callbacks are also the only ones that expect the extra parameters
        # entity_type and entity_ids to be passed in so we need to use a special method with them
        if arg_data["supports_multiple_selection"] is not None:
            engine.execute_old_style_command(
                callback_name, arg_data["entity_type"], arg_data["entity_ids"]
            )
        else:
            # standard route - just run the callback
            engine.commands[callback_name]["callback"]()

    else:
        raise RuntimeError("Unknown action '%s'" % action)


if __name__ == "__main__":
    """
    Main script entry point
    """

    # Suppress unwanted Qt warnings.
    _handle_qt_warnings()

    # unpack file with arguments payload
    arg_data_file = sys.argv[2]
    with open(arg_data_file, "rb") as fh:
        arg_data = sgtk.util.pickle.load(fh)

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

    # we don't want this process to have any traces of
    # any previous environment
    if "TANK_CURRENT_PC" in os.environ:
        del os.environ["TANK_CURRENT_PC"]

    if arg_data["background"]:
        # Done in a try block because it will only work On MacOS
        # if the Python interpreter have the pyobjc package installed.
        try:
            import AppKit

            info = AppKit.NSBundle.mainBundle().infoDictionary()
            info["LSBackgroundOnly"] = "1"
        except Exception:
            # If you don't have AppKit available, it's fine,
            # nothing critical will happen.
            pass

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

    # Make sure we have a clean shutdown.
    if sgtk.platform.current_engine():
        sgtk.platform.current_engine().destroy()

    if task_runner.status == task_runner.SUCCESS:
        sys.exit(0)
    elif task_runner.status == task_runner.ERROR_ENGINE_NOT_STARTED:
        sys.exit(2)

    # for all general errors
    sys.exit(1)
