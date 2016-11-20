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


class TestFramework(TankTestBase):
    """
    General fixtures class for testing Toolkit apps
    """
    
    def setUp(self):
        """
        Fixtures setup
        """
        super(TestFramework, self).setUp()
        self.setup_fixtures()

        # set up an environment variable that points to the root of the
        # framework so we can specify its location in the environment fixture

        self.framework_root = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", ".."))
        os.environ["FRAMEWORK_ROOT"] = self.framework_root

        # Add these to mocked shotgun
        self.add_to_sg_mock_db([self.project])

        # run folder creation for the shot
        self.tk.create_filesystem_structure(self.project["type"], self.project["id"])

        # now make a context
        context = self.tk.context_from_entity(self.project["type"], self.project["id"])

        # and start the engine
        self.engine = tank.platform.start_engine("test_engine", self.tk, context)

        self.app = self.engine.apps["test_app"]
        self.framework = self.app.frameworks['tk-framework-shotgunutils']


    def tearDown(self):
        """
        Fixtures teardown
        """
        # engine is held as global, so must be destroyed.
        cur_engine = tank.platform.current_engine()
        if cur_engine:
            cur_engine.destroy()

        # important to call base class so it can clean up memory
        super(TestFramework, self).tearDown()

    
    
class TestDataHandler(TestFramework):
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
        dh = self.shotgun_model.data_handler.ShotgunDataHandler("/tmp/foo", None)
        print dh


