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
import urlparse
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

# logger for this module
logger = sgtk.platform.get_logger(__name__)


class ShotgunQueryModel(QtGui.QStandardItemModel):
    """
    A Qt Model base class for querying Shotgun data.

    This class is not meant to be used as-is, rather it provides a common
    interface (methods, signals, etc) that users can expect across various
    Shotgun data models.

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

    # XXX whats the interface we present... include _load_data and _refresh_data?

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

    # internal constants - please do not access directly but instead use the helper
    # methods provided! We may change these constants without prior notice.
    SG_DATA_ROLE = QtCore.Qt.UserRole + 1
    IS_SG_MODEL_ROLE = QtCore.Qt.UserRole + 2

    def __init__(self, parent, bg_task_manager=0):
        """
        Initializes the model and provides some default convenience members.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        The following instance members are created for use in subclasses:

        :protected _bundle: The current toolkit bundle
        :protected _shotgun_data: ``shotgunutils.shotgun_data`` handle
        :protected _shotgun_globals: ``shotgunutils.shotgun_globals`` handle
        :protected _sg_data_retriever: A ``ShotgunDataRetriever`` instance.
            Subclasses are responsible for starting it. Connected to virtual
            callback methods ``_on_data_retriever_work_completed`` and
            ``_on_data_retriever_work_failure`` which subclasses must implement.

        """

        super(ShotgunQueryModel, self).__init__(parent)

        # keep a handle to the current bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        # importing these locally to not trip sphinx's imports
        # shotgun_globals is often used for accessing cached schema information
        # such as entity type and field display values.
        self._shotgun_globals = self._bundle.import_module("shotgun_globals")
        self._shotgun_data = self._bundle.import_module("shotgun_data")

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
    # public methods to be implemented in subclasses

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

        raise NotImplementedError(
            "The 'hard_refresh' method has not been implemented for this "
            "ShotgunQueryModel subclass."
        )

    def is_data_cached(self):
        """
        Determine if the model has any cached data

        :return: ``True`` if cached data exists for the model, ``False``
            otherwise.
        """

        raise NotImplementedError(
            "The 'is_data_cached' method has not been implemented for this "
            "ShotgunQueryModel subclass."
        )

    ############################################################################
    # methods overridden from Qt base class

    def reset(self):
        # XXX candidate for base class
        """
        Reimplements QAbstractItemModel:reset() by 'sealing it' so that it
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
    # 

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

        .. note:: This is typically subclassed if you retrieve additional 
            fields alongside the standard "name" field and you want to put
            those into various custom data roles. These custom fields on the
            item can later on be picked up by custom (delegate) rendering code
            in the view.

        :param item: :class:`~PySide.QtGui.QStandardItem` that is about to be
            added to the model. This has been primed with the standard settings
            that the ShotgunModel handles.

        :param sg_data: Shotgun data dictionary that was received from Shotgun
            given the fields and other settings specified in _load_data()
        """
        # default implementation does nothing
        pass

    def _finalize_item(self, item):
        """
        Called whenever an item is fully constructed, either because a shotgun query returned it
        or because it was loaded as part of a cache load from disk.

        .. note:: You can subclass this if you want to run post processing on
            the data as it is arriving. For example, if you are showing a list of
            task statuses in a filter view, you may want to remember which
            statuses a user had checked and unchecked the last time he was running
            the tool. By subclassing this UI you can easily apply those settings
            before items appear in the UI.

        :param item: :class:`~PySide.QtGui.QStandardItem` that is about to be added to the model.
            This has been primed with the standard settings that the ShotgunModel handles.
        """
        # the default implementation does nothing
        pass

    def _set_tooltip(self, item, data):
        # XXX docs
        pass

    def _before_data_processing(self, data):
        """
        Called just after data has been retrieved from Shotgun but before any processing
        takes place.

        .. note:: You can subclass this if you want to perform summaries,
            calculations and other manipulations of the data before it is
            passed on to the model class. For example, if you request the model
            to retrieve a list of versions from Shotgun given a Shot,
            you can then subclass this method to cull out the data so that you
            are only left with the latest version for each task. This method
            is often used in conjunction with the order parameter in :meth:`_load_data()`.

        :param data: a shotgun dictionary, as retunrned by a CRUD SG API call.
        :returns: should return a shotgun dictionary, of the same form as the input.
        """
        # default implementation is a passthrough
        return data

    def _load_external_data(self):
        """
        Called whenever the model needs to be rebuilt from scratch. This is called prior
        to any shotgun data is added to the model.

        .. note:: You can subclass this to add custom data to the model in a very
            flexible fashion. If you for example are loading published files from
            Shotgun, you could use this to load up a listing of files on disk,
            resulting in a model that shows both published files and local files.
            External data will not be cached by the ShotgunModel framework.

        :returns: list of :class:`~PySide.QtGui.QStandardItem`
        """
        pass

    def _on_data_retriever_work_failure(self, uid, msg):
        """
        Asynchronous callback - the data retriever failed to do some work

        :param uid: The unique id of the work that failed
        :param msg: The error message returned for the failure
        """
        raise NotImplementedError(
            "The '_on_data_retriever_work_failure' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )

    def _on_data_retriever_work_completed(self, uid, request_type, data):
        """
        Signaled whenever the data retriever completes some work.
        This method will dispatch the work to different methods
        depending on what async task has completed.

        :param uid:             The unique id of the work that completed
        :param request_type:    Type of work completed
        :param data:            Result of the work
        """
        raise NotImplementedError(
            "The '_on_data_retriever_work_completed' method has not been "
            "implemented for this ShotgunQueryModel subclass."
        )

    ########################################################################################
    # protected convenience methods

    def _do_depth_first_tree_deletion(self, node):
        """
        Depth first interation and deletion of all child nodes

        :param node: :class:`~PySide.QtGui.QStandardItem` tree node
        """

        # depth first traversal
        for index in xrange(node.rowCount()):
            child_node = node.child(index)
            self._do_depth_first_tree_deletion(child_node)

        # delete the child leaves
        for index in range(node.rowCount())[::-1]:
            node.removeRow(index)

    def _sg_clean_data(self, sg_data):
        # XXX docs

        # QT is struggling to handle the special timezone class that the shotgun
        # API returns. in fact, on linux it is struggling to serialize any
        # complex object via QDataStream.
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
        Compares two sg dicts, assumes the same set of keys in both.
        Omits thumbnail fields because these change all the time (S3).
        Both inputs are assumed to contain utf-8 encoded data.
        """
        # handle file attachment data as a special case. If the attachment has been uploaded,
        # it will contain an amazon url.
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
        # https://sg-media-usor-01.s3.amazonaws.com/xxx/yyy/filename.ext?lots_of_authentication_headers
        #
        # the query string changes all the times, so when we check if an item is out of date, omit it.
        elif (isinstance(a, str) and isinstance(b, str)
              and a.startswith("http") and b.startswith("http")
              and ("amazonaws" in a or "AccessKeyId" in a)):
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

