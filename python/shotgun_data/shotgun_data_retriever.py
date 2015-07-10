# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import urlparse
import hashlib
import threading
import time
import random
import copy

import sgtk
from sgtk.platform.qt import QtCore

from .background_task_manager import BackgroundTaskManager

class ShotgunDataRetriever(QtCore.QObject):
    """
    Asyncrounous Shotgun data retriever used to execute queries and download/manage
    thumbnails from Shotgun. Uses the BackgroundTaskManager to run tasks in background 
    threads and emits signals when each query has either completed or failed.
    """

    @staticmethod
    def download_thumbnail(url, bundle):
        """
        Convenience and compatibility method for quick and easy synchrnous thumbnail download.
        This will retrieve a shotgun thumbnail given a url - if it already exists in the cache,
        a path to it will be returned instantly. If not, it will be downloaded from Shotgun,
        placed in the standard cache location on disk and its path will be returned.

        This is a helper method meant to make it easy to port over synchronous legacy
        code - for a better solution, we recommend using the thumbnail retrieval
        that runs in a background thread.

        Bcause Shotgun thumbnail urls have an expiry time, make sure to only
        pass urls to this method that have been very recently retrieved via a Shotgun find call.

        :param url: The thumbnail url string that is associated with this thumbnail. This is
                    the field value as returned by a Shotgun query.
        :param bundle: App, Framework or Engine object requesting the download.

        :returns: A path to the thumbnail on disk.
        """

        path_to_cached_thumb = ShotgunDataRetriever._get_thumbnail_path(url, bundle)

        if not os.path.exists(path_to_cached_thumb):

            # create folders on disk
            bundle.ensure_folder_exists(os.path.dirname(path_to_cached_thumb))

            # download using standard core method. This will ensure that
            # proxy and connection settings as set in the SG API are used
            sgtk.util.download_url(bundle.shotgun, url, path_to_cached_thumb)

            # modify the permissions of the file so it's writeable by others
            old_umask = os.umask(0)
            try:
                os.chmod(path_to_cached_thumb, 0666)
            finally:
                os.umask(old_umask)

        return path_to_cached_thumb    
    
    @staticmethod
    def _get_thumbnail_path(url, bundle):
        """
        Returns the location on disk suitable for a thumbnail given its url.

        :param url:     Path to a thumbnail
        :param bundle:  App, Engine or Framework instance
        :returns:       Path as a string.
        """
    
        # hash the path portion of the thumbnail url
        url_obj = urlparse.urlparse(url)
        url_hash = hashlib.md5()
        url_hash.update(str(url_obj.path))
        hash_str = url_hash.hexdigest()
    
        # Now turn this hash into a tree structure. For a discussion about sensible
        # sharding methodology, see 
        # http://stackoverflow.com/questions/13841931/using-guids-as-folder-names-splitting-up
        #
        # From the hash, generate paths on the form C1C2/C3C4/rest_of_hash.jpeg
        # (where C1 is the first character of the hash.)
        # for a million evenly distributed items, this means ~15 items per folder
        first_folder = hash_str[0:2]
        second_folder = hash_str[2:4]
        file_name = "%s.jpeg" % hash_str[4:]
        path_chunks = [first_folder, second_folder, file_name]
    
        # establish the root path
        cache_path_items = [bundle.cache_location, "thumbs"]
        # append the folders
        cache_path_items.extend(path_chunks)
        # join up the path
        path_to_cached_thumb = os.path.join(*cache_path_items)
    
        # perform a simple migration to check if the old path still exists. In that case, 
        # try to move it across to the new path. This is to help transition from the previous
        # thumb caching structures and should be removed at some point in the future in order
        # to avoid I/O operations. 
        #
        # NOTE! This check means that the _get_thumbnail_path() isn't 
        # just calculating a path for a thumbnail but may have the side effect that it will
        # move files around. 
        old_path = ShotgunDataRetriever._get_thumbnail_path_old(url, bundle)
        if os.path.exists(old_path):
            # move the file across
            try:
                old_umask = os.umask(0)
                try:
                    bundle.ensure_folder_exists(os.path.dirname(path_to_cached_thumb))
                    shutil.move(old_path, path_to_cached_thumb)
                finally:
                    os.umask(old_umask)
            except:
                # ignore any errors in the transfer
                pass
            
        return path_to_cached_thumb
    
    @staticmethod
    def _get_thumbnail_path_old(url, bundle):
        """
        March 2015 - Previous implementation of thumbnail caching logic.
        This has now been replaced by a new, improved sharding algorithm.
        In the interest of disk management, keep this method around so that
        the new logic can attempt to over files over into the new scheme 
        if at all possible.

        :param url:     Path to a thumbnail        
        :param bundle:  App, Engine or Framework instance
        :returns:       Path as a string.        
        """
    
        url_obj = urlparse.urlparse(url)
        url_path = url_obj.path
        path_chunks = url_path.split("/")
    
        CHUNK_LEN = 16
    
        # post process the path
        # old (pre-S3) style result:
        # path_chunks: [ "", "thumbs", "1", "2", "2.jpg"]
    
        # s3 result, form 1:
        # path_chunks: [u'',
        #               u'9902b5f5f336fae2fb248e8a8748fcd9aedd822e',
        #               u'be4236b8f198ae84df2366920e7ee327cc0a567e',
        #               u'render_0400_t.jpg']
    
        # s3 result, form 2:
        # path_chunks: [u'', u'thumbnail', u'api_image', u'150']
    
        def _to_chunks(s):
            #split the string 'abcdefghxx' into ['abcdefgh', 'xx']
            chunks = []
            for start in range(0, len(s), CHUNK_LEN):
                chunks.append( s[start:start+CHUNK_LEN] )
            return chunks
    
        new_chunks = []
        for folder in path_chunks[:-1]: # skip the file name
            if folder == "":
                continue
            if len(folder) > CHUNK_LEN:
                # long url path segment like 9902b5f5f336fae2fb248e8a8748fcd9aedd822e
                # split it into chunks for 4
                new_chunks.extend( _to_chunks(folder) )
            else:
                new_chunks.append(folder)
    
        # establish the root path
        cache_path_items = [bundle.cache_location, "thumbnails"]
        # append the folders
        cache_path_items.extend(new_chunks)
        # and append the file name
        # all sg thumbs are jpegs so append extension too - some url forms don't have this.
        cache_path_items.append("%s.jpeg" % path_chunks[-1])
    
        # join up the path
        path_to_cached_thumb = os.path.join(*cache_path_items)
    
        return path_to_cached_thumb

    ## timeout when Shotgun connection fails
    _SG_CONNECTION_TIMEOUT_SECS = 20

    # default individual task priorities
    _DOWNLOAD_THUMB_PRIORITY, _SG_FIND_PRIORITY, _CHECK_THUMB_PRIORITY = range(3)

    # ------------------------------------------------------------------------------------------------
    # Signals
    #
    # syntax: work_completed(uid, request_type, data_dict)
    # - uid is a unique id which matches the unique id
    #   returned by the corresponding request call.
    #
    # - request_type is a string denoting the type of request
    #   this event is associated with. It can be either "find"
    #   or "thumbnail"
    #
    # - data_dict is a dictionary containing the payload
    #   of the request. It will be different depending on
    #   what type of request it is.
    #
    #   For find() requests, the data_dict will be on the form
    #   {"sg": data }, where data is the data returned by the sg API
    #
    #   For thumbnail requests, the data dict will be on the form
    #   {"thumb_path": path}, where path is a path to a location
    #   on disk where the thumbnail can be accessed.
    work_completed = QtCore.Signal(str, str, dict)

    # syntax: work_failure(uid, error_message)
    # - uid is a unique id which matches the unique id
    #   returned by the corresponding request call.
    # - error message is an error message string.
    work_failure = QtCore.Signal(str, str)
    
    def __init__(self, parent=None, sg=None, bg_task_manager=None):
        """
        Construction
        """
        QtCore.QObject.__init__(self, parent)
        self._bundle = sgtk.platform.current_bundle()

        # thread local storage for the thread-specific shotgun connection:
        self._threadlocal_storage = threading.local()

        # set up the background task manager:
        self._task_manager = bg_task_manager or BackgroundTaskManager(parent=self, max_threads=1)
        self._owns_task_manager = (bg_task_manager is None)
        self._bg_tasks_group = self._task_manager.next_group_id()
        self._task_manager.task_completed.connect(self._on_task_completed)
        self._task_manager.task_failed.connect(self._on_task_failed)

    # ------------------------------------------------------------------------------------------------
    # Public interface

    @property
    def shotgun_connection(self):
        """
        Get a Shotgun connection to use.  Creates a new Shotgun connection if the
        instance doesn't already have one.
        
        :returns:    The Shotgun connection for this instance
        """
        return self._task_manager.shotgun_connection
        #if not hasattr(self._threadlocal_storage, "shotgun"):
        #    print "Creating another shotgun connection..!"
        #    
        #    # create our own private shotgun connection. This is because
        #    # the shotgun API isn't threadsafe, so running multiple models in parallel
        #    # (common) may result in side effects if a single connection is shared
        #    self._threadlocal_storage.shotgun = sgtk.util.shotgun.create_sg_connection()
        #
        #    # set the maximum timeout for this connection for fluency
        #    self._threadlocal_storage.shotgun.config.timeout_secs = ShotgunDataRetriever._SG_CONNECTION_TIMEOUT_SECS
        #
        #return self._threadlocal_storage.shotgun

    def set_shotgun_connection(self):
        """
        This has now been deprecated as it may not be thread-safe!
        """
        pass

    def start(self):
        """
        Start the retriever thread
        """
        self._task_manager.start_processing()

    def stop(self):
        """
        Stop the retriever thread
        """
        if not self._task_manager:
            return
        
        if self._owns_task_manager:
            # we own the task manager so we'll need to completely shut it down before
            # returning
            self._task_manager.shut_down()
            self._task_manager = None
        else:
            # we don't own the task manager so just stop any tasks we might be running 
            # and disconnect from it:
            self._task_manager.stop_task_group(self._bg_tasks_group)
            self._task_manager.task_completed.disconnect(self._on_task_completed)
            self._task_manager.task_failed.disconnect(self._on_task_failed)
            self._task_manager = None

    def stop_work(self, uid):
        """
        """
        self._task_manager.stop_task(int(uid))

    def clear(self):
        """
        Clear the retriever thread job queue
        """
        if not self._task_manager:
            return
        # stop any tasks running in the task group:
        self._task_manager.stop_task_group(self._bg_tasks_group)

    def execute_find(self, entity_type, filters, fields, order = None):
        """
        Overriden base class method.  Executes a Shotgun find query asyncronously
        """
        if not self._task_manager:
            return
        task_id = self._task_manager.add_task(self._task_execute_find,
                                           priority = ShotgunDataRetriever._SG_FIND_PRIORITY,
                                           group = self._bg_tasks_group,
                                           entity_type=entity_type, 
                                           filters=filters, 
                                           fields=fields, 
                                           order=order)
        return str(task_id)

    def request_thumbnail(self, url, entity_type, entity_id, field):
        """
        Overriden base class method.  Downloads a thumbnail form Shotgun asyncronously
        or returns the cached thumbnail if found.
        """
        if not self._task_manager:
            return
        check_task_id = self._task_manager.add_task(self._task_check_thumbnail,
                                                 priority = ShotgunDataRetriever._CHECK_THUMB_PRIORITY,
                                                 group = self._bg_tasks_group,
                                                 url=url)

        dl_task_id = self._task_manager.add_task(self._task_download_thumbnail,
                                              upstream_task_ids = [check_task_id],
                                              priority = ShotgunDataRetriever._DOWNLOAD_THUMB_PRIORITY,
                                              group = self._bg_tasks_group,
                                              entity_type=entity_type, 
                                              entity_id=entity_id,
                                              field=field)
        return str(dl_task_id)



    # ------------------------------------------------------------------------------------------------
    # Background task management and methods

    def _task_execute_find(self, shotgun_connection, entity_type, filters, fields, order):
        """
        """
        sg_res = self._sg_find(shotgun_connection, entity_type, filters, fields, order)
        return {"action":"find", "sg_result":sg_res}

    def _task_check_thumbnail(self, url):
        """
        """
        path_to_cached_thumb = self._get_cached_thumbnail_path(url)
        if not os.path.exists(path_to_cached_thumb):
            path_to_cached_thumb = None
        return {"thumb_path":path_to_cached_thumb}

    def _task_download_thumbnail(self, thumb_path, entity_type, entity_id, field):
        """
        """
        path = thumb_path or self._download_thumbnail(entity_type, entity_id, field)
        return {"action":"find_thumbnail", "thumb_path":path}

    def _on_task_completed(self, task_id, group, result):
        """
        """
        action = result.get("action")
        if action == "find":
            sg_res = result.get("sg_result", [])
            self.work_completed.emit(str(task_id), "find", {"sg": sg_res })
        elif action == "find_thumbnail":
            path = result.get("thumb_path", "")
            self.work_completed.emit(str(task_id), "find", {"thumb_path": path})

    def _on_task_failed(self, task_id, msg, tb):
        """
        """
        self.work_failure.emit(str(task_id), msg)

    # ------------------------------------------------------------------------------------------------
    # Main implementation

    def _sg_find(self, sg, entity_type, filters, fields, order):
        """
        Execute a Shotgun find query for the specified entity type using the specified 
        filters, fields and order.

        :param entity_type: Entity type to find Shotgun records for
        :param filters:     Filters to filter the found records by
        :param fields:      Fields to return for any found records
        :param order:       The order to return any found records in
        :returns:           Any found records as a list of Shotgun dictionaries
        """
        #res = self._bundle.engine.execute_in_main_thread(self._find_in_main_thread, 
        #                                                 entity_type, filters, fields, order)
        #time.sleep(random.randint(0, 20)/100.0)
        #return res

        #res = sgtk.platform.current_engine().execute_in_main_thread(self._find_on_main_thread,
        #                                                            entity_type, 
        #                                                            filters, 
        #                                                            fields, 
        #                                                            order)
        #res = self.shotgun_connection.find(entity_type, filters, fields, order)
        s = ""
        for tick in range(20):
            time.sleep(0.01)
            multiplier = random.randint(1, 8)
            for i in range(8*multiplier):
                s = "%s%d" % (s, i)
        time.sleep(1)
        res = dict((i, c) for i, c in enumerate(s))
        
        #res = sg.find(entity_type, filters, fields, order)
        #res = self.shotgun_connection.find_dummy(entity_type, filters, fields, order)
        #res = sg.find_dummy(entity_type, filters, fields, order)
        return res
    
    def _find_on_main_thread(self, entity_type, filters, fields, order):
        
        app = sgtk.platform.current_bundle()
        res = app.shotgun.find(entity_type, filters, fields, order)
        return res


    def _get_cached_thumbnail_path(self, url):
        """
        Get the cached thumbnail path for the specified url

        :param url: The url to return the cached path for
        :returns:   The cached path for the specified url.
        """
        return ShotgunDataRetriever._get_thumbnail_path(url, self._bundle)

    def _download_thumbnail(self, entity_type, entity_id, field):
        """
        Download the thumbnail for the specified entity type, id and field.  This downloads the
        thumbnail into the thumbnail cache directory and returns the cached path.

        :param entity_type: Type of the entity to retrieve the thumbnail for
        :param entity_id:   Id of the entity to retrieve the thumbnail for
        :param field:       The field on the entity that holds the url for the thumbnail to retrieve
        :returns:           The cached path on disk for the thumbnail if found
        """
        path_to_cached_thumb = None

        # download the actual thumbnail. Because of S3, the url
        # has most likely expired, so need to re-fetch it via a sg find
        sg_data = self.shotgun_connection.find_one(entity_type, [["id", "is", entity_id]], [field])
        if sg_data and sg_data.get(field):
            url = sg_data[field]
            path_to_cached_thumb = self._get_cached_thumbnail_path(url)
            self._bundle.ensure_folder_exists(os.path.dirname(path_to_cached_thumb))
            sgtk.util.download_url(self.shotgun_connection, url, path_to_cached_thumb)
            # modify the permissions of the file so it's writeable by others
            old_umask = os.umask(0)
            try:
                os.chmod(path_to_cached_thumb, 0666)
            finally:
                os.umask(old_umask)

        return path_to_cached_thumb


