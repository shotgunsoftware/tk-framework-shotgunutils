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


class TestShotgunNavDataHandler(TestShotgunUtilsFramework):
    """
    Tests for the data handler low level io
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestShotgunNavDataHandler, self).setUp()
        self.shotgun_model = self.framework.import_module("shotgun_model")

    def test_generate_data_request(self):
        """
        Test generate_data_request
        """
        test_path = os.path.join(self.tank_temp, "test_nav_handler.pickle")

        dh = self.shotgun_model.data_handler_nav.ShotgunNavDataHandler(
            root_path="/",
            seed_entity_field="Version.entity",
            entity_fields=None,
            cache_path=test_path,
        )

        dh.load_cache()

        # first let the data handler perform its request
        # and make sure it registers it in an expected way
        mock_data_retriever = Mock()
        mock_data_retriever.execute_nav_expand = Mock(return_value=1234)

        request_id = dh.generate_data_request(mock_data_retriever, "/")

        mock_data_retriever.execute_nav_expand.assert_called_once_with(
            "/", "Version.entity", None
        )
        self.assertEqual(request_id, 1234)

    def test_updates(self):
        """
        Test generate_data_request
        """
        test_path = os.path.join(self.tank_temp, "test_nav_handler.pickle")

        dh = self.shotgun_model.data_handler_nav.ShotgunNavDataHandler(
            root_path="/",
            seed_entity_field="Version.entity",
            entity_fields=None,
            cache_path=test_path,
        )

        dh.load_cache()

        # apply first data chunk
        sg_data = {
            "path": "/",
            "children": [
                {"label": "foo", "has_children": True, "path": "/foo"},
                {"label": "bar", "has_children": True, "path": "/bar"},
                {"label": "baz", "has_children": False, "path": "/baz"},
            ],
        }

        diff = dh.update_data(sg_data)

        # we are getting a diff of two added nodes back.
        self.assertEqual(len(diff), 3)

        self.assertEqual(diff[0]["mode"], dh.ADDED)
        self.assertEqual(diff[1]["mode"], dh.ADDED)
        self.assertEqual(diff[2]["mode"], dh.ADDED)

        foo = diff[0]["data"]
        bar = diff[1]["data"]
        baz = diff[1]["data"]

        self.assertEqual(foo.unique_id, "/foo")
        self.assertEqual(foo.field, None)
        self.assertEqual(
            foo.shotgun_data, {"has_children": True, "label": "foo", "path": "/foo"}
        )
        self.assertEqual(foo.parent, None)
        self.assertEqual(foo.is_leaf(), False)

        self.assertEqual(dh.get_data_item_from_uid("/foo"), foo)

        # now apply an update
        sg_data = {
            "path": "/",
            "children": [
                {"label": "foo2", "has_children": True, "path": "/foo2"},
                {"label": "bar", "has_children": True, "path": "/bar"},
                {"label": "baz", "has_children": False, "path": "/baz"},
            ],
        }
        diff = dh.update_data(sg_data)

        self.assertEqual(len(diff), 2)
        self.assertEqual(diff[0]["mode"], dh.ADDED)
        self.assertEqual(diff[1]["mode"], dh.DELETED)

        dh.save_cache()
        dh.unload_cache()
        self.assertFalse(dh.is_cache_loaded())
        dh.load_cache()

        self.assertEqual(dh.get_data_item_from_uid("/foo2"), diff[0]["data"])
        self.assertEqual(dh.get_data_item_from_uid("/Prop"), None)

    def test_generate_child_nodes(self):
        """
        Tests child node generation from cache
        """

        test_path = os.path.join(self.tank_temp, "test_nav_handler.pickle")

        dh = self.shotgun_model.data_handler_nav.ShotgunNavDataHandler(
            root_path="/",
            seed_entity_field="Version.entity",
            entity_fields=None,
            cache_path=test_path,
        )

        dh.load_cache()

        # apply first data chunk
        sg_data = {
            "path": "/",
            "children": [
                {"label": "foo", "has_children": True, "path": "/foo"},
                {"label": "bar", "has_children": True, "path": "/bar"},
                {"label": "baz", "has_children": False, "path": "/baz"},
            ],
        }

        dh.update_data(sg_data)

        sg_data = {
            "path": "/foo",
            "children": [
                {"label": "smith", "has_children": False, "path": "/foo/smith"},
                {"label": "jones", "has_children": False, "path": "/foo/jones"},
                {"label": "brown", "has_children": False, "path": "/foo/brown"},
            ],
        }

        dh.update_data(sg_data)

        callback = Mock()

        dh.generate_child_nodes(None, None, callback)

        calls = [
            call(None, dh.get_data_item_from_uid("/foo")),
            call(None, dh.get_data_item_from_uid("/bar")),
            call(None, dh.get_data_item_from_uid("/baz")),
        ]

        # Python 2 and 3 have different ordering internally
        # for their keys, so we can't expect the items
        # be generated in the same order.
        callback.assert_has_calls(calls, any_order=True)

        # and check children
        callback = Mock()
        dh.generate_child_nodes("/foo", None, callback)
        calls = [
            call(None, dh.get_data_item_from_uid("/foo/smith")),
            call(None, dh.get_data_item_from_uid("/foo/brown")),
            call(None, dh.get_data_item_from_uid("/foo/jones")),
        ]
        # Python 2 and 3 have different ordering internally
        # for their keys, so we can't expect the items
        # be generated in the same order.
        callback.assert_has_calls(calls, any_order=True)
