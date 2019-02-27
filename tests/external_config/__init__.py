# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sys

from mock import Mock
from base_test import TestShotgunUtilsFramework


class _MockedShotgunUser(object):
    """
    A fake shotgun user object that we can pass to the manager.
    """
    def __init__(self, mockgun, login):
        self._mockgun = mockgun
        self._login = login

    @property
    def login(self):
        """
        Current User Login.
        """
        return self._login

    def create_sg_connection(self):
        """
        Returns the associated mockgun connection.
        """
        return self._mockgun


class _MockedSignal(object):
    """
    A fake Qt signal object with mocked emit and connect methods.
    """
    def __init__(self, *args, **kwargs):
        self.emit = Mock()
        self.connect = Mock()


class ExternalConfigBase(TestShotgunUtilsFramework):
    """
    Tests for the external config loader.
    """
    def setUp(self):
        """
        Initial setup.
        """
        super(ExternalConfigBase, self).setUp()

        self._john_doe = self.mockgun.create("HumanUser", {"login": "john.doe"})
        self._project = self.mockgun.create("Project", {"name": "my_project"})
        self._mocked_sg_user = _MockedShotgunUser(self.mockgun, "john.doe")
        self._descriptor = "sgtk:descriptor:app_store?name=tk-config-basic&version=v1.2.3"
        self._pc = self.mockgun.create(
            "PipelineConfiguration",
            dict(
                code="Primary",
                project=self._project,
                users=[],
                windows_path=None,
                mac_path=None,
                linux_path=None,
                plugin_ids="basic.*",
                descriptor=self._descriptor,
                uploaded_config=None,
            )
        )

        self.external_config = self.framework.import_module("external_config")

        self.bg_task_manager = Mock()
        self.bg_task_manager.task_completed = _MockedSignal()

        self._engine_name = "test_engine"
        self._plugin_id = "basic.test"

        self.external_config_loader = self.external_config.ExternalConfigurationLoader(
            sys.executable,
            self._engine_name,
            self._plugin_id,
            self._descriptor,
            self.bg_task_manager,
            None,
        )