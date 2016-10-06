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

import datetime
import errno
import os
import urlparse
import cPickle
import time

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

from .errors import ShotgunModelError, CacheReadVersionMismatch
from .shotgun_standard_item import ShotgunStandardItem
from .util import get_sg_data

class ShotgunModelDataError(ShotgunModelError):
    """
    Error used for all data storage related issues.
    """
    pass


class ShotgunDataItem(object):
    """
    Wrapper around a data entry
    """

    def __init__(self, data_dict):
        self._data = data_dict

    @property
    def field(self):
        return self._data["field"]

    @property
    def shotgun_data(self):
        return self._data["sg_data"]

    def is_leaf(self):
        """
        True if leaf node
        """
        return len(self._data["children"]) == 0



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
            self._bundle.log_debug("[%s.%s] %fs" % (func.__module__, func.__name__, time_spent))
        return response
    return wrapper


class ShotgunDataHandler(QtCore.QObject):
    """
    Wrapper around shotgun heirarcical data storage
    """
    # version of binary format
    FORMAT_VERSION = 3

    (UPDATED, ADDED, DELETED) = range(3)

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
        self._cache_data = None
        self._cache_modified = False

    def __repr__(self):
        return "<ShotgunDataHandler %s>" % self._cache_path

    def __del__(self):
        self._log_debug("Deallocating %s" % self)
        self.unload_cache()

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
        return self._cache_data is not None

    def is_modified(self):
        """
        Returns true if the in memory cache has been modified.
        Returns false if no cache is loaded.

        :returns: boolean to indicate if cache in memory has changed since it was loaded.
        """
        return self._cache_modified

    def get_entity_ids(self, entity_type):
        """
        Returns a list of entity ids contained in this data set given an entity type.

        :return: A list of unique ids for all items in the model.
        :rtype: ``list``
        """
        #todo - implement

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

        return True

    @log_timing
    def load_cache(self):
        """
        Loads a cache from disk into memory
        """
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
                    self._cache_data = pickler.load()
            except Exception, e:
                self._log_debug("Cache '%s' not valid - ignoring. Details: %s" % (self._cache_path, e))
                self._cache_data = {}
                self._cache_data["children"] = {}

        else:
            self._log_debug("No cache found on disk. Initializing empty data storage.")
            self._cache_data = {}
            self._cache_data["children"] = {}

        self._cache_modified = False

    def unload_cache(self):
        """
        Unloads any in-memory cache data.
        """
        self._cache_modified = False
        self._cache_data = None

    @log_timing
    def save_cache(self):
        """
        Saves the current cache to disk.
        """
        self._log_debug("Saving to disk: %s" % self._cache_path)

        # try to create the cache folder with as open permissions as possible
        cache_dir = os.path.dirname(self._cache_path)

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

        # now write the file
        old_umask = os.umask(0)
        try:
            with open(self._cache_path, "wb") as fh:
                pickler = cPickle.Pickler(fh, protocol=2)
                pickler.fast = 1
                pickler.dump(self.FORMAT_VERSION)
                pickler.dump(self._cache_data)

            # and ensure the cache file has got open permissions
            os.chmod(self._cache_path, 0666)

        finally:
            # set mask back to previous value
            os.umask(old_umask)

        self._cache_modified = False

    @log_timing
    def generate_child_nodes(self, path, parent_object, factory_fn):
        """
        Generate nodes recursively from the data set

        each node will be passed to the factory method for construction.


        :returns: number of items generated.
        """
        num_nodes_generated = 0
        for item in self._cache_data["children"].itervalues():
            data_item = ShotgunDataItem(item)
            factory_fn(parent_object, data_item)
            num_nodes_generated += 1

        print "CHILD NOTES: %s" % num_nodes_generated
        return num_nodes_generated


    @log_timing
    def update_find_data(self, sg_data, hierarchy):
        """
        Adds find data to the data set in memory.

        Runs a comparison between old and new data and returns a list of entity ids
        that have changed between what was previously in the database and what is there now.

        raises an exception if no cache is loaded.

        :returns: list of updated plugin ids. empty list if cache was up to date.
        """
        self._log_debug("Adding %s shotgun records to tree" % len(sg_data))

        if self._cache_data is None:
            raise ShotgunModelDataError("No data currently loaded in memory!")

        if len(self._cache_data) == 0:
            self._log_debug("In-memory cache is empty.")

        # ensure the data is clean
        self._log_debug("sanitizing data...")
        sg_data = self.__sg_clean_data(sg_data)
        self._log_debug("...done!")

        self._log_debug("Inserting into cache...")

        diff_list = []

        # go through each sg record item and insert it in
        # hierarchy order into the tree
        for sg_item in sg_data:

            sub_tree = self._cache_data

            # Create items by drilling down the hierarchy
            for field_name in hierarchy:

                on_leaf_level = (hierarchy[-1] == field_name)

                if not on_leaf_level:
                    # make a unique key for this item
                    unique_field_value = self.__generate_unique_key(field_name, sg_item)
                else:
                    # on the leaf level, use the entity id as the unique key
                    unique_field_value = sg_item["id"]

                # now check if we need to insert into our memory map

                # two distinct cases for leaves and non-leaves
                if on_leaf_level:
                    # this is an actual entity
                    if unique_field_value in sub_tree["children"]:
                        # this record already exists
                        # check if it has changed
                        current_record = sub_tree["children"][unique_field_value]["sg_data"]
                        if self.__compare_shotgun_data(current_record, sg_item):
                            # this has changed! Add to list
                            diff_list.append({"shotgun_id": sg_item["id"], "mode": self.UPDATED})

                            sub_tree["children"][unique_field_value]["sg_data"] = sg_item

                    else:
                        # record does not exist yet
                        diff_list.append({"shotgun_id": sg_item["id"], "mode": self.ADDED})

                        sub_tree["children"][unique_field_value] = {
                            "sg_data": sg_item,
                            "field": field_name,
                            "children": {},
                        }

                    # TODO: check for deletion

                else:
                    # not on leaf level yet
                    if unique_field_value not in sub_tree["children"]:
                        sub_tree["children"][unique_field_value] = {
                            "sg_data": sg_item,
                            "field": field_name,
                            "children": {}
                        }

                if not on_leaf_level:
                    # recurse down to the next level
                    sub_tree = sub_tree["children"][unique_field_value]

        return diff_list

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

    def __sg_clean_data(self, sg_data):
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
                sg_data[k] = self.__sg_clean_data(sg_data[k])
        elif isinstance(sg_data, list):
            for i in range(len(sg_data)):
                sg_data[i] = self.__sg_clean_data(sg_data[i])
        elif isinstance(sg_data, datetime.datetime):
            # convert to unix timestamp, local time zone
            sg_data = time.mktime(sg_data.timetuple())

        return sg_data

    def __generate_unique_key(self, field, sg_data):
        """
        Generates a unique key from a shotgun field.
        """
        value = sg_data.get(field)

        if isinstance(value, dict) and "id" in value and "type" in value:
            return (value["type"], value["id"])

        elif isinstance(value, list):
            # this is a list of some sort. Loop over all elements and extract a comma separated list.
            formatted_values = []
            if len(value) == 0:
                # no items in list
                formatted_values.append("_")
            for v in value:
                if isinstance(v, dict) and "id" in v and "type" in v:
                    # This is a link field
                    formatted_values.append(v["type"], v["id"])
                else:
                    formatted_values.append(str(v))

            return tuple(formatted_values)

        else:
            # everything else just cast to string
            return str(value)

    def __compare_shotgun_data(self, a, b):
        """
        Compares two dicts, assumes the same set of keys in both.
        Omits thumbnail fields because these change all the time (S3).
        Both inputs are assumed to contain utf-8 encoded data.
        """
        # handle thumbnail fields as a special case
        # thumbnail urls are (typically, there seem to be several standards!)
        # on the form:
        # https://sg-media-usor-01.s3.amazonaws.com/xxx/yyy/
        #   filename.ext?lots_of_authentication_headers
        #
        # the query string changes all the times, so when we check if an item
        # is out of date, omit it.
        if (isinstance(a, str) and isinstance(b, str) and
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
