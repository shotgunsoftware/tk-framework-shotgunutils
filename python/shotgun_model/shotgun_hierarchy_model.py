# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import hashlib
import os
import sys
import pprint

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

# framework imports
from .shotgun_hierarchy_item import ShotgunHierarchyItem
from .shotgun_query_model import ShotgunQueryModel
from .data_handler_nav import ShotgunNavDataHandler
from .util import sanitize_for_qt_model
from tank_vendor import six

logger = sgtk.platform.get_logger(__name__)


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
    `Tracking Settings <https://help.autodesk.com/view/SGSUB/ENU/?guid=SG_Administrator_ar_display_options_ar_project_tracking_settings_html>`__.

    :signal: async_item_retrieval_completed (:class:`ShotgunHierarchyModel`): Emitted when a query to
        :meth:`ShotgunHierarchyModel.async_item_from_entity` or
        :meth:`ShotgunHierarchyModel.async_item_from_paths` has completed.
    """

    # Signal emitted internally whenever a node is updated inside the model. This is used
    # to keep track of nodes refreshed during an async_deep_load call.
    _node_refreshed = QtCore.Signal(object)

    async_item_retrieval_completed = QtCore.Signal(object)

    def __init__(
        self, parent, schema_generation=0, bg_task_manager=None, include_root=None
    ):
        """
        Initialize the Hierarcy model.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        :param schema_generation: Schema generation number. Advanced parameter.
            If your shotgun model contains logic in subclassed methods that
            modify the shotgun data prior to it being put into the cache system
            that the ShotgunModel maintains, you can use this option to ensure
            that different versions of the code access different caches. If you
            change your custom business logic around and update the generation
            number, both new and old versions of the code will work correctly
            against the cached data.

        :param bg_task_manager:  Background task manager to use for any
            asynchronous work. If this is None then a task manager will be
            created as needed.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`

        :param str include_root: Defines the name of an additional, top-level
            model item that represents the root. In views, this item will appear
            as a sibling to top-level children of the root. This allows for
            UX whereby a user can select an item representing the root without
            having a UI that shows a single, top-level item. An example would
            be displaying published file entity hierarchy with top level items:
            "Assets", "Shots", and "Project Publishes". In this example, the
            supplied arg would look like: ``include_root="Project Publishes"``.
            If ``include_root`` is `None`, no root item will be added.
        """
        super(ShotgunHierarchyModel, self).__init__(
            parent, bg_load_thumbs=True, bg_task_manager=bg_task_manager
        )

        # check for hierarchy support
        (
            self._hierarchy_is_supported,
            self._hierarchy_not_supported_reason,
        ) = self.__hierarchy_is_supported()

        if not self._hierarchy_is_supported:
            self._log_warning(self._hierarchy_not_supported_reason)

        self._path = None
        self._seed_entity_field = None
        self._entity_fields = None
        self._include_root = include_root

        self._schema_generation = schema_generation

        # keep these icons around so they're not constantly being created
        self._folder_icon = QtGui.QIcon(":tk-framework-shotgunutils/icon_Folder.png")
        self._none_icon = QtGui.QIcon(":tk-framework-shotgunutils/icon_None_dark.png")

        # Define the foreground color of "empty" items.
        # These special items are used as placeholders in the tree where the
        # parent has no children. An example would be `Shots > No Shots` where
        # `No Shots` is the "empty" item. By default, the color is a mix of the
        # application instance's base and text colors. This will typically
        # result in a dimmed appearance for these special items indicating that
        # they are not clickable. This makes goes outside the typical bounds of
        # the model by pulling the palette colors from the app instance. This
        # can be overridden in subclasses via ``_finalize_item()`` though.
        # Note that "palette()" is a static method that needs to be accessed
        # through "QApplication" rather than "QApplication.instance()" to
        # make sure we are compatible with both Qt 4 and Qt 5.
        base_color = QtGui.QApplication.palette().base().color()
        text_color = QtGui.QApplication.palette().text().color()

        # local import to avoid doc generation issues
        from ..utils import color_mix

        self._empty_item_color = color_mix(text_color, 1, base_color, 2)

    def __repr__(self):
        """
        String representation of this instance
        """
        return "<%s path:%s seed:%s>" % (
            self.__class__.__name__,
            self._path,
            self._seed_entity_field,
        )

    ############################################################################
    # public methods

    def item_from_path(self, path):
        """
        Returns a :class:`~PySide.QtGui.QStandardItem` for the supplied path.

        Returns ``None`` if not found.

        :param str path: The path to search the tree for. The paths match those
            used by and returned from the python-api's
            :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` method.
        :returns: :class:`~PySide.QtGui.QStandardItem` or ``None`` if not found
        """
        logger.debug("Resolving model item for path %s" % path)

        if path == self._path:
            return self.invisibleRootItem()
        else:
            return self._ensure_item_loaded(path)

    class _NodeRefresher(QtCore.QObject):
        """
        This class is used to launch a refresh request to the model and try
        again to resolve the node when the refresh has happened.
        """

        def __init__(self, path_to_refresh, model):
            """
            Triggers a fetchMore on the first node in the paths to refresh.

            :param list(str) path_to_refresh: List of nodes to refresh asynchronously.
            :param model: ``ShotgunHierarchyModel`` we are requesting the nodes for.
            """
            super(ShotgunHierarchyModel._NodeRefresher, self).__init__(model)
            # Connect to the node refreshed signal so we know when
            # our node is refreshed.
            model._node_refreshed.connect(self._node_refreshed)

            logger.debug("Fetching more on %s" % path_to_refresh[0])
            # Fetch data from this path's parent.
            model.fetchMore(model.item_from_path(path_to_refresh[0]).index())

            self._path_to_refresh = path_to_refresh

        def _node_refreshed(self, item):
            """
            Called when the ``async_item_retrieval_completed`` signal is emitted.

            :param item: The ShotgunHierarchyItem that was loaded.
            """
            if item.data(self.parent()._SG_ITEM_UNIQUE_ID) != self._path_to_refresh[1]:
                logger.debug(
                    "Skipping node %s", item.data(self.parent()._SG_ITEM_UNIQUE_ID)
                )
                return
            logger.debug(
                "Model item refreshed: %s", item.data(self.parent()._SG_ITEM_UNIQUE_ID)
            )
            self.parent()._node_refreshed.disconnect(self._node_refreshed)
            utils = sgtk.platform.current_bundle().import_module("utils")
            utils.safe_delete_later(self)

            # Try again to async deep load the node and the next tokens.
            self.parent().async_item_from_paths(self._path_to_refresh)

    def async_item_from_entity(self, entity):
        """
        Asynchronously loads an entity's node and all its parents and emits a signal with the
        associated :class:`ShotgunHierarchyItem` when the node is loaded.

        :param dict entity: Entity dictionary with keys ``type`` and ``id``.

        :signals: ``async_item_retrieval_completed``
        """
        paths = self._resolve_entity_paths(entity)
        self.async_item_from_paths(paths)

    def _resolve_entity_paths(self, entity):
        """
        Resolves an entities path in the nav hierarchy.

        .. note::
            This method is executed in the current thread.

        :param dict entity: Entity dictionary with keys ``type`` and ``id``.

        :returns: The path to the entity in the nav api.
        :rtype: str
        """
        if entity:
            # FIXME: Unfortunately we can't call the endpoint directly because there is a bug in it.
            # We've written a workaround for it in the ShotgunDataRetriever, which we will be
            # using here.

            sg_result = self._sg_data_retriever._task_execute_nav_search_entity(
                "/", entity
            )["sg_result"]

            if len(sg_result) == 0:
                logger.warning("Entity %s not found. Picking /.", entity)
            else:
                sg_data = sg_result[0]
                # The last link in the chain is always the complete link to the entity we seek.

                if len(sg_result) > 1:
                    logger.info(
                        "Entity %s found %d times with nav_search_entity endpoint. Picking %s.",
                        entity,
                        len(sg_result),
                        pprint.pformat(sg_data),
                    )
                    logger.info("Other choices were %s", sg_result[1:])

                return sg_data["incremental_path"]

        # Fallback for when the root was requested or no entity was found.
        # Do not request the server for the path to the site root, this will always be /.
        return ["/"]

    def async_item_from_paths(self, paths):
        """
        Takes a list of paths that incrementally dig deeper into the
        model and signals when the node is found and loaded in memory.

        :param list(str): List of paths from the nav api that drill down further
            and further into the tree.

        :signals: ``async_item_retrieval_completed``
        """
        # Nothing to async load, return early.
        if not paths:
            return

        logger.debug("Async loading of %s", paths)

        for idx, path in enumerate(paths):
            # Iterate on every path.
            item = self.item_from_path(path)
            # If an item is already loaded, move to the next one.
            if item:
                continue
            # Send a refresh request and return. When the node is refreshed,
            # this method will be called a second time with the same parameters.
            # This time around this node will already have been refreshed
            # and the code will dig deeper. At some point the last entry
            # in the list will be reached and we will emit the item.
            logger.debug("Refreshing paths: %s", paths[idx - 1 :])
            self._NodeRefresher(paths[idx - 1 :], self)
            return

        logger.debug("Deep load has been completed for %s", paths[-1])
        logger.debug("Selected items: %s", item)
        # If everything is loaded, emit the signal.
        self.async_item_retrieval_completed.emit(item)

    def fetchMore(self, index):
        """
        Retrieve child items for a node.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """
        # now request the subtree to refresh itself
        if index.isValid():
            item = self.itemFromIndex(index)
            if isinstance(item, ShotgunHierarchyItem) and self.canFetchMore(index):
                self._request_data(item.path())

        return super(ShotgunHierarchyModel, self).fetchMore(index)

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

        current_bundle = sgtk.platform.current_bundle()
        if current_bundle:
            # an engine is running
            project = current_bundle.context.project
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

        if not item.is_entity_related():
            item.setForeground(self._empty_item_color)

    def _load_data(
        self, seed_entity_field, root=None, entity_fields=None, cache_seed=None
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

            NOTE: This value is currently limited to either ``Version.entity``
            or ``PublishedFile.entity``

        :param dict root: This is the entity that will be at the root
            of the hierarchy view. By default, this value is ``None``, which
            means the root of the hierarchy will be at the site level. Only
            projects can be set as the root of a hierarchy model.

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

        self._path = self._resolve_entity_paths(root)[-1]
        self._root = root if self._path != "/" else None

        self._seed_entity_field = seed_entity_field
        self._entity_fields = entity_fields or {}

        logger.debug("")
        logger.debug("Model Reset for: %s" % (self,))
        logger.debug("Root: %s" % (self._root))
        logger.debug("Path: %s" % (self._path,))
        logger.debug("Seed entity field: %s" % (self._seed_entity_field,))
        logger.debug("Entity fields: %s" % (self._entity_fields,))

        # get the cache path based on these new data query parameters
        self._data_handler = ShotgunNavDataHandler(
            self._path,
            self._seed_entity_field,
            self._entity_fields,
            self.__compute_cache_path(cache_seed),
            include_root=self._include_root,
        )

        # load up from disk
        logger.debug("Loading data from cache file into memory...")
        self._data_handler.load_cache()

        logger.debug("First population pass: Calling _load_external_data()")
        self._load_external_data()
        logger.debug("External data population done.")

        # only one column. give it a default value
        self.setHorizontalHeaderLabels(["%s Hierarchy" % (self._seed_entity_field,)])

        root = self.invisibleRootItem()

        # construct the top level nodes
        logger.debug("Creating model nodes for top level of data tree...")
        nodes_generated = self._data_handler.generate_child_nodes(
            None, root, self._create_item
        )

        # if we got some data, emit cache load signal
        if nodes_generated > 0:
            self.cache_loaded.emit()

        # request that the root nodes are updated
        self._request_data(self._path)

        # return true if cache is loaded false if not
        return nodes_generated > 0

    def _populate_default_thumbnail(self, item):
        """
        Sets the icon for the supplied item based on its "kind" as returned
        by the :meth:`~shotgun-api3:shotgun_api3.Shotgun.nav_expand()` api call.

        :param item: The :class:`~PySide.QtGui.QStandardItem` item to set the
            icon for.
        """
        icon = None
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

    def _create_item(self, parent, data_item, top_index=None):
        """
        Creates a model item for the tree given data out of the data store

        :param :class:`~PySide.QtGui.QStandardItem` parent: Model item to parent the node under
        :param :class:`ShotgunItemData` data_item: Data to populate new item with
        :param int top_index: Indicates an index the item should be placed on the tree

        :returns: Model item
        :rtype: :class:`ShotgunStandardItem`
        """
        item = ShotgunHierarchyItem()

        # set construction flags
        item.setEditable(False)

        # keep tabs of which items we are creating
        item.setData(True, self.IS_SG_MODEL_ROLE)

        # we have not fetched more data for this item yet
        item.setData(False, self._SG_ITEM_FETCHED_MORE)

        # update values
        self._update_item(item, data_item)

        # todo: hierarchy model to handle multiple rows?
        parent.appendRow(item)

        self._node_refreshed.emit(item)

    def _update_item(self, item, data_item):
        """
        Updates a model item with the given data

        :param :class:`~PySide.QtGui.QStandardItem` item: Model item to update
        :param :class:`ShotgunItemData` data_item: Data to update item with
        """

        item.setText(data_item.shotgun_data["label"])

        item.setData(not data_item.is_leaf(), self._SG_ITEM_HAS_CHILDREN)

        # transfer a unique id from the data backend so we can
        # refer back to this node later on
        item.setData(data_item.unique_id, self._SG_ITEM_UNIQUE_ID)

        # attach the nav data for access later
        item.setData(sanitize_for_qt_model(data_item.shotgun_data), self.SG_DATA_ROLE)

        # allow item customization prior to adding to model
        self._item_created(item)

        # set up default thumb
        self._populate_default_thumbnail(item)

        self._populate_item(item, data_item.shotgun_data)

        self._set_tooltip(item, data_item.shotgun_data)

        # run the finalizer (always runs on construction, even via cache)
        self._finalize_item(item)

        # If this is a node that already existed and is being refreshed, notify.
        # If the node is not parented yet, this is because we're in the middle
        # of a create_item call, which WILL refresh the node.
        if item.parent():
            self._node_refreshed.emit(item)

    ############################################################################
    # private methods

    def __compute_cache_path(self, cache_seed=None):
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
        params_hash.update(six.ensure_binary(str(self._path)))

        # include the schema generation number for clients
        params_hash.update(six.ensure_binary(str(self._schema_generation)))

        # If this value changes over time (like between Qt4 and Qt5), we need to
        # assume our previous user roles are invalid since Qt might have taken
        # it over. If role's value is 32, don't add it to the hash so we don't
        # invalidate PySide/PyQt4 caches.
        if QtCore.Qt.UserRole != 32:
            params_hash.update(six.ensure_binary(str(QtCore.Qt.UserRole)))

        # include the cache_seed for additional user control over external state
        params_hash.update(six.ensure_binary(str(cache_seed)))

        # iterate through the sorted entity fields to ensure consistent order
        for (entity_type, fields) in sorted(self._entity_fields.items()):
            for field in fields:
                entity_field_hash.update(
                    six.ensure_binary("%s.%s" % (entity_type, field))
                )

        # convert the seed entity field into a path segment.
        # example: Version.entity => Version/entity
        seed_entity_field_path = os.path.join(*self._seed_entity_field.split("."))

        # Organize files on disk based on the seed_entity field path segment and
        # then param and entity field hashes

        # Try to share the cache at the site level which was introduced in tk-core
        # > 0.18.118.
        # If not available, fallback on per project/pipeline config/plugin id
        # caching.
        if hasattr(self._bundle, "site_cache_location"):
            cache_location = self._bundle.site_cache_location
        else:
            cache_location = self._bundle.cache_location

        data_cache_path = os.path.join(
            cache_location,
            "sg_nav",
            seed_entity_field_path,
            params_hash.hexdigest(),
            "%s.%s"
            % (entity_field_hash.hexdigest(), ShotgunNavDataHandler.FORMAT_VERSION),
        )

        # warn if the path is longer than the windows max path limitation
        if sgtk.util.is_windows() and len(data_cache_path) > 250:
            self._log_warning(
                "Flow Production Tracking hierarchy data cache file path may be affected by "
                "windows MAX_PATH limitation."
            )

        return data_cache_path

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
        current_bundle = sgtk.platform.current_bundle()
        sg_connection = current_bundle.shotgun
        server_caps = sg_connection.server_caps

        # make sure we're greater than or equal to SG v7.0.2
        if not (
            hasattr(sg_connection, "server_caps")
            and server_caps.version
            and server_caps.version >= (7, 0, 2)
        ):
            return (
                False,
                "The version of PTR being used does not support querying for the project "
                "hierarchy. v7.0.2 is required.",
            )
        elif not hasattr(sg_connection, "nav_expand"):
            return (
                False,
                "The version of the python-api being used does not support querying for "
                "the project hierarchy.",
            )

        return (True, None)
