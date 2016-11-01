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
from .shotgun_hierarchy_item import ShotgunHierarchyItem
from .shotgun_query_model import ShotgunQueryModel
from .util import get_sg_data, sanitize_qt, sanitize_for_qt_model


class ShotgunHierarchyModel(ShotgunQueryModel):
    """
    A Qt Model representing a Shotgun hierarchy.

    .. warning::

        Use of this model requires version Shotgun ``v7.0.2`` or later.
        Attempts to construct an instance of this model on an older version of
        Shotgun will result with a single item in the model saying that
        Hierarchy model isn't supported. A warning will also be logged.

    This class implements a standard :class:`~PySide.QtCore.QAbstractItemModel`
    specialized to hold the contents of a particular Shotgun query. It is cached
    and refreshes its data asynchronously.

    In order to use this class, you normally subclass it and implement certain
    key data methods for setting up queries, customizing etc. Then you connect
    your class to a :class:`~PySide.QtGui.QAbstractItemView` of some sort which
    will display the result. 

    The model stores a single column, lazy-loaded Shotgun Hierarchy as queried
    via the :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`
    python-api method. The structure of items in the hierarchy mimics what is
    found in Shotgun as configured in each project's
    `Tracking Settings <https://support.shotgunsoftware.com/hc/en-us/articles/219031138-Project-Tracking-Settings>`_.
    """

    # data field that uniquely identifies an entity
    _SG_DATA_UNIQUE_ID_FIELD = "path"

    # constant values to refer to the fields where the paths are stored in the
    # returned navigation data.
    _SG_PATH_FIELD = "path"
    _SG_PARENT_PATH_FIELD = "parent_path"

    # data role used to track whether more data has been fetched for items
    _SG_ITEM_FETCHED_MORE = QtCore.Qt.UserRole + 3

    # use hierarchy items when building the model
    _SG_QUERY_MODEL_ITEM_CLASS = ShotgunHierarchyItem

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns: A string representation of this instance
        """
        return "<%s path:%s seed:%s>" % (
            self.__class__.__name__, self._path, self._seed_entity_field)

    def __init__(self, parent, schema_generation=0, bg_task_manager=None):
        """
        Initialize the Hierarcy model.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        """

        super(ShotgunHierarchyModel, self).__init__(parent, bg_task_manager)

        # check for hierarchy support
        (self._hierarchy_is_supported, self._hierarchy_not_supported_reason) = \
            self.__hierarchy_is_supported()

        if not self._hierarchy_is_supported:
            self._log_warning(self._hierarchy_not_supported_reason)

        self._path = None
        self._seed_entity_field = None
        self._entity_fields = None

        self._schema_generation = schema_generation

        # flag to indicate a full refresh
        self._request_full_refresh = False

        # is the model set up with a query?
        self._has_query = False

        # keeps track of the currently running queries by mapping the id
        # returned by the data retriever to the path being queried
        self._running_query_lookup = {}

        # keep these icons around so they're not constantly being created
        self._folder_icon = QtGui.QIcon(
            ":tk-framework-shotgunutils/icon_Folder.png")
        self._none_icon = QtGui.QIcon(
            ":tk-framework-shotgunutils/icon_None_dark.png")

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

        # local import to avoid doc generation issues
        from ..utils import color_mix
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

    def item_from_path(self, path):
        """
        Returns a :class:`~PySide.QtGui.QStandardItem` for the supplied path.

        Returns ``None`` if not found.

        :param str path: The path to search the tree for. The paths match those
            used by and returned from the python-api's
            :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` method.
        :returns: :class:`~PySide.QtGui.QStandardItem` or ``None`` if not found
        """
        return self._get_item_by_unique_id(path)

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
        return item.has_children()

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

        path = item_data[self._SG_PATH_FIELD]

        # set the flag to prevent subsequent attempts to fetch more
        item.setData(True, self._SG_ITEM_FETCHED_MORE)

        # query the information for this item to populate its children.
        # the slot for handling worker success will handle inserting the
        # queried data into the tree.
        self._log_debug("Fetching more for item: %s" % (item.text(),))
        self.__query_hierarchy(
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

        if not self._hierarchy_is_supported:
            return False

        if not index.isValid():
            return False

        # get the item and it's stored hierarchy data
        item = self.itemFromIndex(index)

        if item.data(self._SG_ITEM_FETCHED_MORE):
            # more data has already been queried for this item
            return False

        item_data = get_sg_data(item)

        if not item_data:
            return False

        # the number of existing child items
        child_item_count = item.rowCount()

        # we can fetch more if there are no children already and the item
        # has children.
        return child_item_count == 0 and item.has_children()

    ############################################################################
    # protected methods

    def _get_default_path(self):
        """
        Returns the default path to use for loading data.

        Attempts to determine the current context and root at the context's
        project level. If no project can be determined, the root path will
        be returned.

        :return: The default path to load data from.
        :rtype: ``str``
        """

        # default, root path
        path = "/"

        current_engine = sgtk.platform.current_engine()
        if current_engine:
            # an engine is running
            project = current_engine.context.project
            if project:
                # we have a project in the context
                path = "/Project/%s" % (project["id"])

        return path

    def _item_created(self, item):
        """
        Called when an item is created, before it is added to the model.

        .. warning:: This base class implementation must be called in any
            subclasses overriding this behavior. Failure to do so will result in
            unexpected behavior.

        This base class implementation handles setting the foreground color
        of the item if it has no associated entities.

        :param item: The item that was just created.
        :type item: :class:`~PySide.QtGui.QStandardItem`
        """

        # call base class implementation as per docs
        super(ShotgunHierarchyModel, self)._item_created(item)

        data = get_sg_data(item)

        if not item.is_entity_related():
            item.setForeground(self._empty_item_color)

    def _load_data(
        self,
        seed_entity_field,
        path=None,
        entity_fields=None,
        cache_seed=None
    ):
        """
        This is the main method to use to configure the hierarchy model. You
        basically pass a specific :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`
        query to the model and it will start tracking this particular set of parameters.

        Any existing data contained in the model will be cleared.

        This method will not call the Shotgun API. If cached data is available,
        this will be immediately loaded (this operation is very fast even for
        substantial amounts of data).

        If you want to refresh the data contained in the model (which you
        typically want to), call the :meth:`_refresh_data()` method.

        :param str seed_entity_field: This is a string that corresponds to the
            field on an entity used to seed the hierarchy. For example, a value
            of ``Version.entity`` would cause the model to display a hierarchy
            where the leaves match the entity value of Version entities.

        :param str path: The path to the root of the hierarchy to display.
            This corresponds to the ``path`` argument of the
            :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`
            api method. For example, ``/Project/65`` would correspond to a
            project on you shotgun site with id of ``65``. By default, this
            value is ``None`` and the project from the current project will
            be used. If no project can be determined, the path will default
            to ``/`` which is the root path, meaning all projects will be
            represented as top-level items in the model.

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
            hierarchy query, this seed is typically generated from the
            seed entity field and return entity fields supplied to this method.
            However, in cases where you are doing advanced subclassing, for
            example when you are culling out data based on some external state,
            the model state does not solely depend on the shotgun parameters. It
            may also depend on some external factors. In this case, the cache
            seed should also be influenced by those parameters and you can pass
            an external string via this parameter which will be added to the
            seed.

        :returns: True if cached data was loaded, False if not.
        """

        if not self._hierarchy_is_supported:
            self.clear()
            root = self.invisibleRootItem()
            item = QtGui.QStandardItem("WARNING: Hierarchy not supported")
            item.setEditable(False)
            root.appendRow([item])
            item = QtGui.QStandardItem("- %s" % (self._hierarchy_not_supported_reason,))
            item.setEditable(False)
            root.appendRow([item])
            return False

        # we are changing the query
        self.query_changed.emit()

        # clear out old data
        self.clear()

        self._has_query = True

        self._path = path or self._get_default_path()
        self._seed_entity_field = seed_entity_field
        self._entity_fields = entity_fields or {}

        # get the cache path based on these new data query parameters
        self._cache_path = self.__get_data_cache_path(cache_seed)

        # print some debug info
        self._log_debug("")
        self._log_debug("Model Reset for: %s" % (self,))
        self._log_debug("Path: %s" % (self._path,))
        self._log_debug("Seed entity field: %s" % (self._seed_entity_field,))
        self._log_debug("Entity fields: %s" % (self._entity_fields,))

        self._log_debug("First population pass: Calling _load_external_data()")
        self._load_external_data()
        self._log_debug("External data population done.")

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
            self._log_debug("Retrieved error from data worker: %s" % (msg,))
            return

        path = self._running_query_lookup[uid]

        # query is done. clear it out
        del self._running_query_lookup[uid]

        full_msg = (
            "Error retrieving data from Shotgun.\n"
            "  Path: %s\n"
            "  Error: %s\n"
        ) % (path, msg)
        self.data_refresh_fail.emit(full_msg)
        self._log_warning(full_msg)

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

        self._log_debug("Received worker payload of type: %s" % (request_type,))

        if uid not in self._running_query_lookup:
            # not our job. ignore.
            return

        # query is done. clear it out
        del self._running_query_lookup[uid]

        nav_data = data["nav"]
        self.__on_nav_data_arrived(nav_data)

    def _populate_default_thumbnail(self, item):
        """
        Sets the icon for the supplied item based on its "kind" as returned
        by the :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` api call.

        :param item: The :class:`~PySide.QtGui.QStandardItem` item to set the
            icon for.
        """

        icon = None
        data = get_sg_data(item)
        item_kind = item.kind()

        if item_kind in ["entity", "entity_type"]:
            entity_type = item.entity_type()
            if entity_type:
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

        if not self._hierarchy_is_supported:
            return

        # get a list of all paths to update. these will be paths for all
        # existing items that are not empty or have no children already queried.
        # we know we always need to refresh the inital path.
        paths = [self._path]
        paths.extend(self.__get_queried_paths_r(self.invisibleRootItem()))

        # query in order of length
        for path in sorted(set(paths)):
            self._log_debug("Refreshing hierarchy model path: %s" % (path,))
            self.__query_hierarchy(
                path,
                self._seed_entity_field,
                self._entity_fields
            )

    ############################################################################
    # private methods

    def __create_item(self, data, parent=None, row=None):
        """
        Creates a model item given the supplied data and optional parent.

        The supplied ``data`` corresponds to the results of a call to the
        :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` api method. The
        data will be stored on the new item via the ``SG_DATA_ROLE``.

        :param dict data: The hierarchy data to use when creating the item.
        :param parent: Optional :class:`~PySide.QtGui.QStandardItem` instance
            to parent the created item to.
        :param int row: If supplied, insert the new item at the specified
            row of the parent. Otherwise, append it to the list of children.

        :return: The new :class:`~PySide.QtGui.QStandardItem` instance.
        """

        # if this is the root item, just return the invisible root item that
        # comes with the model
        if data.get("ref", {}).get("kind") == "root":
            return self.invisibleRootItem()

        item = self._SG_QUERY_MODEL_ITEM_CLASS(data["label"])
        item.setEditable(False)

        # keep tabs of which items we are creating
        item.setData(True, self.IS_SG_MODEL_ROLE)

        # we have not fetched more data for this item yet
        item.setData(False, self._SG_ITEM_FETCHED_MORE)

        # attach the nav data for access later
        self.__update_item(item, data)

        # allow item customization prior to adding to model
        self._item_created(item)

        # set up default thumb
        self._populate_default_thumbnail(item)

        self._populate_item(item, data)

        self._set_tooltip(item, data)

        # run the finalizer (always runs on construction, even via cache)
        self._finalize_item(item)

        # identify a parent if none supplied. could be found via the parent
        # supplied in the data or the root if no parent item exists.
        parent = parent or self.item_from_path(
            data.get(self._SG_PARENT_PATH_FIELD)) or self.invisibleRootItem()

        if row is not None:
            parent.insertRow(row, item)
        else:
            # example of using sort/filter proxy model
            parent.appendRow(item)

        return item

    def __get_data_cache_path(self, cache_seed=None):
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
            self._log_warning(
                "Shotgun hierarchy data cache file path may be affected by "
                "windows MAX_PATH limitation."
            )

        return data_cache_path

    def __get_queried_paths_r(self, item):
        """
        Returns a list of previously queried paths for items under the supplied
        parent item.

        This method is used to identify which items need to be re-queried when a
        model refresh is requested. It recursively iterates over the supplied
        item's children, looking for non-empty leaf nodes that have children.

        :param item: The parent :class:`~PySide.QtGui.QStandardItem` instance
            to use when checking for queried children.

        :return: A list of paths
        :rtype: list
        """

        paths = []

        # iterate over all the child items
        for row in range(item.rowCount()):

            child_item = item.child(row)

            data = get_sg_data(child_item)
            # invisible root item does not have this property
            if hasattr(item, 'is_entity_related') and not item.is_entity_related():
                # empty items don't have valid paths to query
                continue

            if child_item.rowCount() == 0:
                # this is an existing leaf node whose (potential) children have
                # not been queried. do nothing.
                continue

            paths.append(data[self._SG_PATH_FIELD])

            # recurse
            paths.extend(self.__get_queried_paths_r(child_item))

        return paths

    def __hierarchy_is_supported(self):
        """
        Checks the current Shotgun connection to make sure it supports
        hierarchy queries.

        :rtype tuple:
        :returns: A tuple of 2 items where the first item is a boolean indicating
            whether hierarchy is supported. If hierarchy is supported, the second
            item will be ``None``. If hierarchy is not supported, the second item
            will be a string explaining why.

        """
        current_engine = sgtk.platform.current_engine()
        sg_connection = current_engine.shotgun
        server_caps = sg_connection.server_caps

        # make sure we're greater than or equal to SG v7.0.2
        if not (hasattr(sg_connection, "server_caps") and
                server_caps.version and
                server_caps.version >= (7, 0, 2)):
            return (False, "The version of SG being used does not support querying for the project hierarchy. v7.0.2 is required.")
        elif not hasattr(sg_connection, "nav_expand"):
            return (False, "The version of the python-api being used does not support querying for the project hierarchy.")

        return (True, None)

    def __insert_subtree(self, nav_data):
        """
        Inserts a subtree for the item represented by ``nav_data``.

        The method first creates the item, then attempts to update/populate its
        children.

        :param dict nav_data: A dictionary of item data as returned via async
            call to :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`.
        """

        item = self.__create_item(nav_data)
        self.__update_subtree(item, nav_data)

    def __on_nav_data_arrived(self, nav_data):
        """
        Handle asynchronous navigation data arriving after a
        :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` request.

        :param dict nav_data: The data returned from the api call.
        """

        self._log_debug("--> Shotgun data arrived. (%s records)" % len(nav_data))

        # pre-process data
        nav_data = self._before_data_processing(nav_data)

        # ensure the data is clean
        nav_data = self._sg_clean_data(nav_data)

        if self._request_full_refresh:
            # full refresh requested

            # reset flag for next request
            self._request_full_refresh = False

            self._log_debug("Rebuilding tree...")
            self.clear()
            self._load_external_data()
            self.__insert_subtree(nav_data)
            self._log_debug("...done!")

            modifications_made = True

        else:

            # ensure we have a path for the item
            item_path = nav_data.get(self._SG_PATH_FIELD, None)
            self._log_debug("Got hierarchy data for path: %s" % (item_path,))

            if not item_path:
                raise sgtk.TankError(
                    "Unexpected error occured. Could not determine the path"
                    "from the queried hierarchy item."
                )

            # see if we have an item for the path
            item = self.item_from_path(item_path)

            if item:
                # check item and children to see if data has been updated
                self._log_debug(
                    "Item exists in tree. Ensuring up-to-date...")
                modifications_made = self.__update_subtree(item, nav_data)
                self._log_debug("...done!")

            else:
                self._log_debug("Detected new item. Adding in-situ to tree...")
                self.__insert_subtree(nav_data)
                self._log_debug("...done!")
                modifications_made = True

        # last step - save our tree to disk for fast caching next time!
        # todo: the hierarchy data is queried lazily. so this implies a
        # write to disk each time the user expands and item. consider the
        # performance of this setup and whether this logic should be altered.
        if modifications_made:
            self._log_debug("Saving tree to disk %s..." % self._cache_path)
            try:
                self._save_to_disk()
                self._log_debug("...saving complete!")
            except Exception, e:
                self._log_warning("Couldn't save cache data to disk: %s" % e)

        if not self._running_query_lookup.keys():
            # no more data queries running. all data refreshed
            self.data_refreshed.emit(modifications_made)

    def __query_hierarchy(self, path, seed_entity_field, entity_fields):
        """
        Triggers the async :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()`
        query based on the supplied fields.

        This method returns immediately and does not block.

        .. note:: For details on the ``path``, ``seed_entity_field``, and
            ``entity_fields`` arguments, please see the
            `<python-api docs http://developer.shotgunsoftware.com/python-api/reference.html#shotgun>`_.
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

        self._log_debug("Querying hierarchy item: %s" % (path,))

        worker_id = self._sg_data_retriever.execute_nav_expand(
            path, seed_entity_field, entity_fields)

        # keep a lookup to map the worker id with the path it is querying
        self._running_query_lookup[worker_id] = path

    def __update_item(self, item, data):
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

        # compare with the item's existing data
        old_item_data = get_sg_data(item)
        if self._sg_compare_data(old_item_data, new_item_data):
            # data has not changed
            return False

        # data differs. set the new data
        item.setData(sanitize_for_qt_model(new_item_data), self.SG_DATA_ROLE)

        # ensure the label is updated
        item.setText(data["label"])

        return True

    def __update_subtree(self, item, nav_data):
        """
        Updates the subtree rooted at the supplied item with the supplied data.

        This method updates the item and its children given a dictionary of
        newly queried data from Shotgun. It first checks to see if any items
        have been removed, then adds or updates children as needed.

        :param item: A :class:`~PySide.QtGui.QStandardItem` instance to update.
        :param dict nav_data: The data returned by a
            :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` call.

        :returns: ``True`` if the subtree was udpated, ``False`` otherwise.
        """

        # ensure the item's data is up-to-date
        subtree_updated = self.__update_item(item, nav_data)

        children_data = nav_data.get("children")

        if not children_data:
            return subtree_updated

        child_paths = []

        for child_data in children_data:

            if self._SG_PATH_FIELD not in child_data:
                item_data = get_sg_data(item)
                parent_path = item_data[self._SG_PATH_FIELD]

                # handle the case where there are child leaves without paths.
                # these tend to be just items that make it clear there are no
                # children. example: "No Shots"
                # create a dummy path so that we can find it later
                child_data[self._SG_PATH_FIELD] = "/".join(
                    [parent_path, child_data["label"]])

            child_paths.append(child_data[self._SG_PATH_FIELD])

        # iterate over item's children to see if any need to be removed.
        # this would be the case where the supplied nav_data does not contain
        # information about an item that currently exists. iterate in reverse
        # order so we can remove items in place without altering subsequent rows
        for row in reversed(range(0, item.rowCount())):
            child_item = item.child(row)
            child_data = get_sg_data(child_item)
            child_path = child_data[self._SG_PATH_FIELD]
            if child_path not in child_paths:
                # removing item
                self._log_debug("Removing item: %s" % (child_item,))
                self._before_item_removed(child_item)
                item.removeRow(row)
                subtree_updated = True

        # add/update the children for the supplied item
        for (row, child_data) in enumerate(children_data):
            child_path = child_data[self._SG_PATH_FIELD]
            child_item = self.item_from_path(child_path)

            if child_item:
                # child already exists, ensure data is up-to-date
                subtree_updated = self.__update_item(child_item, child_data) \
                    or subtree_updated
            else:
                # child item does not exist, create it at the specified row
                self.__create_item(child_data, parent=item, row=row)
                subtree_updated = True

        return subtree_updated

