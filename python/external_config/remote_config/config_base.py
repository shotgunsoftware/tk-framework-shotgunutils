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
import sgtk
import tempfile
import cPickle
from sgtk.platform.qt import QtCore, QtGui
from ..process_execution import ProcessRunner
from ..remote_command import RemoteCommand
from .. import file_cache

logger = sgtk.platform.get_logger(__name__)


class RemoteConfiguration(QtCore.QObject):
    """
    Object wrapping a remote pipeline configuration.

    Signal Interface
    ----------------

    :signal commands_loaded(commands): Gets emitted after :meth:`request_commands` has
        been called and once commands have been loaded for the configuration. The
        commands parameter contains a list of :class:`RemoteCommand` instances.

    """
    TASK_GROUP = "tk-framework-shotgunutils.external_config.RemoteConfiguration"

    commands_loaded = QtCore.Signal(list)  # list of RemoteCommand instances

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            pipeline_config_interpreter,
    ):
        """
        .. note:: This class is constructed by :class:`RemoteConfigurationLoader`.
            Do not construct objects by hand.

        :param parent: Qt parent object
        :param bg_task_manager: Background task runner instance
        :param str plugin_id: Associated bootstrap plugin id
        :param pipeline_config_interpreter: Path to the python interpreter
            associated with the config
        """
        super(RemoteConfiguration, self).__init__(parent)

        self._parent = parent
        self._plugin_id = plugin_id
        self._pipeline_config_interpreter = pipeline_config_interpreter

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        self._bg_task_manager = bg_task_manager
        self._bg_task_manager.task_completed.connect(self._task_completed)
        self._bg_task_manager.task_failed.connect(self._task_failed)

    @property
    def pipeline_configuration_id(self):
        """
        The associated pipeline configuration id or None if not defined.
        """
        return None

    @property
    def pipeline_configuration_name(self):
        """
        The name of the associated pipeline configuration or None if not defined.
        """
        return None

    @property
    def descriptor_uri(self):
        """
        The descriptor uri associated with this pipeline configuration. For
        configurations that have an associated pipeline configuration ids,
        this returns None.
        """
        return None

    @property
    def plugin_id(self):
        """
        The plugin id associated with the configuration.
        """
        return self._plugin_id

    @property
    def associated_python_interpreter(self):
        """
        The path to a python interpreter that should be used when
        executing commands.
        """
        return self._pipeline_config_interpreter

    def request_commands(self, engine, entity_type, entity_id, link_entity_type):
        """
        Request commands for the given object.

        A ``commands_loaded`` signal will be emitted once the commands are available.

        :param str engine: Engine to run
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where having different values it per linked type can be beneficial.
        """
        logger.debug("Requested commands for %s: %s %s %s" % (self, entity_type, entity_id, link_entity_type))

        # figure out if we have a suitable config for this on disk already
        cache_hash = self._compute_config_hash(engine, entity_type, entity_id, link_entity_type)
        cached_data = file_cache.load_cache(cache_hash)

        if cached_data:
            # got some cached data that we can emit
            self.commands_loaded.emit(
                [RemoteCommand.create(self, d) for d in cached_data]
            )

        else:
            # no cached version exists. Request a bg load
            cache_path = file_cache.get_cache_path(cache_hash)
            self._bg_task_manager.add_task(
                self._cache_commands,
                group=self.TASK_GROUP,
                task_kwargs={
                    "engine": engine,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "cache_path": cache_path,
                }
            )

    def _compute_config_hash(self, engine, entity_type, entity_id, link_entity_type):
        """
        Generates a hash to uniquely identify the configuration.
        Implemented by subclasses.

        :param str engine: Engine to run
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where caching it per linked type can be beneficial.
        :returns: dictionary of values to use for hash computation
        """
        raise NotImplementedError("_compute_config_hash is not implemented.")

    @sgtk.LogManager.log_timing
    def _cache_commands(self, engine, entity_type, entity_id, cache_path):
        """
        :param str engine: Engine to run
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str cache_path: Path where cache data should be written to
        """
        logger.debug("Begin caching commands")

        if os.path.exists(cache_path):
            # no need to cache
            return cache_path

        script = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "scripts",
                "cache_commands.py"
            )
        )

        args_file = self._get_arguments_file(
            dict(
                core_path=sgtk.bootstrap.ToolkitManager.get_core_python_path(),
                cache_path=cache_path,
                configuration_uri=self.descriptor_uri,
                pipeline_config_id=self.pipeline_configuration_id,
                plugin_id=self.plugin_id,
                engine_name=engine,
                entity_type=entity_type,
                entity_id=entity_id,
                bundle_cache_fallback_paths=self._bundle.engine.sgtk.bundle_cache_fallback_paths,
            )
        )

        args = [self._pipeline_config_interpreter, script, args_file]
        logger.debug("Command arguments: %s", args)

        retcode, stdout, stderr = ProcessRunner.call_cmd(args)

        if retcode == 0:
            logger.error("Command stdout: %s", stdout)
            logger.error("Command stderr: %s", stderr)
        else:
            logger.error("Command failed: %s", args)
            logger.error("Failed command stdout: %s", stdout)
            logger.error("Failed command stderr: %s", stderr)
            logger.error("Failed command retcode: %s", retcode)
            raise Exception("%s\n\n%s" % (stdout, stderr))

        logger.debug("Caching complete.")
        return cache_path

    def _task_completed(self, unique_id, group, result):
        """
        Called when a task completes
        """
        if group != self.TASK_GROUP:
            # not for us
            return

        logger.debug("Got configuration info!")
        # the return value from the process is the cache path
        cache_path = result
        cached_data = file_cache.load_cache_file(cache_path)

        if cached_data:
            # got some cached data.
            self.commands_loaded.emit(
                [RemoteCommand.create(self, d) for d in cached_data]
            )
        else:
            logger.error("TODO: handle this")

    def _task_failed(self, unique_id, group, message, traceback_str):
        """
        When a task fails
        @param unique_id:
        @param group:
        @param message:
        @param traceback_str:
        @return:
        """
        if group != self.TASK_GROUP:
            # not for us
            return

        logger.error("TASK FAILED %s %s " % (message, traceback_str))

    def _get_arguments_file(self, args_data):
        """
        Dumps out a temporary file containing the provided data structure.

        :param args_data: The data to serialize to disk.

        :returns: File path
        :rtype: str
        """
        args_file = tempfile.mkstemp()[1]

        with open(args_file, "wb") as fh:
            cPickle.dump(
                args_data,
                fh,
                cPickle.HIGHEST_PROTOCOL,
            )

        return args_file

