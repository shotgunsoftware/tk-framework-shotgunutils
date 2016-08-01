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
import hashlib
import os
import sys

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

# framework imports
from .shotgun_query_model import ShotgunQueryModel
from .util import get_sg_data, sanitize_qt, sanitize_for_qt_model
from ..util import color_mix

# logger for this module
logger = sgtk.platform.get_logger(__name__)


class ShotgunHierarchyModel(ShotgunQueryModel):
    """
    A QT Model representing a Shotgun hierarchy query (``nav_expand()``).

    This class implements the
    :class:`~shotgunutils.shotgun_model.ShotgunQueryModel` interface. It is
    cached and refreshes its data asynchronously.

    In order to use this class, you normally subclass it and implement certain
    key data methods for setting up queries, customizing etc. Then you connect
    your class to a :class:`~PySide.QtGui.QAbstractItemView` of some sort which
    will display the result. 

    The model stores a single column, lazy-loaded Shotgun Hierarchy as queried
    via the ``nav_expand()`` python-api method. The structure of items in the
    hierarchy mimics what is found in Shotgun as configured in each project's
    *Tracking Settings*.
    """

    # data field that uniquely identifies an entity
    SG_DATA_UNIQUE_ID_FIELD = "url"

    # data role used to track whether more data has been fetched for items
    SG_ITEM_FETCHED_MORE = QtCore.Qt.UserRole + 3

    def __init__(self, parent, schema_generation=0, bg_task_manager=None):
        """
        Initialize the Hierarcy model.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        """

        super(ShotgunHierarchyModel, self).__init__(parent, bg_task_manager)

        self._schema_generation = schema_generation

        # flag to indicate a full refresh
        self._request_full_refresh = False

        # is the model set up with a query?
        self._has_query = False

        # keeps track of the currently running queries by mapping the id
        # returned by the data retriever to the path/url being queried
        self._running_query_lookup = {}

        # keep these icons around so they're not constantly being created
        self._folder_icon = QtGui.QIcon(
            ":tk-framework-shotgunutils/icon_Folder.png")
        self._none_icon = QtGui.QIcon(
            ":tk-framework-shotgunutils/icon_None.png")

        # Define the foreground color of "empty" items.
        # These special items are used as placeholders in the tree where the
        # parent has no children. An example would be `Shots > No Shots` where
        # `No Shots` is the "empty" item. By default, the color is a mix of the
        # application instance's base and text colors. This will typically
        # result in a dimmed appearance for these special items indicating that
        # they are not clickable. This makes goes outside the typical bounds of
        # the model by pulling the palette colors from the app instance. This
        # can be overridden in subclasses via ``_finalize_item()`` though.
        base_color = QtGui.QApplication.instance().palette().base().color()
        text_color = QtGui.QApplication.instance().palette().text().color()
        self._empty_item_color = color_mix(text_color, 1, base_color, 2)

    ############################################################################
    # public methods

    def clear(self):
        """
        Removes all items (including header items) from the model and
        sets the number of rows and columns to zero.
        """

        # we are not looking for any data from the async processor
        self._running_query_lookup = {}

        super(ShotgunHierarchyModel, self).clear()

    def destroy(self):
        """
        Call this method prior to destroying this object.
        This will ensure all worker threads etc are stopped.
        """
        self._running_query_lookup = {}

        super(ShotgunHierarchyModel, self).destroy()

    def hard_refresh(self):
        """
        Clears any caches on disk, then refreshes the data.
        """
        if not self._has_query:
            # no query in this model yet
            return

        # when data arrives, force full rebuild
        self._request_full_refresh = True

        super(ShotgunHierarchyModel, self).hard_refresh()

    def item_from_url(self, url):
        """
        Returns a :class:`~PySide.QtGui.QStandardItem` for the supplied url.

        Returns ``None`` if not found.

        :param str url: The url to search the tree for. The urls match those
            used by and returned from the python-api's ``nav_expand()`` method.
        :returns: :class:`~PySide.QtGui.QStandardItem` or ``None`` if not found
        """
        return self._get_item_by_unique_id(url)

    ############################################################################
    # methods overridden from Qt base class

    def hasChildren(self, index):
        """
        Returns True if parent has any children; otherwise returns False.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """

        if not index.isValid():
            return super(ShotgunHierarchyModel, self).hasChildren(index)

        item = self.itemFromIndex(index)
        item_data = get_sg_data(item)

        if not item_data:
            # could not get the item data, let the base class check
            return super(ShotgunHierarchyModel, self).hasChildren(index)

        # the nav data knows whether it has children
        return item_data.get("has_children", False)

    def fetchMore(self, index):
        """
        Returns True if there is more data available for parent; otherwise
        returns False.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """

        if not index.isValid():
            return

        item = self.itemFromIndex(index)
        item_data = get_sg_data(item)

        if not item_data:
            return

        path = item_data["url"]

        # set the flag to prevent subsequent attempts to fetch more
        item.setData(True, self.SG_ITEM_FETCHED_MORE)

        # query the information for this item to populate its children.
        # the slot for handling worker success will handle inserting the
        # queried data into the tree.
        logger.debug("Fetching more for item: %s" % (item.text(),))
        self._query_hierarchy(
            path,
            self._seed_entity_field,
            self._entity_fields
        )

    def canFetchMore(self, index):
        """
        Returns True if there is more data available for parent; otherwise
        returns False.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """

        if not index.isValid():
            return False

        # get the item and it's stored hierarchy data
        item = self.itemFromIndex(index)

        if item.data(self.SG_ITEM_FETCHED_MORE):
            # more data has already been queried for this item
            return False

        item_data = get_sg_data(item)

        if not item_data:
            return False

        # the number of existing child items
        child_item_count = item.rowCount()

        # we can fetch more if there are no children already and the item
        # has children.
        return child_item_count == 0 and item_data.get("has_children", False)

    ############################################################################
    # protected methods

    def _create_item(self, data, parent=None):
        """
        Creates a model item given the supplied data and optional parent.

        The supplied ``data`` corresponds to the results of a call to the
        ``nav_expand()`` api method. The data will be stored on the new item via
        the ``SG_DATA_ROLE``.

        :param dict data: The hierarchy data to use when creating the item.
        :param parent: Optional :class:`~PySide.QtGui.QStandardItem` instance
            to parent the created item to.

        :return: The new :class:`~PySide.QtGui.QStandardItem` instance.
        """

        # if this is the root item, just return the invisible root item that
        # comes with the model
        if data.get("ref", {}).get("kind") == "root":
            return self.invisibleRootItem()

        item = self.SG_QUERY_MODEL_ITEM_CLASS(data["label"])
        item.setEditable(False)

        # keep tabs of which items we are creating
        item.setData(True, self.IS_SG_MODEL_ROLE)

        # we have not fetched more data for this item yet
        item.setData(False, self.SG_ITEM_FETCHED_MORE)

        # attach the nav data for access later
        self._update_item(item, data)

        # allow item customization prior to adding to model
        self._item_created(item)

        # set up default thumb
        self._populate_default_thumbnail(item)

        self._populate_item(item, data)

        self._set_tooltip(item, data)

        # run the finalizer (always runs on construction, even via cache)
        self._finalize_item(item)

        # identify a parent if none supplied. could be found via the
        # `parent_url` supplied in the data or the root if no parent item
        # exists.
        parent = parent or self.item_from_url(data.get("parent_url")) or \
            self.invisibleRootItem()

        # example of using sort/filter proxy model
        parent.appendRow(item)

        return item

    def _get_data_cache_path(self, cache_seed=None):
        """
        Calculates and returns a cache path to use for this instance's query.

        :param cache_seed: Cache seed supplied to the ``__init__`` method.

        :return: The path to use when caching the model data.
        :rtype: str
        """

        # hashes to use to generate the cache path
        params_hash = hashlib.md5()
        entity_field_hash = hashlib.md5()

        # even though the navigation path provides a nice organizational
        # structure for caching, it can get long. to avoid MAX_PATH issues on
        # windows, just hash it
        params_hash.update(str(self._path))

        # include the schema generation number for clients
        params_hash.update(str(self._schema_generation))

        # If this value changes over time (like between Qt4 and Qt5), we need to
        # assume our previous user roles are invalid since Qt might have taken
        # it over. If role's value is 32, don't add it to the hash so we don't
        # invalidate PySide/PyQt4 caches.
        if QtCore.Qt.UserRole != 32:
            params_hash.update(str(QtCore.Qt.UserRole))

        # include the cache_seed for additional user control over external state
        params_hash.update(str(cache_seed))

        # iterate through the sorted entity fields to ensure consistent order
        for (entity_type, fields) in sorted(self._entity_fields.iteritems()):
            for field in fields:
                entity_field_hash.update("%s.%s" % (entity_type, field))

        # convert the seed entity field into a path segment.
        # example: Version.entity => Version/entity
        seed_entity_field_path = os.path.join(
            *self._seed_entity_field.split("."))

        # organize files on disk based on the seed_entity field path segment and
        # then param and entity field hashes
        data_cache_path = os.path.join(
            self._bundle.cache_location,
            "sg_nav",
            seed_entity_field_path,
            params_hash.hexdigest(),
            entity_field_hash.hexdigest(),
        )

        # warn if the path is longer than the windows max path limitation
        if sys.platform == "win32" and len(data_cache_path) > 250:
            logger.warning(
                "Shotgun hierarchy data cache file path may be affected by "
                "windows MAX_PATH limitation."
            )

        return data_cache_path

    def _get_queried_urls_r(self, item):
        """
        Returns a list of previously queried urls for items under the supplied
        parent item.

        This method is used to identify which items need to be re-queried when a
        model refresh is requested. It recursively iterates over the supplied
        item's children, looking for non-empty leaf nodes that have children.

        :param item: The parent :class:`~PySide.QtGui.QStandardItem` instance
            to use when checking for queried children.

        :return: A list of urls
        :rtype: list
        """

        urls = []

        # iterate over all the child items
        for row in range(item.rowCount()):

            child_item = item.child(row)

            data = get_sg_data(child_item)
            if data.get("ref", {}).get("kind") == "empty":
                # empty items don't have valid urls to query
                continue

            if child_item.rowCount() == 0:
                # this is an existing leaf node whose (potential) children have
                # not been queried. do nothing.
                continue

            urls.append(data["url"])

            # recurse
            urls.extend(self._get_queried_urls_r(child_item))

        return urls

    def _insert_subtree(self, nav_data):
        """
        Inserts a subtree for the item represented by ``nav_data``.

        The method first creates the item, then attempts to update/populate its
        children.

        :param dict nav_data: A dictionary of item data as returned via async
            call to ``nav_expand``.
        """

        item = self._create_item(nav_data)
        self._update_subtree(item, nav_data)

    def _item_created(self, item):
        """
        Checks to see if the item is an "empty" item and sets the foreground
        role accordingly.

        :param item: The :class:`~PySide.QtGui.QStandardItem` that was created.
        """

        # call base class implementation as per docs
        super(ShotgunHierarchyModel, self)._item_created(item)

        data = get_sg_data(item)

        if data.get("ref", {}).get("kind") == "empty":
            item.setForeground(self._empty_item_color)

    def _load_data(
        self,
        path,
        seed_entity_field,
        entity_fields=None,
        cache_seed=None
    ):
        """
        This is the main method to use to configure the hierarchy model. You
        basically pass a specific ``nav_expand`` query to the model and it will
        start tracking this particular set of parameters.

        Any existing data contained in the model will be cleared.

        This method will not call the Shotgun API. If cached data is available,
        this will be immediately loaded (this operation is very fast even for
        substantial amounts of data).

        If you want to refresh the data contained in the model (which you
        typically want to), call the :meth:`_refresh_data()` method.

        :param str path: The path (url) to the root of the hierarchy to display.
            This corresponds to the ``path`` argument of the ``nav_expand()``
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

        :param cache_seed:
            Advanced parameter. With each shotgun query being cached on disk,
            the model generates a cache seed which it is using to store data on
            disk. Since the cache data on disk is a reflection of a particular
            ``nav_dev()`` query, this seed is typically generated from the
            seed entity field and return entity fields supplied to this method.
            However, in cases where you are doing advanced subclassing, for
            example when you are culling out data based on some external state,
            the model state does not solely depend on the shotgun parameters. It
            may also depend on some external factors. In this case, the cache
            seed should also be influenced by those parameters and you can pass
            an external string via this parameter which will be added to the
            seed.

        .. note:: For additional information on the ``path``,
            ``seed_entity_field``, and ``entity_fields`` arguments, please see
            the `<python-api docs http://developer.shotgunsoftware.com/python-api/reference.html#shotgun>`_.

        :return:
        """

        # we are changing the query
        self.query_changed.emit()

        # clear out old data
        self.clear()

        self._has_query = True

        self._path = path
        self._seed_entity_field = seed_entity_field
        self._entity_fields = entity_fields or {}

        # get the cache path based on these new data query parameters
        self._cache_path = self._get_data_cache_path(cache_seed)

        # print some debug info
        logger.debug("")
        logger.debug("Model Reset for: %s" % (self,))
        logger.debug("Path: %s" % (self._path,))
        logger.debug("Seed entity field: %s" % (self._seed_entity_field,))
        logger.debug("Entity fields: %s" % (self._entity_fields,))

        logger.debug("First population pass: Calling _load_external_data()")
        self._load_external_data()
        logger.debug("External data population done.")

        # only one column. give it a default value
        self.setHorizontalHeaderLabels(
            ["%s Hierarchy" % (self._seed_entity_field,)]
        )

        return self._load_cached_data()

    def _on_data_retriever_work_failure(self, uid, msg):
        """
        Asynchronous callback - the data retriever failed to do some work

        :param uid: The unique id of the work that failed
        :param msg: The error message returned for the failure
        """
        uid = sanitize_qt(uid)  # qstring on pyqt, str on pyside
        msg = sanitize_qt(msg)

        if uid not in self._running_query_lookup:
            # not our job. ignore
            logger.debug("Retrieved error from data worker: %s" % (msg,))
            return

        url = self._running_query_lookup[uid]

        # query is done. clear it out
        del self._running_query_lookup[uid]

        full_msg = (
            "Error retrieving data from Shotgun."
            "  URL: %s"
            "  Error: %s"
        ) % (url, msg)
        self.data_refresh_fail.emit(full_msg)
        logger.warning(full_msg)

    def _on_data_retriever_work_completed(self, uid, request_type, data):
        """
        Signaled whenever the data retriever completes some work.
        This method will dispatch the work to different methods
        depending on what async task has completed.

        :param uid:             The unique id of the work that completed
        :param request_type:    Type of work completed
        :param data:            Result of the work
        """
        uid = sanitize_qt(uid)  # qstring on pyqt, str on pyside
        data = sanitize_qt(data)

        logger.debug("Received worker payload of type: %s" % (request_type,))

        if uid not in self._running_query_lookup:
            # not our job. ignore.
            return

        # query is done. clear it out
        del self._running_query_lookup[uid]

        nav_data = data["nav"]
        self._on_nav_data_arrived(nav_data)

    def _on_nav_data_arrived(self, nav_data):
        """
        Handle asynchronous navigation data arriving after a nav_expand request.

        :param dict nav_data: The data returned from the api call.
        """

        logger.debug("--> Shotgun data arrived. (%s records)" % len(nav_data))

        # pre-process data
        nav_data = self._before_data_processing(nav_data)

        if self._request_full_refresh:
            # full refresh requested

            # reset flag for next request
            self._request_full_refresh = False

            logger.debug("Rebuilding tree...")
            self.clear()
            self._load_external_data()
            self._insert_subtree(nav_data)
            logger.debug("...done!")

            modifications_made = True

        else:

            # ensure we have a url for the item
            item_url = nav_data.get("url", None)
            logger.debug("Got hierarchy data for url: %s" % (item_url,))

            if not item_url:
                raise sgtk.TankError(
                    "Unexpected error occured. Could not determine the url "
                    "from the queried hierarchy item."
                )

            # see if we have an item for the url
            item = self.item_from_url(item_url)

            if item:
                # check item and children to see if data has been updated
                logger.debug(
                    "Item exists in tree. Ensuring up-to-date...")
                modifications_made = self._update_subtree(item, nav_data)
                logger.debug("...done!")

            else:
                logger.debug("Detected new item. Adding in-situ to tree...")
                self._insert_subtree(nav_data)
                logger.debug("...done!")
                modifications_made = True

        # last step - save our tree to disk for fast caching next time!
        # todo: the hierarchy data is queried lazily. so this implies a
        # write to disk each time the user expands and item. consider the
        # performance of this setup and whether this logic should be altered.
        if modifications_made:
            logger.debug("Saving tree to disk %s..." % self._cache_path)
            try:
                self._save_to_disk()
                logger.debug("...saving complete!")
            except Exception, e:
                logger.warning("Couldn't save cache data to disk: %s" % e)

        if not self._running_query_lookup.keys():
            # no more data queries running. all data refreshed
            self.data_refreshed.emit(modifications_made)

    def _populate_default_thumbnail(self, item):
        """
        Sets the icon for the supplied item based on its "kind" as returned
        by the ``nav_expand()`` api call.

        :param item: The :class:`~PySide.QtGui.QStandardItem` item to set the
            icon for.
        """

        data = get_sg_data(item)

        item_ref = data.get("ref", {})
        item_kind = item_ref.get("kind")

        if item_kind == "entity":
            entity_type = item_ref.get("value", {}).get("type")
            icon = self._shotgun_globals.get_entity_type_icon(entity_type)
        elif item_kind == "entity_type":
            entity_type = item_ref["value"]
            icon = self._shotgun_globals.get_entity_type_icon(entity_type)
        elif item_kind == "list":
            icon = self._folder_icon
        elif item_kind == "no_entity":
            # this is typically items like "Shots with no Sequence"
            icon = self._folder_icon
        else:
            icon = self._none_icon

        if icon:
            item.setIcon(icon)

    def _query_hierarchy(self, path, seed_entity_field, entity_fields):
        """
        Triggers the async ``nav_expand()`` query based on the supplied fields.

        This method returns immediately and does not block.

        .. note:: For details on the ``path``, ``seed_entity_field``, and
            ``entity_fields`` arguments, please see the
            `<python-api docs http://developer.shotgunsoftware.com/python-api/reference.html#shotgun>`_.

        :return:
        """

        if not self._sg_data_retriever:
            raise sgtk.TankError("Data retriever is not available!")

        # reverse the query lookup to see if the path is already being queried
        path_to_worker_ids = \
            dict((v, k) for k, v in self._running_query_lookup.items())

        if path in path_to_worker_ids:
            # a query is already running for this path. stop it.
            worker_id = path_to_worker_ids[path]
            self._sg_data_retriever.stop_work(worker_id)

            # forget about the old query
            del self._running_query_lookup[worker_id]

        self.data_refreshing.emit()

        logger.debug("** Querying hierarchy item: %s" % (path,))

        worker_id = self._sg_data_retriever.execute_nav_expand(
            path, seed_entity_field, entity_fields)

        # keep a lookup to map the worker id with the url it is querying
        self._running_query_lookup[worker_id] = path

    def _refresh_data(self):
        """
        Rebuild the data in the model to ensure it is up to date.

        This call should be asynchronous and return instantly. The update should
        be applied as soon as the data from Shotgun is returned.

        If the model is empty (no cached data) no data will be shown at first
        while the model fetches data from Shotgun.

        As soon as a local cache exists, data is shown straight away and the
        shotgun update happens silently in the background.

        If data has been added, this will be injected into the existing
        structure. In this case, the rest of the model is intact, meaning that
        also selections and other view related states are unaffected.

        If data has been modified or deleted, a full rebuild is issued, meaning
        that all existing items from the model are removed. This does affect
        view related states such as selection.
        """

        # get a list of all urls to update. these will be paths for all existing
        # items that are not empty or have no children already queried. we know
        # we always need to refresh the inital path.
        urls = [self._path]
        urls.extend(self._get_queried_urls_r(self.invisibleRootItem()))

        # query in order of length
        for url in sorted(set(urls)):
            logger.debug("Refreshing hierarchy model url: %s" % (url,))
            self._query_hierarchy(
                url,
                self._seed_entity_field,
                self._entity_fields
            )

    def _update_item(self, item, data):
        """
        Updates the supplied item with the newly queried data.

        :param item: A :class:`~PySide.QtGui.QStandardItem` instance to update.
        :param dict data: The newly queried data.

        :return: ``True`` if the item was updated, ``False`` otherwise.
        """

        # get a copy of the data and remove the child item info so that
        # each item in the tree only stores data about itself
        new_item_data = copy.deepcopy(data)
        if "children" in data.keys():
            del new_item_data["children"]

        # make sure the data is clean
        new_item_data = self._sg_clean_data(new_item_data)

        # compare with the item's existing data
        old_item_data = get_sg_data(item)
        if self._sg_compare_data(old_item_data, new_item_data):
            # data has not changed
            return False

        # data differs. set the new data
        item.setData(sanitize_for_qt_model(new_item_data), self.SG_DATA_ROLE)

        return True

    def _update_subtree(self, item, nav_data):
        """
        Updates the subtree rooted at the supplied item with the supplied data.

        This method updates the item and its children given a dictionary of
        newly queried data from Shotgun. It first checks to see if any items
        have been remove, then adds or updates children as needed.

        :param item: A :class:`~PySide.QtGui.QStandardItem` instance to update.
        :param dict nav_data: The data returned by a ``nav_expand()`` call.

        :returns: ``True`` if the subtree was udpated, ``False`` otherwise.
        """

        # ensure the item's data is up-to-date
        subtree_updated = self._update_item(item, nav_data)

        children_data = nav_data.get("children")

        if not children_data:
            return subtree_updated

        child_urls = []

        for child_data in children_data:

            if "url" not in child_data:
                item_data = get_sg_data(item)
                parent_url = item_data["url"]

                # handle the case where there are child leaves without urls.
                # these tend to be just items that make it clear there are no
                # children. example: "No Shots"
                # create a dummy url so that we can find it later
                child_data["url"] = "/".join([parent_url, child_data["label"]])

            child_urls.append(child_data["url"])

        # iterate over item's children to see if any need to be removed.
        # this would be the case where the supplied nav_data does not contain
        # information about an item that currently exists. iterate in reverse
        # order so we can remove items in place without altering subsequent rows
        for row in reversed(range(0, item.rowCount())):
            child_item = item.child(row)
            child_data = get_sg_data(child_item)
            child_url = child_data["url"]
            if child_url not in child_urls:
                # removing item
                logger.debug("Removing item: %s" % (child_item,))
                self._before_item_removed(child_item)
                item.removeRow(row)
                subtree_updated = True

        # add/update the children for the supplied item
        for (row, child_data) in enumerate(children_data):
            child_url = child_data["url"]
            child_item = self.item_from_url(child_url)

            if child_item:
                # child already exists, ensure data is up-to-date
                subtree_updated = self._update_item(child_item, child_data) \
                    or subtree_updated
            else:
                # child item does not exist, create it
                self._create_item(child_data, parent=item)
                subtree_updated = True

        return subtree_updated