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


class TestExternalCommandUtils(ExternalConfigBase):
    """
    Tests for the external config loader.
    """

    def test_enabled_on_current_os(self):
        """
        Make sure each platform see themselves as not executable
        """
        # Should be denied on all platforms.
        self.assertFalse(
            self.external_config.external_command_utils.enabled_on_current_os(
                {"deny_platforms": ["Windows", "Linux", "Mac"]}
            )
        )

        self.assertTrue(
            self.external_config.external_command_utils.enabled_on_current_os(
                {"deny_platforms": []}
            )
        )
