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
import hashlib
import json

from tank_vendor.shotgun_api3.lib import six

from sgtk.platform.qt import QtCore, QtGui

logger = sgtk.platform.get_logger(__name__)

shotgun_model = sgtk.platform.current_bundle().import_module("shotgun_model")
ShotgunModel = shotgun_model.ShotgunModel


class ConfigurationState(QtCore.QObject):
    """
    Represents the state in Shotgun which may affect
    configurations and ultimately registered commands.

    Looks at the following items:

    - The list of software entities
    - The list of Pipeline Configurations
    - The state of TK_BOOTSTRAP_CONFIG_OVERRIDE

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

        self._software_model = ConfigStateModel("Software", [], bg_task_manager, parent)

        # Determine the overall state of pipeline configurations
        # based on configs linked to active projects plus any
        # site configurations.
        self._pipeline_config_model = ConfigStateModel(
            "PipelineConfiguration",
            [
                {
                    "filter_operator": "any",
                    "filters": [
                        ["project.Project.archived", "is", False],
                        ["project", "is", None],
                    ],
                }
            ],
            bg_task_manager,
            parent,
        )

        self._software_model.data_refreshed.connect(self._on_software_refreshed)
        self._pipeline_config_model.data_refreshed.connect(
            self._on_pipeline_configs_refreshed
        )

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

    def get_software_hash(self):
        """
        Returns a hash representing the state of the
        software entity in Shotgun.

        :returns: Hash string or ``None`` if not yet defined.
        """
        return self._software_model.get_hash()

    def get_configuration_hash(self):
        """
        Returns a hash representing the global state of Shotgun.

        :returns: Hash string or ``None`` if not yet defined.
        """
        pc_hash = self._pipeline_config_model.get_hash()
        if pc_hash is None:
            return None
        # note: include the value of TK_BOOTSTRAP_CONFIG_OVERRIDE
        #       as this is a global 'switch' which overrides
        #       the pipeline configuration settings
        return "%s%s%s" % (
            self.get_software_hash(),
            pc_hash,
            os.environ.get("TK_BOOTSTRAP_CONFIG_OVERRIDE"),
        )

    def _on_software_refreshed(self, has_changed):
        """
        Software entity data has been retrieved

        :param bool has_changed: The cached data changed
        """
        if has_changed:
            logger.debug("ShotGrid software entity change detected.")
            self.state_changed.emit()

    def _on_pipeline_configs_refreshed(self, has_changed):
        """
        Pipeline Config entity data has been retrieved

        :param bool has_changed: The cached data changed
        """
        if has_changed:
            logger.debug("ShotGrid pipeline config change detected.")
            self.state_changed.emit()


class ConfigStateModel(ShotgunModel):
    """
    A ShotgunModel use to retrieve the state of a given entity.

    Holds *all* records for the given entity type (unless external
    filters have been provided) and exposes a hash representing
    the full state of the entity via the `get_hash()`
    method. Any change to the given entity type within the filter
    subset will be detected and will affect the hash.

    Internally, the hash is build based on the aggregate of updated_at
    values found for all records that the model tracks.
    """

    def __init__(self, entity_type, filters, bg_task_manager, parent):
        """
        :param bg_task_manager: Background task manager to use for any asynchronous work.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        :param parent: QT parent object.
        :type parent: :class:`~PySide.QtGui.QObject`
        """
        super(ConfigStateModel, self).__init__(
            parent, download_thumbs=False, bg_task_manager=bg_task_manager
        )
        self._entity_type = entity_type
        self._filters = filters

    def load_and_refresh(self):
        """
        Load cached data into the model and request a refresh.
        """
        # Clear the cache first. It's important that we not let the disk cache
        # get in the way of having an accurate state to test against.
        self.hard_refresh()

        hierarchy = ["id"]
        fields = ["updated_at", "id"]
        self._load_data(self._entity_type, self._filters, hierarchy, fields)
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
            # note: there *may* be a bug when deleting items out of a shotgun
            #       model in certain cases, so in order to ensure we
            #       get a correct representation, include entity_ids in the hash.

            hash_data = {"sg_data": self._get_sg_data(), "entity_ids": self.entity_ids}
            hash_data_str = json.dumps(hash_data, sort_keys=True)

            return hashlib.md5(six.ensure_binary(hash_data_str)).hexdigest()

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
