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
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

# framework imports
from .shotgun_hierarchy_item import ShotgunHierarchyItem
from .shotgun_model import CacheReadVersionMismatch
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

    # XXX consider moving to base class if caching works identially to sg model
    # magic number for IO streams
    FILE_MAGIC_NUMBER = 0xDEADBEEF

    # version of binary format
    FILE_VERSION = 22

    def __init__(self, parent, schema_generation=0, bg_task_manager=None):
        """
        Initialize the Hierarcy model.

        :param parent: The model's parent.
        :type parent: :class:`~PySide.QtGui.QObject`

        """

        super(ShotgunHierarchyModel, self).__init__(parent)

        self._schema_generation = schema_generation
        self._full_cache_path = None

        # flag to indicate a full refresh
        self._request_full_refresh = False

        # is the model set up with a query?
        self._has_query = False

        # keep various references to all items that the model holds.
        # some of these data structures are to keep the GC
        # happy, others to hold alternative access methods to the data.
        self._all_tree_items = []
        self._nav_tree_data = {}

        # keeps track of the currently running data retriever
        self._current_work_id = None

        # keep these icons around so they're not constantly being created
        self._folder_icon = QtGui.QIcon(
            ":tk-framework-shotgunutils/icon_Folder.png")
        self._none_icon = QtGui.QIcon(
            ":tk-framework-shotgunutils/icon_None.png")

    ########################################################################################
    # public methods

    def destroy(self):
        """
        Call this method prior to destroying this object.
        This will ensure all worker threads etc are stopped.
        """
        self._current_work_id = None

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

        # delete cache file
        if self._full_cache_path and os.path.exists(self._full_cache_path):
            try:
                os.remove(self._full_cache_path)
                logger.debug(
                    "Removed cache file '%s' from disk." %
                    self._full_cache_path
                )
            except Exception, e:
                logger.warning(
                    "Hard refresh failed and could not remove cache file '%s' "
                    "from disk. Details: %s" % (self._full_cache_path, e)
                )

        self._refresh_data()

    def item_from_url(self, url):
        # XXX docs

        return self._nav_tree_data.get(url, None)

    def is_data_cached(self):
        """
        Determine if the model has any cached data

        :returns: True if cached data exists for the model, otherwise False
        """
        return self._full_cache_path and os.path.exists(self._full_cache_path)

    ########################################################################################
    # methods overridden from the base class.

    def clear(self):
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
            self._current_work_id = None

            # ask async data retriever to clear its queue of queries
            # note that there may still be requests actually running
            # - these are not cancelled
            if self._sg_data_retriever:
                self._sg_data_retriever.clear()

            # model data in alt format
            self._nav_tree_data = {}

            # pyside will crash unless we actively hold a reference
            # to all items that we create.
            self._all_tree_items = []

            # lastly, remove all data in the underlying internal data storage
            # note that we don't cannot clear() here since that causing
            # crashing in various environments. Also note that we need to do
            # in a depth-first manner to ensure that there are no
            # cyclic parent/child dependency cycles, which will cause
            # a crash in some versions of shiboken
            # (see https://bugreports.qt-project.org/browse/PYSIDE-158 )
            self._do_depth_first_tree_deletion(self.invisibleRootItem())
        finally:
            # Advertise that we're done resetting.
            self.endResetModel()


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

        self._has_query = True

        self._path = path
        self._seed_entity_field = seed_entity_field
        self._entity_fields = entity_fields or {}

        # get the cache path based on these new data query parameters
        self._full_cache_path = self._get_data_cache_path(cache_seed)

        # print some debug info
        logger.debug("")
        logger.debug("Model Reset for: %s" % (self,))
        logger.debug("Path: %s" % (self._path,))
        logger.debug("Seed entity field: %s" % (self._seed_entity_field,))
        logger.debug("Entity fields: %s" % (self._entity_fields,))
        logger.debug("Cache path: %s" % (self._full_cache_path,))

        # only one column. give it a default value
        self.setHorizontalHeaderLabels(
            ["%s Hierarchy" % (self._seed_entity_field,)]
        )

        return self._load_cached_data()

    def _load_cached_data(self):
        # XXX docs

        # XXX load failing... not parenting properly???
        return False

        # warn if the cache file does not exist
        if not os.path.exists(self._full_cache_path):
            logger.debug(
                "Data cache file does not exist on disk.\n"
                "Looking here: %s" % (self._full_cache_path)
            )
            return False

        logger.debug(
            "Now attempting cached data load from: %s ..." %
            (self._full_cache_path,)
        )

        try:
            time_before = time.time()
            num_items = self._load_from_disk()
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
        seed_entity_field_path = os.path.join(*self._seed_entity_field.split("."))

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

    def _query_hierarchy(self, path, seed_entity_field, entity_fields):

        if not self._sg_data_retriever:
            raise sgtk.TankError("Data retriever is not available!")

        if self._current_work_id is not None:
            self._sg_data_retriever.stop_work(self._current_work_id)
            self._current_work_id = None

        self.data_refreshing.emit()

        self._current_work_id = self._sg_data_retriever.execute_nav_expand(
            path, seed_entity_field, entity_fields)

    ########################################################################################
    # methods to be implemented by subclasses

    def _refresh_data(self):
        # XXX docs

        # XXX this only refresh the top level item and its children
        # XXX maybe a refresh should query all expanded items?

        # refresh with the original root path and args
        self._query_hierarchy(
            self._path,
            self._seed_entity_field,
            self._entity_fields
        )


    ########################################################################################
    # private methods

    def _on_data_retriever_work_failure(self, uid, msg):
        """
        Asynchronous callback - the data retriever failed to do some work

        :param uid: The unique id of the work that failed
        :param msg: The error message returned for the failure
        """
        uid = sanitize_qt(uid) # qstring on pyqt, str on pyside
        msg = sanitize_qt(msg)

        if self._current_work_id != uid:
            # not our job. ignore
            logger.debug("Retrieved error from data worker: %s" % (msg,))
            return

        self._current_work_id = None

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

        if self._current_work_id == uid:
            # our data has arrived from sg!
            # process the data
            self._current_work_id = None
            nav_data = data["nav"]
            self._on_nav_data_arrived(nav_data)

    def _on_nav_data_arrived(self, nav_data):
        # XXX docs
        """
        Handle asynchronous navigation data arriving after a nav_expand request.
        """

        logger.debug("--> Shotgun data arrived. (%s records)" % len(nav_data))

        # pre-process data
        sg_data = self._before_data_processing(nav_data)

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
        # XXX consider: the hierarchy data is queried lazily. so this implies
        # XXX a write to disk each time the user expands and item. consider the
        # XXX performance of this setup and whether this logic should be altered.
        # XXX perhaps save on delete?
        if modifications_made:
            logger.debug("Saving tree to disk %s..." % self._full_cache_path)
            try:
                self._save_to_disk(self._full_cache_path)
                logger.debug("...saving complete!")
            except Exception, e:
                logger.warning("Couldn't save cache data to disk: %s" % e)

        # and emit completion signal
        self.data_refreshed.emit(modifications_made)

    def _update_subtree(self, item, nav_data):
        # XXX docs

        # ensure the item's data is up-to-date
        subtree_updated = self._update_item(item, nav_data)

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
                del self._nav_tree_data[child_url]
                self.removeRow(row)
                subtree_updated = True

        # add/update the children for the supplied item
        for child_data in children_data:
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

    def _insert_subtree(self, nav_data):
        # XXX docs

        item = self._create_item(nav_data)
        self._update_subtree(item, nav_data)

    def _polish_item(self, item):
        # XXX docs
        # XXX finalize item!

        data = get_sg_data(item)

        if data.get("ref", {}).get("kind") == "empty":
            item.setForeground(self._get_empty_item_color(item))

    def _get_empty_item_color(self, item):

        # Change the foreground color of "empty" items.
        # These special items are used as placeholders in the tree where the
        # parent has no children. An example would be `Shots > No Shots` where
        # `No Shots` is the "empty" item. By default, the returned color is a mix
        # of the application instance's base and text colors. This will typically
        # result in a dimmed appearance for these special items indicating that
        # they are not clickable.
        base_color = QtGui.QApplication.instance().palette().base().color()
        text_color = QtGui.QApplication.instance().palette().text().color()

        return color_mix(
            text_color, 1,
            base_color, 2
        )

    def _create_item(self, data, parent=None):
        # XXX docs

        # XXX need to hide the root item
        # if this is the root item, just return the invisible root item that
        # comes with the model
        if data.get("ref", {}).get("kind") == "root":
            return self.invisibleRootItem()

        item = ShotgunHierarchyItem(data["label"])
        item.setEditable(False)

        self._set_icon(item, data)

        # keep tabs of which items we are creating
        item.setData(True, self.IS_SG_MODEL_ROLE)

        # keep a reference to this object to make GC happy
        # (pyside may crash otherwise)
        self._all_tree_items.append(item)

        # attach the nav data for access later
        self._update_item(item, data)

        # keep a lookup of items by their url
        self._nav_tree_data[data["url"]] = item

        # identify a parent if none supplied. could be found via the
        # `parent_url` supplied in the data or the root if no parent item
        # exists.
        parent = parent or self.item_from_url(data.get("parent_url")) or \
            self.invisibleRootItem()

        parent.appendRow(item)

        self._polish_item(item)

        return item

    def _set_icon(self, item, data):

        item_ref = data.get("ref", {})
        item_kind = item_ref.get("kind")

        icon = None

        # XXX this will change soon. these will need to be separated
        if item_kind in ["entity_type", "entity"]:
            entity_type = item_ref.get("value", {}).get("type")
            icon = self._shotgun_globals.get_entity_type_icon(entity_type)
        elif item_kind == "list":
            icon = self._folder_icon
        else:
            icon = self._none_icon

        if icon:
            item.setIcon(icon)

        # XXX if "empty" show special icon?

    def _update_item(self, item, data):
        # XXX docs

        # get a copy of the data and remove the child item info so that
        # each item in the tree only stores data about itself
        item_data = copy.deepcopy(data)
        if "children" in data.keys():
            del item_data["children"]

        # clean and set the item data
        item_data = self._sg_clean_data(item_data)
        item.setData(sanitize_for_qt_model(item_data), self.SG_DATA_ROLE)

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
        self._query_hierarchy(
            path, self._seed_entity_field, self._entity_fields)

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

    def _save_to_disk(self, filename):
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
                self._save_to_disk_r(out_stream, root, 0)

            finally:
                fh.close()

            # and ensure the cache file has got open permissions
            os.chmod(filename, 0666)

        except Exception, e:
            logger.warning(
                "Could not write cache file '%s' to disk: %s" % (filename, e))

        finally:
            os.umask(old_umask)

    def _save_to_disk_r(self, stream, item, depth):
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
                self._save_to_disk_r(stream, child, depth+1)

    def _load_from_disk(self):
        # XXX candidate for base class
        """
        Load a serialized model from disk.

        :returns: Number of items loaded
        """
        num_items_loaded = 0

        # open the data cache for reading
        fh = QtCore.QFile(self._full_cache_path)
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
                self._all_tree_items.append(item)
                item.read(in_stream)
                node_depth = in_stream.readInt32()

                # all nodes have a url stored in their metadata
                # the role data accessible via item.data() contains the url for
                # this item. if there is a url id associated with this node
                sg_data = get_sg_data(item)
                if sg_data:
                    # add the model item to our tree data dict keyed by id
                    self._nav_tree_data[sg_data["url"]] = item

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
                #if self._download_thumbs:
                #    self._process_thumbnail_for_item(item)

                prev_node = item
        finally:
            fh.close()

        return num_items_loaded

