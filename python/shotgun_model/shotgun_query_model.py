# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import datetime
import errno
import os
import urlparse
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

from .errors import ShotgunModelError, CacheReadVersionMismatch
from .shotgun_standard_item import ShotgunStandardItem
from .util import get_sg_data


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

    Class Members
    -------------

    Subclasses can set a ``_SG_QUERY_MODEL_ITEM_CLASS`` class member that
    identifies the class of item to use when constructing the model. This is
    also used during deserialization to create model items. The default is
    the ``ShotgunStandardItem``. If overriding, the class must subclass from
    ``ShotgunStandardItem``.

        _SG_QUERY_MODEL_ITEM_CLASS = ShotgunStandardItem

    Subclasses must also define the ``_SG_DATA_UNIQUE_ID_FIELD`` class member.
    This is used to specify the field in the Shotgun payload that is used to
    uniquely identify an item in the model.

        _SG_DATA_UNIQUE_ID_FIELD = "id"

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

    # ---- "abstract" class members

    # subclasses should define a unique id field from the SG data for use in
    # caching and associating data with items in the model
    _SG_DATA_UNIQUE_ID_FIELD = None

    # subclasses should define the class to use when loading items from disk
    _SG_QUERY_MODEL_ITEM_CLASS = ShotgunStandardItem

    # ---- caching/serialization related costants

    # magic number for IO streams
    _FILE_MAGIC_NUMBER = 0xDEADBEEF

    # version of binary format
    _FILE_VERSION = 22

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

        # ensure subclasses define the required class members
        if not self._SG_DATA_UNIQUE_ID_FIELD:
            raise ShotgunModelError(
                "ShotgunQueryModel subclass does not define the instance attr: "
                "`_SG_DATA_UNIQUE_ID_FIELD`"
            )

        # intialize the Qt base class
        super(ShotgunQueryModel, self).__init__(parent)

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        # path to this instance's cache on disk
        self.__full_cache_path = None

        # importing these locally to not trip sphinx's imports
        # shotgun_globals is often used for accessing cached schema information
        # such as entity type and field display values.
        self._shotgun_globals = self._bundle.import_module("shotgun_globals")
        self._shotgun_data = self._bundle.import_module("shotgun_data")

        # keep various references to all items that the model holds.
        # some of these data structures are to keep the GC
        # happy, others to hold alternative access methods to the data.
        self.__all_tree_items = []
        self.__tree_data = {}

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
            self.__tree_data = {}

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

        # delete cache file
        if self._cache_path and os.path.exists(self._cache_path):
            try:
                os.remove(self._cache_path)
                self._log_debug(
                    "Removed cache file '%s' from disk." % self._cache_path
                )
            except Exception, e:
                self._log_warning(
                    "Hard refresh failed and could not remove cache file '%s' "
                    "from disk. Details: %s" % (self._cache_path, e)
                )

        self._refresh_data()

    def is_data_cached(self):
        """
        Determine if the model has any cached data.

        :return: ``True`` if cached data exists for the model, ``False``
            otherwise.
        """

        return self._cache_path and os.path.exists(self._cache_path)

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
    # protected properties

    def _get_cache_path(self):
        """
        Returns the cache path on disk for this instance.
        """
        return self.__full_cache_path

    def _set_cache_path(self, path):
        """
        Set the cache path for this instance.

        :param str path:
        """

        self._log_debug("Cache path set to: %s" % (path,))
        self.__full_cache_path = path

    # define the property for python 2.5 and older
    _cache_path = property(_get_cache_path, _set_cache_path)

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

    def _load_data(self, *args, **kwargs):
        """
        This is the main method used to configure the model. The method should
        essentially define a SG query to begin tracking a particular set of
        parameters.

        Any existing data in contained in the model should be cleared.

        This method should not call the Shotgun API. If cached data is
        available, it should be immediately loaded (this operation should be
        very fast even for substantial amounts of data).

        To refresh the data contained in the model, clients should call the
        :meth:`_refresh_data()` method.

        :param args: Arguments required for loading data.
        :param kwargs: Keyword arguments required for loading data.

        :returns: ``True`` if cached data was loaded, ``False`` otherwise.
        """

        raise NotImplementedError(
            "The '_load_data' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )

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

    def _before_item_removed(self, item):
        """
        Called just before an item is removed from the model.

        .. warning:: This base class implementation must be called in any
            subclasses overriding this behavior. Failure to do so will result in
            unexpected behavior.

        The base class handles cleaning up the underlying item lookup when an
        item is removed.

        :param item: The item about to be removed
        :type item: :class:`~PySide.QtGui.QStandardItem`
        """

        data = get_sg_data(item)
        if data and self._SG_DATA_UNIQUE_ID_FIELD in data:
            uid = data.get(self._SG_DATA_UNIQUE_ID_FIELD)
            # remove the item from the tree data lookup
            del self.__tree_data[uid]

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

        # try to retrieve the uniqe identifier for this item via the data
        data = get_sg_data(item)
        if data and self._SG_DATA_UNIQUE_ID_FIELD in data:
            # found the field in the data. store the item in the lookup
            uid = data[self._SG_DATA_UNIQUE_ID_FIELD]
            self.__tree_data[uid] = item

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

    def _get_all_item_unique_ids(self):
        """
        Conveneince method. Returns the unique IDs of all items in the model.

        The unique IDs correspond to the field defined by
        ``_SG_DATA_UNIQUE_ID_FIELD``

        :return: A list of uniqe ids for all items in the model.
        :rtype: ``list``
        """

        return self.__tree_data.keys()

    def _get_item_by_unique_id(self, uid):
        """
        Convenience method. Returns an item given a unique ID.

        The unique ``uid`` corresponds to the field defined by
        ``_SG_DATA_UNIQUE_ID_FIELD``

        :param id: The unique id for an item in the model.

        :return: An item corresponding to the supplied uniqueid
        :rtype: :class:`~PySide.QtGui.QStandardItem`
        """

        if uid not in self.__tree_data:
            return None

        return self.__tree_data[uid]

    def _load_cached_data(self):
        """
        Convenience wrapper from loading cached data from disk.

        Handles logging cache load attempts/failures.

        :returns: ``True`` if data loaded from disk, ``False`` otherwise.
        """

        # warn if the cache file does not exist
        if not self._cache_path or not os.path.exists(self._cache_path):
            self._log_debug(
                "Data cache file does not exist on disk.\n"
                "Looking here: %s" % (self._cache_path,)
            )
            return False

        self._log_debug(
            "Now attempting cached data load from: %s ..." %
            (self._cache_path,)
        )

        try:
            time_before = time.time()
            num_items = self.__load_from_disk()
            time_diff = (time.time() - time_before)
            self._log_debug(
                "Loading finished! Loaded %s items in %4fs" %
                (num_items, time_diff)
            )
            self.cache_loaded.emit()
            return True
        except Exception, e:
            self._log_debug(
                "Couldn't load cache data from disk.\n"
                " Will proceed with full SG load.\n"
                "Error reported: %s" % (e,)
            )
            return False

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

    def _sg_clean_data(self, sg_data):
        """
        Recursively clean the supplied SG data for use by clients.

        This method currently handles:

            - Converting datetime objects to universal time stamps.

        :param sg_data:
        :return:
        """
        # Older versions of Shotgun return special timezone classes. QT is
        # struggling to handle these. In fact, on linux it is struggling to
        # serialize any complex object via QDataStream. So we need to account
        # for this for older versions of SG.
        #
        # Convert time stamps to unix time. Unix time is a number representing
        # the timestamp in the number of seconds since 1 Jan 1970 in the UTC
        # timezone. So a unix timestamp is universal across time zones and DST
        # changes.
        #
        # When you are pulling data from the shotgun model and want to convert
        # this unix timestamp to a *local* timezone object, which is typically
        # what you want when you are displaying a value on screen, use the
        # following code:
        # >>> local_datetime = datetime.fromtimestamp(unix_time)
        #
        # furthermore, if you want to turn that into a nicely formatted string:
        # >>> local_datetime.strftime('%Y-%m-%d %H:%M')

        if isinstance(sg_data, dict):
            for k in sg_data.keys():
                sg_data[k] = self._sg_clean_data(sg_data[k])
        elif isinstance(sg_data, list):
            for i in range(len(sg_data)):
                sg_data[i] = self._sg_clean_data(sg_data[i])
        elif isinstance(sg_data, datetime.datetime):
            # convert to unix timestamp, local time zone
            sg_data = time.mktime(sg_data.timetuple())

        return sg_data

    def _sg_compare_data(self, a, b):
        """
        Compares two dicts, assumes the same set of keys in both.
        Omits thumbnail fields because these change all the time (S3).
        Both inputs are assumed to contain utf-8 encoded data.
        """
        # handle file attachment data as a special case. If the attachment has
        # been uploaded, it will contain an amazon url.
        #
        # example:
        # {'name': 'review_2015-05-13_16-53.mov',
        #  'url': 'https://....',
        #  'content_type': 'video/quicktime',
        #  'type': 'Attachment',
        #  'id': 24919,
        #  'link_type': 'upload'}
        #
        if isinstance(a, dict) and isinstance(b, dict):
            # keep it simple here. if both values are dicts, iterate
            # over each of the keys and compare them separately
            # S3 string equality will be automatically handled by
            # the logic above.
            for a_key in a.keys():
                if not self._sg_compare_data(a.get(a_key), b.get(a_key)):
                    return False

        # handle thumbnail fields as a special case
        # thumbnail urls are (typically, there seem to be several standards!)
        # on the form:
        # https://sg-media-usor-01.s3.amazonaws.com/xxx/yyy/
        #   filename.ext?lots_of_authentication_headers
        #
        # the query string changes all the times, so when we check if an item
        # is out of date, omit it.
        elif (isinstance(a, str) and isinstance(b, str) and
              a.startswith("http") and b.startswith("http") and
              ("amazonaws" in a or "AccessKeyId" in a)):
            # attempt to parse values are urls and eliminate the querystring
            # compare hostname + path only
            url_obj_a = urlparse.urlparse(a)
            url_obj_b = urlparse.urlparse(b)
            compare_str_a = "%s/%s" % (url_obj_a.netloc, url_obj_a.path)
            compare_str_b = "%s/%s" % (url_obj_b.netloc, url_obj_b.path)
            if compare_str_a != compare_str_b:
                # url has changed
                return False

        elif a != b:
            return False

        return True

    ############################################################################
    # additional method used during de/serialization of model contents

    def _save_to_disk(self):
        """
        Save the model to disk using QDataStream serialization.
        This all happens on the C++ side and is very fast.
        """

        filename = self._cache_path

        # set umask to zero, store old umask
        old_umask = os.umask(0)
        try:
            # try to create the cache folder with as open permissions as
            # possible
            cache_dir = os.path.dirname(filename)

            # make sure the cache directory exists
            if not os.path.exists(cache_dir):
                try:
                    os.makedirs(cache_dir, 0777)
                except OSError, e:
                    # Race conditions are perfectly possible on some network
                    # storage setups so make sure that we ignore any file
                    # already exists errors, as they are not really errors!
                    if e.errno != errno.EEXIST:
                        # re-raise
                        raise

            # write cache file
            fh = QtCore.QFile(filename)
            fh.open(QtCore.QIODevice.WriteOnly)
            try:
                out_stream = QtCore.QDataStream(fh)

                # write a header
                out_stream.writeInt64(self._FILE_MAGIC_NUMBER)
                out_stream.writeInt32(self._FILE_VERSION)

                # todo: if it turns out that there are ongoing issues with
                # md5 cache collisions, we could write the actual query
                # parameters to the header of the cache file here and compare
                # that against the desired query info just to be confident we
                # are getting a correct cache...

                # tell which serialization dialect to use
                out_stream.setVersion(QtCore.QDataStream.Qt_4_0)

                root = self.invisibleRootItem()
                self.__save_to_disk_r(out_stream, root, 0)

            finally:
                fh.close()

                # set mask back to previous value
                os.umask(old_umask)

            # and ensure the cache file has got open permissions
            os.chmod(filename, 0666)

        except Exception, e:
            self._log_warning(
                "Could not write cache file '%s' to disk: %s" % (filename, e))

    ############################################################################
    # private methods

    def __do_depth_first_tree_deletion(self, node):
        """
        Depth first interation and deletion of all child nodes

        :param node: :class:`~PySide.QtGui.QStandardItem` tree node
        """

        # depth first traversal
        for index in xrange(node.rowCount()):
            child_node = node.child(index)
            self.__do_depth_first_tree_deletion(child_node)

        # delete the child leaves
        for index in range(node.rowCount())[::-1]:
            node.removeRow(index)

    def __load_from_disk(self):
        """
        Load a serialized model from disk./

        :returns: Number of items loaded
        """
        num_items_loaded = 0

        # open the data cache for reading
        fh = QtCore.QFile(self._cache_path)
        fh.open(QtCore.QIODevice.ReadOnly)

        try:
            in_stream = QtCore.QDataStream(fh)

            magic = in_stream.readInt64()
            if magic != self._FILE_MAGIC_NUMBER:
                raise Exception("Invalid file magic number!")

            version = in_stream.readInt32()
            if version != self._FILE_VERSION:
                raise CacheReadVersionMismatch(
                    "Cache file version %s, expected version %s" %
                    (version, self._FILE_VERSION)
                )

            # tell which deserialization dialect to use
            in_stream.setVersion(QtCore.QDataStream.Qt_4_0)

            curr_parent = self.invisibleRootItem()
            prev_node = None
            curr_depth = 0

            while not in_stream.atEnd():

                # this is the item where the deserialized data will live
                item = self._SG_QUERY_MODEL_ITEM_CLASS()
                num_items_loaded += 1

                # keep a reference to this object to make GC happy (pyside may
                # crash otherwise)
                self.__all_tree_items.append(item)
                item.read(in_stream)
                node_depth = in_stream.readInt32()

                # all nodes have a unique identifier stored in their metadata
                # the role data accessible via item.data() contains the
                # identifier for this item.
                sg_data = get_sg_data(item)

                if sg_data:
                    # add the model item to our tree data dict keyed by the
                    # unique identifier
                    uid = sg_data.get(self._SG_DATA_UNIQUE_ID_FIELD)
                    if uid:
                        self.__tree_data[uid] = item

                # serialized items contain some sort of strange low-rez thumb
                # data which we cannot use. Make sure that is all cleared.
                item.setIcon(QtGui.QIcon())

                # allow item customization prior to adding to model
                self._item_created(item)

                # serialized items do not contain a full high rez thumb, so
                # re-create that. First, set the default thumbnail
                self._populate_default_thumbnail(item)

                # run the finalize method so that subclasses can do any setup
                # they need
                self._finalize_item(item)

                if node_depth == curr_depth + 1:
                    # this new node is a child of the previous node
                    curr_parent = prev_node
                    if prev_node is None:
                        raise Exception("File integrity issues!")
                    curr_depth = node_depth

                elif node_depth > curr_depth + 1:
                    # something's wrong!
                    raise Exception("File integrity issues!")

                elif node_depth < curr_depth:
                    # we are going back up to parent level
                    while curr_depth > node_depth:
                        curr_depth -= 1
                        curr_parent = curr_parent.parent()
                        if curr_parent is None:
                            # we reached the root. special case
                            curr_parent = self.invisibleRootItem()

                # get complete row containing all columns for the current item
                row = self._get_columns(item, bool(sg_data))

                # and attach the node
                curr_parent.appendRow(row)

                prev_node = item
        finally:
            fh.close()

        return num_items_loaded

    def __save_to_disk_r(self, stream, item, depth):
        """
        Recursive tree writer.

        Recursively writes the item and its children to the supplied stream.

        :param stream: A ``QtCore.QDataStream`` for serializing the items
        :param item: The item to serialize recursively
        :param int depth: The current depth
        """
        num_rows = item.rowCount()
        for row in range(num_rows):
            # write this
            child = item.child(row)
            # only write shotgun data!
            # data from external sources is never serialized
            if child.data(self.IS_SG_MODEL_ROLE):
                child.write(stream)
                stream.writeInt32(depth)

            if child.hasChildren():
                # write children
                self.__save_to_disk_r(stream, child, depth+1)

