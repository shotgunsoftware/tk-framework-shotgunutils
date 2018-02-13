# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


import sgtk

logger = sgtk.platform.get_logger(__name__)


class RemoteCommand(object):
    """
    Instance representing a remote Toolkit command object
    """

    @classmethod
    def serialize_command(cls, command_name, properties):
        """
        Generates a data chunk given a set of standard
        toolkit command data, as obtained from engine.commands.

        :param str command_name: Command name (the key
            name for an entry in engine.commands)
        :param dict properties: Properties dictionary
            as returned by engine.commands.
        :returns: dictionary suitable to pass to :meth:`create`.
        """

        # props = data["properties"]
        # app = props.get("app")
        #
        # if app:
        #     app_name = app.name
        # else:
        #     app_name = None
        #
        # commands.append(
        #     dict(
        #         name=cmd_name,
        #         title=props.get("title", cmd_name),
        #         deny_permissions=props.get("deny_permissions", []),
        #         supports_multiple_selection=props.get(
        #             "supports_multiple_selection",
        #             False
        #         ),
        #         app_name=app_name,
        #         group=props.get("group"),
        #         group_default=props.get("group_default"),
        #         engine_name=props.get("engine_name"),
        #     ),
        # )
        #
        return {"name": command_name}


    @classmethod
    def create(cls, data):
        """
        Creates a new :class:`RemoteCommand` instance based on the
        data in data. This data is generated by :meth:`serialize_command`.

        :param dict data: Serialized data to be turned into an instance
        :returns: :class:`RemoteCommand` instance.
        """
        return RemoteCommand(data["name"])

    def __init__(self, name):
        """
        """
        super(RemoteCommand, self).__init__()

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()
        self._name = name

    @classmethod
    def from_string(cls, chunk):
        """
        Create
        """
        return RemoteCommand("foo")

    def to_string(self):
        """
        Serialialize
        """
        return "foooo"

    def __repr__(self):
        return "<RemoteCommand>"

    @property
    def name(self):
        return self._name

    def tooltip(self):
        return "foo"

    def execute(self):
        """
        Execute the remote command
        @return:
        """
        logger.debug("%s: execute command" % self)


