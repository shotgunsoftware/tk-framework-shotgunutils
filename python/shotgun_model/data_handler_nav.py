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
    Data storage for navigation tree data via the nav_expand API endpoint.
    """

    # constant values to refer to the fields where the paths are stored in the
    # returned navigation data.
    _SG_PATH_FIELD = "path"
    _SG_PARENT_PATH_FIELD = "parent_path"

    def __init__(self, root_path, seed_entity_field, entity_fields, cache_path, parent):
        """
        :param cache_path: Path to cache file location
        :param parent: Parent QT object
        """
        super(ShotgunNavDataHandler, self).__init__(cache_path, parent)
        self.__root_path = root_path
        self.__seed_entity_field = seed_entity_field
        self.__entity_fields = entity_fields

    def generate_data_request(self, data_retriever, path):
        """
        Generate a data request for a data retriever.
        Once the data has arrived, update_data() will be called.

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
        Adds data to the data set in memory.

        Runs a comparison between old and new data and returns a list of items
        that have changed between what was previously in the database and what is there now.

        raises an exception if no cache is loaded.

        :returns: list of updated plugin ids. empty list if cache was up to date.
        """
        if self._cache is None:
            raise ShotgunModelDataError("No data currently loaded in memory!")

        self._log_debug("Updating %s with %s shotgun records." % (self, len(sg_data)))

        item_path = sg_data.get(self._SG_PATH_FIELD, None)

        self._log_debug("Got hierarchy data for path: %s" % (item_path,))

        if not item_path:
            raise ShotgunModelDataError(
                "Unexpected error occured. Could not determine the path"
                "from the queried hierarchy item."
            )

        if len(self._cache[self.CACHE_CHILDREN]) == 0:
            self._log_debug("In-memory cache is empty.")

        # ensure the data is clean
        # todo - optimize this!
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

            unique_field_value = sg_item[self._SG_PATH_FIELD]

            # this is an actual entity - insert into our new tree
            item = {
                self.SG_DATA: sg_item,
                self.FIELD: None,
                self.IS_LEAF: not sg_item["has_children"],
                self.UID: unique_field_value,
                self.PARENT: parent_item,
                self.CACHE_CHILDREN: {},
            }
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



