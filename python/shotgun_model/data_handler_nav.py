# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import gc

from .data_handler import ShotgunDataHandler, log_timing
from .errors import ShotgunModelDataError
from .data_item import ShotgunDataItem


class ShotgunNavDataHandler(ShotgunDataHandler):
    """
    Shotgun Model low level data storage for use
    with the Shotgun Hierarchy Model.

    This implements a data storage where a series of
    nav_expand queries are stringed together into a single
    cache file on disk.
    """

    # constant values to refer to the fields where the paths are stored in the
    # returned navigation data.
    _SG_PATH_FIELD = "path"
    _SG_PARENT_PATH_FIELD = "parent_path"

    def __init__(self, root_path, seed_entity_field, entity_fields, cache_path, parent):
        """
        :param str root_path: The path to the root of the hierarchy to display.
            This corresponds to the ``path`` argument of the
            :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`
            api method. For example, ``/Project/65`` would correspond to a
            project on you shotgun site with id of ``65``.

        :param str seed_entity_field: This is a string that corresponds to the
            field on an entity used to seed the hierarchy. For example, a value
            of ``Version.entity`` would cause the model to display a hierarchy
            where the leaves match the entity value of Version entities.

        :param dict entity_fields: A dictionary that identifies what fields to
            include on returned entities. Since the hierarchy can include any
            entity structure, this argument allows for specification of
            additional fields to include as these entities are returned. The
            dict's keys correspond to the entity type and the value is a list
            of field names to return.

        :param str cache_path: Path to cache file location.

        :param :class:`~PySide.QtGui.QObject` parent: Parent Qt object.
        """
        super(ShotgunNavDataHandler, self).__init__(cache_path, parent)
        self.__root_path = root_path
        self.__seed_entity_field = seed_entity_field
        self.__entity_fields = entity_fields

    def generate_data_request(self, data_retriever, path):
        """
        Generate a data request for a data retriever.

        Once the data has arrived, the caller is expected to
        call meth:`update_data` and pass in the received
        data payload for processing.

        :param data_retriever: :class:`~tk-framework-shotgunutils:shotgun_data.ShotgunDataRetriever` instance.
        :returns: Request id or None if no work is needed
        """
        self._log_debug("generate_data_request for path %s" % path)

        worker_id = data_retriever.execute_nav_expand(
            path,
            self.__seed_entity_field,
            self.__entity_fields
        )

        return worker_id

    @log_timing
    def update_data(self, sg_data):
        """
        The counterpart to :meth:`generate_data_request`. When the data
        request has been carried out, this method should be called by the calling
        class and the data payload from Shotgun should be provided via the
        sg_data parameter.

        The shotgun nav data is compared against an existing part of the tree and
        a list of differences is returned, indicating which nodes were
        added, deleted and modified, on the following form::

            [
             {
                "data": ShotgunDataItem instance,
                "mode": self.UPDATED|ADDED|DELETED
             },
             {
                "data": ShotgunDataItem instance,
                "mode": self.UPDATED|ADDED|DELETED
             },
             ...
            ]

        :param sg_data: list, resulting from a Shotgun nav_expand query
        :returns: list of updates. see above
        :raises: :class:`ShotgunModelDataError` if no cache is loaded into memory
        """
        if self._cache is None:
            raise ShotgunModelDataError("No data currently loaded in memory!")

        self._log_debug("Updating %s with %s shotgun records." % (self, len(sg_data)))

        item_path = sg_data.get(self._SG_PATH_FIELD, None)

        self._log_debug("Got hierarchy data for path: %s" % (item_path,))

        if not item_path:
            raise ShotgunModelDataError(
                "Unexpected error occurred. Could not determine the path"
                "from the queried hierarchy item."
            )

        if len(self._cache[self.CACHE_CHILDREN]) == 0:
            self._log_debug("In-memory cache is empty.")

        # ensure the data is clean
        self._log_debug("sanitizing data...")
        sg_data = self._sg_clean_data(sg_data)
        self._log_debug("...done!")

        self._log_debug("Generating new tree in memory...")

        if item_path == self.__root_path:
            self._log_debug("This is the root of the tree.")
            parent_item = self._cache
        else:
            parent_item = self._cache[self.CACHE_BY_UID][item_path]

        # create a brand new tree rather than trying to be clever
        # about how we cull intermediate nodes for deleted items
        diff_list = []
        num_adds = 0
        num_deletes = 0
        num_modifications = 0

        # insert the new items in this dict
        new_items = {}

        # analyze the incoming shotgun data
        for sg_item in sg_data["children"]:


            if self._SG_PATH_FIELD not in sg_item:
                # note: leaf nodes of kind 'empty' don't have a path
                unique_field_value = "/".join(parent_item[self.UID], sg_item["label"])

            else:
                unique_field_value = sg_item.get(self._SG_PATH_FIELD)


            # this is an actual entity - insert into our new tree
            item = {
                self.SG_DATA: sg_item,
                self.FIELD: None,
                self.IS_LEAF: not sg_item["has_children"],
                self.UID: unique_field_value,
                self.PARENT: parent_item,
                self.CACHE_CHILDREN: {},
            }

            # if we have children in the existing cache, include those
            if unique_field_value in self._cache[self.CACHE_BY_UID]:
                item[self.CACHE_CHILDREN] = self._cache[self.CACHE_BY_UID][unique_field_value][self.CACHE_CHILDREN]

            new_items[unique_field_value] = item

            # now check with prev data structure to see if it has changed
            if unique_field_value not in self._cache[self.CACHE_BY_UID]:
                # this is a new node that wasn't there before
                diff_list.append({
                    "data": ShotgunDataItem(item),
                    "mode": self.ADDED
                })
                num_adds += 1
            else:
                # record already existed in prev dataset. Check if value has changed
                old_record = self._cache[self.CACHE_BY_UID][unique_field_value][self.SG_DATA]
                if not self._sg_compare_data(old_record, sg_item):
                    diff_list.append({
                        "data": ShotgunDataItem(item),
                        "mode": self.UPDATED
                    })
                    num_modifications += 1

        # now figure out if anything has been removed
        self._log_debug("Diffing new tree against old tree...")

        current_uids = set(parent_item[self.CACHE_CHILDREN].keys())
        new_uids = set(new_items.keys())

        for deleted_uid in current_uids.difference(new_uids):
            item = self._cache[self.CACHE_BY_UID][deleted_uid]
            diff_list.append({
                "data": ShotgunDataItem(item),
                "mode": self.DELETED
            })
            num_deletes += 1

        # lastly swap the new for the old
        parent_item[self.CACHE_CHILDREN] = new_items
        self._cache[self.CACHE_BY_UID].update(new_items)

        # at this point, kick the gc to make sure the memory is freed up
        # despite its cycles.
        gc.collect()

        self._log_debug("Shotgun data (%d records) received and processed. " % len(sg_data))
        self._log_debug("    The new tree is %d records." % len(self._cache[self.CACHE_BY_UID]))
        self._log_debug("    There were %d diffs from in-memory cache:" % len(diff_list))
        self._log_debug("    Number of new records: %d" % num_adds)
        self._log_debug("    Number of deleted records: %d" % num_deletes)
        self._log_debug("    Number of modified records: %d" % num_modifications)

        return diff_list



