# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

from sgtk.platform.qt import QtCore, QtGui
from .ui import resources_rc

# list of all entity types for which an icon exists
_entity_types_with_icons = ["Asset", 
                           "ClientUser",
                           "EventLogEntry",
                           "Group",
                           "HumanUser",
                           "PublishedFile",
                           "TankPublishedFile",
                           "Note",
                           "Playlist",
                           "Project",
                           "Sequence",
                           "Shot",
                           "Tag",
                           "Task",
                           "Ticket",
                           "Version",
                           ]

_cached_entity_icons = {}


def get_entity_type_icon_url(entity_type):
    """
    Retrieve the icon resource path for the specified entity type if available.
    
    This is useful if you want to include an icon in a ``QLabel`` using
    an ``<img>`` html tag.

    :param entity_type: The entity type to retrieve the icon for
    :returns:           A string url with a qt resource path
    """
    if entity_type in _entity_types_with_icons:
        return ":/tk-framework-shotgunutils/icon_%s_dark.png" % entity_type
    else:
        return None

def get_entity_type_icon(entity_type):
    """
    Retrieve the icon for the specified entity type if available.

    :param entity_type: The entity type to retrieve the icon for
    :returns:           A QIcon if an icon was found for the specified entity
                        type, otherwise None.
    """
    global _cached_entity_icons
    if entity_type not in _cached_entity_icons:
        # not yet cached
        icon = None
        url = get_entity_type_icon_url(entity_type) 
        if url:
            # create a QIcon for it
            icon = QtGui.QIcon(QtGui.QPixmap(url))
        # cache it
        _cached_entity_icons[entity_type] = icon
        
    # we've previously asked for the icon
    return _cached_entity_icons[entity_type]
    


