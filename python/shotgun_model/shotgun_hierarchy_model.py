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
import datetime
import hashlib
import os
import sys
import urlparse
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

# framework imports
from .shotgun_hierarchy_item import ShotgunHierarchyItem
from .shotgun_model import ShotgunModelError, CacheReadVersionMismatch
from .util import get_sg_data, sanitize_qt, sanitize_for_qt_model

from ..shotgun_globals import get_entity_type_icon

# logger for this module
logger = sgtk.platform.get_logger(__name__)


class ShotgunHierarchyModel(QtGui.QStandardItemModel):
    # XXX docs

    # signal which gets emitted whenever the model's sg query is changed.
    query_changed = QtCore.Signal()

    # signal which gets emitted whenever the model loads cache data.
    cache_loaded = QtCore.Signal()

    # signal which gets emitted whenever the model starts to refresh its shotgun data.
    data_refreshing = QtCore.Signal()

    # signal which gets emitted whenever the model has been updated with fresh shotgun data.
    data_refreshed = QtCore.Signal(bool)

    # signal which gets emitted in the case the refresh fails
    data_refresh_fail = QtCore.Signal(str)

    # Custom model role that holds the shotgun data payload.
    SG_DATA_ROLE = QtCore.Qt.UserRole + 1

    # internal constants - please do not access directly but instead use the helper
    # methods provided! We may change these constants without prior notice.
    IS_SG_MODEL_ROLE = QtCore.Qt.UserRole + 2

    # magic number for IO streams
    FILE_MAGIC_NUMBER = 0xDEADBEEF

    # version of binary format
    FILE_VERSION = 22

    def __init__(self,
        parent,
        schema_generation=0,
        bg_task_manager=None
    ):

        super(ShotgunHierarchyModel, self).__init__(parent)

        self._bundle = sgtk.platform.current_bundle()

        # importing locally to not trip sphinx's imports.
        self._shotgun_globals = self._bundle.import_module("shotgun_globals")

        self.__schema_generation = schema_generation
        self.__full_cache_path = None

        # is the model set up with a query?
        self.__has_query = False

        # flag to indicate a full refresh
        self._request_full_refresh = False

        # keep various references to all items that the model holds.
        # some of these data structures are to keep the GC
        # happy, others to hold alternative access methods to the data.
        self.__all_tree_items = []
        self.__nav_tree_data = {}

        # set up data retriever and start work:
        shotgun_data = self._bundle.import_module("shotgun_data")
        self.__sg_data_retriever = shotgun_data.ShotgunDataRetriever(
            parent=self, bg_task_manager=bg_task_manager)
        self.__sg_data_retriever.work_completed.connect(
            self._on_data_retriever_work_completed)
        self.__sg_data_retriever.work_failure.connect(
            self._on_data_retriever_work_failure)
        self.__current_work_id = None
        self.__sg_data_retriever.start()

        # keep this around so it's not constantly being created
        self.__folder_icon = QtGui.QIcon(":tk-framework-shotgunutils/icon_Folder.png")
        self.__none_icon = QtGui.QIcon(":tk-framework-shotgunutils/icon_None.png")

    ########################################################################################
    # public methods

    def destroy(self):
        # XXX candidate for base class
        """
        Call this method prior to destroying this object.
        This will ensure all worker threads etc are stopped.
        """
        self.__current_work_id = None

        # gracefully stop the data retriever:
        self.__sg_data_retriever.stop()
        self.__sg_data_retriever = None

        # block all signals before we clear the model otherwise downstream
        # proxy objects could cause crashes.
        signals_blocked = self.blockSignals(True)
        try:
            # clear all internal memory storage
            self.clear()
        finally:
            # reset the stage of signal blocking:
            self.blockSignals(signals_blocked)

    def item_from_url(self, url):
        # XXX docs

        return self.__nav_tree_data.get(url, None)

    def hard_refresh(self):
        # XXX candidate for base class
        """
        Clears any caches on disk, then refreshes the data.
        """
        if not self.__has_query:
            # no query in this model yet
            return

        # when data arrives, force full rebuild
        self._request_full_refresh = True

        # delete cache file
        if self.__full_cache_path and os.path.exists(self.__full_cache_path):
            try:
                os.remove(self.__full_cache_path)
                logger.debug(
                    "Removed cache file '%s' from disk." %
                    self.__full_cache_path
                )
            except Exception, e:
                logger.warning(
                    "Hard refresh failed and could not remove cache file '%s' "
                    "from disk. Details: %s" % (self.__full_cache_path, e)
                )

        self._refresh_data()

    def _refresh_data(self):
        # XXX docs

        # XXX this only refresh the top level item and its children
        # XXX maybe a refresh should query all expanded items?

        # refresh with the original root path and args
        self.__query_hierarchy(
            self.__path,
            self.__seed_entity_field,
            self.__entity_fields
        )

    def is_data_cached(self):
        # XXX candidate for base class
        """
        Determine if the model has any cached data

        :returns: True if cached data exists for the model, otherwise False
        """
        return self.__full_cache_path and os.path.exists(self.__full_cache_path)

    ########################################################################################
    # methods overridden from the base class.

    def clear(self):
        # XXX candidate for base class.
        # sg model has different item vars though.
        """
        Removes all items (including header items) from the model and
        sets the number of rows and columns to zero.
        """
        # Advertise that the model is about to completely cleared. This is super important because proxy
        # models usually cache data like indices and these are about to get updated potentially thousands
        # of times while the tree is being destroyed.
        self.beginResetModel()
        try:
            # note! We are reimplementing this explicitly because the default implementation
            # results in memory issues - similar to reset(), scenarios where objects are constructed
            # in python (e.g. qstandarditems) and then handed over to a model and then subsequently
            # cleared and deallocated by QT itself (on the C++ side) often results in dangling pointers
            # across the pyside/QT boundary, ultimately resulting in crashes or instability.

            # we are not looking for any data from the async processor
            self.__current_work_id = None

            # ask async data retriever to clear its queue of queries
            # note that there may still be requests actually running
            # - these are not cancelled
            if self.__sg_data_retriever:
                self.__sg_data_retriever.clear()

            # model data in alt format
            self.__nav_tree_data = {}

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

    def reset(self):
        # XXX candidate for base class
        """
        Reimplements QAbstractItemModel:reset() by 'sealing it' so that
        it cannot be executed by calling code easily. This is because the reset method
        often results in crashes and instability because of how PySide/QT manages memory.

        For more information, see the clear() method.
        """
        raise NotImplementedError(
            "The QAbstractItemModel::reset method has explicitly been disabled "
            "because memory is not correctly freed up across C++/Python when "
            "executed, sometimes resulting in runtime instability. For an "
            "semi-equivalent method, use clear(), however keep in mind that "
            "this method will not emit the standard before/after reset signals. "
            "It is possible that this method may be implemented in later "
            "versions of the framework. For more information, please email "
            "support@shotgunsoftware.com."
        )

    ########################################################################################
    # protected methods not meant to be subclassed but meant to be called by subclasses

    def _load_data(
        self,
        path,
        seed_entity_field,
        entity_fields=None,
        cache_seed=None
    ):
        # XXX docs

        # we are changing the query
        self.query_changed.emit()

        # clear out old data
        self.clear()

        self.__has_query = True
        self.__path = path
        self.__seed_entity_field = seed_entity_field
        self.__entity_fields = entity_fields or {}

        # get the cache path based on these new data query parameters
        self.__full_cache_path = self._get_data_cache_path(cache_seed)

        # print some debug info
        logger.debug("")
        logger.debug("Model Reset for: %s" % (self,))
        logger.debug("Path: %s" % (self.__path,))
        logger.debug("Seed entity field: %s" % (self.__seed_entity_field,))
        logger.debug("Entity fields: %s" % (self.__entity_fields,))
        logger.debug("Cache path: %s" % (self.__full_cache_path,))

        # only one column. give it a default value
        self.setHorizontalHeaderLabels(
            ["%s Hierarchy" % (self.__seed_entity_field,)]
        )

        return self._load_cached_data()

    def _load_cached_data(self):
        # XXX docs

        # XXX load failing... not parenting properly???
        return False

        # warn if the cache file does not exist
        if not os.path.exists(self.__full_cache_path):
            logger.debug(
                "Data cache file does not exist on disk.\n"
                "Looking here: %s" % (self.__full_cache_path)
            )
            return False

        logger.debug(
            "Now attempting cached data load from: %s ..." %
            (self.__full_cache_path,)
        )

        try:
            time_before = time.time()
            num_items = self.__load_from_disk()
            time_diff = (time.time() - time_before)
            logger.debug(
                "Loading finished! Loaded %s items in %4fs" %
                (num_items, time_diff)
            )
            self.cache_loaded.emit()
            return True
        except Exception, e:
            logger.debug(
                "Couldn't load cache data from disk.\n"
                " Will proceed with full SG load.\n"
                "Error reported: %s" % (e,)
            )
            return False

    def _get_data_cache_path(self, cache_seed=None):
        # XXX docs
        """

        :param cache_seed:
        :return:
        """

        # hashes to use to generate the cache path
        params_hash = hashlib.md5()
        entity_field_hash = hashlib.md5()

        # even though the navigation path provides a nice organizational
        # structure for caching, it can get long. to avoid MAX_PATH issues on
        # windows, just hash it
        params_hash.update(str(self.__path))

        # include the schema generation number for clients
        params_hash.update(str(self.__schema_generation))

        # If this value changes over time (like between Qt4 and Qt5), we need to
        # assume our previous user roles are invalid since Qt might have taken
        # it over. If role's value is 32, don't add it to the hash so we don't
        # invalidate PySide/PyQt4 caches.
        if QtCore.Qt.UserRole != 32:
            params_hash.update(str(QtCore.Qt.UserRole))

        # include the cache_seed for additional user control over external state
        params_hash.update(str(cache_seed))

        # iterate through the sorted entity fields to ensure consistent order
        for (entity_type, fields) in sorted(self.__entity_fields.iteritems()):
            for field in fields:
                entity_field_hash.update("%s.%s" % (entity_type, field))

        # convert the seed entity field into a path segment.
        # example: Version.entity => Version/entity
        seed_entity_field_path = os.path.join(*self.__seed_entity_field.split("."))

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

    def __query_hierarchy(self, path, seed_entity_field, entity_fields):

        if not self.__sg_data_retriever:
            raise sgtk.TankError("Data retriever is not available!")

        if self.__current_work_id is not None:
            self.__sg_data_retriever.stop_work(self.__current_work_id)
            self.__current_work_id = None

        self.data_refreshing.emit()

        self.__current_work_id = self.__sg_data_retriever.execute_nav_expand(
            path, seed_entity_field, entity_fields)

    ########################################################################################
    # methods to be implemented by subclasses

    def _populate_item(self, item, sg_data):
        # XXX candidate for base class
        """
        Whenever an item is downloaded from Shotgun, this method is called. It allows subclasses to intercept
        the construction of a :class:`~PySide.QtGui.QStandardItem` and add additional metadata or make other changes
        that may be useful. Nothing needs to be returned.

        This method is called before the item is added into the model tree. At the point when
        the item is added into the tree, various signals will fire, informing views and proxy
        models that a new item has been added. This methods allows a subclassing object to
        add custom data prior to this.

        .. note:: When an item is fetched from the cache, this method is *not* called, it will
            only be called when shotgun data initially arrives from a Shotgun API query.

        .. note:: This is typically subclassed if you retrieve additional fields alongside the standard "name" field
            and you want to put those into various custom data roles. These custom fields on the item
            can later on be picked up by custom (delegate) rendering code in the view.

        :param item: :class:`~PySide.QtGui.QStandardItem` that is about to be added to the model. This has been primed
                     with the standard settings that the ShotgunModel handles.
        :param sg_data: Shotgun data dictionary that was received from Shotgun given the fields
                        and other settings specified in _load_data()
        """
        # default implementation does nothing

    def _finalize_item(self, item):
        # XXX candidate for base class
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

    def _set_tooltip(self, item, data):
        # XXX candidate for base class
        pass

    def _before_nav_data_processing(self, nav_data):
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

        :param nav_data: a shotgun dictionary, as retunrned by the nav_expand() call.
        :returns: should return a shotgun dictionary, of the same form as the input.
        """
        # default implementation is a passthrough
        return nav_data

    def _load_external_data(self):
        # XXX candidate for base class
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

    ########################################################################################
    # private methods

    def __do_depth_first_tree_deletion(self, node):
        # XXX base class candidate
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

    def _on_data_retriever_work_failure(self, uid, msg):
        # XXX base class candidate
        """
        Asynchronous callback - the data retriever failed to do some work

        :param uid: The unique id of the work that failed
        :param msg: The error message returned for the failure
        """
        uid = sanitize_qt(uid) # qstring on pyqt, str on pyside
        msg = sanitize_qt(msg)

        if self.__current_work_id != uid:
            # not our job. ignore
            logger.debug("Retrieved error from data worker: %s" % (msg,))
            return

        self.__current_work_id = None

        full_msg = "Error retrieving data from Shotgun: %s" % (msg,)
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
        uid = sanitize_qt(uid) # qstring on pyqt, str on pyside
        data = sanitize_qt(data)

        logger.debug("Received worker payload of type: %s" % (request_type,))

        if self.__current_work_id == uid:
            # our data has arrived from sg!
            # process the data
            self.__current_work_id = None
            nav_data = data["nav"]
            self.__on_nav_data_arrived(nav_data)

    def __on_nav_data_arrived(self, nav_data):
        # XXX docs
        """
        Handle asynchronous navigation data arriving after a nav_expand request.
        """

        logger.debug("--> Shotgun data arrived. (%s records)" % len(nav_data))

        # pre-process data
        sg_data = self._before_nav_data_processing(nav_data)

        if self._request_full_refresh:
            # full refresh requested

            # reset flag for next request
            self._request_full_refresh = False

            logger.debug("Rebuilding tree...")
            self.clear()
            self._load_external_data()
            self.__insert_subtree(nav_data)
            logger.debug("...done!")

            modifications_made = True

        else:

            # ensure we have a url for the item
            item_url = nav_data.get("url", None)
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
                modifications_made = self.__update_subtree(item, nav_data)
                logger.debug("...done!")

            else:
                logger.debug("Detected new item. Adding in-situ to tree...")
                self.__insert_subtree(nav_data)
                logger.debug("...done!")
                modifications_made = True

        # last step - save our tree to disk for fast caching next time!
        # XXX consider: the hierarchy data is queried lazily. so this implies
        # XXX a write to disk each time the user expands and item. consider the
        # XXX performance of this setup and whether this logic should be altered.
        # XXX perhaps save on delete?
        if modifications_made:
            logger.debug("Saving tree to disk %s..." % self.__full_cache_path)
            try:
                self.__save_to_disk(self.__full_cache_path)
                logger.debug("...saving complete!")
            except Exception, e:
                logger.warning("Couldn't save cache data to disk: %s" % e)

        # and emit completion signal
        self.data_refreshed.emit(modifications_made)

    def __update_subtree(self, item, nav_data):
        # XXX docs

        # ensure the item's data is up-to-date
        subtree_updated = self.__update_item(item, nav_data)

        children_data = nav_data.get("children")

        if not children_data:
            return subtree_updated

        child_urls = []

        for child_data in children_data:

            if not "url" in child_data:
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
            if not child_url in child_urls:
                # removing item
                del self.__nav_tree_data[child_url]
                self.removeRow(row)
                subtree_updated = True

        # add/update the children for the supplied item
        for child_data in children_data:
            child_url = child_data["url"]
            child_item = self.item_from_url(child_url)

            if child_item:
                # child already exists, ensure data is up-to-date
                subtree_updated = self.__update_item(child_item, child_data) \
                    or subtree_updated
            else:
                # child item does not exist, create it
                self.__create_item(child_data, parent=item)
                subtree_updated = True

        return subtree_updated

    def __insert_subtree(self, nav_data):
        # XXX docs

        item = self.__create_item(nav_data)
        self.__update_subtree(item, nav_data)

    def __create_item(self, data, parent=None):
        # XXX docs

        # XXX need to hide the root item
        # if this is the root item, just return the invisible root item that
        # comes with the model
        if data.get("ref", {}).get("kind") == "root":
            return self.invisibleRootItem()

        item = ShotgunHierarchyItem(data["label"])
        item.setEditable(False)

        self.__set_icon(item, data)

        # keep tabs of which items we are creating
        item.setData(True, self.IS_SG_MODEL_ROLE)

        # keep a reference to this object to make GC happy
        # (pyside may crash otherwise)
        self.__all_tree_items.append(item)

        # attach the nav data for access later
        self.__update_item(item, data)

        # keep a lookup of items by their url
        self.__nav_tree_data[data["url"]] = item

        # identify a parent if none supplied. could be found via the
        # `parent_url` supplied in the data or the root if no parent item
        # exists.
        parent = parent or self.item_from_url(data.get("parent_url")) or \
            self.invisibleRootItem()

        parent.appendRow(item)

        return item

    def __set_icon(self, item, data):

        item_ref = data.get("ref", {})
        item_kind = item_ref.get("kind")

        icon = None

        # XXX this will change soon. these will need to be separated
        if item_kind in ["entity_type", "entity"]:
            entity_type = item_ref.get("value", {}).get("type")
            icon = get_entity_type_icon(entity_type)
        elif item_kind == "list":
            icon = self.__folder_icon
        else:
            icon = self.__none_icon

        if icon:
            item.setIcon(icon)

        # XXX if "empty" show special icon?

    def __update_item(self, item, data):
        # XXX docs

        # get a copy of the data and remove the child item info so that
        # each item in the tree only stores data about itself
        item_data = copy.deepcopy(data)
        #if "children" in data.keys():
        #    del item_data["children"]

        # clean and set the item data
        item_data = self.__sg_clean_data(item_data)
        item.setData(sanitize_for_qt_model(item_data), self.SG_DATA_ROLE)

        return True

    def __sg_clean_data(self, sg_data):
        # XXX docs
        # logic from sg model though not recursive, method on base class?

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
                sg_data[k] = self.__sg_clean_data(sg_data[k])
        elif isinstance(sg_data, list):
            for i in range(len(sg_data)):
                sg_data[i] = self.__sg_clean_data(sg_data[i])
        elif isinstance(sg_data, datetime.datetime):
            # convert to unix timestamp, local time zone
            sg_data = time.mktime(sg_data.timetuple())

        return sg_data

    def __sg_compare_data(self, a, b):
        # XXX candidate for base class
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
                if not self.__sg_compare_data(a.get(a_key), b.get(a_key)):
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

    def hasChildren(self, index):

        if not index.isValid():
            return super(ShotgunHierarchyModel, self).hasChildren(index)

        item = self.itemFromIndex(index)
        item_data = get_sg_data(item)

        if not item_data:
            return super(ShotgunHierarchyModel, self).hasChildren(index)

        return item_data.get("has_children", False)

    def fetchMore(self, index):
        # XXX docs

        if not index.isValid():
            return

        item = self.itemFromIndex(index)
        item_data = get_sg_data(item)

        if not item_data:
            return

        # XXX considering using "url" everywhere
        path = item_data["url"]

        # query the information for this item to populate its children.
        # the slot for handling worker success will handle inserting the
        # queried data into the tree.
        # XXX do we keep forwarding the seed entity and fields this way?
        self.__query_hierarchy(
            path, self.__seed_entity_field, self.__entity_fields)

    def canFetchMore(self, index):
        # XXX docs

        if not index.isValid():
            return False

        # get the item and it's stored hierarchy data
        item = self.itemFromIndex(index)
        item_data = get_sg_data(item)

        if not item_data:
            return False

        # the number of existing child items
        child_item_count = item.rowCount()

        # we can fetch more if there are no children already and the item
        # has children.
        return child_item_count == 0 and item_data.get("has_children", False)

    ############################################################################
    # de/serialization of model contents

    def __save_to_disk(self, filename):
        # XXX candidate for base class
        """
        Save the model to disk using QDataStream serialization.
        This all happens on the C++ side and is very fast.
        """
        old_umask = os.umask(0)
        try:
            # try to create the cache folder with as open permissions as possible
            cache_dir = os.path.dirname(filename)
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, 0777)

            # write cache file
            fh = QtCore.QFile(filename)
            fh.open(QtCore.QIODevice.WriteOnly)
            try:
                out_stream = QtCore.QDataStream(fh)

                # write a header
                out_stream.writeInt64(self.FILE_MAGIC_NUMBER)
                out_stream.writeInt32(self.FILE_VERSION)

                # todo: if it turns out that there are ongoing issues with
                # md5 cache collisions, we could write the actual query parameters
                # to the header of the cache file here and compare that against the
                # desired query info just to be confident we are getting a correct cache...

                # tell which serialization dialect to use
                out_stream.setVersion(QtCore.QDataStream.Qt_4_0)

                root = self.invisibleRootItem()
                self.__save_to_disk_r(out_stream, root, 0)

            finally:
                fh.close()

            # and ensure the cache file has got open permissions
            os.chmod(filename, 0666)

        except Exception, e:
            logger.warning(
                "Could not write cache file '%s' to disk: %s" % (filename, e))

        finally:
            os.umask(old_umask)

    def __save_to_disk_r(self, stream, item, depth):
        # XXX candidate for base class
        """
        Recursive tree writer
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

    def __load_from_disk(self):
        # XXX candidate for base class
        """
        Load a serialized model from disk.

        :returns: Number of items loaded
        """
        num_items_loaded = 0

        # open the data cache for reading
        fh = QtCore.QFile(self.__full_cache_path)
        fh.open(QtCore.QIODevice.ReadOnly)

        try:
            in_stream = QtCore.QDataStream(fh)

            magic = in_stream.readInt64()
            if magic != self.FILE_MAGIC_NUMBER:
                raise Exception("Invalid file magic number!")

            version = in_stream.readInt32()
            if version != self.FILE_VERSION:
                raise CacheReadVersionMismatch(
                    "Cache file version %s, expected version %s" %
                    (version, self.FILE_VERSION)
                )

            # tell which deserialization dialect to use
            in_stream.setVersion(QtCore.QDataStream.Qt_4_0)

            curr_parent = self.invisibleRootItem()
            prev_node = None
            curr_depth = 0

            while not in_stream.atEnd():

                # this is the item where the deserialized data will live
                item = ShotgunHierarchyItem()
                num_items_loaded += 1

                # keep a reference to this object to make GC happy (pyside may
                # crash otherwise)
                self.__all_tree_items.append(item)
                item.read(in_stream)
                node_depth = in_stream.readInt32()

                # all nodes have a url stored in their metadata
                # the role data accessible via item.data() contains the url for
                # this item. if there is a url id associated with this node
                sg_data = get_sg_data(item)
                if sg_data:
                    # add the model item to our tree data dict keyed by id
                    self.__nav_tree_data[sg_data["url"]] = item

                # serialized items contain some sort of strange low-rez thumb
                # data which we cannot use. Make sure that is all cleared.
                item.setIcon(QtGui.QIcon())

                # serialized items do not contain a full high rez thumb, so
                # re-create that. First, set the default thumbnail
                # XXX consider if needed for hierarchy items
                #self._populate_default_thumbnail(item)

                # run the finalize method so that subclasses can do any setup
                # they need
                # XXX consider if needed for hierarchy items
                #self._finalize_item(item)

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
                        curr_depth = curr_depth - 1
                        curr_parent = curr_parent.parent()
                        if curr_parent is None:
                            # we reached the root. special case
                            curr_parent = self.invisibleRootItem()

                # request thumb
                # XXX consider if needed for hierarchy items
                #if self.__download_thumbs:
                #    self.__process_thumbnail_for_item(item)

                prev_node = item
        finally:
            fh.close()

        return num_items_loaded

