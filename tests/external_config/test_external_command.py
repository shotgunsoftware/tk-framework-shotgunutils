# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from mock import patch

from sgtk.util import process # noqa
from sgtk.util import filesystem # noqa
from tank_test.tank_test_base import setUpModule # noqa
from . import ExternalConfigBase


class TestExternalCommand(ExternalConfigBase):
    """
    Tests for the external config loader.
    """
    def setUp(self):
        """
        Initial setup.
        """        
        super(TestExternalCommand, self).setUp()

        # example taken from a working 'Shotgun Create / tk-desktop2' setup
        self._data = {
            "sg_supports_multiple_selection": None,
            "display_name": "Maya 2017",
            "engine_name": "tk-desktop2",
            "sg_deny_permissions": None,
            "entity_type": "Task",
            "tooltip": "Launches and initializes an application environment.",
            "callback_name": "maya_2017",
            "group": "Maya",
            "type": None,
            "group_default": False,
            "icon": "/Applications/Autodesk/maya2017/Maya.app/Contents/icons/mayaico.png"
        }

        # The ExternalCommand create method expects the following field which I couldn't figure out origin
        # Maybe they are missing or were renamed from/in Mockgun ?
        self._descriptor_uri = self.external_config_loader.base_config_uri
        self._pipeline_configuration_id = None
        self._pipeline_configuration_name = None

        self.external_config_loader.descriptor_uri = self.external_config_loader.base_config_uri
        # Setting None as the configuration I was testing the App with actually had this set to None
        self.external_config_loader.pipeline_configuration_id = None
        self.external_config_loader.pipeline_configuration_name = None

        # Creating the external command object
        self._external_command = self.external_config.ExternalCommand.create(
            self.external_config_loader,
            self.ec_data,
            "Task"
        )

    @property
    def ec_data(self):
        """
        A dictionary of the test data used to create the ExternalCommand object
        """
        return self._data

    @property
    def ec(self):
        """
        An ExternalCommand test instance
        """
        return self._external_command

    def test_properties(self):
        """
        Make sure public properties can be accessed without exception
        """
        self.assertEquals(self.ec.pipeline_configuration_name, self._pipeline_configuration_id)
        # Yes, the prop. name and dict key are different
        self.assertEquals(self.ec.system_name, self.ec_data["callback_name"])
        self.assertEquals(self.ec.engine_name, self.ec_data["engine_name"])
        self.assertEquals(self.ec.display_name, self.ec_data["display_name"])
        self.assertEquals(self.ec.group, self.ec_data["group"])
        self.assertEquals(self.ec.icon, self.ec_data["icon"])
        self.assertEquals(self.ec.is_group_default, self.ec_data["group_default"])
        if self.ec_data["sg_deny_permissions"]:
            self.assertEquals(self.ec.excluded_permission_groups_hint, self.ec_data["sg_deny_permissions"])
        else:
            self.assertEquals(self.ec.excluded_permission_groups_hint, [])
        self.assertEquals(self.ec.support_shotgun_multiple_selection, self.ec_data["sg_supports_multiple_selection"])
        self.assertEquals(self.ec.tooltip, self.ec_data["tooltip"])
        self.assertTrue(len(repr(self.ec)) > 0)

    def test_serialize_deserialize(self):
        """
        Make sure that serializing and deserialize an ExternalCommand instance produce a similar object.
        """
        # Serialize our test base object
        a_pickle = self.ec.serialize()

        # Create a new object from the serialize data
        ec2 = self.external_config.ExternalCommand.deserialize(a_pickle)

        # Test that new object similarity with original one
        # Unfortunately the ExternalCommand object is not implementing a custom equal method
        # we have to check properties one by one.
        self.assertNotEquals(self.ec, ec2)
        self.assertEquals(self.ec.pipeline_configuration_name, ec2.pipeline_configuration_name)
        self.assertEquals(self.ec.system_name, ec2.system_name)
        self.assertEquals(self.ec.engine_name, ec2.engine_name)
        self.assertEquals(self.ec.display_name, ec2.display_name)
        self.assertEquals(self.ec.group, ec2.group)
        self.assertEquals(self.ec.icon, ec2.icon)
        self.assertEquals(self.ec.is_group_default, ec2.is_group_default)
        self.assertEquals(self.ec.excluded_permission_groups_hint, ec2.excluded_permission_groups_hint)
        self.assertEquals(self.ec.support_shotgun_multiple_selection, ec2.support_shotgun_multiple_selection)
        self.assertEquals(self.ec.tooltip, ec2.tooltip)
        self.assertEquals(repr(self.ec), repr(ec2))

    @patch("sgtk.util.process.subprocess_check_output")
    @patch("sgtk.util.filesystem.safe_delete_file")
    def test_execute_with_default_params(self, mockedSafeDeleteFile, mockedCheckOutput):
        """
        Test & exercise the code as much as possible up to the subprocess method call
        """
        # Note our mock won't be returning an output
        self.ec.execute()
        self.assertEqual(mockedCheckOutput.call_count, 1)
        self.assertEqual(mockedSafeDeleteFile.call_count, 1)

    @patch("sgtk.util.process.subprocess_check_output")
    @patch("sgtk.util.filesystem.safe_delete_file")
    def test_execute_on_multiple_entities_with_default_params(self, mockedSafeDeleteFile, mockedCheckOutput):
        """
        Test & exercise the code as much as possible up to the subprocess method call
        """
        # Note our mock won't be returning an output
        self.ec.execute_on_multiple_entities()
        self.assertEqual(mockedCheckOutput.call_count, 1)
        self.assertEqual(mockedSafeDeleteFile.call_count, 1)

