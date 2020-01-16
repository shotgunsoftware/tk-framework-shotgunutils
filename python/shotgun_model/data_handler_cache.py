# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


from .util import compare_shotgun_data
from tank_vendor import six


class ShotgunDataHandlerCache(object):
    """
    Low level convenience wrapper around a data handler cache.
    Contains a dictionary structure of simple objects suitable
    for fast serialization with pickle.

    Used in conjunction with the data handler.
    """

    # internal constants for serialization performance
    (CACHE_BY_UID, CACHE_CHILDREN, UID, IS_LEAF, PARENT, FIELD, SG_DATA) = range(7)

    def __init__(self, raw_data=None):
        """
        :param raw_data: raw data to initialize with.
        """
        if raw_data:
            self._cache = raw_data
        else:
            # init clear cache
            self._cache = {
                self.CACHE_CHILDREN: {},  # hierarchy
                self.CACHE_BY_UID: {},  # uid-based lookup
                self.UID: None,  # the uid of the root is None
            }

    @property
    def raw_data(self):
        """
        The raw dictionary data contained in the cache.
        """
        return self._cache

    @property
    def size(self):
        """
        The number of items in the cache
        """
        return len(self._cache[self.CACHE_BY_UID])

    @property
    def uids(self):
        """
        All uids in unspecified order, as an iterator for scalability
        """
        return six.iterkeys(self._cache[self.CACHE_BY_UID])

    def get_child_uids(self, parent_uid):
        """
        Returns all the child uids for the given parent
        Returned in unspecified order as an iterator for scalability

        :param parent_uid: Parent uid
        :returns: list of child uids
        """
        if parent_uid is None:
            return six.iterkeys(self._cache[self.CACHE_CHILDREN])
        else:
            return six.iterkeys(
                self._cache[self.CACHE_BY_UID][parent_uid][self.CACHE_CHILDREN]
            )

    def item_exists(self, unique_id):
        """
        Checks if an item exists in the cache

        :param unique_id: unique id for cache item
        :returns: True if item exists, false if not
        """
        return unique_id in self._cache[self.CACHE_BY_UID]

    def get_shotgun_data(self, unique_id):
        """
        Optimization. Returns the shotgun data for the given uid.

        :param unique_id: unique id for cache item
        :returns: Associated Shotgun data dictionary
        """
        return self._cache[self.CACHE_BY_UID][unique_id][self.SG_DATA]

    def get_entry_by_uid(self, unique_id):
        """
        Returns a :class:`ShotgunItemData` for a given unique id.

        :param unique_id: unique id for cache item
        :returns: :class:`ShotgunItemData` instance or None if not found.
        """
        from .data_item import ShotgunItemData  # local import to avoid cycles

        data = self._cache[self.CACHE_BY_UID].get(unique_id)
        return ShotgunItemData(data) if data else None

    def get_all_items(self):
        """
        Generator that returns all items in no particular order

        :returns: :class:`ShotgunItemData` instances
        """
        for unique_id in self._cache[self.CACHE_BY_UID]:
            yield self.get_entry_by_uid(unique_id)

    def get_children(self, parent_uid):
        """
        Generator that returns all childen for the given item.

        :param parent_uid: unique id for cache item
        :returns: :class:`ShotgunItemData` instances
        """
        from .data_item import ShotgunItemData  # local import to avoid cycles

        if parent_uid is None:
            # this is the root
            cache_node = self._cache
        else:
            # resolve cache node from uid
            cache_node = self._cache[self.CACHE_BY_UID].get(parent_uid)

        if cache_node:
            for item in six.itervalues(cache_node[self.CACHE_CHILDREN]):
                data_item = ShotgunItemData(item)
                yield data_item

    def add_item(self, parent_uid, sg_data, field_name, is_leaf, uid):
        """
        Adds an item to the cache. Checks if the item already exists
        and if it does, performs an up to date check. If the data is
        different from the existing data, True is returned.

        :param parent_uid: parent unique id
        :param sg_data: Shotgun data dictionary
        :param field_name: optional name of associated shotgun field
        :param is_leaf: boolean to indicate if node is a child node
        :param uid: unique id for the item.

        :returns: True if the item was updated, False if not.
        """
        if parent_uid is None:
            parent_node = self._cache
        else:
            parent_node = self._cache[self.CACHE_BY_UID][parent_uid]

        if uid in parent_node[self.CACHE_CHILDREN]:
            # node already exists. See if it differs
            existing_sg_data = parent_node[self.CACHE_CHILDREN][uid][self.SG_DATA]
            if compare_shotgun_data(existing_sg_data, sg_data):
                # data is the same
                return False
            else:
                # data has changed, so update the record
                parent_node[self.CACHE_CHILDREN][uid][self.SG_DATA] = sg_data
                parent_node[self.CACHE_CHILDREN][uid][self.FIELD] = field_name
                parent_node[self.CACHE_CHILDREN][uid][self.IS_LEAF] = is_leaf
                return True

        else:
            # brand new node
            item = {
                self.SG_DATA: sg_data,
                self.FIELD: field_name,
                self.IS_LEAF: is_leaf,
                self.UID: uid,
                self.PARENT: parent_node,
                self.CACHE_CHILDREN: {},
            }

            parent_node[self.CACHE_CHILDREN][uid] = item
            self._cache[self.CACHE_BY_UID][uid] = item
            return True

    def take_item(self, unique_id):
        """
        Remove and return the given unique id from the cache

        :param unique_id: unique id for cache item
        :returns: :class:`ShotgunItemData` instance or None if not found.
        """
        item_data = self.get_entry_by_uid(unique_id)
        if item_data:
            # remove it
            item = self._cache[self.CACHE_BY_UID][unique_id]
            del self._cache[self.CACHE_BY_UID][unique_id]
            parent = item[self.PARENT]
            del parent[self.CACHE_CHILDREN][unique_id]
        return item_data
