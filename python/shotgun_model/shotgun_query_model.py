# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
# toolkit imports
import sgtk
import weakref
import datetime

# NOTE: This is a dummy call to work around a known bug in datetime
# whereby there is code imported at call time that is done so in a
# manner that is not threadsafe. Calling it here, where we know we
# are in the main thread, means the non-threadsafe stuff is out of
# the way later on when it might be used from a thread.
#
# https://stackoverflow.com/questions/16309650/python-importerror-for-strptime-in-spyder-for-windows-7
datetime.datetime.strptime('2012-01-01', '%Y-%m-%d')

from sgtk.platform.qt import QtCore, QtGui

from .util import sanitize_qt

from .shotgun_standard_item import ShotgunStandardItem


class ShotgunQueryModel(QtGui.QStandardItemModel):
    """
    A Qt Model base class for querying Shotgun data.

    This class is not meant to be used as-is, rather it provides a common
    interface (methods, signals, etc) for developers to provide across various
    Shotgun data query models.

    Some convenience methods are also provided for handling and manipulating
    data returned from Shotgun.

    Signal Interface
    ----------------

    :signal query_changed(): Gets emitted whenever the model's sg query is
        changed. When the query changes, the contents of the model is cleared
        and the loading of new data is initiated.

    :signal cache_loaded(): Emitted whenever the model loads cache data.
        This typically follows shortly after a query changed signal, if
        cache data is available.

    :signal data_refreshing(): Emitted whenever the model starts to refresh its
        shotgun data. Useful signal if you want to present a loading indicator
        of some kind.

    :signal data_refreshed(bool): Emitted whenever the model has been updated
        with fresh shotgun data. The boolean indicates that a change in the
        model data has taken place as part of this process. If the refresh fails
        for some reason, this signal may not be emitted.

    :signal data_refresh_fail(str): Emitted in the case the refresh fails for
        some reason, typically due to the absence of an internet connection.
        This signal could for example be used to drive a "retry" button of some
        kind. The str parameter carries an error message with details about why
        the refresh wasn't successful.

    Constants
    ---------

    :constant SG_DATA_ROLE: Custom model role that holds the shotgun data
        payload

    :constant IS_SG_MODEL_ROLE: Used to identify model items related to Shotgun
        data


    """

    # ---- signals

    # signal emitted after the model's sg query is changed
    query_changed = QtCore.Signal()

    # signal emitted after the model loads cache data
    cache_loaded = QtCore.Signal()

    # signal emitted before the model starts to refresh its shotgun data
    data_refreshing = QtCore.Signal()

    # signal emitted after the model is updated with fresh shotgun data
    data_refreshed = QtCore.Signal(bool)

    # signal emitted in the case the refresh fails
    data_refresh_fail = QtCore.Signal(str)

    # ---- internal constants

    # please do not access directly but instead use the helper
    # methods provided! We may change these constants without prior notice.
    SG_DATA_ROLE = QtCore.Qt.UserRole + 1
    IS_SG_MODEL_ROLE = QtCore.Qt.UserRole + 2

    # data role used to track whether more data has been fetched for items
    _SG_ITEM_FETCHED_MORE = QtCore.Qt.UserRole + 3
    _SG_ITEM_HAS_CHILDREN = QtCore.Qt.UserRole + 4
    _SG_ITEM_UNIQUE_ID = QtCore.Qt.UserRole + 5


    def __init__(self, parent, bg_load_thumbs, bg_task_manager=None):
        """
        Initializes the model and provides some default convenience members.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        :param bg_load_thumbs: If set to True, thumbnails will be loaded in the background.
        :param bg_task_manager: Background task manager to use for any
            asynchronous work. If this is None then a task manager will be
            created as needed.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`

        The following instance members are created for use in subclasses:

        :protected _bundle: The current toolkit bundle

        :protected _shotgun_data: ``shotgunutils.shotgun_data`` handle

        :protected _data_handler: :class:`ShotgunDataHandler` instance or None

        :protected _shotgun_globals: ``shotgunutils.shotgun_globals`` handle
        """
        # intialize the Qt base class
        super(ShotgunQueryModel, self).__init__(parent)

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        # should thumbs be processed async
        self.__bg_load_thumbs = bg_load_thumbs

        # a class to handle loading and saving from disk
        self._data_handler = None

        # importing these locally to not trip sphinx's imports
        # shotgun_globals is often used for accessing cached schema information
        # such as entity type and field display values.
        self._shotgun_globals = self._bundle.import_module("shotgun_globals")
        self._shotgun_data = self._bundle.import_module("shotgun_data")

        # keep various references to all items that the model holds.
        # some of these data structures are to keep the GC
        # happy, others to hold alternative access methods to the data.
        self.__all_tree_items = []
        self.__items_by_uid = {}

        # keep track of current requests
        self.__thumb_map = {}
        self.__current_work_id = None

        # set up data retriever and start work:
        self._sg_data_retriever = self._shotgun_data.ShotgunDataRetriever(
            parent=self,
            bg_task_manager=bg_task_manager
        )
        self._sg_data_retriever.work_completed.connect(self.__on_data_retriever_work_completed)
        self._sg_data_retriever.work_failure.connect(self.__on_data_retriever_work_failure)
        self._sg_data_retriever.start()

    ############################################################################
    # public methods

    def clear(self):
        """
        Removes all items (including header items) from the model and
        sets the number of rows and columns to zero.
        """
        # clear thumbnail download lookup so we don't process any more results:
        self.__thumb_map = {}

        # we are not looking for any data from the async processor
        self.__current_work_id = None

        # Advertise that the model is about to completely cleared. This is super
        # important because proxy models usually cache data like indices and
        # these are about to get updated potentially thousands of times while
        # the tree is being destroyed.
        self.beginResetModel()
        try:
            # note! We are reimplementing this explicitly because the default
            # implementation results in memory issues - similar to reset(),
            # scenarios where objects are constructed in python (e.g.
            # QStandardItems) and then handed over to a model and then
            # subsequently cleared and deallocated by Qt itself (on the C++
            # side) often results in dangling pointers across the pyside/Qt
            # boundary, ultimately resulting in crashes or instability.

            # ask async data retriever to clear its queue of queries
            # note that there may still be requests actually running
            # - these are not cancelled
            if self._sg_data_retriever:
                self._sg_data_retriever.clear()

            # model data in alt format
            self.__items_by_uid = {}

            # pyside will crash unless we actively hold a reference
            # to all items that we create.
            self.__all_tree_items = []

            # lastly, remove all data in the underlying internal data storage
            # note that we don't cannot clear() here since that causing
            # crashing in various environments. Also note that we need to do
            # in a depth-first manner to ensure that there are no
            # cyclic parent/child dependency cycles, which will cause
            # a crash in some versions of shiboken
            # (see https://bugreports.qt-project.org/browse/PYSIDE-158 )
            self.__do_depth_first_tree_deletion(self.invisibleRootItem())

            # unload the data backend
            if self._data_handler:
                self._data_handler.unload_cache()
                self._data_handler = None

        finally:
            # Advertise that we're done resetting.
            self.endResetModel()

    def destroy(self):
        """
        Call this method prior to destroying this object.

        Base implementation ensures the data worker is stopped and calls
        ``clear()`` on the model.
        """
        self.__current_work_id = None
        self.__thumb_map = {}

        # gracefully stop the data retriever:
        self._sg_data_retriever.stop()
        self._sg_data_retriever = None

        # block all signals before we clear the model otherwise downstream
        # proxy objects could cause crashes.
        signals_blocked = self.blockSignals(True)
        try:
            # clear all internal memory storage
            self.clear()
        finally:
            # reset the stage of signal blocking:
            self.blockSignals(signals_blocked)

    def hard_refresh(self):
        """
        Clears any caches on disk, then refreshes the data.
        """
        if self._data_handler is None:
            # no data to refresh
            return

        # delete cache file
        self._data_handler.remove_cache()

        # Clear ourselves, preserving the data handler so that we can then
        # refresh. Clearing the model here ensures we don't end up with
        # duplicate items once the cache is cleared and repopulated.
        #
        # Block all signals before we clear the model otherwise downstream
        # proxy objects could cause crashes.
        signals_blocked = self.blockSignals(True)
        try:
            # First, we need to clear out some internal data from the model. This
            # logic represents part of what happens in a call to the model's
            # clear() method, but we need to omit part of that process, so we're
            # not calling it directly. The below represents the minimum amount of
            # work we need to do to properly refresh the model's data.
            #
            # Clearing the below combats some PySide crashing problems, as outlined
            # in the clear() method, and ensures that when we refresh the model's
            # data below that we don't end up with duplicated items in the model.
            self.__items_by_uid = {}
            self.__all_tree_items = []
            self.__do_depth_first_tree_deletion(self.invisibleRootItem())

            # Repopulate the model with fresh data. Since we've already cleared
            # the data handler's cache, refreshing the data here will pull
            # everything down from Shotgun.
            self._refresh_data()
        finally:
            # Reset the state of signal blocking.
            self.blockSignals(signals_blocked)
            self.modelReset.emit()

    def is_data_cached(self):
        """
        Determine if the model has any cached data.

        :return: ``True`` if cached data exists for the model, ``False``
            otherwise.
        """
        if self._data_handler is None:
            return False

        return self._data_handler.is_cache_available()

    ############################################################################
    # methods overridden from Qt base class

    def reset(self):
        """
        Re-implements QAbstractItemModel:reset() by 'sealing it' so that it
        cannot be executed by calling code easily. This is because the reset
        method often results in crashes and instability because of how
        PySide/Qt manages memory.

        For more information, see the clear() method in ``ShotgunModel``.
        """
        raise NotImplementedError(
            "The QAbstractItemModel::reset method has explicitly been disabled "
            "because memory is not correctly freed up across C++/Python when "
            "executed, sometimes resulting in runtime instability. For an "
            "semi-equivalent method, use clear(), however keep in mind that "
            "this method will not emit the standard before/after reset "
            "signals. It is possible that this method may be implemented in "
            "later versions of the framework. For more information, please "
            "email support@shotgunsoftware.com."
        )

    def hasChildren(self, index):
        """
        Returns True if parent has any children; otherwise returns False.

        This is used for the staged loading of nodes in hierarchies.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """
        if not index.isValid():
            return super(ShotgunQueryModel, self).hasChildren(index)

        item = self.itemFromIndex(index)

        if not isinstance(item, ShotgunStandardItem):
            # there may be items of other types in the model
            # (although unlikely) in that case push to base class
            return super(ShotgunQueryModel, self).hasChildren(index)

        return item.data(self._SG_ITEM_HAS_CHILDREN)

    def fetchMore(self, index):
        """
        Retrieve child items for a node.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """
        if not index.isValid():
            return super(ShotgunQueryModel, self).fetchMore(index)

        item = self.itemFromIndex(index)

        if not isinstance(item, ShotgunStandardItem):
            return super(ShotgunQueryModel, self).fetchMore(index)

        # set the flag to prevent subsequent attempts to fetch more
        item.setData(True, self._SG_ITEM_FETCHED_MORE)

        # query the information for this item to populate its children.
        # the slot for handling worker success will handle inserting the
        # queried data into the tree.
        self._log_debug("Fetching more for item: %s" % item.text())

        unique_id = item.data(self._SG_ITEM_UNIQUE_ID)
        self._data_handler.generate_child_nodes(unique_id, item, self._create_item)

    def canFetchMore(self, index):
        """
        Returns True if there is more data available for parent; otherwise
        returns False.

        :param index: The index of the item being tested.
        :type index: :class:`~PySide.QtCore.QModelIndex`
        """
        if not index.isValid():
            return super(ShotgunQueryModel, self).canFetchMore(index)

        # get the item and its stored hierarchy data
        item = self.itemFromIndex(index)

        if not isinstance(item, ShotgunStandardItem):
            return super(ShotgunQueryModel, self).canFetchMore(index)

        if item.data(self._SG_ITEM_FETCHED_MORE):
            # more data has already been queried for this item
            return False

        # the number of existing child items
        current_child_item_count = item.rowCount()
        data_has_children = item.data(self._SG_ITEM_HAS_CHILDREN)

        # we can fetch more if there are no children already and the item
        # has children.
        return current_child_item_count == 0 and data_has_children


    ############################################################################
    # abstract, protected methods. these methods should be implemented by
    # subclasses to provide a consistent developer experience.

    def _create_item(self, parent, data_item):
        """
        Creates a model item for the tree given data out of the data store

        :param :class:`~PySide.QtGui.QStandardItem` parent: Model item to parent the node under
        :param :class:`ShotgunItemData` data_item: Data to populate new item with

        :returns: Model item
        :rtype: :class:`ShotgunStandardItem`

        Abstract method
        """
        raise NotImplementedError(
            "The '_create_item' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )

    def _update_item(self, item, data_item):
        """
        Updates a model item with the given data

        :param :class:`~PySide.QtGui.QStandardItem` item: Model item to update
        :param :class:`ShotgunItemData` data_item: Data to update item with

        Abstract method
        """
        raise NotImplementedError(
            "The '_update_item' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )


    ############################################################################
    # These methods provide the developer experience for shotgun query models.
    # Subclasses of this abstract class should call these methods as the model
    # is being constructed (as described in the docstrings) such that client
    # developers can further customize to meet their needs.

    def _before_data_processing(self, data):
        """
        Called just after data has been retrieved from Shotgun but before any
        processing takes place.

        .. note:: You can subclass this if you want to perform summaries,
            calculations and other manipulations of the data before it is
            passed on to the model class.

        :param data: a shotgun dictionary, as retunrned by a CRUD SG API call.
        :returns: should return a shotgun dictionary, of the same form as the
            input.
        """
        # default implementation is a passthrough
        return data

    def _finalize_item(self, item):
        """
        Called whenever an item is fully constructed, either because a shotgun
        query returned it or because it was loaded as part of a cache load from
        disk.

        .. note:: You can subclass this if you want to run post processing on
            the data as it is arriving. For example, if you are showing a list
            of task statuses in a filter view, you may want to remember which
            statuses a user had checked and unchecked the last time he was
            running the tool. By subclassing this method you can easily apply
            those settings before items appear in the UI.

        :param item: :class:`~PySide.QtGui.QStandardItem` that is about to be
            added to the model.  This has been primed with the standard settings
            that the ShotgunModel handles.
        """
        # the default implementation does nothing
        pass

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
        # keep a reference to this object to make GC happy
        # (pyside may crash otherwise)
        self.__all_tree_items.append(item)

        # organize items by unique id if they have one
        unique_id = item.data(self._SG_ITEM_UNIQUE_ID)
        if unique_id:
            # found the field in the data. store the item in the lookup
            self.__items_by_uid[unique_id] = item

        return item

    def _get_columns(self, item, is_leaf):
        """
        Returns a row (list of QStandardItems) given an initial QStandardItem.

        The item itself is always the first item in the row, but additional
        columns may be appended.

        :param item: A :class:`~PySide.QtGui.QStandardItem` that is associated
            with this model.
        :param is_leaf: A boolean indicating if the item is a leaf item or not

        :returns: A list of :class:`~PySide.QtGui.QStandardItem` objects
        """

        # the default implementation simply returns the supplied item as the
        # only column. subclasses may provide additional items/columns.
        return [item]

    def _load_external_data(self):
        """
        Called whenever the model needs to be rebuilt from scratch. This is
        called prior to any shotgun data is added to the model.

        .. note:: You can subclass this to add custom data to the model in a
            very flexible fashion. If you for example are loading published
            files from Shotgun, you could use this to load up a listing of
            files on disk, resulting in a model that shows both published files
            and local files.  External data will not be cached by the
            ShotgunModel framework.

        :returns: list of :class:`~PySide.QtGui.QStandardItem`
        """
        pass

    def _populate_default_thumbnail(self, item):
        """
        Called whenever an item is constructed and needs to be associated with
        a default thumbnail.  In the current implementation, thumbnails are not
        cached in the same way as the rest of the model data, meaning that this
        method is executed each time an item is constructed, regardless of if
        it came from an asynchronous shotgun query or a cache fetch.

        The purpose of this method is that you can subclass it if you want to
        ensure that items have an associated thumbnail directly when they are
        first created.

        Later on in the data load cycle, if the model was instantiated with the
        `download_thumbs` parameter set to True, the standard Shotgun ``image``
        field thumbnail will be automatically downloaded for all items (or
        picked up from local cache if possible).

        :param item: :class:`~PySide.QtGui.QStandardItem` that is about to be
            added to the model.  This has been primed with the standard
            settings that the ShotgunModel handles.
        """
        # the default implementation does nothing
        pass

    def _populate_item(self, item, sg_data):
        """
        Whenever an item is downloaded from Shotgun, this method is called. It
        allows subclasses to intercept the construction of a
        :class:`~PySide.QtGui.QStandardItem` and add additional metadata or
        make other changes that may be useful. Nothing needs to be returned.

        This method is called before the item is added into the model tree. At
        the point when the item is added into the tree, various signals will
        fire, informing views and proxy models that a new item has been added.
        This methods allows a subclassing object to add custom data prior to
        this.

        :param item: :class:`~PySide.QtGui.QStandardItem` that is about to be
            added to the model.

        :param sg_data: Shotgun data dictionary that was received from Shotgun.
        """
        # default implementation does nothing
        pass

    def _set_tooltip(self, item, data):
        """
        Sets the tooltip for the supplied item.

        Called when an item is created.

        :param item: Shotgun model item that requires a tooltip.
        :param data: Dictionary of the SG data associated with the model.
        """
        # the default implementation does not set a tooltip
        pass

    def _populate_thumbnail(self, item, field, path):
        """
        Called whenever the real thumbnail for an item exists on disk. The following
        execution sequence typically happens:

        - :class:`~PySide.QtGui.QStandardItem` is created, either through a cache load from disk or
          from a payload coming from the Shotgun API.
        - After the item has been set up with its associated Shotgun data,
          :meth:`_populate_default_thumbnail()` is called, allowing client code to set
          up a default thumbnail that will be shown while potential real thumbnail
          data is being loaded.
        - The model will now start looking for the real thumbail.
        - If the thumbnail is already cached on disk, :meth:`_populate_thumbnail()` is called very soon.
        - If there isn't a thumbnail associated, :meth:`_populate_thumbnail()` will not be called.
        - If there isn't a thumbnail cached, the model will asynchronously download
          the thumbnail from Shotgun and then (after some time) call :meth:`_populate_thumbnail()`.

        This method will be called for standard thumbnails if the model has been
        instantiated with the download_thumbs flag set to be true. It will be called for
        items which are associated with shotgun entities (in a tree data layout, this is typically
        leaf nodes). It will also be called once the data requested via _request_thumbnail_download()
        arrives.

        This method makes it possible to control how the thumbnail is applied and associated
        with the item. The default implementation will simply set the thumbnail to be icon
        of the item, but this can be altered by subclassing this method.

        :param item: :class:`~PySide.QtGui.QStandardItem` which is associated with the given thumbnail
        :param field: The Shotgun field which the thumbnail is associated with.
        :param path: A path on disk to the thumbnail. This is a file in jpeg format.
        """
        # the default implementation sets the icon
        thumb = QtGui.QPixmap(path)
        item.setIcon(thumb)

    def _populate_thumbnail_image(self, item, field, image, path):
        """
        Similar to :meth:`_populate_thumbnail()` but this method is called instead
        when the bg_load_thumbs parameter has been set to true. In this case, no
        loading of thumbnail data from disk is necessary - this has already been
        carried out async and is passed in the form of a QImage object.

        For further details, see :meth:`_populate_thumbnail()`

        :param item: :class:`~PySide.QtGui.QStandardItem` which is associated with the given thumbnail
        :param field: The Shotgun field which the thumbnail is associated with.
        :param image: QImage object with the thumbnail loaded
        :param path: A path on disk to the thumbnail. This is a file in jpeg format.
        """
        # the default implementation sets the icon
        thumb = QtGui.QPixmap.fromImage(image)
        item.setIcon(thumb)

    ############################################################################
    # protected convenience methods. these methods can be used by subclasses
    # to manipulate and manage data returned from Shotgun.

    def _request_data(self, *args, **kwargs):
        """
        Routes a data request to the current :class:`DataHandler` and initiates
        a data fetching operation. Once data has arrived, :meth:`_create_item` and
        :meth:`_update_item` will be called for each created or updated object
        retrieved from the remote data set.

        This is normally called from subclassing implementations when they want
        trigger a new data fetch cycle.

        All parameters passed to this method will be forwarded to
        :meth:`DataHandler.generate_data_request`.
        """
        if not self._sg_data_retriever:
            raise sgtk.TankError("Data retriever is not available!")

        # Stop any queued work that hasn't completed yet.  Note that we intentionally only stop the
        # find query and not the thumbnail cache/download.  This is because the thumbnails returned
        # are likely to still be valid for the current data in the model and if they are stopped then
        # the pattern 'create model->load cached->refresh from sg' would result in empty icons being
        # presented to the user until the shotgun query has completed!
        #
        # This may result in unnecessary thumbnail downloads from Shotgun but in all likelihood, the
        # thumbnails are going to be the same before and after the refresh and any additional overhead
        # should be weighed against a cleaner user experience
        if self.__current_work_id is not None:
            self._sg_data_retriever.stop_work(self.__current_work_id)
            self.__current_work_id = None

        # emit that the data is refreshing.
        self.data_refreshing.emit()

        # request the data asynchronously from the data handler
        self.__current_work_id = self._data_handler.generate_data_request(
            self._sg_data_retriever,
            *args,
            **kwargs
        )

        if self.__current_work_id is None:
            # no async request was needed. process callback directly
            self.__on_sg_data_arrived([])

    def _request_thumbnail_download(self, item, field, url, entity_type, entity_id):
        """
        Request that a thumbnail is downloaded for an item. If a thumbnail is successfully
        retrieved, either from disk (cached) or via shotgun, the method _populate_thumbnail()
        will be called. If you want to control exactly how your shotgun thumbnail is
        to appear in the UI, you can subclass this method. For example, you can subclass
        this method and perform image composition prior to the image being added to
        the item object.

        .. note:: This is an advanced method which you can use if you want to load thumbnail
            data other than the standard 'image' field. If that's what you need, simply make
            sure that you set the download_thumbs parameter to true when you create the model
            and standard thumbnails will be automatically downloaded. This method is either used
            for linked thumb fields or if you want to download thumbnails for external model data
            that doesn't come from Shotgun.

        :param item: :class:`~PySide.QtGui.QStandardItem` which belongs to this model
        :param field: Shotgun field where the thumbnail is stored. This is typically ``image`` but
                      can also for example be ``sg_sequence.Sequence.image``.
        :param url: thumbnail url
        :param entity_type: Shotgun entity type
        :param entity_id: Shotgun entity id
        """
        if url is None:
            # nothing to download. bad input. gracefully ignore this request.
            return

        if not self._sg_data_retriever:
            raise sgtk.ShotgunModelError("Data retriever is not available!")

        uid = self._sg_data_retriever.request_thumbnail(
            url,
            entity_type,
            entity_id,
            field,
            self.__bg_load_thumbs
        )

        # keep tabs of this and call out later - note that we use a weakref to allow
        # the model item to be gc'd if it's removed from the model before the thumb
        # request completes.
        self.__thumb_map[uid] = {
            "item_ref": weakref.ref(item),
            "field": field
        }

    def _ensure_item_loaded(self, uid):
        """
        Ensures that the given unique id is loaded by the model.

        :param str uid: Unique id for a :class:`ShotgunDataHandler` item.
        :returns: :returns: :class:`~PySide.QtGui.QStandardItem` or ``None`` if not found
        """
        data_item = self._data_handler.get_data_item_from_uid(uid)

        if data_item is None:
            # no match in data store
            self._log_debug("...uid '%s' is not part of the data set" % uid)
            return None

        # this node is loaded in the query cached by the data handler
        # but may not exist in the model yet - because of deferred loading.

        # first see if we have it in the model already
        item = self._get_item_by_unique_id(uid)

        if not item:

            # item was not part of the model. Attempt to load its parents until it is visible.
            self._log_debug("Item %s does not exist in the tree - will expand tree." % data_item)

            # now get a list of all parents and recurse back down towards
            # the node we want to load. If at any level, the data has not
            # yet been loaded, we expand that level.
            hierarchy_bottom_up = []
            node = data_item
            while node:
                hierarchy_bottom_up.append(node)
                node = node.parent

            # reverse the list to get the top-down hierarchy
            hierarchy_top_down = hierarchy_bottom_up[::-1]

            self._log_debug("Resolved top-down hierarchy to be %s" % hierarchy_top_down)

            for data_item in hierarchy_top_down:
                # see if we have this item in the tree
                item = self._get_item_by_unique_id(data_item.unique_id)
                if not item:
                    self._log_debug(
                        "Data item %s does not exist in model - fetching parent's children..." % data_item
                    )
                    # this parent does not yet exist in the tree
                    # find the parent and kick it to expand it

                    # assume that the top level is always loaded in tree
                    # so that it's always safe to do data_item.parent.uid here
                    parent_item = self._get_item_by_unique_id(data_item.parent.unique_id)
                    # get model index
                    parent_model_index = parent_item.index()
                    # kick it
                    self.fetchMore(parent_model_index)

            # now try again
            item = self._get_item_by_unique_id(uid)

        return item

    def _get_item_by_unique_id(self, uid):
        """
        Convenience method. Returns an item given a unique ID.

        The unique ``uid`` corresponds to the ``_SG_ITEM_UNIQUE_ID`` role.

        :param uid: The unique id for an item in the model.

        :return: An item corresponding to the supplied uniqueid
        :rtype: :class:`~PySide.QtGui.QStandardItem`
        """
        if uid not in self.__items_by_uid:
            return None
        return self.__items_by_uid[uid]

    def _delete_item(self, item):
        """
        Remove an item and all its children if it exists.
        Removes the entire row that item belongs to.

        :param str uid: The unique id for an item in the model.
        """
        # find all items in subtree and remove them
        # from the uid based lookup to avoid issues
        # where the C++ object has been deleted but we
        # still a pyside reference.
        self.__remove_unique_id_r(item)

        # remove it
        parent_model_item = item.parent()

        if parent_model_item:
            # remove entire row that item belongs to.
            # we are the owner of the data so we just do a `takeRow` and not a
            # `removeRow` to prevent the model to delete the data. Because we
            # don't keep any reference to the item, it will be garbage collected
            # if not already done.
            parent_model_item.takeRow(item.row())

    def _log_debug(self, msg):
        """
        Convenience wrapper around debug logging

        :param msg: debug message
        """
        self._bundle.log_debug("[%s] %s" % (self.__class__.__name__, msg))

    def _log_warning(self, msg):
        """
        Convenience wrapper around warning logging

        :param msg: debug message
        """
        self._bundle.log_warning("[%s] %s" % (self.__class__.__name__, msg))

    ############################################################################
    # private methods

    def __do_depth_first_tree_deletion(self, node):
        """
        Depth first iteration and deletion of all child nodes

        :param node: :class:`~PySide.QtGui.QStandardItem` tree node
        """
        # depth first traversal
        for index in xrange(node.rowCount()):
            child_node = node.child(index)
            self.__do_depth_first_tree_deletion(child_node)

        # delete the child leaves
        for index in xrange(node.rowCount(), 0, -1):
            # notes about xrange syntax:
            # index will count from rowCount down to 1
            # to get zero based indices, subtract 1
            node.removeRow(index - 1)

    def __remove_unique_id_r(self, item):
        """
        Removes the unique id (if one exists) from
        the self.__items_by_uid dictionary for this item
        and all its children

        :param :class:`~PySide.QtGui.QStandardItem` item: Model item to process
        """
        # process children
        for row_index in xrange(item.rowCount()):
            child_item = item.child(row_index)
            self.__remove_unique_id_r(child_item)

        # now process self
        unique_id = item.data(self._SG_ITEM_UNIQUE_ID)
        if unique_id and unique_id in self.__items_by_uid:
            del self.__items_by_uid[unique_id]

    def __on_data_retriever_work_failure(self, uid, msg):
        """
        Asynchronous callback - the data retriever failed to do some work

        :param uid: The unique id of the work that failed
        :param msg: The error message returned for the failure
        """
        uid = sanitize_qt(uid) # qstring on pyqt, str on pyside
        msg = sanitize_qt(msg)

        if self.__current_work_id != uid:
            # not our job. ignore
            self._log_debug("Retrieved error from data worker: %s" % msg)
            return
        self.__current_work_id = None

        full_msg = "Error retrieving data from Shotgun: %s" % msg
        self.data_refresh_fail.emit(full_msg)
        self._log_warning(full_msg)

    def __on_data_retriever_work_completed(self, uid, request_type, data):
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

        if self.__current_work_id == uid:
            # our data has arrived from sg!
            # process the data
            self.__current_work_id = None
            sg_data = data["sg"]
            self.__on_sg_data_arrived(sg_data)

        elif uid in self.__thumb_map:
            # a thumbnail is now present on disk!
            thumb_info = self.__thumb_map[uid]
            del self.__thumb_map[uid]

            thumbnail_path = data["thumb_path"]
            thumbnail = data["image"]

            # if the requested thumbnail has since dissapeared on the server,
            # path and image will be None. In this case, skip processing
            if thumbnail_path:
                # get the model item from the weakref we stored in the thumb info:
                item = thumb_info["item_ref"]()
                if not item:
                    # the model item no longer exists so we can ignore this result!
                    return
                sg_field = thumb_info["field"]

                # call our deriving class implementation
                if self.__bg_load_thumbs:
                    # worker thread already loaded the thumbnail in as a QImage.
                    # call a separate method.
                    self._populate_thumbnail_image(item, sg_field, thumbnail, thumbnail_path)
                else:
                    # worker thread only ensured that the image exists
                    # call method to populate it
                    self._populate_thumbnail(item, sg_field, thumbnail_path)

    def __save_data_async(self, sg):
        """
        Asynchronous callback to perform a cache save in the background.

        :param :class:`Shotgun` sg: Shotgun API instance
        """
        self._log_debug("Begin asynchronously saving cache to disk")
        self._data_handler.save_cache()
        self._log_debug("Asynchronous cache save complete.")

    def __on_sg_data_arrived(self, sg_data):
        """
        Handle asynchronous shotgun data arriving after a find request.

        :param list sg_data: Shotgun data payload.
        """
        self._log_debug("--> Shotgun data arrived. (%s records)" % len(sg_data))

        # pre-process data
        sg_data = self._before_data_processing(sg_data)

        # push shotgun data into our data handler which will figure out
        # if there are any changes
        self._log_debug("Updating data model with new shotgun data...")
        modified_items = self._data_handler.update_data(sg_data)

        self._log_debug("Shotgun data contained %d modifications" % len(modified_items))

        if len(modified_items) > 0:
            # save cache changes to disk in the background
            self._sg_data_retriever.execute_method(self.__save_data_async)

        root = self.invisibleRootItem()
        if root.rowCount() == 0:
            # an empty model - in this case just insert the root level items
            # applying the root changes like this is an optimization so that
            # we don't need to look at the entire data set in the case when
            # it's a deep nested tree structure with an empty cache and lots
            # of items.
            self._log_debug("Model was empty - loading root level items...")
            self._data_handler.generate_child_nodes(None, root, self._create_item)
            self._log_debug("...done")

        else:
            self._log_debug("Begin applying diffs to model...")

            # we have some items loaded into our qt model. Look at the diff
            # and make sure that what's loaded in the model is up to date.
            for item in modified_items:
                data_item = item["data"]

                self._log_debug("Processing change %s" % item)

                if item["mode"] == self._data_handler.ADDED:
                    # look for the parent of this item
                    parent_data_item = data_item.parent
                    if parent_data_item is None:
                        # item is parented under the root
                        parent_model_item = self.invisibleRootItem()
                    else:
                        # this item has a well defined parent
                        # see if this exists in the tree
                        parent_model_item = self._get_item_by_unique_id(parent_data_item.unique_id)

                    if parent_model_item:
                        # The parent exists in the view. It might not because of
                        # lazy loading.
                        # If its children were already populated we need to add
                        # the new ones now. If not, we let fetchMore does its job
                        # later in lazy loading mode.
                        if not self.canFetchMore(parent_model_item.index()):
                            self._log_debug("Creating new model item for %s" % data_item)
                            self._create_item(parent_model_item, data_item)

                elif item["mode"] == self._data_handler.DELETED:
                    # see if the node exists in the tree, in that case delete it.
                    # we check if it exists in the model because it may not have been
                    # loaded in yet by the deferred loader
                    model_item = self._get_item_by_unique_id(data_item.unique_id)
                    if model_item:
                        self._log_debug("Deleting model subtree %s" % model_item)
                        self._delete_item(model_item)

                elif item["mode"] == self._data_handler.UPDATED:
                    # see if the node exists in the tree, in that case update it with new info
                    # we check if it exists in the model because it may not have been
                    # loaded in yet by the deferred loader
                    model_item = self._get_item_by_unique_id(data_item.unique_id)
                    if model_item:
                        self._log_debug("Updating model item %s" % model_item)
                        self._update_item(model_item, data_item)

            self._log_debug("...diffs applied!")

        # and emit completion signal
        self.data_refreshed.emit(len(modified_items) > 0)
