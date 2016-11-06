# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from .data_handler import ShotgunDataHandler, log_timing

class ShotgunNavDataHandler(ShotgunDataHandler):
    """
    Data storage for navigation tree data via the nav_expand API endpoint.
    """

    def __init__(self, cache_path, parent):
        """
        :param cache_path: Path to cache file location
        :param parent: Parent QT object
        """
        super(ShotgunNavDataHandler, self).__init__(cache_path, parent)



    def generate_data_request(self, data_retriever):
        """
        Generate a data request for a data retriever.
        Once the data has arrived, update_find_data() will be called.

        :returns: Request id or None if no work is needed
        """





        if not self._sg_data_retriever:
            raise sgtk.TankError("Data retriever is not available!")

        # clear any existing work queue
        for worker_id in self._running_query_lookup.keys():
            self._sg_data_retriever.stop_work(worker_id)
        self._running_query_lookup = {}

        # emit that the data is refreshing.
        self.data_refreshing.emit()

        # get a list of all paths to update. these will be paths for all
        # existing items that are not empty or have no children already queried.
        # we know we always need to refresh the inital path.
        paths = [self._path]
        paths.extend(self.__get_queried_paths_r(self.invisibleRootItem()))

        # query in order of length
        # NOTE: this could have performance implications for large extended trees
        # as a number of queries are sent to the server.
        # TODO: refactor the logic around refresh?
        for path in sorted(set(paths)):
            self._log_debug("Refreshing hierarchy model path: %s" % (path,))

            worker_id = data_retriever.execute_nav_expand(
                path,
                self._seed_entity_field,
                self._entity_fields
            )

            # keep a lookup to map the worker id with the path it is querying
            self._running_query_lookup[worker_id] = path



    @log_timing
    def update_find_data(self, sg_data, hierarchy):
        """
        Adds find data to the data set in memory.

        Runs a comparison between old and new data and returns a list of entity ids
        that have changed between what was previously in the database and what is there now.

        raises an exception if no cache is loaded.

        :returns: list of updated plugin ids. empty list if cache was up to date.
        """
        self._log_debug("Updating %s with %s shotgun records." % (self, len(sg_data)))
        self._log_debug("Hierarchy: %s" % hierarchy)

        if self._cache is None:
            raise ShotgunModelDataError("No data currently loaded in memory!")

        if len(self._cache[self.CACHE_CHILDREN]) == 0:
            self._log_debug("In-memory cache is empty.")

        # ensure the data is clean
        # todo - optimize this!
        self._log_debug("sanitizing data...")
        sg_data = self.__sg_clean_data(sg_data)
        self._log_debug("...done!")

        self._log_debug("Generating new tree in memory...")

        # create a brand new tree rather than trying to be clever
        # about how we cull intermediate nodes for deleted items
        diff_list = []
        num_adds = 0
        num_deletes = 0
        num_modifications = 0

        new_cache = self._init_clear_cache()

        # analyze the incoming shotgun data
        for sg_item in sg_data:

            sub_tree = new_cache
            # maintain a hierarchy of unique ids

            # Create items by drilling down the hierarchy
            for field_name in hierarchy:

                on_leaf_level = (hierarchy[-1] == field_name)

                if not on_leaf_level:
                    # get the parent uid or None if we are at the root level
                    parent_uid = sub_tree.get(self.UID)
                    # generate path for this item
                    unique_field_value = self.__generate_unique_key(parent_uid, field_name, sg_item)
                else:
                    # on the leaf level, use the entity id as the unique key
                    unique_field_value = sg_item["id"]

                # two distinct cases for leaves and non-leaves
                if on_leaf_level:
                    # this is an actual entity - insert into our new tree
                    item = {
                        self.SG_DATA: sg_item,
                        self.FIELD: field_name,
                        self.IS_LEAF: True,
                        self.UID: unique_field_value,
                        self.PARENT: sub_tree,
                        self.CACHE_CHILDREN: {},
                    }
                    sub_tree[self.CACHE_CHILDREN][unique_field_value] = item
                    new_cache[self.CACHE_BY_UID][unique_field_value] = item

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
                        if not self.__compare_shotgun_data(old_record, sg_item):
                            diff_list.append({
                                "data": ShotgunDataItem(item),
                                "mode": self.UPDATED
                            })
                            num_modifications += 1

                else:
                    # not on leaf level yet
                    if unique_field_value not in sub_tree[self.CACHE_CHILDREN]:
                        # item is not yet inserted in our new tree so add it
                        # because these are parent items like project nodes

                        item = {
                            self.SG_DATA: sg_item,
                            self.FIELD: field_name,
                            self.IS_LEAF: False,
                            self.UID: unique_field_value,
                            self.PARENT: sub_tree,
                            self.CACHE_CHILDREN: {},
                        }
                        sub_tree[self.CACHE_CHILDREN][unique_field_value] = item
                        new_cache[self.CACHE_BY_UID][unique_field_value] = item

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
                            current_record = self._cache[self.CACHE_BY_UID][unique_field_value][self.SG_DATA]
                            # don't compare the whole record but just the part that relates to this
                            # intermediate node value. For example, we may be looking at a project node
                            # in the hierarchy but the full sg record contains all the data for a shot.
                            # in this case, just run the comparison on the project subset of the full
                            # shot data dict.
                            if not self.__compare_shotgun_data(current_record.get(field_name), sg_item.get(field_name)):
                                diff_list.append({
                                    "data": ShotgunDataItem(item),
                                    "mode": self.UPDATED
                                })
                                num_modifications += 1

                    # recurse down to the next level
                    sub_tree = sub_tree[self.CACHE_CHILDREN][unique_field_value]

        # now figure out if anything has been removed
        self._log_debug("Diffing new tree against old tree...")

        current_uids = set(self._cache[self.CACHE_BY_UID].keys())
        new_uids = set(new_cache[self.CACHE_BY_UID].keys())

        for deleted_uid in current_uids.difference(new_uids):
            item = self._cache[self.CACHE_BY_UID][deleted_uid]
            diff_list.append({
                "data": ShotgunDataItem(item),
                "mode": self.DELETED
            })
            num_deletes += 1

        # lastly swap the new for8 the old
        self._clear_cache()

        # at this point, kick the gc to make sure the memory is freed up
        # despite its cycles.
        gc.collect()

        # and set the new cache
        self._cache = new_cache

        self._log_debug("Shotgun data (%d records) received and processed. " % len(sg_data))
        self._log_debug("    The new tree is %d records." % len(self._cache[self.CACHE_BY_UID]))
        self._log_debug("    There were %d diffs from in-memory cache:" % len(diff_list))
        self._log_debug("    Number of new records: %d" % num_adds)
        self._log_debug("    Number of deleted records: %d" % num_deletes)
        self._log_debug("    Number of modified records: %d" % num_modifications)

        return diff_list





    #
    #
    #
    #
    #
    # def __on_sg_data_arrived(self, sg_data):
    #     """
    #     Handle asynchronous navigation data arriving after a
    #     :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` request.
    #
    #     :param dict sg_data: The data returned from the api call.
    #     """
    #     # ensure we have a path for the item
    #     item_path = sg_data.get(self._SG_PATH_FIELD, None)
    #     self._log_debug("Got hierarchy data for path: %s" % (item_path,))
    #
    #     if not item_path:
    #         raise sgtk.TankError(
    #             "Unexpected error occured. Could not determine the path"
    #             "from the queried hierarchy item."
    #         )
    #
    #     # see if we have an item for the path
    #     item = self.item_from_path(item_path)
    #
    #     if item:
    #         # check item and children to see if data has been updated
    #         self._log_debug(
    #             "Item exists in tree. Ensuring up-to-date...")
    #         modifications_made = self.__update_subtree(item, nav_data)
    #         self._log_debug("...done!")
    #
    #     else:
    #         self._log_debug("Detected new item. Adding in-situ to tree...")
    #         self.__insert_subtree(nav_data)
    #         self._log_debug("...done!")
    #         modifications_made = True
    #
    #     # last step - save our tree to disk for fast caching next time!
    #     # todo: the hierarchy data is queried lazily. so 2this implies a
    #     # write to disk each time the user expands and item. consider the
    #     # performance of this setup and whether this logic should be altered.
    #     if self._data_handler.is_modified():
    #         try:
    #             self._data_handler.save_cache()
    #         except Exception, e:
    #             self._log_warning("Couldn't save cache data to disk: %s" % e)
    #
    #     if not self._running_query_lookup.keys():
    #         # no more data queries running. all data refreshed
    #         self.data_refreshed.emit(modifications_made)
    #
    # def __insert_subtree(self, nav_data):
    #     """
    #     Inserts a subtree for the item represented by ``nav_data``.
    #
    #     The method first creates the item, then attempts to update/populate its
    #     children.
    #
    #     :param dict nav_data: A dictionary of item data as returned via async
    #         call to :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`.
    #     """
    #
    #     item = self._create_item(nav_data)
    #     self.__update_subtree(item, nav_data)
    #
    # def __update_item(self, item, data):
    #     """
    #     Updates the supplied item with the newly queried data.
    #
    #     :param item: A :class:`~PySide.QtGui.QStandardItem` instance to update.
    #     :param dict data: The newly queried data.
    #
    #     :return: ``True`` if the item was updated, ``False`` otherwise.
    #     """
    #
    #     # get a copy of the data and remove the child item info so that
    #     # each item in the tree only stores data about itself
    #     new_item_data = copy.deepcopy(data)
    #     if "children" in data.keys():
    #         del new_item_data["children"]
    #
    #     # compare with the item's existing data
    #     old_item_data = get_sg_data(item)
    #     if self._sg_compare_data(old_item_data, new_item_data):
    #         # data has not changed
    #         return False
    #
    #     # data differs. set the new data
    #     item.setData(sanitize_for_qt_model(new_item_data), self.SG_DATA_ROLE)
    #
    #     # ensure the label is updated
    #     item.setText(data["label"])
    #
    #     return True
    #
    # def __update_subtree(self, item, nav_data):
    #     """
    #     Updates the subtree rooted at the supplied item with the supplied data.
    #
    #     This method updates the item and its children given a dictionary of
    #     newly queried data from Shotgun. It first checks to see if any items
    #     have been removed, then adds or updates children as needed.
    #
    #     :param item: A :class:`~PySide.QtGui.QStandardItem` instance to update.
    #     :param dict nav_data: The data returned by a
    #         :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` call.
    #
    #     :returns: ``True`` if the subtree was udpated, ``False`` otherwise.
    #     """
    #
    #     # ensure the item's data is up-to-date
    #     subtree_updated = self.__update_item(item, nav_data)
    #
    #     children_data = nav_data.get("children")
    #
    #     if not children_data:
    #         return subtree_updated
    #
    #     child_paths = []
    #
    #     for child_data in children_data:
    #
    #         if self._SG_PATH_FIELD not in child_data:
    #             item_data = get_sg_data(item)
    #             parent_path = item_data[self._SG_PATH_FIELD]
    #
    #             # handle the case where there are child leaves without paths.
    #             # these tend to be just items that make it clear there are no
    #             # children. example: "No Shots"
    #             # create a dummy path so that we can find it later
    #             child_data[self._SG_PATH_FIELD] = "/".join(
    #                 [parent_path, child_data["label"]])
    #
    #         child_paths.append(child_data[self._SG_PATH_FIELD])
    #
    #     # iterate over item's children to see if any need to be removed.
    #     # this would be the case where the supplied nav_data does not contain
    #     # information about an item that currently exists. iterate in reverse
    #     # order so we can remove items in place without altering subsequent rows
    #     for row in reversed(range(0, item.rowCount())):
    #         child_item = item.child(row)
    #         child_data = get_sg_data(child_item)
    #         child_path = child_data[self._SG_PATH_FIELD]
    #         if child_path not in child_paths:
    #             # removing item
    #             #self._log_debug("Removing item: %s" % (child_item,))
    #             #self._before_item_removed(child_item)
    #             # todo - update with new data backend
    #             item.removeRow(row)
    #             subtree_updated = True
    #
    #     # add/update the children for the supplied item
    #     for (row, child_data) in enumerate(children_data):
    #         child_path = child_data[self._SG_PATH_FIELD]
    #         child_item = self.item_from_path(child_path)
    #
    #         if child_item:
    #             # child already exists, ensure data is up-to-date
    #             subtree_updated = self.__update_item(child_item, child_data) \
    #                 or subtree_updated
    #         else:
    #             # child item does not exist, create it at the specified row
    #             self._create_item(child_data, parent=item, row=row)
    #             subtree_updated = True
    #
    #     return subtree_updated
    #
