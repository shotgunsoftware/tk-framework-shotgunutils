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

    Signal Interface
    ----------------

    :signal state_changed(): Indicates that the state has changed since
        it was last checked.

    """
    state_changed = QtCore.Signal()

    def __init__(self, bg_task_manager, parent):
        """
        :param bg_task_manager: Background task manager to use for any asynchronous work. If
            this is None then a task manager will be created as needed.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`
        """
        super(ConfigurationState, self).__init__(parent)
        self._software_model = SoftwareModel(bg_task_manager, parent)
        self._software_model.data_refreshed.connect(self._on_software_refreshed)

        self._pipeline_config_model = PipelineConfigModel(bg_task_manager, parent)
        self._pipeline_config_model.data_refreshed.connect(self._on_pipeline_configs_refreshed)

    def refresh(self):
        """
        Trigger an asynchronous background check of the Shotgun site
        configuration state. If a change is detected, indicating that
        configurations should be recomputed, a ``state_changed`` signal is emitted.
        """
        self._pipeline_config_model.load()
        self._software_model.load()

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
        pc_hash = self._pipeline_config_model.get_hash()
        if sw_hash is None or pc_hash is None:
            return None
        return str(sw_hash) + str(pc_hash)

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


class SoftwareModel(ShotgunModel):
    """
    All software entities
    """
    def __init__(self, bg_task_manager, parent):
        """
        :param parent: QT parent object
        """
        super(SoftwareModel, self).__init__(
            parent,
            download_thumbs=False,
            bg_task_manager=bg_task_manager
        )

    def load(self):
        """
        Load all data into model.
        """
        hierarchy = ["id"]
        fields = ["code", "updated_at"]
        self._load_data("Software", [], hierarchy, fields)
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

        :returns: The sg data dictionary for the associated item,
                  None if not available.
        """
        if self.rowCount() == 0:
            data = None
        else:
            data = []
            for idx in range(self.rowCount()):
                item = self.item(idx)
                data.append(item.get_sg_data())

        return data


class PipelineConfigModel(ShotgunModel):
    """
    Pipeline configurations for all active projects.
    """
    def __init__(self, bg_task_manager, parent):
        """
        :param parent: QT parent object
        """
        super(PipelineConfigModel, self).__init__(
            parent,
            download_thumbs=False,
            bg_task_manager=bg_task_manager
        )

    def load(self):
        """
        Load all data into model.
        """
        hierarchy = ["id"]
        fields = ["code", "updated_at"]
        self._load_data(
            "PipelineConfiguration",
            [["project.Project.archived", "is", False]],
            hierarchy,
            fields
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

        :returns: The sg data dictionary for the associated item,
                  None if not available.
        """
        if self.rowCount() == 0:
            data = None
        else:
            data = []
            for idx in range(self.rowCount()):
                item = self.item(idx)
                data.append(item.get_sg_data())

        return data
