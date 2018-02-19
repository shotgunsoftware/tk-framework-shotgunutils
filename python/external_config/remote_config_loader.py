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
from .errors import RemoteConfigNotAccessibleError, RemoteConfigParseError
from . import remote_config

logger = sgtk.platform.get_logger(__name__)


class RemoteConfigurationLoader(QtCore.QObject):
    """
    Class for loading configurations across contexts.

    **Signal Interface**

    :signal configurations_loaded(project_id, configs): Gets emitted configurations
        have been loaded for the given project. The parameters passed is the
        project id and a list of :class:`RemoteConfiguration` instances.

    :signal configurations_changed(): Gets emitted whenever the class
        has detected a change to the state of shotgun which could invalidate
        any existing :class:`RemoteConfiguration` instances. This can be
        emitted at startup or typically after :meth:`refresh` has been called.
        Any implementation which caches :class:`RemoteConfiguration` instances
        can use this signal to invalidate their caches.
    """

    # signal emitted to indicate that an update has been detected
    # to the pipeline configurations for a project
    configurations_loaded = QtCore.Signal(int, list)  # project_id, list of configs

    # signal to indicate that change to the configurations have been detected.
    configurations_changed = QtCore.Signal()

    TASK_GROUP = "tk-framework-shotgunutils.external_config.RemoteConfigurationLoader"

    def __init__(self, plugin_id, base_config, bg_task_manager, parent):
        """
        Initialize the class with the following parameters:

        :param plugin_id: Plugin id of the current environment
        :param base_config: base_config
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        """
        super(RemoteConfigurationLoader, self).__init__(parent)

        self._plugin_id = plugin_id
        self._base_config = base_config

        self._config_state = ConfigurationState(bg_task_manager, parent)
        self._config_state.state_changed.connect(self.configurations_changed.emit)
        # always trigger a check at startup
        self.refresh()

        self._bg_task_manager = bg_task_manager
        self._bg_task_manager.task_completed.connect(self._task_completed)
        self._bg_task_manager.task_failed.connect(self._task_failed)

    def __repr__(self):
        """
        String representation
        """
        return "<CommandHandler@%s" % self._plugin_id

    def shut_down(self):
        """
        Shut down and deallocate.
        """
        self._config_state.shut_down()

    def refresh(self):
        """
        Requests a refresh. If the State of Shotgun has changed in a way which
        may affect configurations, this will result in a ``configuration_changed``
        signal being emitted.

        Examples of state changes which may affect configurations are any changes
        to related pipeline configuration, but also indirect changes such as a
        change to the list of software entities, since these can implicitly affect
        the list of commands associated with a project or entity.
        """
        self._config_state.refresh()

    def request_configurations(self, project_id, force=False):
        """
        Requests a list of configuration objects for the given project.

        Emits a ``configurations_loaded`` signal when the configurations
        have been loaded.

        :param project_id: Project to request configurations for.
        :param force: If ``True``, force reload the configuration data.
            If ``False`` (default), use a cached representation. This
            cache is refreshed at startup and whenever :meth:`refresh`
            is called.
        """
        # load existing cache file if it exists
        config_cache_key = {
            "project": project_id,
            "plugin": self._plugin_id,
            "hash": self._config_state.get_hash()
        }

        config_data = file_cache.load_cache(config_cache_key)
        # attempt to load configurations
        config_data_emitted = False
        if config_data and not force:
            # got the data cached so emit is straight away
            try:
                config_objects = []
                for cfg in config_data["configurations"]:
                    remote_config.deserialize(self, self._bg_task_manager, cfg)

            except RemoteConfigParseError:
                # get rid of this configuration
                file_cache.delete_cache(config_cache_key)
                logger.debug("Detected and deleted out of date cache.")

            else:
                self.configurations_loaded.emit(project_id, config_objects)
                config_data_emitted = True

        if not config_data_emitted:
            # no cached version exists. Request a bg load
            self._bg_task_manager.add_task(
                self._execute_get_configurations,
                priority=1,
                group=self.TASK_GROUP,
                task_kwargs={
                    "project_id": project_id,
                    "hash": self._config_state.get_hash()
                }
            )

    def _execute_get_configurations(self, project_id, hash):
        """
        Background task to load configs.

        :param int project_id: Project id to load configs for.
        :param str hash: Hash representing the relevant global state of Shotgun.
        """
        # get list of configurations
        mgr = sgtk.bootstrap.ToolkitManager()
        mgr.plugin_id = self._plugin_id
        configs = mgr.get_pipeline_configurations({"type": "Project", "id": project_id})
        return (project_id, hash, configs)

    def _task_completed(self, unique_id, group, result):
        """
        Called after pipeline configuration enumeration completes.

        :param str unique_id: unique task id
        :param str group: task group
        :param str result: return data from worker
        """
        logger.debug("Got configuration info!")
        if group != self.TASK_GROUP:
            # not for us
            return

        (project_id, hash, config_dicts) = result

        # check that the configs are complete. If not, issue warnings
        config_objects = []
        for config_dict in config_dicts:
            try:
                config_object = remote_config.create_from_pipeline_configuration_data(
                    self,
                    self._bg_task_manager,
                    self._plugin_id,
                    config_dict
                )
                config_objects.append(config_object)
            except RemoteConfigNotAccessibleError, e:
                logger.warning(str(e))

        # if no custom pipeline configs were found, we use the default one
        if len(config_objects) == 0:
            config_objects.append(
                remote_config.create_default(
                    self,
                    self._bg_task_manager,
                    self._plugin_id,
                    self._base_config
                )
            )

        # create a dictionary we can serialize
        data = {
            "project_id": project_id,
            "plugin_id": self._plugin_id,
            "global_state_hash": hash,
            "configurations": [remote_config.serialize(cfg_obj) for cfg_obj in config_objects]
        }

        # save cache
        file_cache.write_cache(
            {"project": project_id, "plugin": self._plugin_id, "hash": hash},
            data
        )

        self.configurations_loaded.emit(project_id, config_objects)

    def _task_failed(self, unique_id, group, message, traceback_str):
        """
        Called after pipeline configuration enumeration fails.

        :param str unique_id: unique task id
        :param str group: task group
        :param message:
        :param traceback_str:
        """
        if group != self.TASK_GROUP:
            # not for us
            return

