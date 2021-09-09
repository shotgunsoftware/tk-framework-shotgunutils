# Copyright (c) 2019 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import time

import mock

from tank_vendor import six

from tank_test.tank_test_base import setUpModule  # noqa
from base_test import TestShotgunUtilsFramework


class TestCachedSchema(TestShotgunUtilsFramework):
    """
    Tests the Shotgun Model utilities
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestCachedSchema, self).setUp()

        self._patch_mockgun("schema_read")
        self._patch_mockgun("schema_entity_read")

        # We need a background task manager so the schema can be cached in a background thread.
        self._bg_task_manager = self.framework.import_module(
            "task_manager"
        ).BackgroundTaskManager(self._qapp, start_processing=True)

        self._shotgun_globals = self.framework.import_module("shotgun_globals")
        self._shotgun_globals.register_bg_task_manager(self._bg_task_manager)
        self.addCleanup(
            lambda: self._bg_task_manager.shut_down()
            or self._shotgun_globals.unregister_bg_task_manager(self._bg_task_manager)
        )

        # Make sure there is no test data leaking from another test.
        self._shotgun_globals.clear_cached_data()
        self._cached_schema = self.framework.import_module(
            "shotgun_globals"
        ).cached_schema.CachedShotgunSchema._CachedShotgunSchema__get_instance()

    def _patch_mockgun(self, method):
        """
        Mockgun does not accept the project argument that is passed to the schema read methods,
        so we'll mock the methods and return the expected schema.
        """
        patcher = mock.patch.object(
            self.mockgun, method, return_value=getattr(self.mockgun, method)()
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_serialize_unserialize_schema(self):
        """
        Test serialization and unserialization of a schema.
        """

        assert self._cached_schema._is_schema_loaded() is False
        assert self._cached_schema._is_status_loaded() is False

        self._trigger_cache_load()

        # Ensure the cache is now loaded.
        assert self._cached_schema._is_schema_loaded() is True
        assert self._cached_schema._is_status_loaded() is True

        # Mockgun should have been called to cache the data.
        assert self.mockgun.schema_read.called
        assert self.mockgun.schema_entity_read.called

        # The schema should be the same as what is in mockgun.
        assert self._cached_schema._field_schema, self.mockgun.schema_read()
        assert self._cached_schema._type_schema, self.mockgun.schema_entity_read()

        # Reset the mock so we can track if when reloading from cache mockgun is called or not.
        # We'll be expecting it not to be called.
        self.mockgun.schema_read.reset_mock()
        self.mockgun.schema_entity_read.reset_mock()
        assert self.mockgun.schema_read.called is False
        assert self.mockgun.schema_entity_read.called is False

        # Peak behind the curtain to reload the cache.
        assert self._cached_schema._load_cached_schema()
        assert self._cached_schema._load_cached_status()

        # Mockgun should not have been called.
        assert self.mockgun.schema_read.called is False
        assert self.mockgun.schema_entity_read.called is False

        # The data reloaded from disk should be the same as before.
        assert self._cached_schema._field_schema, self.mockgun.schema_read()
        assert self._cached_schema._type_schema, self.mockgun.schema_entity_read()

        if six.PY2:
            self._assert_no_unicode(self._cached_schema._field_schema)
            self._assert_no_unicode(self._cached_schema._type_schema)

    def test_is_valid_entity_type(self):
        """
        Test the function that checks whether not entity types are in the schema.
        """

        valid_entity_types = self._cached_schema._field_schema

        for entity_type in valid_entity_types:
            assert self._cached_schema.is_valid_entity_type(entity_type)

        invalid_type = "bad entity"
        assert invalid_type not in valid_entity_types
        assert not self._cached_schema.is_valid_entity_type(invalid_type)

    def _assert_no_unicode(self, value):
        """
        Asserts that a value is not a Python 2 ``unicode`` object.
        """
        if isinstance(value, dict):
            for k, v in value.items():
                self._assert_no_unicode(k)
                self._assert_no_unicode(v)
        elif isinstance(value, list):
            for v in value:
                self._assert_no_unicode(v)
        else:
            assert isinstance(value, unicode) is False

    def _trigger_cache_load(self):
        """
        Trigger a cache reload and wait until it is completed.
        """
        # Kick the hornet's nest so the background thread loads the schema.
        self._shotgun_globals.get_entity_fields("Asset")
        self._shotgun_globals.get_status_display_name("ip")

        # The schema is loaded by a background thread, so we'll have to process events so the results can more in.
        before = time.time()
        while (
            self._cached_schema._is_schema_loaded() is False
            or self._cached_schema._is_status_loaded() is False
        ):
            self._qapp.processEvents()
            assert (
                before + 2 > time.time()
            ), "Timeout, schema shouldn't take this long to load from Mockgun."
