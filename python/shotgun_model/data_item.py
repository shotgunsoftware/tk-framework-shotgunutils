# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from .data_handler import ShotgunDataHandlerCache


class ShotgunItemData(object):
    """
    Object wrapper around an entry in the :class:`DataHandler`.
    These objects are returned by all datahandler methods and
    forms the official interface for data exchange.
    """

    # @todo - a future optimisation may be to explore the usse of __slots__.
    #
    # It would be interesting to revisit ShotgunItemData in the future by
    # having ShotgunDataItems stored directly in the pickled cache and
    # use __slots__ to keep memory usage low. This would probably
    # require a resolver class however for the Pickler since
    # the path to our classes change every reload.

    def __init__(self, data_dict):
        """
        Do not construct this object by hand. Instances are created
        by :class:`ShotgunDataHandler`.
        :param data_dict: Internal ShotgunDataHandler data dictionary.
        """
        self._data = data_dict

    def __repr__(self):
        """
        String representation of this instance
        """
        return "<%s uid:%s>" % (self.__class__.__name__, self.unique_id)

    def __eq__(self, other):
        """
        Test if this ShotgunItemData instance is equal to another ShotgunItemData instance

        :param other:   Other ShotgunItemData instance to compare with
        :returns:       True if equal to other, False otherwise
        """
        if not isinstance(other, ShotgunItemData):
            return NotImplemented

        return self.unique_id == other.unique_id

    @property
    def unique_id(self):
        """
        The unique id for this node
        """
        return self._data[ShotgunDataHandlerCache.UID]

    @property
    def field(self):
        """
        The shotgun field that this item represents
        """
        return self._data[ShotgunDataHandlerCache.FIELD]

    @property
    def shotgun_data(self):
        """
        The shotgun data associated with this item
        """
        return self._data[ShotgunDataHandlerCache.SG_DATA]

    @property
    def parent(self):
        """
        The parent of this item or None if no parent
        """
        parent = self._data[ShotgunDataHandlerCache.PARENT]
        if parent is None:
            return None

        parent = ShotgunItemData(parent)
        if parent.unique_id is None:
            # this is the invisible root node
            return None

        return parent

    def is_leaf(self):
        """
        Flag to indicate if this item is a leaf in the tree
        """
        return self._data[ShotgunDataHandlerCache.IS_LEAF]


