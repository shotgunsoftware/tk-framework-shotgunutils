# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
import copy
import os
import sys
import hashlib


from sgtk.platform.qt import QtCore, QtGui

from .shotgun_standard_item import ShotgunStandardItem
from .shotgun_query_model import ShotgunQueryModel
from .data_handler_find import ShotgunFindDataHandler
from .util import get_sanitized_data, get_sg_data, sanitize_for_qt_model

class ShotgunModel(ShotgunQueryModel):
    """
    A Qt Model representing a Shotgun query.

    This class implements a standard :class:`~PySide.QtCore.QAbstractItemModel`
    specialized to hold the contents of a particular Shotgun query. It is cached
    and refreshes its data asynchronously.

    In order to use this class, you normally subclass it and implement certain key data
    methods for setting up queries, customizing etc. Then you connect your class to
    a :class:`~PySide.QtGui.QAbstractItemView` of some sort which will display the result.
    If you need to do manipulations such as sorting or filtering on the data,
    connect a proxy model (typically :class:`~PySide.QtGui.QSortFilterProxyModel`)
    between your class and the view.
    """

    # Custom model role that holds the associated value
    SG_ASSOCIATED_FIELD_ROLE = QtCore.Qt.UserRole + 10

    # header value for the first column
    FIRST_COLUMN_HEADER = "Name"

    def __init__(self, parent, download_thumbs=True, schema_generation=0, bg_load_thumbs=True, bg_task_manager=None):
        """
        :param parent: Parent object.
        :type parent: :class:`~PySide.QtGui.QWidget`
        :param download_thumbs: Boolean to indicate if this model should attempt
                                to download and process thumbnails for the downloaded data.
        :param schema_generation: Schema generation number. Advanced parameter. If your
                                  shotgun model contains logic in subclassed methods
                                  that modify the shotgun data prior to it being put into
                                  the cache system that the ShotgunModel maintains, you can
                                  use this option to ensure that different versions of the code
                                  access different caches. If you change your custom business logic
                                  around and update the generation number, both new and old
                                  versions of the code will work correctly against the cached data.
        :param bg_load_thumbs: If set to True, thumbnails will be loaded in the background.
        :param bg_task_manager:  Background task manager to use for any asynchronous work. If
                                 this is None then a task manager will be created as needed.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        """
        super(ShotgunModel, self).__init__(parent, bg_load_thumbs, bg_task_manager)

        # default value so that __repr__ can be used before load_data
        self.__entity_type = None

        self.__schema_generation = schema_generation

        # keep track of info for thumbnail download/load
        self.__download_thumbs = download_thumbs

    def __repr__(self):
        """
        String representation of this instance
        """
        return "<%s entity_type:%s>" % (
            self.__class__.__name__, self.__entity_type)

    ########################################################################################
    # public methods

    @property
    def entity_ids(self):
        """
        Returns a list of entity ids that are part of this model.
        """
        # note that all of the ids may not be loaded into the actual model
        # yet so we have to query the data handler for this.
        return self._data_handler.get_entity_ids()

    def item_from_entity(self, entity_type, entity_id):
        """
        Returns a :class:`~PySide.QtGui.QStandardItem` based on
        entity type and entity id. Returns none if not found.

        :param entity_type: Shotgun entity type to look for
        :param entity_id: Shotgun entity id to look for
        :returns: :class:`~PySide.QtGui.QStandardItem` or None if not found
        """
        self._log_debug("Resolving model item for entity %s:%s" % (entity_type, entity_id))

        if entity_type != self.__entity_type:
            self._log_debug("...entity type is not part of this model!")
            return None

        uid = self._data_handler.get_uid_from_entity_id(entity_id)

        if uid is None:
            # no match in data store
            self._log_debug("...entity id is not part of the data set")
            return None

        return self._ensure_item_loaded(uid)

    def index_from_entity(self, entity_type, entity_id):
        """
        Returns a QModelIndex based on entity type and entity id
        Returns none if not found.

        :param entity_type: Shotgun entity type to look for
        :param entity_id: Shotgun entity id to look for
        :returns: :class:`~PySide.QtCore.QModelIndex` or None if not found
        """
        item = self.item_from_entity(entity_type, entity_id)
        if not item:
            return None
        return self.indexFromItem(item)

    def get_filters(self, item):
        """
        Returns a list of Shotgun filters representing the given item. This is useful if
        you are trying to determine how intermediate leaf nodes partition leaf node data.

        For example, if you have created a hierarchical model for a Shot listing::

            hierarchy: [sg_sequence, sg_status, code]

        The Shotgun model will group the data by sequence, then by status, then the leaf
        nodes will be the shot names. If you execute the get_filters() method on a sequence
        level tree node, it may return::

            [ ['sg_sequence', 'is', {'type': 'Sequence', 'id': 123, 'name': 'foo'}] ]

        If you execute the get_filters() on a status node in the tree, it may return::

            [
              ['sg_sequence', 'is', {'type': 'Sequence', 'id': 123, 'name': 'foo'}],
              ['sg_status', 'is', 'ip']
            ]

        :param item: One of the :class:`~PySide.QtGui.QStandardItem` items that are associated with this model.
        :returns: standard shotgun filter list to represent that item
        """
        # prime filters with our base query
        filters = copy.deepcopy(self.__filters)

        # now walk up the tree and get all fields
        p = item
        while p:
            field_data = get_sanitized_data(p, self.SG_ASSOCIATED_FIELD_ROLE)
            filters.append([field_data["name"], "is", field_data["value"]])
            p = p.parent()
        return filters

    def ensure_data_is_loaded(self, index=None):
        """
        Recursively processes the model and ensures that all data
        has been loaded into the model.

        Beginning with v5, the Shotgun model defer loads its data into the model for
        optimal performance. Normally, this is not an issue - the data is typically
        requested prior to a user expanding a tree node in a view. In some cases,
        however, it is necessary to pre-fetch parts of the tree. One example of this
        is if you want to perform filtering via a
        :class:`~PySide.QtGui.QSortFilterProxyModel`. Please note that for large
        data sets, this operation may be slow.

        .. versionadded:: 5.0.0

        :param index: Model index for which to recursively load data.
                      If set to None, the entire tree will be loaded.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """
        if index is None:
            # load everything
            index = self.invisibleRootItem().index()

        if self.canFetchMore(index):
            self.fetchMore(index)

        for child_index in xrange(self.rowCount(index)):
            child_model_index = self.index(child_index, 0, parent=index)
            self.ensure_data_is_loaded(child_model_index)

    def get_entity_type(self):
        """
        Returns the Shotgun Entity type associated with this model.

        :returns: Shotgun entity type string (e.g. 'Shot', 'Asset' etc).
        """
        return self.__entity_type

    def get_additional_column_fields(self):
        """
        Returns the fields for additional columns and their associated column in the model.

        :returns: A list of dictionaries with the following keys:
            "field": the requested additional field for the column
            "column_idx": the column number in the model associated with the additional field
        """
        # column is one greater than the index because of the default initial column
        return [{"column_idx": i + 1, "field": field} for (i, field) in enumerate(self.__column_fields)]

    ########################################################################################
    # protected methods

    def _load_data(
        self, entity_type, filters, hierarchy, fields, order=None, seed=None, limit=None,
        columns=None, additional_filter_presets=None, editable_columns=None
    ):
        """
        This is the main method to use to configure the model. You basically
        pass a specific find query to the model and it will start tracking
        this particular set of filter and hierarchy parameters.

        Any existing data contained in the model will be cleared.

        This method will not call the Shotgun API. If cached data is available,
        this will be immediately loaded (this operation is very fast even for
        substantial amounts of data).

        If you want to refresh the data contained in the model (which you typically
        want to), call the :meth:`_refresh_data()` method.

        .. code-block:: python

            # Example call from a subclass of ShotgunModel that displays assets.
            # Additional "code" and " description" columns will be displayed,
            # and the "description" column will be editable.
            self._load_data(
                "Asset",                            # entity_type
                [],                                 # filters
                ["sg_asset_type", "code"],          # hierarchy
                ["description"],                    # fields
                columns=["code", "description"],    # additional columns to display
                editable_columns=["description"],
            )

        :param entity_type:               Shotgun entity type to download
        :param filters:                   List of Shotgun filters. Standard Shotgun syntax. Passing None instead
                                          of a list of filters indicates that no shotgun data should be retrieved
                                          and no API calls will be made.
        :param hierarchy:                 List of grouping fields. These should be names of Shotgun
                                          fields. If you for example want to create a list of items,
                                          the value ``["code"]`` will be suitable. This will generate a data
                                          model which is flat and where each item's default name is the
                                          Shotgun name field. If you want to generate a tree where assets
                                          are broken down by asset type, you could instead specify
                                          ``["sg_asset_type", "code"]``.
        :param fields:                    Fields to retrieve from Shotgun (in addition to the ones specified
                                          in the hierarchy parameter). Standard Shotgun API syntax. If you
                                          specify None for this parameter, Shotgun will not be called when
                                          the _refresh_data() method is being executed.
        :param order:                     Order clause for the Shotgun data. Standard Shotgun API syntax.
                                          Note that this is an advanced parameter which is meant to be used
                                          in subclassing only. The model itself will be ordered by its
                                          default display name, and if any other type of ordering is desirable,
                                          use for example a QProxyModel to handle this. However, knowing in which
                                          order results will arrive from Shotgun can be beneficial if you are doing
                                          grouping, deferred loading and aggregation of data as part of your
                                          subclassed implementation, typically via the :meth:`_before_data_processing()` method.
        :param seed:                      Advanced parameter. With each shotgun query being cached on disk, the model
                                          generates a cache seed which it is using to store data on disk. Since the cache
                                          data on disk is a reflection of a particular shotgun query, this seed is typically
                                          generated from the various query and field parameters passed to this method. However,
                                          in some cases when you are doing advanced subclassing, for example when you are culling
                                          out data based on some external state, the model state does not solely depend on the
                                          shotgun query parameters. It may also depend on some external factors. In this case,
                                          the cache seed should also be influenced by those parameters and you can pass
                                          an external string via this parameter which will be added to the seed.
        :param limit:                     Limit the number of results returned from Shotgun. In conjunction with the order
                                          parameter, this can be used to effectively cap the data set that the model
                                          is handling, allowing a user to for example show the twenty most recent notes or
                                          similar.
        :param list columns:              If columns is specified, then any leaf row in the model will have columns created where
                                          each column in the row contains the value for the corresponding field from columns. This means
                                          that the data from the loaded entity will be available field by field. Subclasses can modify
                                          this behavior by overriding _get_additional_columns.
        :param additional_filter_presets: List of Shotgun filter presets to apply, e.g.
                                          ``[{"preset_name":"LATEST","latest_by":"BY_PIPELINE_STEP_NUMBER_AND_ENTITIES_CREATED_AT"}]``
        :param list editable_columns:     A subset of ``columns`` that will be editable in views that use this model.

        :returns:                         True if cached data was loaded, False if not.
        """
        # we are changing the query
        self.query_changed.emit()

        # clear out old data
        self.clear()

        self.__entity_type = entity_type
        self.__filters = filters
        self.__fields = fields
        self.__order = order or []
        self.__hierarchy = hierarchy
        self.__column_fields = columns or []
        self.__editable_fields = editable_columns or []
        self.__limit = limit or 0  # 0 means get all matches
        self.__additional_filter_presets = additional_filter_presets

        # make sure `editable_fields` is a subset of `column_fields`
        if not set(self.__editable_fields).issubset(set(self.__column_fields)):
            raise sgtk.TankError(
                "The `editable_fields` argument is not a subset of "
                "`column_fields`."
            )

        self._log_debug("")
        self._log_debug("Model Reset for %s" % self)
        self._log_debug("Entity type: %s" % self.__entity_type)
        self._log_debug("Filters: %s" % self.__filters)
        self._log_debug("Hierarchy: %s" % self.__hierarchy)
        self._log_debug("Fields: %s" % self.__fields)
        self._log_debug("Order: %s" % self.__order)
        self._log_debug("Columns: %s" % self.__column_fields)
        self._log_debug("Editable Columns: %s" % self.__editable_fields)
        self._log_debug("Filter Presets: %s" % self.__additional_filter_presets)

        # get the cache path based on these new data query parameters
        self._data_handler = ShotgunFindDataHandler(
            self.__entity_type,
            self.__filters,
            self.__order,
            self.__hierarchy,
            self.__fields + self.__column_fields,
            self.__download_thumbs,
            self.__limit,
            self.__additional_filter_presets,
            self.__compute_cache_path(seed)
        )
        # load up from disk
        self._log_debug("Loading data from cache file into memory...")
        self._data_handler.load_cache()

        self._log_debug("First population pass: Calling _load_external_data()")
        self._load_external_data()
        self._log_debug("External data population done.")

        # set our headers
        headers = [self.FIRST_COLUMN_HEADER] + self._get_additional_column_headers(
            self.__entity_type,
            self.__column_fields,
        )
        self.setHorizontalHeaderLabels(headers)

        root = self.invisibleRootItem()

        # construct the top level nodes
        self._log_debug("Creating model nodes for top level of data tree...")
        nodes_generated = self._data_handler.generate_child_nodes(
            None,
            root,
            self._create_item
        )

        # if we got some data, emit cache load signal
        if nodes_generated > 0:
            self.cache_loaded.emit()

        # return true if cache is loaded false if not
        return nodes_generated > 0

    def _refresh_data(self):
        """
        Rebuilds the data in the model to ensure it is up to date.
        This call is asynchronous and will return instantly.
        The update will be applied whenever the data from Shotgun is returned.

        If the model is empty (no cached data) no data will be shown at first
        while the model fetches data from Shotgun.

        As soon as a local cache exists, data is shown straight away and the
        shotgun update happens silently in the background.

        If data has been added, this will be injected into the existing structure.
        In this case, the rest of the model is intact, meaning that also selections
        and other view related states are unaffected.

        If data has been modified or deleted, a full rebuild is issued, meaning that
        all existing items from the model are removed. This does affect view related
        states such as selection.
        """
        self._request_data()

    def _item_created(self, item):
        """
        Called when an item is created, before it is added to the model.

        .. warning:: This base class implementation must be called in any
            subclasses overriding this behavior. Failure to do so will result in
            unexpected behavior.

        This base class implementation handles storing item lookups for
        efficiency as well as to prevent issues with garbage collection.

        :param item: The item that was just created.
        :type item: :class:`~PySide.QtGui.QStandardItem`
        """
        # as per docs, call the base implementation
        super(ShotgunModel, self)._item_created(item)

        # request thumbnail for this item
        if self.__download_thumbs:
            sg_data = item.data(self.SG_DATA_ROLE)

            if sg_data:
                for field in sg_data.keys():
                    # note: we check for all fields containing "image"
                    # so that we'll catch a field such as 'sg_sequence.Sequence.image'
                    # as well as a straight 'image' field
                    if "image" in field and sg_data[field] is not None:
                        # we have a thumb we are supposed to download!
                        # get the thumbnail - store the unique id we get back from
                        # the data retrieve in a dict for fast lookup later
                        self._request_thumbnail_download(
                            item,
                            field,
                            sg_data[field],
                            sg_data.get("type"),
                            sg_data.get("id")
                        )

    def _set_tooltip(self, item, sg_item):
        """
        Called when an item is created.

        .. note:: You can subclass this if you want to set your own tooltip for the model item. By
            default, the SG_ASSOCIATED_FIELD_ROLE data is retrieved and the field name is used to
            determine which field to pick tooltip information from.

            For example,

            .. code-block:: python

               {
                   "type": "Task",
                   "entity": {                       # (1) Tooltip becomes "Asset 'Alice'"
                       "sg_asset_type": "Character", # (2) Tooltip becomes "Asset Type 'Character'"
                       "type": "Asset",
                       "code": "Alice"
                   },
                   "content": "Art"                  # (3) Tooltip becomes "Task 'Art'"
               }

            1) If the field is an entity (e.g. entity), then the display name of that entity's type
            will be used.

            2) If the field is part of a sub-entity (e.g entity.Asset.sg_asset_type), the display
            name of the sub-entity's type followed by a space and the sub-entity's field display name
            will be used.

            3) If the field is part of an entity and not an entity field(e.g. content), the display
            name of the entity's type will be used.

            In all cases, the string ends with the quoted name of the ShotgunStandardItem.

        :param item: Shotgun model item that requires a tooltip.
        :param sg_item: Dictionary of the entity associated with the Shotgun model item.
        """
        data = item.data(self.SG_ASSOCIATED_FIELD_ROLE)
        field = data["name"]

        if isinstance(sg_item[field], dict) and "type" in sg_item[field]:
            # This is scenario 1 described above.
            item.setToolTip(
                "%s '%s'" % (
                    self._shotgun_globals.get_type_display_name(sg_item[field]["type"]),
                    item.text()
                )
            )
        elif "." in field:
            # This is scenario 2 described above. We only want to get the last entity and field.
            _, sub_entity_type, sub_entity_field_name = field.rsplit(".", 2)
            item.setToolTip(
                "%s %s '%s'" % (
                    self._shotgun_globals.get_type_display_name(sub_entity_type),
                    self._shotgun_globals.get_field_display_name(sub_entity_type, sub_entity_field_name),
                    item.text()
                )
            )
        else:
            # This is scenario 3 described above.
            item.setToolTip(
                "%s '%s'" % (
                    self._shotgun_globals.get_type_display_name(sg_item["type"]),
                    item.text()
                )
            )

    def _get_additional_columns(self, primary_item, is_leaf, columns):
        """
        Called when an item is about to be inserted into the model, to get additional items
        to be included in the same row as the specified item. This provides an opportunity
        for subclasses to create one or more additional columns for each item in the model.

        Note that this method is always called before inserting an item, even when loading
        from the cache. Any data that is expensive to compute or query should be added
        to the ShotgunStandardItem in _populate_item, since column data is not cached.
        Also note that item population methods (_populate_item, _populate_thumbnail, etc)
        will not be called on the return columns.

        This method should return a list of QStandardItems, one for each additional column.
        The original ShotgunStandardItem is always the first item in each row and should
        NOT be included in the returned list. Any empty value returned by this method
        is guaranteed to be treated as an empty list (i.e. you may return None).

        This method is called after _finalize_item.

        :param primary_item: :class:`~PySide.QtGui.QStandardItem` that is about to be added to the model
        :param is_leaf: boolean that is True if the item is a leaf item
        :param columns: list of Shotgun field names requested as the columns from _load_data

        :returns: list of :class:`~PySide.QtGui.QStandardItem`
        """
        # default implementation will create items for the given fields from the item if it is a leaf
        # with the display role being the string value for the field and the actual data value in
        # SG_ASSOCIATED_FIELD_ROLE
        items = []

        if is_leaf and columns:
            data = get_sg_data(primary_item)
            for column in columns:
                # set the display role to the string representation of the value
                column_item = ShotgunStandardItem(
                    self.__generate_display_name(column, data)
                )
                column_item.setEditable(column in self.__editable_fields)

                # set associated field role to be the column value itself
                value = data.get(column)
                column_item.setData(sanitize_for_qt_model(value), self.SG_ASSOCIATED_FIELD_ROLE)

                items.append(column_item)

        return items

    def _get_additional_column_headers(self, entity_type, columns):
        """
        Called to set the headers for the additional columns requested from _load_data.

        :param entity_type: type name of the entity the columns are for
        :param columns: list of Shotgun field names requested as the columns from _load_data

        :returns: list of strings to use as the headers
        """
        # default implementation will set the headers to the display names for the fields
        return [self._shotgun_globals.get_field_display_name(entity_type, c) for c in columns]

    def _get_columns(self, item, is_leaf):
        """
        Returns a row (list of QStandardItems) given an initial QStandardItem.  The item itself
        is always the first item in the row, but additional columns may be appended.

        :param item: A :class:`~PySide.QtGui.QStandardItem` that is associated with this model.
        :param is_leaf: A boolean indicating if the item is a leaf item or not

        :returns: A list of :class:`~PySide.QtGui.QStandardItem` s
        """
        # the first item in the row is always the standard shotgun model item,
        # but subclasses may provide additional columns to be appended.
        row = [item]
        row.extend(self._get_additional_columns(item, is_leaf, self.__column_fields))
        return row

    def _create_item(self, parent, data_item):
        """
        Creates a model item for the tree given data out of the data store

        :param :class:`~PySide.QtGui.QStandardItem` parent: Model item to parent the node under
        :param :class:`ShotgunItemData` data_item: Data to populate new item with

        :returns: Model item
        :rtype: :class:`ShotgunStandardItem`
        """
        # construct tree view node object
        item = ShotgunStandardItem()
        item.setEditable(data_item.field in self.__editable_fields)

        self._update_item(item, data_item)

        # run the finalizer
        self._finalize_item(item)

        # get complete row containing all columns for the current item
        row = self._get_columns(item, data_item.is_leaf())

        # and attach the node
        parent.appendRow(row)

        return item

    def _update_item(self, item, data_item):
        """
        Updates a model item with the given data

        :param :class:`~PySide.QtGui.QStandardItem` item: Model item to update
        :param :class:`ShotgunItemData` data_item: Data to update item with
        """

        field_display_name = self.__generate_display_name(data_item.field, data_item.shotgun_data)
        item.setText(field_display_name)

        # keep tabs of which items we are creating
        item.setData(True, self.IS_SG_MODEL_ROLE)

        # flag if item has children, for the fetchMore functionality
        item.setData(not data_item.is_leaf(), self._SG_ITEM_HAS_CHILDREN)

        # transfer a unique id from the data backend so we can
        # refer back to this node later on
        item.setData(data_item.unique_id, self._SG_ITEM_UNIQUE_ID)

        # store the actual value we have
        item.setData(
            {"name": data_item.field, "value": data_item.shotgun_data[data_item.field]},
            self.SG_ASSOCIATED_FIELD_ROLE
        )

        if data_item.is_leaf():
            # this is the leaf level!
            # attach the shotgun data so that we can access it later
            # note: Qt automatically changes everything to be unicode
            # according to strange rules of its own, so force convert
            # all shotgun values to be proper unicode prior to setData
            item.setData(sanitize_for_qt_model(data_item.shotgun_data), self.SG_DATA_ROLE)

        # Now we got the object set up. Now start calling custom methods:

        # allow item customization prior to adding to model
        # note: this now runs both on update and create, which may be
        #       conceptually confusing.
        self._item_created(item)

        # set up default thumb
        self._populate_default_thumbnail(item)

        # run the populate item method
        if data_item.is_leaf():
            self._populate_item(item, data_item.shotgun_data)
        else:
            self._populate_item(item, None)

        self._set_tooltip(item, data_item.shotgun_data)

    ########################################################################################
    # private methods

    def __compute_cache_path(self, cache_seed=None):
        """
        Calculates and returns a cache path to use for this instance's query.

        :param cache_seed: Cache seed supplied to the ``__init__`` method.

        :return: The path to use when caching the model data.
        :rtype: str
        """

        # when we cache the data associated with this model, create
        # the file name and path based on several parameters.
        # the path will be on the form CACHE_LOCATION/cached_sg_queries/EntityType/params_hash/filter_hash
        #
        # params_hash is an md5 hash representing all parameters going into a particular
        # query setup and filters_hash is an md5 hash of the filter conditions.
        #
        # the reason these are split up is because the params tend to be constant and
        # the filters keep varying depending on user input.
        #
        # some comment regarding the fields that make up the hash
        #
        # fields, order, hierarchy are all coming from Shotgun
        # and are used to uniquely identify the cache file. Typically,
        # code using the shotgun model will keep these fields constant
        # while varying filters. With the filters hashed separately,
        # this typically generates a folder structure where there is one
        # top level folder containing a series of cache files
        # all for different filters.
        #
        # the schema generation is used for advanced implementations
        # See constructor docstring for details.
        #
        # bg_load_thumbs is hashed so that the system can cache
        # thumb and non-thumb caches independently. This is because
        # as soon as you start caching thumbnails, qpixmap will be used
        # internally by the serialization and this means that you get
        # warnings if you try to use those caches in threads. By keeping
        # caches separate, there is no risk that a thumb cache 'pollutes'
        # a non-thumb cache.
        #
        # now hash up the rest of the parameters and make that the filename
        params_hash = hashlib.md5()
        params_hash.update(str(self.__schema_generation))
        params_hash.update(str(self.__fields))
        params_hash.update(str(self.__order))
        params_hash.update(str(self.__hierarchy))
        # If this value changes over time (like between Qt4 and Qt5), we need to
        # assume our previous user roles are invalid since Qt might have taken over
        # it. If role's value is 32, don't add it to the hash so we don't
        # invalidate PySide/PyQt4 caches.
        if QtCore.Qt.UserRole != 32:
            params_hash.update(str(QtCore.Qt.UserRole))

        # now hash up the filter parameters and the seed - these are dynamic
        # values that tend to change and be data driven, so they are handled
        # on a different level in the path
        filter_hash = hashlib.md5()
        filter_hash.update(str(self.__filters))
        filter_hash.update(str(self.__additional_filter_presets))
        params_hash.update(str(cache_seed))

        # Organize files on disk based on entity type and then filter hash
        # keep extension names etc short in order to stay away from MAX_PATH
        # on windows.
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
            "sg",
            self.__entity_type,
            params_hash.hexdigest(),
            "%s.%s" % (filter_hash.hexdigest(), ShotgunFindDataHandler.FORMAT_VERSION)
        )

        if sys.platform == "win32" and len(data_cache_path) > 250:
            self._log_warning(
                "Shotgun model data cache file path may be affected by windows "
                "windows MAX_PATH limitation."
            )

        return data_cache_path

    def __generate_display_name(self, field, sg_data):
        """
        Generates a name from a shotgun field.
        For non-nested structures, this is typically just "code".
        For nested structures it can either be something like sg_sequence
        or something like sg_asset_type.

        :params field: field name to generate name from
        :params sg_data: sg data dictionary, straight from shotgun, no unicode, all UTF-8
        :returns: name string
        """
        value = sg_data.get(field)

        if isinstance(value, dict) and "name" in value and "type" in value:
            if value["name"] is None:
                return "Unnamed"
            else:
                return value["name"]

        elif isinstance(value, list):
            # this is a list of some sort. Loop over all elements and extrat a comma separated list.
            formatted_values = []
            if len(value) == 0:
                # no items in list
                formatted_values.append("No Value")
            for v in value:
                if isinstance(v, dict) and "name" in v and "type" in v:
                    # This is a link field
                    if v.get("name"):
                        formatted_values.append(v.get("name"))
                else:
                    formatted_values.append(str(v))

            return ", ".join(formatted_values)

        elif value is None:
            return "Unnamed"

        else:
            # everything else just cast to string
            return str(value)
