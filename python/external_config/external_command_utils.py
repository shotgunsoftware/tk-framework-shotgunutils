# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
import sys
import sgtk

#############################################################################
# WARNING!!!! Any code in this file will be used by the current config
# and the config for which we'll run external commands. That config may have
# a much older Toolkit core and as such may be missing features. So try to be
# conservative when making changes and do not use post 0.18 features from
# Toolkit, such as sgtk.util.is_*, used for OS detection.

FORMAT_GENERATION = 5


def serialize_command(engine_name, entity_type, command_name, properties):
    """
    Generates a data chunk given a set of standard
    Toolkit command data, as obtained from engine.commands.

    This can be passed to :meth:`create` in order to construct a
    :class:`ExternalCommand` instance.

    :param str engine_name: Name of engine command is associated with.
    :param str entity_type: Shotgun entity type that the
        command is associated with.
    :param str command_name: Command name (the key
        name for an entry in engine.commands)
    :param dict properties: Properties dictionary
        as returned by the ``Engine.commands`` dictionary property.
    :returns: dictionary suitable to pass to :meth:`create`.
    """
    data = {
        "engine_name": engine_name,
        "entity_type": entity_type,
        "callback_name": command_name,
        "display_name": properties.get("title") or command_name,
        "tooltip": properties.get("description") or "",
        "type": properties.get("type"),
        "icon": properties.get("icon"),
        "group": properties.get("group"),
        "group_default": properties.get("group_default") or False,
        # special for shotgun
        "sg_deny_permissions": properties.get("deny_permissions"),
        "sg_supports_multiple_selection": properties.get("supports_multiple_selection"),
    }

    return data


def enabled_on_current_os(properties):
    """
    Checks toolkit command properties to determine
    if a command is enabled on the current OS or not.

    :param dict properties: Properties dictionary
        as returned by the ``Engine.commands`` dictionary property.
    :returns: True if enabled, False if not.
    """
    if "deny_platforms" in properties:
        if sys.platform.startswith("linux"):
            curr_os = "Linux"
        elif sys.platform == "win32":
            curr_os = "Windows"
        else:
            curr_os = "Mac"
        if curr_os in properties["deny_platforms"]:
            # not enabled on this platform
            return False

    return True
