# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from . import ExternalConfigBase
from tank_test.tank_test_base import setUpModule  # noqa


class TestConfigurationState(ExternalConfigBase):
    """
    Tests for the external config loader.
    """

    def item_factory(self, sg_data):
        item = self.shotgun_model.shotgun_standard_item.ShotgunStandardItem()
        item.setData(
            sg_data,
            self.shotgun_model.shotgun_query_model.ShotgunQueryModel.SG_DATA_ROLE,
        )
        return item

    def test_config_state_none_hash(self):
        foo = self.external_config.configuration_state.ConfigStateModel(
            "Dummy", [], self.bg_task_manager, None
        )
        bar = self.external_config.configuration_state.ConfigStateModel(
            "Dummy", [], self.bg_task_manager, None
        )

        self.assertEqual(foo.get_hash(), None)
        self.assertEqual(bar.get_hash(), None)
        self.assertEqual(foo.get_hash(), bar.get_hash())

    def test_config_state_similar_item_hash(self):
        foo = self.external_config.configuration_state.ConfigStateModel(
            "Dummy", [], self.bg_task_manager, None
        )
        bar = self.external_config.configuration_state.ConfigStateModel(
            "Dummy", [], self.bg_task_manager, None
        )

        foo.appendRow(self.item_factory("1"))
        bar.appendRow(self.item_factory("1"))

        self.assertNotEqual(foo.get_hash(), None)
        self.assertNotEqual(bar.get_hash(), None)
        self.assertEqual(foo.get_hash(), bar.get_hash())

    def test_config_state_different_item_hash(self):
        foo = self.external_config.configuration_state.ConfigStateModel(
            "Dummy", [], self.bg_task_manager, None
        )
        bar = self.external_config.configuration_state.ConfigStateModel(
            "Dummy", [], self.bg_task_manager, None
        )

        foo.appendRow(self.item_factory("1"))
        bar.appendRow(self.item_factory("2"))

        self.assertNotEqual(foo.get_hash(), None)
        self.assertNotEqual(bar.get_hash(), None)
        self.assertNotEqual(foo.get_hash(), bar.get_hash())
