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

logger = sgtk.platform.get_logger(__name__)

shotgun_model = sgtk.platform.current_bundle().import_module("shotgun_model")
ShotgunModel = shotgun_model.ShotgunModel


class ConfigurationState(QtCore.QObject):
    """
    Represents the state in Shotgun which may affect
    configurations and ultimately registered commands.

    Looks at software entities and Pipeline Configurations.

    As an example, changing a software entity may affect
    the list of registered commands.

    **Signals**

    :signal state_changed(): Indicates that the state has changed since
        it was last checked.

    """
    state_changed = QtCore.Signal()

    def __init__(self, bg_task_manager, parent):
        """
        Initialize the class with the following parameters:

        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        """
        super(ConfigurationState, self).__init__(parent)

        self._software_model = ConfigStateModel(
            "Software",
            [],
            bg_task_manager,
            parent
        )
        self._pipeline_config_model = ConfigStateModel(
            "PipelineConfiguration",
            [["project.Project.archived", "is", False]],
            bg_task_manager,
            parent
        )

        self._software_model.data_refreshed.connect(self._on_software_refreshed)
        self._pipeline_config_model.data_refreshed.connect(self._on_pipeline_configs_refreshed)

    def refresh(self):
        """
        Trigger an asynchronous background check of the Shotgun site
        configuration state. If a change is detected, indicating that
        configurations should be recomputed, a ``state_changed`` signal is emitted.
        """
        self._pipeline_config_model.load_and_refresh()
        self._software_model.load_and_refresh()

    def shut_down(self):
        """
        Shut down and deallocate.
        """
        self._software_model.destroy()
        self._pipeline_config_model.destroy()

    def get_hash(self):
        """
        Returns a hash representing the global state of Shotgun.

        :returns: Hash string or ``None`` if not yet defined.
        """
        sw_hash = self._software_model.get_hash()
        if sw_hash is None:
            return None
        pc_hash = self._pipeline_config_model.get_hash()
        if pc_hash is None:
            return None
        return "%s%s" % (sw_hash, pc_hash)

    def _on_software_refreshed(self, has_changed):
        """
        Software entity data has been retrieved

        :param bool has_changed: The cached data changed
        """
        if has_changed:
            logger.debug("Shotgun software entity change detected.")
            self.state_changed.emit()

    def _on_pipeline_configs_refreshed(self, has_changed):
        """
        Pipeline Config entity data has been retrieved

        :param bool has_changed: The cached data changed
        """
        if has_changed:
            logger.debug("Shotgun pipeline config change detected.")
            self.state_changed.emit()


class ConfigStateModel(ShotgunModel):
    """
    A ShotgunModel use to retrieve the state of a given entity.

    Maintains the most recent updated_at timestamp for a given query
    and allows this to be used as a way to detect if a change has
    happened to the given state.

    .. note:: This state model does not currently track deletion.
              If an object gets deleted, the model will not be able
              to indicate this.
    """

    def __init__(self, entity_type, filters, bg_task_manager, parent):
        """
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        """
        super(ConfigStateModel, self).__init__(
            parent,
            download_thumbs=False,
            bg_task_manager=bg_task_manager
        )
        self._entity_type = entity_type
        self._filters = filters

    def load_and_refresh(self):
        """
        Load cached data into the model and request a refresh.
        """
        hierarchy = ["id"]
        fields = ["updated_at"]
        self._load_data(
            self._entity_type,
            self._filters,
            hierarchy,
            fields,
            [{"field_name": "updated_at", "direction": "desc"}],
            limit=1
        )
        self._refresh_data()

    def get_hash(self):
        """
        Computes a hash representing the state of all entities.

        :returns: Hash int or None if nothing is loaded.
        """
        sg_data = self._get_sg_data()
        if sg_data is None:
            return None
        else:
            return hash(str(sg_data))

    def _get_sg_data(self):
        """
        Currently loaded Shotgun data.

        :returns: List of sg data dictionaries
            or ``None`` if not data is loaded.
        """
        if self.rowCount() == 0:
            data = None
        else:
            data = []
            for idx in range(self.rowCount()):
                item = self.item(idx)
                data.append(item.get_sg_data())

        return data


