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
import os

from tank_test.tank_test_base import *
from mock import patch, Mock
from sgtk.bootstrap import ToolkitManager

# import the test base class
test_python_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python"))
sys.path.append(test_python_path)
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

class TestExternalConfigLoader(TestShotgunUtilsFramework):
    """
    Tests for the external config loader.
    """
    def setUp(self):
        """
        Initial setup.
        """        
        super(TestExternalConfigLoader, self).setUp()

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

    def test_task_failed(self):
        """
        Make sure we properly report a failed config retrieval.
        """
        ec = self.external_config_loader
        ec.configurations_loaded = _MockedSignal()

        # If given a bogus task id it doesn't emit.
        ec._task_failed("9876", "test", "test failure", "test failure stack")
        ec.configurations_loaded.emit.assert_not_called()

        # If the given task id is legit, we'll see an emit.
        ec._task_ids["1234"] = self._project["id"]
        ec._task_failed("1234", "test", "ignore this", "ignore this")
        ec.configurations_loaded.emit.assert_called_once()

        # Make sure it was called with what we expected.
        project_id, configs = ec.configurations_loaded.emit.call_args[0]

        self.assertEqual(project_id, self._project["id"])
        self.assertEqual(configs, [])

    def test_task_completed(self):
        """
        Make sure the right signal is emitted with the correct data when
        configs are successfully retrieved from Shotgun.
        """
        ec = self.external_config_loader
        ec.configurations_loaded = _MockedSignal()
        ec._bootstrap_manager = ToolkitManager(self._mocked_sg_user)
        software_hash = "123"
        result = ec._execute_get_configurations(self._project["id"], software_hash)

        # If given a bogus task id it doesn't emit.
        ec._task_completed("9876", "test", [])
        ec.configurations_loaded.emit.assert_not_called()

        # If the task id is legit, then we should see an emit.
        ec._task_ids["1234"] = "test"
        ec._task_completed("1234", "test", result)
        ec.configurations_loaded.emit.assert_called_once()

        # Make sure it was called with what we expect.
        project_id, configs = ec.configurations_loaded.emit.call_args[0]

        self.assertEqual(project_id, (self._project["id"]))
        self.assertEqual(len(configs), 1)

        config = configs[0]

        self.assertTrue(isinstance(config, self.external_config.ExternalConfiguration))
        self.assertTrue(config.is_valid)
        self.assertEqual(config.plugin_id, self._plugin_id)
        self.assertEqual(config.engine_name, self._engine_name)
        self.assertTrue(config.is_primary)
        self.assertEqual(config.pipeline_configuration_id, self._pc["id"])
        self.assertEqual(config.descriptor_uri, self._descriptor)
        self.assertEqual(config.pipeline_configuration_name, "Primary")
        self.assertEqual(config.interpreter, sys.executable)

    def test_get_configs(self):
        """
        Make sure we get the right config data from Shotgun.
        """
        ec = self.external_config_loader
        ec._bootstrap_manager = ToolkitManager(self._mocked_sg_user)
        res_project_id, res_hash, res_pcs = ec._execute_get_configurations(self._project["id"], "123")

        self.assertEqual(res_project_id, self._project["id"])
        self.assertEqual(res_hash, "123")
        self.assertEqual(len(res_pcs), 1)
        self.assertEqual(res_pcs[0]["id"], self._pc["id"])

        
