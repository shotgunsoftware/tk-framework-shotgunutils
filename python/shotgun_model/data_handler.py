# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
from __future__ import with_statement

import errno
import os
import cPickle
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

from .errors import ShotgunModelDataError

def log_timing(func):
    """
    Decorator that times and logs the execution of a method.
    Borrowed from 0.18.
    """
    def wrapper(self, *args, **kwargs):
        time_before = time.time()
        try:
            response = func(self, *args, **kwargs)
        finally:
            time_spent = time.time() - time_before
            # log to special timing logger
            self._bundle.log_debug("ShotgunDataHandler.%s took %fs" % (func.__name__, time_spent))
        return response
    return wrapper


class ShotgunDataHandler(QtCore.QObject):
    """
    Shotgun Model low level data storage.
    """
    # version of binary format
    FORMAT_VERSION = 23

    (UPDATED, ADDED, DELETED) = range(3)

    # for serialization performance
    (CACHE_BY_UID, CACHE_CHILDREN, IS_LEAF, UID, PARENT, FIELD, SG_DATA) = range(7)

    def __init__(self, cache_path, parent):
        """
        :param cache_path: Path to cache file location
        :param parent: Parent QT object
        """
        super(ShotgunDataHandler, self).__init__(parent)
        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()
        # the path to the cache file
        self._cache_path = cache_path
        # data in cache
        self._cache = None

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns: A string representation of this instance
        """
        return "<%s@%s (%d items)>" % (
            self.__class__.__name__,
            self._cache_path,
            len(self._cache[self.CACHE_BY_UID])
        )

    def _init_clear_cache(self):
        """
        Helper method - initializes a clear cache.
        :returns: new cache dictionary
        """
        return {
            self.CACHE_CHILDREN: {},
            self.CACHE_BY_UID: {},
            self.UID: None
        }

    def _clear_cache(self):
        """
        Sets up an empty cache in memory
        """
        self._cache = self._init_clear_cache()

    def is_cache_available(self):
        """
        Returns true if the cache exists on disk, false if not.

        :returns: boolean to indicate if cache exists on disk
        """
        return os.path.exists(self._cache_path)

    def is_cache_loaded(self):
        """
        Returns true if the cache has been loaded into memory, false if not.

        :returns: boolean to indicate if cache is loaded
        """
        return self._cache is not None

    @log_timing
    def remove_cache(self):
        """
        Removes the associated cache file from disk
        and unloads cache data from memory.

        :returns: True if the cache was sucessfully unloaded.
        """
        if os.path.exists(self._cache_path):
            try:
                os.remove(self._cache_path)
            except Exception, e:
                self._log_warning(
                    "Could not remove cache file '%s' "
                    "from disk. Details: %s" % (self._cache_path, e)
                )
                return False
        else:
            self._log_debug("...no cache file found on disk. Nothing to remove.")

        # unload from memory
        self.unload_cache()

        # init again
        self.load_cache()

        return True

    @log_timing
    def load_cache(self):
        """
        Loads a cache from disk into memory
        """
        # init empty cache
        self._clear_cache()

        # try to load
        self._log_debug("Loading from disk: %s" % self._cache_path)
        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, "rb") as fh:
                    pickler = cPickle.Unpickler(fh)
                    file_version = pickler.load()
                    if file_version != self.FORMAT_VERSION:
                        raise ShotgunModelDataError(
                            "Cache file has version %s - version %s is required" % (file_version, self.FORMAT_VERSION)
                        )
                    self._cache = pickler.load()
            except Exception, e:
                self._log_debug("Cache '%s' not valid - ignoring. Details: %s" % (self._cache_path, e))

        else:
            self._log_debug("No cache found on disk. Starting from empty data store.")

        self._log_debug("Cache load complete: %s" % self)

    def unload_cache(self):
        """
        Unloads any in-memory cache data.
        """
        if self._cache is None:
            # nothing to do
            return

        self._log_debug("Unloading in-memory cache for %s" % self)
        self._cache = None

    @log_timing
    def save_cache(self):
        """
        Saves the current cache to disk.
        """
        self._log_debug("Saving to disk: %s" % self._cache_path)

        # try to create the cache folder with as open permissions as possible
        cache_dir = os.path.dirname(self._cache_path)

        # make sure the cache directory exists
        # todo: upgrade to 0.18 filesystem methods
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

        # now write the file
        old_umask = os.umask(0)
        try:
            with open(self._cache_path, "wb") as fh:
                pickler = cPickle.Pickler(fh, protocol=2)
                # speeds up pickling but only works when there
                # are no cycles in the data set
                #pickler.fast = 1

                # TODO: we are currently storing a parent node in our data structure
                # for performance and cache size. By removing this, we could turn
                # on the fast mode and this would speed things up further.

                pickler.dump(self.FORMAT_VERSION)
                pickler.dump(self._cache)

            # and ensure the cache file has got open permissions
            os.chmod(self._cache_path, 0666)

        finally:
            # set mask back to previous value
            os.umask(old_umask)

    def get_data_item_from_uid(self, unique_id):
        """
        Given a unique id, return a :class:`ShotgunDataItem`
        Returns None if the given uid is not present in the cache.

        :returns: :class:`ShotgunDataItem`
        """
        # avoid cyclic imports
        from .data_item import ShotgunDataItem

        if not self.is_cache_loaded():
            return None

        return ShotgunDataItem(self._cache[self.CACHE_BY_UID].get(unique_id))

    @log_timing
    def generate_child_nodes(self, unique_id, parent_object, factory_fn):
        """
        Generate nodes recursively from the data set

        each node will be passed to the factory method for construction.

        unique id can be none, meaning generate the top level of the tree

        :returns: number of items generated.
        """
        # avoid cyclic imports
        from .data_item import ShotgunDataItem

        num_nodes_generated = 0

        self._log_debug("Creating child nodes for parent uid %s" % unique_id)

        if unique_id is None:
            # this is the root
            cache_node = self._cache
        else:
            # resolve cache node from uid
            cache_node = self._cache[self.CACHE_BY_UID].get(unique_id)

        if cache_node:
            for item in cache_node[self.CACHE_CHILDREN].itervalues():
                data_item = ShotgunDataItem(item)
                factory_fn(parent_object, data_item)
                num_nodes_generated += 1
        else:
            self._log_debug("No cache item found for id %s" % unique_id)

        return num_nodes_generated

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

