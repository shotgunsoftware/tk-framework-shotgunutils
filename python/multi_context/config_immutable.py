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
from sgtk.platform.qt import QtCore, QtGui
from . import file_cache
from .config_base import BaseConfiguration

logger = sgtk.platform.get_logger(__name__)


class ImmutableConfiguration(BaseConfiguration):
    """
    Class for loading and caching registered commands for a given
    """

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            project_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_interpreter,
            local_path,
    ):
        """
        :param parent:
        :param bg_task_manager:
        :param plugin_id:
        :param project_id:
        :param pipeline_config_id:
        :param pipeline_config_name:
        :param pipeline_config_uri:
        :param pipeline_config_interpreter:
        :param local_path:
        """
        super(ImmutableConfiguration, self).__init__(
            parent,
            bg_task_manager,
            plugin_id,
            project_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_interpreter,
            local_path,
        )

    def _compute_config_hash(self, engine, entity_type, entity_id, link_entity_type):
        """
        Returns a cache key
        """
        return {
            "config_id": self.id,
            "engine": engine,
            "uri": self.descriptor_uri,
            "type": entity_type,
            "link_type": link_entity_type,
        }


