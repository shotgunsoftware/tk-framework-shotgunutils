# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
from __future__ import with_statement

import errno
import os
import cPickle
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui


from .data_handler import ShotgunDataHandler


class ShotgunDataItem(object):
    """
    Object wrapper around a data entry. This is used by
    the :meth:`ShotgunDataHandler.generate_child_nodes()` method in order
    to pass data cleanly into the item factory method callback.
    """

    def __init__(self, data_dict):
        """
        Do not construct this object by hand. Instances are created
        by :class:`ShotgunDataHandler`.
        :param data_dict: Internal ShotgunDataHandler data dictionary.
        """
        self._data = data_dict

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns: A string representation of this instance
        """
        return "<%s uid:%s>" % (self.__class__.__name__, self.unique_id)

    @property
    def unique_id(self):
        """
        The unique id for this node
        """
        return self._data[ShotgunDataHandler.UID]

    @property
    def field(self):
        """
        The shotgun field that this item represents
        """
        return self._data[ShotgunDataHandler.FIELD]

    @property
    def shotgun_data(self):
        """
        The shotgun data associated with this item
        """
        return self._data[ShotgunDataHandler.SG_DATA]

    @property
    def parent(self):
        """
        The parent of this item or None if no parent
        """
        parent = self._data[ShotgunDataHandler.PARENT]
        if parent is None:
            return None

        parent = ShotgunDataItem(parent)
        if parent.unique_id is None:
            # this is the invisible root node
            return None

        return parent

    def is_leaf(self):
        """
        Flag to indicate if this item is a leaf in the tree
        """
        return self._data[ShotgunDataHandler.IS_LEAF]


