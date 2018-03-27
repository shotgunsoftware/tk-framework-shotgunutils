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
from sgtk.platform.qt import QtCore, QtGui
from .configuration_state import ConfigurationState
from . import file_cache
from .errors import ExternalConfigNotAccessibleError, ExternalConfigParseError
from . import config

logger = sgtk.platform.get_logger(__name__)


class ExternalConfigurationLoader(QtCore.QObject):
    """
    Class for loading configurations across contexts.

    **Signal Interface**

    :signal configurations_loaded(project_id, configs): Gets emitted configurations
        have been loaded for the given project. The parameters passed is the
        project id and a list of :class:`ExternalConfiguration` instances.

    :signal configurations_changed(): Gets emitted whenever the class
        has detected a change to the state of shotgun which could invalidate
        any existing :class:`ExternalConfiguration` instances. This can be
        emitted at startup or typically after :meth:`refresh_shotgun_global_state`
        has been called. Any implementation which caches
        :class:`ExternalConfiguration` instances can use this signal to invalidate
        their caches.
    """

    # signal emitted to indicate that an update has been detected
    # to the pipeline configurations for a project
    configurations_loaded = QtCore.Signal(int, list)  # project_id, list of configs

    # signal to indicate that change to the configurations have been detected.
    configurations_changed = QtCore.Signal()

    # grouping used by the background task manager
    TASK_GROUP = "tk-framework-shotgunutils.external_config.ExternalConfigurationLoader"

    def __init__(self, interpreter, engine_name, plugin_id, base_config, bg_task_manager, parent):
        """
        Initialize the class with the following parameters:

        .. note:: The interpreter needs to support the VFX Platform, e.g be
            able to import ``PySide`` or ``Pyside2``.

        :param str interpreter: Path to Python interpreter to use.
        :param str engine_name: Engine to run.
        :param str plugin_id: Plugin id to use when executing external requests.
        :param str base_config: Default configuration URI to use if nothing else
            is provided via Shotgun overrides.
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        """
        super(ExternalConfigurationLoader, self).__init__(parent)

        self._task_ids = {}

        self._plugin_id = plugin_id
        self._base_config_uri = base_config
        self._engine_name = engine_name
        self._interpreter = interpreter

        self._config_state = ConfigurationState(bg_task_manager, parent)
        self._config_state.state_changed.connect(self.configurations_changed.emit)
        # always trigger a check at startup
        self.refresh_shotgun_global_state()

        self._bg_task_manager = bg_task_manager
        self._bg_task_manager.task_completed.connect(self._task_completed)
        self._bg_task_manager.task_failed.connect(self._task_failed)

    def __repr__(self):
        """
        String representation
        """
        return "<CommandHandler %s@%s>" % (self._engine_name, self._plugin_id)

    def shut_down(self):
        """
        Shut down and deallocate.
        """
        self._config_state.shut_down()

    def refresh_shotgun_global_state(self):
        """
        Requests an async refresh. If the State of Shotgun has
        changed in a way which may affect configurations, this will
        result in a ``configurations_changed`` signal being emitted.

        Examples of state changes which may affect configurations are any changes
        to related pipeline configuration, but also indirect changes such as a
        change to the list of software entities, since these can implicitly affect
        the list of commands associated with a project or entity.
        """
        self._config_state.refresh()

    @property
    def engine_name(self):
        """
        The name of the engine associated with this external configuration loader.
        """
        return self._engine_name

    @property
    def interpreter(self):
        """
        The Python interpreter to when bootstrapping and loading external configurations.
        """
        return self._interpreter

    @property
    def plugin_id(self):
        """
        The plugin id which will be used when executing external requests.
        """
        return self._plugin_id

    @property
    def base_config_uri(self):
        """
        Cnfiguration URI string to be used when nothing is provided via Shotgun overrides.
        """
        return self._base_config_uri

    def request_configurations(self, project_id):
        """
        Requests a list of configuration objects for the given project.

        Emits a ``configurations_loaded`` signal when the configurations
        have been loaded.

        .. note:: If this method is called multiple times in quick succession, only
                  a single ``configurations_loaded`` signal will be emitted, belonging
                  to the last request.

        :param project_id: Project to request configurations for.
        """
        # First of all, remove any existing requests for this project from
        # our internal task tracker. This will ensure that only one signal
        # is emitted even if this method is called multiple times
        # in rapid succession.
        #
        for (task_id, task_project_id) in self._task_ids.iteritems():
            if task_project_id == project_id:
                logger.debug(
                    "Discarding existing request_configurations request for project %s" % project_id
                )
                del self._task_ids[task_id]

        # load existing cache file if it exists
        config_cache_key = {
            "project": project_id,
            "plugin": self._plugin_id,
            "base_config": self._base_config_uri,
            "state_hash": self._config_state.get_hash()
        }

        config_data = file_cache.load_cache(config_cache_key)
        # attempt to load configurations
        config_data_emitted = False
        if config_data:
            # got the data cached so emit it straight away
            try:
                config_objects = []
                for cfg in config_data["configurations"]:
                    config_objects.append(
                        config.deserialize(self, self._bg_task_manager, cfg)
                    )

            except ExternalConfigParseError:
                # get rid of this configuration
                file_cache.delete_cache(config_cache_key)
                logger.debug("Detected and deleted out of date cache.")

            else:
                self.configurations_loaded.emit(project_id, config_objects)
                config_data_emitted = True

        if not config_data_emitted:
            # Request a bg load
            unique_id = self._bg_task_manager.add_task(
                self._execute_get_configurations,
                priority=1,
                group=self.TASK_GROUP,
                task_kwargs={
                    "project_id": project_id,
                    "state_hash": self._config_state.get_hash()
                }
            )

            self._task_ids[unique_id] = project_id

    def _execute_get_configurations(self, project_id, state_hash):
        """
        Background task to load configs using the ToolkitManager.

        :param int project_id: Project id to load configs for.
        :param str state_hash: Hash representing the relevant
            global state of Shotgun.
        :returns: Tuple with (project id, state hash, list of configs), where
            the two first items are the input parameters to this method
            and the last item is the return data from
            ToolkitManager.get_pipeline_configurations()
        """
        # get list of configurations
        mgr = sgtk.bootstrap.ToolkitManager()
        mgr.plugin_id = self._plugin_id
        configs = mgr.get_pipeline_configurations({"type": "Project", "id": project_id})
        return (project_id, state_hash, configs)

    def _task_completed(self, unique_id, group, result):
        """
        Called after pipeline configuration enumeration completes.

        :param str unique_id: unique task id
        :param str group: task group
        :param str result: return data from worker
        """
        if unique_id not in self._task_ids:
            return

        del self._task_ids[unique_id]

        logger.debug("Got configuration info!")
        (project_id, state_hash, config_dicts) = result

        # check that the configs are complete. If not, issue warnings
        config_objects = []
        for config_dict in config_dicts:
            try:
                config_object = config.create_from_pipeline_configuration_data(
                    parent=self,
                    bg_task_manager=self._bg_task_manager,
                    config_loader=self,
                    configuration_data=config_dict
                )
                config_objects.append(config_object)
            except ExternalConfigNotAccessibleError as e:
                logger.warning("%s Configuration will not be loaded." % e)

        # if no custom pipeline configs were found, we use the base config
        # note: because the base config can change over time, we make sure
        # to include it as an ingredient in the hash key below.
        if len(config_dicts) == 0:
            config_objects.append(
                config.create_fallback_configuration(
                    self,
                    self._bg_task_manager,
                    self
                )
            )

        # create a dictionary we can serialize
        data = {
            "project_id": project_id,
            "plugin_id": self._plugin_id,
            "global_state_hash": state_hash,
            "configurations": [
                config.serialize(cfg_obj) for cfg_obj in config_objects
                ]
        }

        # save cache
        file_cache.write_cache(
            {
                "project": project_id,
                "plugin": self._plugin_id,
                "base_config": self._base_config_uri,
                "state_hash": state_hash
            },
            data
        )

        logger.debug("Got configuration objects for project %d: %s" % (project_id, config_objects))

        self.configurations_loaded.emit(project_id, config_objects)

    def _task_failed(self, unique_id, group, message, traceback_str):
        """
        Called after pipeline configuration enumeration fails.

        :param str unique_id: unique task id
        :param str group: task group
        :param str message: Error message
        :param str traceback_str: Full traceback
        """
        if unique_id not in self._task_ids:
            return

        project_id = self._task_ids[unique_id]
        del self._task_ids[unique_id]

        logger.error("Could not determine project configurations: %s" % message)

        # emit an empty list of configurations
        self.configurations_loaded.emit(project_id, [])
