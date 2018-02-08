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
from sgtk.platform.qt import QtCore, QtGui

logger = sgtk.platform.get_logger(__name__)

shotgun_model = sgtk.platform.current_bundle().import_module("shotgun_model")
ShotgunModel = shotgun_model.ShotgunModel


class ConfigurationState(QtCore.QObject):
    """
    Represents the state in Shotgun which may affect
    configurations and ultimately registered commands.

    Looks at software entities and Pipeline Configurations.

    Calling refresh will check for changes and if changes have
    happened, the state_changed signal will be emitted.
    """
    state_changed = QtCore.Signal()

    def __init__(self, bg_task_manager, parent=None):
        """
        @param bg_task_manager:
        @param parent:
        """
        super(ConfigurationState, self).__init__(parent)
        self._software_model = SoftwareModel(bg_task_manager, parent)
        self._software_model.data_refreshed.connect(self._on_software_refreshed)

        self._pipeline_config_model = SoftwareModel(bg_task_manager, parent)
        self._pipeline_config_model.data_refreshed.connect(self._on_pipeline_configs_refreshed)

    def refresh(self):
        self._pipeline_config_model.load()
        self._software_model.load()

    def shut_down(self):
        """
        turn stuff off
        """
        self._software_model.destroy()
        self._pipeline_config_model.destroy()

    def get_hash(self):
        """
        Returns a hash representing the global state of Shotgun or None if not yet defined.
        """
        return str(self._software_model.get_hash()) + str(self._pipeline_config_model.get_hash())

    def _on_software_refreshed(self, has_changed):
        """
        Software entity model is updated
        :param has_changed:
        """
        logger.error("SW HAS CHANGED: %s" % has_changed)
        if has_changed:
            logger.debug("Shotgun software entity change detected.")
            self.state_changed.emit()

    def _on_pipeline_configs_refreshed(self, has_changed):
        """
        Software entity model is updated
        :param has_changed:
        """
        logger.error("PC HAS CHANGED: %s" % has_changed)
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
        Load all pipeline configuration data into model.
        """
        app = sgtk.platform.current_bundle()
        hierarchy = ["id"]
        fields = ["code", "updated_at"]
        self._load_data("Software", [], hierarchy, fields)
        self._refresh_data()

    def get_sg_data(self):
        """
        Access current user shotgun data.

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

    def get_hash(self):
        """
        Returns a hash representing the state of all sw entities
        or None if nothing is loaded
        """
        sg_data = self.get_sg_data()
        if sg_data is None:
            return None
        else:
            return hash(str(sg_data))


class PipelineConfigModel(ShotgunModel):
    """
    All Pipeline Configurations
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
        Load all pipeline configuration data into model.
        """
        app = sgtk.platform.current_bundle()
        hierarchy = ["id"]
        fields = ["code", "updated_at"]
        self._load_data("PipelineConfiguration", [], hierarchy, fields)
        self._refresh_data()

    def get_sg_data(self):
        """
        Access current user shotgun data.

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

    def get_hash(self):
        """
        Returns a hash representing the state of all sw entities
        or None if nothing is loaded
        """
        sg_data = self.get_sg_data()
        if sg_data is None:
            return None
        else:
            return hash(str(sg_data))

