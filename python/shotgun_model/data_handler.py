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
import datetime
import time

# toolkit imports
import sgtk

from .errors import ShotgunModelDataError
from .data_handler_cache import ShotgunDataHandlerCache


class ShotgunDataHandler(object):
    """
    Abstract class that manages low level data storage for Qt models.

    This class abstracts away the data management and allows
    the model to access the data in a simple tree-like fashion.
    Each node in the tree is also identified by a unique id
    and can be accessed directly via this id in an O(1) lookup.

    It also offers fast serialization and loading. Each
    ShotgunDataHandler is connected to a single cache file on disk.

    Each Qt model typically has a corresponding ShotgunDataHandler
    subclass where data related business logic is implemented.
    The following methods need to be implemented by all
    deriving classes:

    - generate_data_request - called by the model when it needs
      additional data to be loaded from shotgun. The data handler
      formulates the exact request to be sent out to the server.

    - update_data - the counterpart of generate_data_request: this
      is called when the requested shotgun data is returned and
      needs to be inserted into the data structure.

    Data returned back from this class to the Model layer
    is always sent as ShotgunItemData object to provide a full
    encapsulation around the internals of this class.
    """

    # version of binary format - increment this whenever changes
    # are made which renders the cache files non-backwards compatible.
    FORMAT_VERSION = 27

    # constants for updates
    (UPDATED, ADDED, DELETED) = range(3)

    def __init__(self, cache_path):
        """
        :param cache_path: Path to cache file location
        """
        super(ShotgunDataHandler, self).__init__()
        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()
        # the path to the cache file
        self._cache_path = cache_path
        # data in cache
        self._cache = None

    def __repr__(self):
        """
        String representation of this instance
        """
        if self._cache is None:
            return "<%s@%s (unloaded)>" % (self.__class__.__name__, self._cache_path)
        else:
            return "<%s@%s (%d items)>" % (
                self.__class__.__name__,
                self._cache_path,
                self._cache.size,
            )

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

    @sgtk.LogManager.log_timing
    def remove_cache(self):
        """
        Removes the associated cache file from disk
        and unloads cache data from memory.

        :returns: True if the cache was sucessfully unloaded.
        """
        if os.path.exists(self._cache_path):
            try:
                os.remove(self._cache_path)
            except Exception as e:
                self._log_warning(
                    "Could not remove cache file '%s' "
                    "from disk. Details: %s" % (self._cache_path, e)
                )
                return False
        else:
            self._log_debug("...no cache file found on disk. Nothing to remove.")

        # unload from memory
        self.unload_cache()

        return True

    @sgtk.LogManager.log_timing
    def load_cache(self):
        """
        Loads a cache from disk into memory
        """
        # init empty cache
        self._cache = ShotgunDataHandlerCache()

        # try to load
        self._log_debug("Loading from disk: %s" % self._cache_path)
        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, "rb") as fh:
                    file_version = sgtk.util.pickle.load(fh)
                    if file_version != self.FORMAT_VERSION:
                        raise ShotgunModelDataError(
                            "Cache file has version %s - version %s is required"
                            % (file_version, self.FORMAT_VERSION)
                        )
                    raw_cache_data = sgtk.util.pickle.load(fh)
                    self._cache = ShotgunDataHandlerCache(raw_cache_data)
            except Exception as e:
                self._log_debug(
                    "Cache '%s' not valid - ignoring. Details: %s"
                    % (self._cache_path, e)
                )

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

    @sgtk.LogManager.log_timing
    def save_cache(self):
        """
        Saves the current cache to disk.
        """
        self._log_debug("Saving to disk: %s" % self)

        # try to create the cache folder with as open permissions as possible
        cache_dir = os.path.dirname(self._cache_path)

        # make sure the cache directory exists
        # todo: upgrade to 0.18 filesystem methods
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir, 0o777)
            except OSError as e:
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
                # speeds up pickling but only works when there
                # are no cycles in the data set
                # pickler.fast = 1

                # TODO: we are currently storing a parent node in our data structure
                # for performance and cache size. By removing this, we could turn
                # on the fast mode and this would speed things up further.

                sgtk.util.pickle.dump(self.FORMAT_VERSION, fh)
                if self._cache is None:
                    # dump an empty cache
                    empty_cache = ShotgunDataHandlerCache()
                    sgtk.util.pickle.dump(empty_cache.raw_data, fh)

                else:
                    sgtk.util.pickle.dump(self._cache.raw_data, fh)

            # and ensure the cache file has got open permissions
            os.chmod(self._cache_path, 0o666)

        finally:
            # set mask back to previous value
            os.umask(old_umask)

        self._log_debug(
            "Completed save of %s. Size %s bytes"
            % (self, os.path.getsize(self._cache_path))
        )

    def get_data_item_from_uid(self, unique_id):
        """
        Given a unique id, return a :class:`ShotgunItemData`
        Returns None if the given uid is not present in the cache.

        Unique ids are constructed by :class:`ShotgunDataHandler`
        and are usually retrieved from a :class:`ShotgunItemData`.
        They are implementation specific and can be any type object,
        but are normally strings, ints or None for the root node.

        :param unique_id: unique identifier
        :returns: :class:`ShotgunItemData`
        """
        if not self.is_cache_loaded():
            return None

        return self._cache.get_entry_by_uid(unique_id)

    @sgtk.LogManager.log_timing
    def generate_child_nodes(self, unique_id, parent_object, factory_fn):
        """
        Generate nodes recursively from the data set

        each node will be passed to the factory method for construction.

        unique id can be none, meaning generate the top level of the tree

        :param unique_id:     Unique identifier, typically an int or a string
        :param parent_object: Parent object that the requester wants to parent
                              newly created nodes to. This object is passed into
                              the node creation factory method as nodes are being
                              created.
        :param factory_fn:    Method to execute whenever a child node needs to
                              be created. The factory_fn will be called with the
                              following syntax: factory_fn(parent_object, data_item),
                              where parent_object is the parent_object parameter and
                              data_item is a :class:`ShotgunItemData` representing the
                              data that the node should be associated with.

        :returns: number of items generated.
        """
        num_nodes_generated = 0

        self._log_debug("Creating child nodes for parent uid %s" % unique_id)

        for data_item in self._cache.get_children(unique_id):
            factory_fn(parent_object, data_item)
            num_nodes_generated += 1

        return num_nodes_generated

    def generate_data_request(self, data_retriever, *args, **kwargs):
        """
        Generate a data request for a data retriever.
        Subclassed implementations can add arbitrary
        arguments in order to control the parameters and loading state.

        Once the data has arrived, the caller is expected to
        call meth:`update_data` and pass in the received
        data payload for processing.

        :param data_retriever: :class:`~tk-framework-shotgunutils:shotgun_data.ShotgunDataRetriever` instance.
        :returns: Request id or None if no work is needed
        """
        raise NotImplementedError(
            "The 'generate_data_request' method has not been "
            "implemented for this ShotgunDataHandler subclass."
        )

    def update_data(self, sg_data):
        """
        The counterpart to :meth:`generate_data_request`. When the data
        request has been carried out, this method should be called by the calling
        class and the data payload from Shotgun should be provided via the
        sg_data parameter. Deriving classes implement the business logic for
        how to insert the data correctly into the internal data structure.

        A list of differences should be returned, indicating which nodes were
        added, deleted and modified, on the following form::

            [
             {
                "data": ShotgunItemData instance,
                "mode": self.UPDATED|ADDED|DELETED
             },
             {
                "data": ShotgunItemData instance,
                "mode": self.UPDATED|ADDED|DELETED
             },
             ...
            ]

        :param sg_data: data payload, usually a dictionary
        :returns: list of updates. see above
        """
        raise NotImplementedError(
            "The 'update_data' method has not been "
            "implemented for this ShotgunDataHandler subclass."
        )

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

        :param sg_data: Shotgun data dictionary
        :return: Cleaned up Shotgun data dictionary
        """
        # Older versions of Shotgun return special timezone classes. Qt is
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
            for k in sg_data:
                sg_data[k] = self._sg_clean_data(sg_data[k])
        elif isinstance(sg_data, list):
            for i in range(len(sg_data)):
                sg_data[i] = self._sg_clean_data(sg_data[i])
        elif isinstance(sg_data, datetime.datetime):
            # convert to unix timestamp, local time zone
            sg_data = time.mktime(sg_data.timetuple())

        return sg_data
