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

from sgtk.bootstrap import ToolkitManager
from . import ExternalConfigBase, _MockedSignal
from tank_test.tank_test_base import setUpModule  # noqa


class TestExternalConfigLoader(ExternalConfigBase):
    """
    Tests for the external config loader.
    """

    def setUp(self):
        """
        Initial setup.
        """
        super(TestExternalConfigLoader, self).setUp()

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
        software_hash = "123"
        result = ec._execute_get_configurations(
            self._project["id"],
            software_hash,
            toolkit_manager=ToolkitManager(self._mocked_sg_user),
        )

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
        res_project_id, res_hash, res_pcs = ec._execute_get_configurations(
            self._project["id"],
            "123",
            toolkit_manager=ToolkitManager(self._mocked_sg_user),
        )

        self.assertEqual(res_project_id, self._project["id"])
        self.assertEqual(res_hash, "123")
        self.assertEqual(len(res_pcs), 1)
        self.assertEqual(res_pcs[0]["id"], self._pc["id"])

    def test_request_configurations_twice(self):
        """
        Make sure requesting the same configuration twice only register it once.
        """
        ec = self.external_config_loader

        ec.configurations_loaded = _MockedSignal()
        ec.configurations_loaded.emit.assert_not_called()
        self.bg_task_manager.add_task.reset_mock()

        ec.request_configurations(self._project["id"])
        self.assertEqual(len(ec._task_ids.items()), 1)
        self.bg_task_manager.add_task.assert_called_once()
        self.bg_task_manager.add_task.reset_mock()

        ec.request_configurations(self._project["id"])
        self.assertEqual(len(ec._task_ids.items()), 1)  # No duplicate of task ids
        self.bg_task_manager.add_task.assert_called_once()
