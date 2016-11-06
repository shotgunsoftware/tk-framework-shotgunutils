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
import gc

from .data_handler import ShotgunDataHandler, log_timing
from .data_item import ShotgunDataItem
from .errors import ShotgunModelDataError

class ShotgunFindDataHandler(ShotgunDataHandler):
    """
    Shotgun Model low level data storage.
    """

    def __init__(self, entity_type, filters, order, hierarchy, fields, column_fields, download_thumbs, limit, additional_filter_presets, cache_path, parent):
        """
        :param cache_path: Path to cache file location
        :param parent: Parent QT object
        """
        super(ShotgunFindDataHandler, self).__init__(cache_path, parent)
        self.__entity_ids = None
        self.__entity_type = entity_type
        self.__filters = filters
        self.__order = order
        self.__hierarchy = hierarchy
        self.__fields = fields
        self.__column_fields = column_fields
        self.__download_thumbs = download_thumbs
        self.__limit = limit
        self.__additional_filter_presets = additional_filter_presets

    def _clear_cache(self):
        """
        Sets up an empty cache in memory
        """
        self.__entity_ids = None
        super(ShotgunFindDataHandler, self)._clear_cache()

    def unload_cache(self):
        """
        Unloads any in-memory cache data.
        """
        self.__entity_ids = None
        super(ShotgunFindDataHandler, self).unload_cache()

    def get_entity_ids(self):
        """
        Returns a list of entity ids contained in this data set given an entity type.

        :return: A list of unique ids for all items in the model.
        :rtype: ``list``
        """
        # loop over all cache items - the find data handler organizes
        # its unique ids so that all leaf nodes (e.g. representing an entity
        # are ints and all other items are strings

        # memoized for performance
        if self.__entity_ids is None:
            entity_ids = []
            for uid in self._cache[self.CACHE_BY_UID].keys():
                if isinstance(uid, int):
                    # this is a leaf node representing an entity
                    entity_ids.append(uid)
            self.__entity_ids = entity_ids

        return self.__entity_ids

    def get_uid_from_entity_id(self, entity_id):
        """
        Returns the unique id for a given entity or None if not found
        """
        for uid in self._cache[self.CACHE_BY_UID].keys():
            if isinstance(uid, int) and uid == entity_id:
                return uid
        return None


    def generate_data_request(self, data_retriever):
        """
        Generate a data request for a data retriever.
        Once the data has arrived, update_data() will be called.

        :returns: Request id or None if no work is needed
        """
        # only request data from shotgun is filters are defined.
        if self.__filters is None:
            request_id = None

        else:
            # get data from shotgun - list/set cast to ensure unique fields
            fields = self.__hierarchy + self.__fields + self.__column_fields
            if self.__download_thumbs:
                fields = fields + ["image"]
            fields = list(set(fields))

            find_kwargs = dict(
                limit=self.__limit,
            )

            # We only want to include the filter presets kwarg if it was explicitly asked
            # for. The reason for this is that it's a Shotgun 7.0 feature server side, and
            # we don't want to break backwards compatibility with older versions of Shotgun.
            if self.__additional_filter_presets:
                find_kwargs["additional_filter_presets"] = self.__additional_filter_presets

            request_id = data_retriever.execute_find(
                self.__entity_type,
                self.__filters,
                fields,
                self.__order,
                **find_kwargs
            )

        print "req id: %s" % request_id
        return request_id


    @log_timing
    def update_data(self, sg_data):
        """
        Adds find data to the data set in memory.

        Runs a comparison between old and new data and returns a list of entity ids
        that have changed between what was previously in the database and what is there now.

        raises an exception if no cache is loaded.

        :returns: list of updated plugin ids. empty list if cache was up to date.
        """
        self._log_debug("Updating %s with %s shotgun records." % (self, len(sg_data)))
        self._log_debug("Hierarchy: %s" % self.__hierarchy)

        if self._cache is None:
            raise ShotgunModelDataError("No data currently loaded in memory!")

        if len(self._cache[self.CACHE_CHILDREN]) == 0:
            self._log_debug("In-memory cache is empty.")

        # ensure the data is clean
        # todo - optimize this!
        self._log_debug("sanitizing data...")
        sg_data = self.__sg_clean_data(sg_data)
        self._log_debug("...done!")

        self._log_debug("Generating new tree in memory...")

        # create a brand new tree rather than trying to be clever
        # about how we cull intermediate nodes for deleted items
        diff_list = []
        num_adds = 0
        num_deletes = 0
        num_modifications = 0

        new_cache = self._init_clear_cache()

        # analyze the incoming shotgun data
        for sg_item in sg_data:

            sub_tree = new_cache
            # maintain a hierarchy of unique ids

            # Create items by drilling down the hierarchy
            for field_name in self.__hierarchy:

                on_leaf_level = (self.__hierarchy[-1] == field_name)

                if not on_leaf_level:
                    # get the parent uid or None if we are at the root level
                    parent_uid = sub_tree.get(self.UID)
                    # generate path for this item
                    unique_field_value = self.__generate_unique_key(parent_uid, field_name, sg_item)
                else:
                    # on the leaf level, use the entity id as the unique key
                    unique_field_value = sg_item["id"]

                # two distinct cases for leaves and non-leaves
                if on_leaf_level:
                    # this is an actual entity - insert into our new tree
                    item = {
                        self.SG_DATA: sg_item,
                        self.FIELD: field_name,
                        self.IS_LEAF: True,
                        self.UID: unique_field_value,
                        self.PARENT: sub_tree,
                        self.CACHE_CHILDREN: {},
                    }
                    sub_tree[self.CACHE_CHILDREN][unique_field_value] = item
                    new_cache[self.CACHE_BY_UID][unique_field_value] = item

                    # now check with prev data structure to see if it has changed
                    if unique_field_value not in self._cache[self.CACHE_BY_UID]:
                        # this is a new node that wasn't there before
                        diff_list.append({
                            "data": ShotgunDataItem(item),
                            "mode": self.ADDED
                        })
                        num_adds += 1
                    else:
                        # record already existed in prev dataset. Check if value has changed
                        old_record = self._cache[self.CACHE_BY_UID][unique_field_value][self.SG_DATA]
                        if not self.__compare_shotgun_data(old_record, sg_item):
                            diff_list.append({
                                "data": ShotgunDataItem(item),
                                "mode": self.UPDATED
                            })
                            num_modifications += 1

                else:
                    # not on leaf level yet
                    if unique_field_value not in sub_tree[self.CACHE_CHILDREN]:
                        # item is not yet inserted in our new tree so add it
                        # because these are parent items like project nodes

                        item = {
                            self.SG_DATA: sg_item,
                            self.FIELD: field_name,
                            self.IS_LEAF: False,
                            self.UID: unique_field_value,
                            self.PARENT: sub_tree,
                            self.CACHE_CHILDREN: {},
                        }
                        sub_tree[self.CACHE_CHILDREN][unique_field_value] = item
                        new_cache[self.CACHE_BY_UID][unique_field_value] = item

                        # now check with prev data structure to see if it has changed
                        if unique_field_value not in self._cache[self.CACHE_BY_UID]:
                            # this is a new node that wasn't there before
                            diff_list.append({
                                "data": ShotgunDataItem(item),
                                "mode": self.ADDED
                            })
                            num_adds += 1
                        else:
                            # record already existed in prev dataset. Check if value has changed
                            current_record = self._cache[self.CACHE_BY_UID][unique_field_value][self.SG_DATA]
                            # don't compare the whole record but just the part that relates to this
                            # intermediate node value. For example, we may be looking at a project node
                            # in the hierarchy but the full sg record contains all the data for a shot.
                            # in this case, just run the comparison on the project subset of the full
                            # shot data dict.
                            if not self.__compare_shotgun_data(current_record.get(field_name), sg_item.get(field_name)):
                                diff_list.append({
                                    "data": ShotgunDataItem(item),
                                    "mode": self.UPDATED
                                })
                                num_modifications += 1

                    # recurse down to the next level
                    sub_tree = sub_tree[self.CACHE_CHILDREN][unique_field_value]

        # now figure out if anything has been removed
        self._log_debug("Diffing new tree against old tree...")

        current_uids = set(self._cache[self.CACHE_BY_UID].keys())
        new_uids = set(new_cache[self.CACHE_BY_UID].keys())

        for deleted_uid in current_uids.difference(new_uids):
            item = self._cache[self.CACHE_BY_UID][deleted_uid]
            diff_list.append({
                "data": ShotgunDataItem(item),
                "mode": self.DELETED
            })
            num_deletes += 1

        # lastly swap the new for8 the old
        self._clear_cache()

        # at this point, kick the gc to make sure the memory is freed up
        # despite its cycles.
        gc.collect()

        # and set the new cache
        self._cache = new_cache

        self._log_debug("Shotgun data (%d records) received and processed. " % len(sg_data))
        self._log_debug("    The new tree is %d records." % len(self._cache[self.CACHE_BY_UID]))
        self._log_debug("    There were %d diffs from in-memory cache:" % len(diff_list))
        self._log_debug("    Number of new records: %d" % num_adds)
        self._log_debug("    Number of deleted records: %d" % num_deletes)
        self._log_debug("    Number of modified records: %d" % num_modifications)

        return diff_list


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

    def __generate_unique_key(self, parent_unique_key, field, sg_data):
        """
        Generates a unique key from a shotgun field.

        Used in conjunction with the hierarchical nature of the find data handler -
        assuming that on each level, values are unique.
        """
        value = sg_data.get(field)

        if isinstance(value, dict) and "id" in value and "type" in value:
            # for single entity links, return the entity id
            unique_key = value["id"]

        elif isinstance(value, list):
            # this is a list of some sort. Loop over all elements and extract a comma separated list.
            formatted_values = []
            if len(value) == 0:
                # no items in list
                formatted_values.append("_")
            for v in value:
                if isinstance(v, dict) and "id" in v and "type" in v:
                    # This is a link field
                    formatted_values.append(str(v["id"]))
                else:
                    formatted_values.append(str(v))

            unique_key = ",".join(formatted_values)

        else:
            # everything else just cast to string
            unique_key = str(value)

        if parent_unique_key is None:
            # no parent
            return "/%s" % unique_key
        else:
            return "%s/%s" % (parent_unique_key, unique_key)

    def __compare_shotgun_data(self, a, b):
        """
        Compares two dicts, assumes the same set of keys in both.
        Omits thumbnail fields because these change all the time (S3).
        Both inputs are assumed to contain utf-8 encoded data.

        :returns: True if a is same as b, false otherwise
        """
        if isinstance(a, dict) and isinstance(b, dict):

            for key in a.iterkeys():
                a_value = a[key]
                b_value = b[key]

                # handle thumbnail fields as a special case
                # thumbnail urls are (typically, there seem to be several standards!)
                # on the form:
                # https://sg-media-usor-01.s3.amazonaws.com/xxx/yyy/
                #   filename.ext?lots_of_authentication_headers
                #
                # the query string changes all the times, so when we check if an item
                # is out of date, omit it.
                if (isinstance(a_value, str) and isinstance(b_value, str) and
                      a_value.startswith("http") and b_value.startswith("http") and
                      ("amazonaws" in a_value or "AccessKeyId" in a_value)):
                    # attempt to parse values are urls and eliminate the querystring
                    # compare hostname + path only
                    url_obj_a = urlparse.urlparse(a_value)
                    url_obj_b = urlparse.urlparse(b_value)
                    compare_str_a = "%s/%s" % (url_obj_a.netloc, url_obj_a.path)
                    compare_str_b = "%s/%s" % (url_obj_b.netloc, url_obj_b.path)
                    if compare_str_a != compare_str_b:
                        # url has changed
                        return False

                elif a_value != b_value:
                    return False

        else:
            if a != b:
                return False

        return True


