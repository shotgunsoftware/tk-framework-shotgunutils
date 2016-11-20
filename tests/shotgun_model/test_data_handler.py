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

from tank_test.tank_test_base import *

# import the test base class
test_python_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "python"))
sys.path.append(test_python_path)
from base_test import TestShotgunUtilsFramework


class TestDataHandler(TestShotgunUtilsFramework):
    """
    Tests for the data handler low level io
    """
    
    def setUp(self):
        """
        Fixtures setup
        """        
        super(TestDataHandler, self).setUp()
        self.shotgun_model = self.framework.import_module("shotgun_model")

    def test_io(self):
        """
        Test loading and saving
        """
        test_path = os.path.join(self.tank_temp, "cache.pickle")

        dh = self.shotgun_model.data_handler.ShotgunDataHandler(test_path, None)

        # no cache file on disk
        self.assertFalse(dh.is_cache_available())

        # not loaded
        self.assertFalse(dh.is_cache_loaded())

        # now load the cache
        dh.load_cache()

        # no cache file on disk
        self.assertFalse(dh.is_cache_available())

        # but it is loaded
        self.assertTrue(dh.is_cache_loaded())

        # save the cache
        dh.save_cache()

        # no cache file on disk
        self.assertTrue(dh.is_cache_available())

        # but it is loaded
        self.assertTrue(dh.is_cache_loaded())

        # remove from disk
        dh.remove_cache()

        # no cache file on disk
        self.assertFalse(dh.is_cache_available())

        # but it is loaded
        self.assertFalse(dh.is_cache_loaded())



