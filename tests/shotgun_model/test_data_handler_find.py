# Copyright (c) 2016 Shotgun Software Inc.
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

from mock import patch, Mock, call
from tank_test.tank_test_base import *

# import the test base class
test_python_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "python")
)
sys.path.append(test_python_path)
from base_test import TestShotgunUtilsFramework


class TestShotgunFindDataHandler(TestShotgunUtilsFramework):
    """
    Tests for the data handler low level io
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestShotgunFindDataHandler, self).setUp()
        self.shotgun_model = self.framework.import_module("shotgun_model")

    def test_generate_data_request(self):
        """
        Test generate_data_request
        """
        test_path = os.path.join(self.tank_temp, "test_find_handler.pickle")

        dh = self.shotgun_model.data_handler_find.ShotgunFindDataHandler(
            entity_type="Asset",
            filters=[],
            order=None,
            hierarchy=["sg_asset_type", "code"],
            fields=["code"],
            download_thumbs=True,
            limit=None,
            additional_filter_presets=None,
            cache_path=test_path,
        )

        dh.load_cache()
        self.assertEqual(len(dh.get_entity_ids()), 0)

        # first let the data handler perform its request
        # and make sure it registers it in an expected way
        mock_data_retriever = Mock()
        mock_data_retriever.execute_find = Mock(return_value=1234)

        request_id = dh.generate_data_request(mock_data_retriever)

        # The test invokes the method with a list, but internally it temporarily
        # stores them inside a set which in Python 3 has no guaranteed order
        # of iteration, so we have to tests each parameter manually instead of
        # using assert_called_once_with.
        self.assertEqual(mock_data_retriever.execute_find.call_count, 1)
        parameters = mock_data_retriever.execute_find.call_args.call_list()[0][0]
        self.assertEqual(parameters[0], "Asset")
        self.assertEqual(parameters[1], [])
        self.assertEqual(
            sorted(parameters[2]), sorted(["code", "image", "sg_asset_type"])
        )
        self.assertEqual(parameters[3], None)
        self.assertEqual(
            mock_data_retriever.execute_find.call_args.kwargs, {"limit": None}
        )

        self.assertEqual(request_id, 1234)

    def test_updates(self):
        """
        Test generate_data_request
        """
        test_path = os.path.join(self.tank_temp, "test_find_handler.pickle")

        dh = self.shotgun_model.data_handler_find.ShotgunFindDataHandler(
            entity_type="Asset",
            filters=[],
            order=None,
            hierarchy=["sg_asset_type", "code"],
            fields=["code"],
            download_thumbs=True,
            limit=None,
            additional_filter_presets=None,
            cache_path=test_path,
        )

        dh.load_cache()

        # apply first data chunk
        # two records are added (parent + child)
        sg_data = [
            {"code": "foo", "type": "Asset", "id": 1234, "sg_asset_type": "Prop"}
        ]

        diff = dh.update_data(sg_data)

        # we are getting a diff of two added nodes back.
        self.assertEqual(len(diff), 2)

        self.assertEqual(diff[0]["mode"], dh.ADDED)
        self.assertEqual(diff[1]["mode"], dh.ADDED)

        prop_data = diff[0]["data"]
        asset_data = diff[1]["data"]

        self.assertEqual(prop_data.unique_id, "/Prop")
        self.assertEqual(prop_data.field, "sg_asset_type")
        self.assertEqual(
            prop_data.shotgun_data,
            {"code": "foo", "type": "Asset", "id": 1234, "sg_asset_type": "Prop"},
        )
        self.assertEqual(prop_data.parent, None)
        self.assertEqual(prop_data.is_leaf(), False)

        self.assertEqual(asset_data.unique_id, 1234)
        self.assertEqual(asset_data.field, "code")
        self.assertEqual(
            asset_data.shotgun_data,
            {"code": "foo", "type": "Asset", "id": 1234, "sg_asset_type": "Prop"},
        )
        self.assertEqual(asset_data.parent, prop_data)
        self.assertEqual(asset_data.is_leaf(), True)

        self.assertEqual(dh.get_data_item_from_uid(1234), asset_data)
        self.assertEqual(dh.get_data_item_from_uid("/Prop"), prop_data)

        # now apply an update
        sg_data = [
            {
                "code": "foo_renamed",
                "type": "Asset",
                "id": 1234,
                "sg_asset_type": "Prop",
            }
        ]
        diff = dh.update_data(sg_data)

        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["mode"], dh.UPDATED)
        asset_data = diff[0]["data"]

        self.assertEqual(asset_data.unique_id, 1234)
        self.assertEqual(
            asset_data.shotgun_data,
            {
                "code": "foo_renamed",
                "type": "Asset",
                "id": 1234,
                "sg_asset_type": "Prop",
            },
        )

        # test the data
        self.assertEqual(dh.get_entity_ids(), [1234])
        self.assertEqual(dh.get_uid_from_entity_id(1234), 1234)
        self.assertEqual(dh.get_uid_from_entity_id(12345), None)

        # update a complex update
        sg_data = [
            {
                "code": "new_asset",
                "type": "Asset",
                "id": 3333,
                "sg_asset_type": "Character",
            }
        ]
        diff = dh.update_data(sg_data)

        # we are getting a diff of two added nodes back.
        self.assertEqual(len(diff), 4)

        # Items will be sorted as /Character, /Prop, 1234 and 3333.
        diff = sorted(diff, key=lambda x: str(x["data"].unique_id))

        self.assertEqual(diff[0]["mode"], dh.ADDED)
        self.assertEqual(diff[1]["mode"], dh.DELETED)
        self.assertEqual(diff[2]["mode"], dh.DELETED)
        self.assertEqual(diff[3]["mode"], dh.ADDED)

        # the deleted records are our old data
        self.assertEqual(diff[1]["data"], prop_data)
        self.assertEqual(diff[2]["data"], asset_data)

        self.assertEqual(diff[0]["data"].unique_id, "/Character")
        self.assertEqual(diff[3]["data"].unique_id, 3333)

        dh.save_cache()
        dh.unload_cache()
        self.assertFalse(dh.is_cache_loaded())
        dh.load_cache()

        self.assertEqual(dh.get_data_item_from_uid(3333), diff[3]["data"])
        self.assertEqual(dh.get_data_item_from_uid("/Character"), diff[0]["data"])
        self.assertEqual(dh.get_data_item_from_uid("/Prop"), None)

    def test_generate_child_nodes(self):
        """
        Tests child node generation from cache
        """

        test_path = os.path.join(self.tank_temp, "test_find_handler.pickle")

        dh = self.shotgun_model.data_handler_find.ShotgunFindDataHandler(
            entity_type="Asset",
            filters=[],
            order=None,
            hierarchy=["sg_asset_type", "code"],
            fields=["code"],
            download_thumbs=True,
            limit=None,
            additional_filter_presets=None,
            cache_path=test_path,
        )

        dh.load_cache()

        # push some test data in
        sg_data = [
            {"code": "p_foo", "type": "Asset", "id": 1, "sg_asset_type": "Prop"},
            {"code": "p_bar", "type": "Asset", "id": 2, "sg_asset_type": "Prop"},
            {"code": "p_baz", "type": "Asset", "id": 3, "sg_asset_type": "Prop"},
            {"code": "c_foo", "type": "Asset", "id": 4, "sg_asset_type": "Character"},
            {"code": "c_bar", "type": "Asset", "id": 5, "sg_asset_type": "Character"},
            {"code": "c_baz", "type": "Asset", "id": 6, "sg_asset_type": "Character"},
        ]
        dh.update_data(sg_data)

        callback = Mock()

        dh.generate_child_nodes(None, None, callback)

        calls = [
            call(None, dh.get_data_item_from_uid("/Character")),
            call(None, dh.get_data_item_from_uid("/Prop")),
        ]

        # Python 2 and 3 have different ordering internally
        # for their keys, so we can't expect the items
        # be generated in the same order.
        callback.assert_has_calls(calls, any_order=True)

        # and check children
        callback = Mock()
        dh.generate_child_nodes("/Character", None, callback)
        calls = [
            call(None, dh.get_data_item_from_uid(4)),
            call(None, dh.get_data_item_from_uid(5)),
            call(None, dh.get_data_item_from_uid(6)),
        ]
        # Python 2 and 3 have different ordering internally
        # for their keys, so we can't expect the items
        # be generated in the same order.
        callback.assert_has_calls(calls, any_order=True)

        callback = Mock()
        dh.generate_child_nodes("/Prop", None, callback)
        calls = [
            call(None, dh.get_data_item_from_uid(1)),
            call(None, dh.get_data_item_from_uid(2)),
            call(None, dh.get_data_item_from_uid(3)),
        ]
        # Python 2 and 3 have different ordering internally
        # for their keys, so we can't expect the items
        # be generated in the same order.
        callback.assert_has_calls(calls, any_order=True)
