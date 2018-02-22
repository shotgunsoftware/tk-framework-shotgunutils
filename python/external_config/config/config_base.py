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
import sgtk
from sgtk.platform.qt import QtCore, QtGui
from sgtk.util.process import subprocess_check_output, SubprocessCalledProcessError
from ..external_command import ExternalCommand
from ..util import create_parameter_file
from .. import file_cache

logger = sgtk.platform.get_logger(__name__)


class ExternalConfiguration(QtCore.QObject):
    """
    Object wrapping an external pipeline configuration.

    **Signals**

    :signal commands_loaded(project_id, config, commands): Gets emitted after :meth:`request_commands` has
        been called and once commands have been loaded for the configuration. The
        commands parameter contains a list of :class:`ExternalCommand` instances.

    """

    # grouping used by the background task manager
    TASK_GROUP = "tk-framework-shotgunutils.external_config.ExternalConfiguration"

    commands_loaded = QtCore.Signal(int, object, list)
    # signal parameters:
    # 1. project_id
    # 2. configuration instance
    # 3. configuration object, list of :class:`ExternalCommand` instances

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            engine_name,
            interpreter,
    ):
        """
        .. note:: This class is constructed by :class:`ExternalConfigurationLoader`.
            Do not construct objects by hand.

        Constructor parameters:

        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param str plugin_id: Associated bootstrap plugin id
        :param str engine_name: Associated engine name
        :param str interpreter: Associated Python interpreter
        """
        super(ExternalConfiguration, self).__init__(parent)

        self._plugin_id = plugin_id
        self._engine_name = engine_name
        self._interpreter = interpreter

        self._task_ids = {}

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        self._bg_task_manager = bg_task_manager
        self._bg_task_manager.task_completed.connect(self._task_completed)
        self._bg_task_manager.task_failed.connect(self._task_failed)

    @property
    def plugin_id(self):
        """
        The plugin id associated with the configuration.
        """
        return self._plugin_id

    @property
    def engine_name(self):
        """
        The engine name associated with the configuration.
        """
        return self._engine_name

    @property
    def interpreter(self):
        """
        The Python interpreter to use when accessing this configuration
        """
        return self._interpreter

    @property
    def is_primary(self):
        """
        Returns ``True`` if this is the primary configuration, ``False`` if not.
        """
        if self.pipeline_configuration_name is None or self.pipeline_configuration_name == "Primary":
            # all fallback configs are primary
            return True
        else:
            return False

    @property
    def pipeline_configuration_id(self):
        """
        The associated pipeline configuration id or ``None`` if not defined.
        """
        # note: subclassed implementations will override this return value
        return None

    @property
    def pipeline_configuration_name(self):
        """
        The name of the associated pipeline configuration or ``None`` if not defined.
        """
        # note: subclassed implementations will override this return value
        return None

    @property
    def descriptor_uri(self):
        """
        The descriptor URI associated with this pipeline configuration. For
        configurations that have an associated :meth:`pipeline_configuration_id`,
        this returns ``None``.
        """
        # note: subclassed implementations will override this return value
        return None

    def request_commands(self, project_id, entity_type, entity_id, link_entity_type):
        """
        Request commands for the given shotgun entity.

        A ``commands_loaded`` signal will be emitted once the commands are available.

        :param int project_id: Associated project id
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where having different values it per linked type can be beneficial.
        """
        logger.debug("Requested commands for %s: %s %s %s" % (self, entity_type, entity_id, link_entity_type))

        # run entire command check and generation in worker
        task_id = self._bg_task_manager.add_task(
            self._request_commands,
            group=self.TASK_GROUP,
            task_kwargs={
                "project_id": project_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "link_entity_type": link_entity_type,
            }
        )
        self._task_ids[task_id] = (project_id, entity_type, entity_id)

    def _compute_config_hash_keys(self, entity_type, entity_id, link_entity_type):
        """
        Generates a hash to uniquely identify the configuration.

        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where caching it per linked type can be beneficial.
        :returns: dictionary of values to use for hash computation
        """
        # This needs to be implemented by subclasses.
        raise NotImplementedError("_compute_config_hash_keys is not implemented.")

    @sgtk.LogManager.log_timing
    def _request_commands(self, project_id, entity_type, entity_id, link_entity_type):
        """
        Execution, runs in a separate thread and launches an external
        process to cache commands.

        :param int project_id: Associated project id
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str link_entity_type: Entity type that the item is linked to.
            This is typically provided for things such as task, versions or notes,
            where caching it per linked type can be beneficial.
        """
        # figure out if we have a suitable config for this on disk already
        cache_hash = self._compute_config_hash_keys(
            entity_type,
            entity_id,
            link_entity_type
        )
        cache_path = file_cache.get_cache_path(cache_hash)
        cached_data = file_cache.load_cache(cache_hash)

        if not cached_data:
            logger.debug("Begin caching commands")

            # launch external process to carry out caching.
            script = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "scripts",
                    "external_runner.py"
                )
            )

            args_file = create_parameter_file(
                dict(
                    action="cache_actions",
                    cache_path=cache_path,
                    configuration_uri=self.descriptor_uri,
                    pipeline_config_id=self.pipeline_configuration_id,
                    plugin_id=self.plugin_id,
                    engine_name=self.engine_name,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    bundle_cache_fallback_paths=self._bundle.engine.sgtk.bundle_cache_fallback_paths,
                )
            )

            args = [
                self.interpreter,
                script,
                sgtk.bootstrap.ToolkitManager.get_core_python_path(),
                args_file
            ]
            logger.debug("Launching external script: %s", args)

            try:
                subprocess_check_output(args)
            except SubprocessCalledProcessError as e:
                # caching failed!
                raise RuntimeError("Error retrieving actions: %s" % e.output)
            finally:
                # clean up temp file
                sgtk.util.filesystem.safe_delete_file(args_file)

            logger.debug("Caching complete.")

            # now try again
            cached_data = file_cache.load_cache(cache_hash)

            if cached_data is None:
                raise RuntimeError("Could not locate cached commands for %s" % self)

        return cached_data


    def _task_completed(self, unique_id, group, result):
        """
        Called after command caching completes.

        :param str unique_id: unique task id
        :param str group: task group
        :param str result: return data from worker
        """
        if unique_id not in self._task_ids:
            # this was not for us
            return

        (project_id, entity_type, entity_id) = self._task_ids[unique_id]

        del self._task_ids[unique_id]

        # result contains our cached data
        cached_data = result

        # got some cached data that we can emit
        self.commands_loaded.emit(
            project_id,
            self,
            [ExternalCommand.create(self, d, entity_id) for d in cached_data]
        )


    def _task_failed(self, unique_id, group, message, traceback_str):
        """
        Called if command caching fails.

        :param str unique_id: unique task id
        :param str group: task group
        :param message: error message
        :param traceback_str: callstack
        """
        if unique_id not in self._task_ids:
            # this was not for us
            return

        (project_id, _, _) = self._task_ids[unique_id]

        del self._task_ids[unique_id]

        # log exception message to error log
        logger.error(message)

        # emit an empty list of commands
        self.commands_loaded.emit(project_id, self, [])

