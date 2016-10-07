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
from sgtk.platform.qt import QtCore, QtGui

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


    def __init__(self, parent, bg_task_manager=None):
        """
        Initializes the model and provides some default convenience members.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        :param bg_task_manager: Background task manager to use for any
            asynchronous work. If this is None then a task manager will be
            created as needed.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`

        The following instance members are created for use in subclasses:

        :protected _bundle: The current toolkit bundle

        :protected _shotgun_data: ``shotgunutils.shotgun_data`` handle

        :protected _shotgun_globals: ``shotgunutils.shotgun_globals`` handle

        :protected _sg_data_retriever: A ``ShotgunDataRetriever`` instance.
            Connected to virtual slots ``_on_data_retriever_work_completed``
            and ``_on_data_retriever_work_failure`` which subclasses must
            implement.

        """
        # intialize the Qt base class
        super(ShotgunQueryModel, self).__init__(parent)

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

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

        # set up data retriever and start work:
        self._sg_data_retriever = self._shotgun_data.ShotgunDataRetriever(
            parent=self,
            bg_task_manager=bg_task_manager
        )
        self._sg_data_retriever.work_completed.connect(
            self._on_data_retriever_work_completed)
        self._sg_data_retriever.work_failure.connect(
            self._on_data_retriever_work_failure)
        self._sg_data_retriever.start()

    ############################################################################
    # public methods

    def clear(self):
        """
        Removes all items (including header items) from the model and
        sets the number of rows and columns to zero.
        """

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
            # subsequently cleared and deallocated by QT itself (on the C++
            # side) often results in dangling pointers across the pyside/QT
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
        Clear any caches on disk, then refresh the data.
        """
        if self._data_handler is None:
            # no data to refresh
            return

        # delete cache file
        self._data_handler.remove_cache()
        # request a reload
        self._refresh_data()

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
        PySide/QT manages memory.

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

    ############################################################################
    # abstract, protected slots. these methods are connected to the internal
    # data retriever's signals during initialization, so subclasses should
    # implement these to act accordingly.

    def _on_data_retriever_work_failure(self, uid, msg):
        """
        Asynchronous callback - the data retriever failed to do some work

        :param uid: The unique id of the work that failed
        :param msg: The error message returned for the failure

        Abstract method
        """
        raise NotImplementedError(
            "The '_on_data_retriever_work_failure' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )

    def _on_data_retriever_work_completed(self, uid, request_type, data):
        """
        Signaled whenever the data retriever completes some work.

        Dispatch the work to different methods depending on what async task has
        completed.

        :param uid:             The unique id of the work that completed
        :param request_type:    Type of work completed
        :param data:            Result of the work

        Abstract method
        """
        raise NotImplementedError(
            "The '_on_data_retriever_work_completed' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )

    ############################################################################
    # abstract, protected methods. these methods should be implemented by
    # subclasses to provide a consistent developer experience.

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

        raise NotImplementedError(
            "The '_refresh_data' method has not been "
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

        .. note:: When an item is fetched from the cache, this method is *not*
            called, it will only be called when shotgun data initially arrives
            from a Shotgun API query.

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

    ############################################################################
    # protected convenience methods. these methods can be used by subclasses
    # to manipulate and manage data returned from Shotgun.

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
        for index in range(node.rowCount())[::-1]:
            node.removeRow(index)

