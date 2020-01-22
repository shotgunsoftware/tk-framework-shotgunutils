# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from mock import Mock, patch

from tank_test.tank_test_base import setUpModule  # noqa
from base_test import TestShotgunUtilsFramework


class TestHierarchyModel(TestShotgunUtilsFramework):
    """
    Tests for ShotgunHierarchyModel
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestHierarchyModel, self).setUp()

        # We need a background task manager so the model can fetch data in the background.
        self._bg_task_manager = self.framework.import_module(
            "task_manager"
        ).BackgroundTaskManager(self._qapp, start_processing=True)
        self.addCleanup(
            lambda: self._bg_task_manager.shut_down() or self._qapp.processEvents()
        )

        self.shotgun_model = self.framework.import_module("shotgun_model")

        patcher = patch.object(
            self.mockgun, "server_caps", Mock(version=(8, 0, 0)), create=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch.object(self.mockgun, "nav_expand", create=True, return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ensure_path_can_compute(self):
        """
        Test loading and saving
        """
        model = self.shotgun_model.ShotgunHierarchyModel(
            None, bg_task_manager=self._bg_task_manager
        )
        model._load_data(
            "Version.entity", None, {"Asset": ["code", "status_list"]}, "seed"
        )
