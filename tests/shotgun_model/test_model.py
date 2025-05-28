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

from unittest.mock import Mock, patch

from tank_test.tank_test_base import setUpModule  # noqa
from base_test import TestShotgunUtilsFramework


class TestModel(TestShotgunUtilsFramework):
    """
    Tests for ShotgunModel
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super().setUp()

        # We need a background task manager so the model can fetch data in the background.
        self._bg_task_manager = self.framework.import_module(
            "task_manager"
        ).BackgroundTaskManager(self._qapp, start_processing=True)
        self.addCleanup(
            lambda: self._bg_task_manager.shut_down() or self._qapp.processEvents()
        )

        self.shotgun_model = self.framework.import_module("shotgun_model")

    def test_update_and_check_row(self):
        # Create a ShotgunModel instance
        model = self.shotgun_model.ShotgunModel(
            None, bg_task_manager=self._bg_task_manager
        )
        model._load_data(
            entity_type="Asset",
            filters=None,
            hierarchy=["code"],
            fields=["code", "sg_asset_type", "sg_status_list"],
            columns=["code", "sg_asset_type", "sg_status_list"],
        )

        # Simulate `model.__on_sg_data_arrived` when data is first loaded
        diff = model._data_handler.update_data(
            [
                {
                    "code": "asset1",
                    "id": 1,
                    "sg_asset_type": "Matte Painting",
                    "sg_status_list": "wtg",
                    "type": "Asset",
                }
            ]
        )
        root = model.invisibleRootItem()
        model._data_handler.generate_child_nodes(None, root, model._create_item)

        self.assertEqual(1, model.rowCount())
        self.assertEqual("asset1", model.item(0, 0).text())
        self.assertEqual("asset1", model.item(0, 1).text())
        self.assertEqual("Matte Painting", model.item(0, 2).text())
        self.assertEqual("wtg", model.item(0, 3).text())

        # Simulate `model._refresh_data` | fetch data from the server and update the model
        diff = model._data_handler.update_data(
            [
                {
                    "code": "asset1-renamed",  # Renamed asset
                    "id": 1,
                    "sg_asset_type": "Matte Painting",
                    "sg_status_list": "fin",  # Status changed to 'fin'
                    "type": "Asset",
                }
            ]
        )
        for item in diff:
            data_item = item["data"]
            model_item = model._get_item_by_unique_id(data_item.unique_id)
            self.assertTrue(model_item is not None, "Item should exist in the model")

            model._update_item(model_item, data_item)

            # Check that only the first item was updated
            self.assertEqual("asset1-renamed", model.item(0, 0).text())
            self.assertEqual("asset1", model.item(0, 1).text())
            self.assertEqual("wtg", model.item(0, 3).text())

            model._update_item_columns(model_item, data_item)

        # Check that the columns were updated
        self.assertEqual("asset1-renamed", model.item(0, 0).text())
        self.assertEqual("asset1-renamed", model.item(0, 1).text())
        self.assertEqual("fin", model.item(0, 3).text())
