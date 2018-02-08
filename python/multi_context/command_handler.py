# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


import sgtk
import sys
import os
from sgtk.platform.qt import QtCore, QtGui

logger = sgtk.platform.get_logger(__name__)

from .shotgun_state import ConfigurationState
from .config_immutable import ImmutableConfiguration
from .config_live import LiveConfiguration

from . import file_cache


class CommandHandler(QtCore.QObject):
    """
    class for handling multiple commands across contexts.
    """

    # signal emitted to indicate that an update has been detected
    # to the pipeline configurations for a project
    configurations_loaded = QtCore.Signal(int, list)  # project_id, list of configs

    # signal to indicate that change to the configurations have been detected.
    configurations_changed = QtCore.Signal()

    TASK_GROUP = "tk-framework-shotgunutils.multi_context.config_resolve"

    def __init__(self, plugin_id, bg_task_manager, parent=None):
        """
        """
        super(CommandHandler, self).__init__(parent)

        self._plugin_id = plugin_id

        self._config_state = ConfigurationState(bg_task_manager, parent)
        self._config_state.state_changed.connect(self.configurations_changed.emit)
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
        turn stuff off
        """
        self._config_state.shut_down()

    def refresh(self):
        """
        Requests a refresh. If things have changed, this may result in a
        configuration_changed being emitted.
        @return:
        """
        self._config_state.refresh()

    def request_configurations(self, project_id, force=False):
        """
        Requests a list of configuration objects for the given project.
        a configuration_changed signal will be emitted with the result.
        """
        # load existing cache file if it exists
        config_data = file_cache.load_cache(
            {
                "project": project_id,
                "plugin": self._plugin_id,
                "hash": self._config_state.get_hash()
            }
        )
        if config_data and not force:
            # got the data cached so emit is straight away
            config_objects = [self._create_configuration_object(project_id, c) for c in config_data["configurations"]]

            self.configurations_loaded.emit(
                project_id,
                config_objects
            )

        else:
            # no cached version exists. Request a bg load
            self._bg_task_manager.add_task(
                self._execute_get_configurations,
                group=self.TASK_GROUP,
                task_kwargs={
                    "project_id": project_id,
                    "hash": self._config_state.get_hash()
                }
            )

    def _execute_get_configurations(self, project_id, hash):
        """
        Background task to load configs
        """
        # get list of configurations
        mgr = sgtk.bootstrap.ToolkitManager()
        mgr.plugin_id = self._plugin_id
        configs = mgr.get_pipeline_configurations({"type": "Project", "id": project_id})
        return (project_id, hash, configs)

    def _task_completed(self, unique_id, group, result):
        """
        When a task completes
        """
        logger.debug("Got configuration info!")
        if group != self.TASK_GROUP:
            # not for us
            return

        (project_id, hash, configs) = result

        # set of a dictionary we can serialize
        data = {
            "project_id": project_id,
            "plugin_id": self._plugin_id,
            "global_state_hash": hash,
            "configurations": []
        }

        for config in configs:

            data["configurations"].append(
                {
                    "id": config["id"],
                    "name": config["name"],
                    "uri": config["descriptor"].get_uri(),
                    "immutable": config["descriptor"].is_immutable(),
                    "interpreter": self._get_python_interpreter(config["descriptor"]),
                    "location": config["descriptor"]._get_config_folder()
                }
            )

        # save cache
        file_cache.save_cache(
            {"project": project_id, "plugin": self._plugin_id, "hash": hash},
            data
        )

        config_objects = [self._create_configuration_object(project_id, c) for c in data["configurations"]]
        self.configurations_loaded.emit(project_id, config_objects)

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

    def _create_configuration_object(self, project_id, configuration_data):

        if configuration_data["immutable"]:
            config_class = ImmutableConfiguration
        else:
            config_class = LiveConfiguration

        return config_class(
            self.parent(),
            self._bg_task_manager,
            self._plugin_id,
            project_id,
            configuration_data["id"],
            configuration_data["name"],
            configuration_data["uri"],
            configuration_data["interpreter"],
            configuration_data["location"]
        )

    def _get_python_interpreter(self, descriptor):
        """
        Retrieves the python interpreter from the configuration. Returns the
        current python interpreter if no interpreter was specified.
        """
        try:
            path_to_python = descriptor.python_interpreter
        except sgtk.TankFileDoesNotExistError:
            # note - for configurations not declaring this,
            # a perfectly valid thing to do - we just use the
            # default one
            if sys.platform == "darwin":
                path_to_python = os.path.join(sys.prefix, "bin", "python")
            elif sys.platform == "win32":
                path_to_python = os.path.join(sys.prefix, "python.exe")
            else:
                path_to_python = os.path.join(sys.prefix, "bin", "python")
        return path_to_python
