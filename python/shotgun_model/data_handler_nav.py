# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import copy

from .data_handler import ShotgunDataHandler
from .errors import ShotgunModelDataError
import sgtk


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

    def __init__(self, root_path, seed_entity_field, entity_fields, cache_path, include_root=None):
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

        :param str include_root: Defines the name of an additional, top-level
            model item that represents the root. In views, this item will appear
            as a sibling to top-level children of the root. This allows for
            UX whereby a user can select an item representing the root without
            having a UI that shows a single, top-level item. An example would
            be displaying published file entity hierarchy with top level items:
            "Assets", "Shots", and "Project Publishes". In this example, the
            supplied arg would look like: ``include_root="Project Publishes"``.
            If ``include_root`` is ``None``, no root item will be added.
        """
        super(ShotgunNavDataHandler, self).__init__(cache_path)
        self.__root_path = root_path
        self.__seed_entity_field = seed_entity_field
        self.__entity_fields = entity_fields
        self.__include_root = include_root

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

    @sgtk.LogManager.log_timing
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
                "data": ShotgunItemData instance,
                "mode": self.UPDATED|ADDED|DELETED
             },
             {
                "data": ShotgunItemData instance,
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

        if self._cache.size == 0:
            self._log_debug("In-memory cache is empty.")

        # ensure the data is clean
        self._log_debug("sanitizing data...")
        sg_data = self._sg_clean_data(sg_data)
        self._log_debug("...done!")

        self._log_debug("Generating new tree in memory...")

        # create a brand new tree rather than trying to be clever
        # about how we cull intermediate nodes for deleted items
        diff_list = []
        num_adds = 0
        num_deletes = 0
        num_modifications = 0

        new_uids = set()

        # a list of sg data dicts to display items for
        child_data = []

        if item_path == self.__root_path:
            self._log_debug("This is the root of the tree.")
            parent_uid = None

            if self.__include_root:
                # the calling code has requested that the root of the tree be
                # displayed as a top-level sibling (to make it easy to discover
                # hierarchy targets attached to the root entity). To do this, we
                # simply make a copy of the root item dictionary (sans children)
                # and add it as an additional child to display. We also set the
                # label to the supplied value.
                root_item = copy.deepcopy(sg_data)
                root_item["label"] = self.__include_root

                # get rid of child data since it'll be displayed as a sibling
                root_item["has_children"] = False
                del root_item["children"]

                # add the root dict to the list of data to build items for
                child_data.append(root_item)
        else:
            parent_uid = item_path

        previous_uids = set(self._cache.get_child_uids(parent_uid))

        # process all the children
        child_data.extend(sg_data["children"])

        # analyze the incoming shotgun data
        for sg_item in child_data:

            if self._SG_PATH_FIELD not in sg_item:
                # note: leaf nodes of kind 'empty' don't have a path
                unique_field_value = "%s/%s" % (parent_uid, sg_item["label"])

            else:
                unique_field_value = sg_item.get(self._SG_PATH_FIELD)

            new_uids.add(unique_field_value)

            # check if item already exists
            already_exists = self._cache.item_exists(unique_field_value)

            # insert the change into the data set directly.
            # if the item already existed and was updated,
            # this returns true
            updated = self._cache.add_item(
                parent_uid=parent_uid,
                sg_data=sg_item,
                field_name=None,
                is_leaf=not sg_item["has_children"],
                uid=unique_field_value
            )

            if not already_exists:
                # item was added
                diff_list.append({
                    "data": self._cache.get_entry_by_uid(unique_field_value),
                    "mode": self.ADDED
                })
                num_adds += 1

            elif updated:
                # item existed but was updated
                diff_list.append({
                    "data": self._cache.get_entry_by_uid(unique_field_value),
                    "mode": self.UPDATED
                })
                num_modifications += 1

        # now figure out if anything has been removed
        for deleted_uid in previous_uids.difference(new_uids):
            item = self._cache.take_item(deleted_uid)
            diff_list.append({
                "data": item,
                "mode": self.DELETED
            })
            num_deletes += 1

        self._log_debug("Shotgun data (%d records) received and processed. " % len(sg_data))
        self._log_debug("    The new tree is %d records." % self._cache.size)
        self._log_debug("    There were %d diffs from in-memory cache:" % len(diff_list))
        self._log_debug("    Number of new records: %d" % num_adds)
        self._log_debug("    Number of deleted records: %d" % num_deletes)
        self._log_debug("    Number of modified records: %d" % num_modifications)

        return diff_list
