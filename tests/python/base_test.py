# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os

from tank_test.tank_test_base import TankTestBase
import sgtk


class TestShotgunUtilsFramework(TankTestBase):
    """
    Baseclass for all Shotgun Utils unit tests.

    This sets up the fixtures, starts an engine and provides
    the following members:

    - self.framework_root: The path on disk to the framework bundle
    - self.engine: The test engine running
    - self.app: The test app running
    - self.framework: The shotgun utils fw running

    In your test classes, import module functionality like this::

        self.shotgun_model = self.framework.import_module("shotgun_model")

    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestShotgunUtilsFramework, self).setUp()

        self.setup_fixtures()

        # set up an environment variable that points to the root of the
        # framework so we can specify its location in the environment fixture

        self.framework_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        os.environ["FRAMEWORK_ROOT"] = self.framework_root

        # Add these to mocked shotgun
        self.add_to_sg_mock_db([self.project])

        # run folder creation for the shot
        self.tk.create_filesystem_structure(self.project["type"], self.project["id"])

        # now make a context
        context = self.tk.context_from_entity(self.project["type"], self.project["id"])

        # and start the engine
        self.engine = sgtk.platform.start_engine("test_engine", self.tk, context)
        # This ensures that the engine will always be destroyed.
        self.addCleanup(self.engine.destroy)

        # Ensure a QApplication instance for the tests.
        self._qapp = sgtk.platform.qt.QtGui.QApplication.instance()
        if not self._qapp:
            self._qapp = sgtk.platform.qt.QtGui.QApplication([])

        self.app = self.engine.apps["test_app"]
        self.framework = self.app.frameworks["tk-framework-shotgunutils"]
