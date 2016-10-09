# Copyright (c) 2013 Shotgun Software Inc.
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
import shutil
import tempfile

from tank_test.tank_test_base import *
import tank
from tank.errors import TankError
from tank.platform import application
from tank.platform import constants
from tank.template import Template
from tank.deploy import descriptor


class TestApplication(TankTestBase):
    """
    General fixtures class for testing Toolkit apps
    """
    
    def setUp(self):
        """
        Fixtures setup
        """
        super(TestApplication, self).setUp()

        

    def test
    
    
class TestApi(TestApplication):
    """
    Tests for the Breakdown App's API interface
    """
    
    def setUp(self):
        """
        Fixtures setup
        """        
        super(TestApi, self).setUp()
        
        # short hand for the app
        self.app = self.engine.apps["tk-multi-breakdown"]
        
        # set up some test data
        self.test_path_1 = os.path.join(self.project_root, 
                                   "sequences", 
                                   self.seq["code"], 
                                   self.shot["code"], 
                                   self.step["short_name"], 
                                   "publish", 
                                   "foo.v003.ma")

        self.test_path_2 = os.path.join(self.project_root,  
                                   "sequences", 
                                   self.seq["code"], 
                                   self.shot["code"], 
                                   self.step["short_name"], 
                                   "publish", 
                                   "foo.v004.ma")

        fh = open(self.test_path_1, "wt")
        fh.write("hello")
        fh.close()
        
        fh = open(self.test_path_2, "wt")
        fh.write("hello")
        fh.close()

        # this will be read by our hook so push
        # it out into env vars...
        os.environ["TEST_PATH_1"] = self.test_path_1
        os.environ["TEST_PATH_2"] = self.test_path_2
        
        
    def test_analyze_scene(self):
        """
        Tests the analyze_scene method
        """
        scene_data = self.app.analyze_scene()
        self.assertEqual(len(scene_data), 1)
        
        item = scene_data[0]
        self.assertEqual(item["fields"], {'Shot': 'shot_code', 
                                          'name': 'foo', 
                                          'Sequence': 'seq_code', 
                                          'Step': 'step_short_name', 
                                          'version': 3, 
                                          'maya_extension': 'ma', 
                                          'eye': '%V'})
        self.assertEqual(item["node_name"], "maya_publish")
        self.assertEqual(item["node_type"], "TestNode")
        self.assertEqual(item["template"], self.tk.templates["maya_shot_publish"])
        self.assertEqual(item["sg_data"], None)
        
        
    def test_compute_highest_version(self):
        """
        Tests the version computation logic
        """
        scene_data = self.app.analyze_scene()
        item = scene_data[0]        
        # test logic
        self.assertEqual(self.app.compute_highest_version(item["template"], item["fields"]), 4)
        # test bad data
        self.assertRaises(TankError, 
                          self.app.compute_highest_version, 
                          self.tk.templates["maya_asset_publish"], 
                          item["fields"])
        
    def test_update(self):
        """
        Test scene update
        """
        scene_data = self.app.analyze_scene()
        item = scene_data[0]
        
        # increment version
        fields = item["fields"]
        fields["version"] = 4

        # clear temp location where hook writes to
        tank._hook_items = None
        
        # execute hook
        self.app.update_item(item["node_type"], item["node_name"], item["template"], fields)        
        
        # check result
        self.assertEqual(len(tank._hook_items), 1)
        self.assertEqual(tank._hook_items[0]["node"], "maya_publish")
        self.assertEqual(tank._hook_items[0]["path"], self.test_path_2)
        self.assertEqual(tank._hook_items[0]["type"], "TestNode")
        
                
