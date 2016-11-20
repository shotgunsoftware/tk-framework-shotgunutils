# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from .data_handler import ShotgunDataHandler


class ShotgunDataItem(object):
    """
    Object wrapper around an entry in the :class:`DataHandler`.
    These objects are returned by all datahandler methods and
    forms the official interface for data exchange.
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

    def __eq__(self, other):
        """
        Test if this ShotgunDataItem instance is equal to another ShotgunDataItem instance

        :param other:   Other ShotgunDataItem instance to compare with
        :returns:       True if equal to other, False otherwise
        """
        if not isinstance(other, ShotgunDataItem):
            return NotImplemented

        return self.unique_id == other.unique_id

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


