# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import tank
import uuid
import shutil
import hashlib
import urlparse



# timeout when connection fails
CONNECTION_TIMEOUT_SECS = 20

from tank.platform.qt import QtCore, QtGui

class ShotgunDataRetriever(QtCore.QThread):
    """
    Asynchronous data retrieve class which can be used to retrieve data
    and thumbnails from Shotgun and from disk thumbnail cache.

    The class manages a queue where you can add various requests.
    Requests are queued up using the execute_find() and request_thumbnail() methods.

    Requests are executed in the following priority order:

    - first any thumbnails that are already cached on disk are handled
    - next, shotgun find() queries are handled
    - lastly thumbnail downloads are handled

    The thread will emit work_completed and work_failure signals
    when tasks are completed (or fail).

    The clear() method will clear the current queue. The currently
    processing item will finish processing and may send out signals
    even after a clear.

    Make sure you call the stop() method prior to destruction in order
    for the system to gracefully shut down.
    """


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

    # async task types
    _THUMB_CHECK, _SG_FIND_QUERY, _THUMB_DOWNLOAD = range(3)


    def __init__(self, parent=None):
        """
        Construction
        """
        QtCore.QThread.__init__(self, parent)
        self._bundle = tank.platform.current_bundle()
        self._wait_condition = QtCore.QWaitCondition()
        self._queue_mutex = QtCore.QMutex()
        self.__sg = None

        # queue data structures
        self._thumb_download_queue = []
        self._sg_find_queue = []
        self._thumb_check_queue = []

        # indicates that we should keep processing queue items
        self._process_queue = True

    ############################################################################################################
    # Public methods

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
            tank.util.download_url(bundle.shotgun, url, path_to_cached_thumb)

            # modify the permissions of the file so it's writeable by others
            old_umask = os.umask(0)
            try:
                os.chmod(path_to_cached_thumb, 0666)
            finally:
                os.umask(old_umask)

        return path_to_cached_thumb





    def set_shotgun_connection(self, sg):
        """
        Specify the shotgun api instance this model should use to communicate
        with Shotgun. If not specified, each instance will instantiate its
        own connection, via toolkit. The behavior where each instance has its own
        connection is generally recommended for thread safety reasons since
        the Shotgun API isn't natively threadsafe.

        We strongly recommend that the API instance passed in here is not used
        in any other threads since this may lead to undefined behaviour.

        :param sg: Shotgun API instance
        """
        self.__sg = sg

    def clear(self):
        """
        Clears the queue.

        Any currently processing item will complete without interruption, and signals will be
        sent out for these items.
        """
        self._queue_mutex.lock()
        try:
            self._bundle.log_debug("%s: Clearing queue. Discarded items: SG api requests: [%s] Thumb checks: [%s] "
                                   "Thumb downloads: [%s]" % (self,
                                                              len(self._sg_find_queue),
                                                              len(self._thumb_check_queue),
                                                              len(self._thumb_download_queue) ))
            self._thumb_download_queue = []
            self._sg_find_queue = []
            self._thumb_check_queue = []
        finally:
            self._queue_mutex.unlock()

    def stop(self):
        """
        Gracefully stop the receiver.

        Once stop() has been called, the object needs to be discarded.
        This is a blocking call. It will  synchronounsly wait
        until any potential currently processing item has completed.
        """
        self._bundle.log_debug("%s: Initiating shutdown." % self)
        self._process_queue = False
        self._wait_condition.wakeAll()
        self.wait()
        self._bundle.log_debug("%s: Stopped." % self)

    def execute_find(self, entity_type, filters, fields, order = None):
        """
        Adds a find query to the queue.

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param entity_type: Shotgun entity type
        :param filters: List of find filters to pass to Shotgun find call
        :param fields: List of fields to pass to Shotgun find call
        :param order: List of order dicts to pass to Shotgun find call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.
        """
        uid = uuid.uuid4().hex

        work = {"id": uid,
                "entity_type": entity_type,
                "filters": filters,
                "fields": fields,
                "order": order }
        self._queue_mutex.lock()
        try:
            self._sg_find_queue.append(work)
        finally:
            self._queue_mutex.unlock()

        # wake up execution loop!
        self._wait_condition.wakeAll()

        return uid


    def request_thumbnail(self, url, entity_type, entity_id, field):
        """
        Adds a Shotgun thumbnail request to the queue.

        If a cached version of the thumbnail exists, this will be returned.
        If not, the Shotgun will be downloaded from Shotgun.

        :param url: The thumbnail url string that is associated with this thumbnail. This is
                    the field value as returned by a Shotgun query.
        :param entity_type: Shotgun entity type with which the thumb is associated.
        :param entity_id: Shotgun entity id with which the thumb is associated.
        :param field: Thumbnail field. Normally 'image' but could also for example
                      be a deep link field such as 'sg_sequence.Sequence.image'

        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.
        """
        uid = uuid.uuid4().hex

        work = {"id": uid,
                "url": url,
                "field": field,
                "entity_type": entity_type,
                "entity_id": entity_id }
        self._queue_mutex.lock()
        try:
            self._thumb_check_queue.append(work)
        finally:
            self._queue_mutex.unlock()

        # wake up execution loop!
        self._wait_condition.wakeAll()

        return uid


    ############################################################################################################
    # Internal methods

    @staticmethod
    def _get_thumbnail_path_old(url, bundle):
        """
        March 2015 - Previous implementation of thumbnail caching logic.
        This has now been replaced by a new, improved sharding algorithm.
        In the interest of disk management, keep this method around so that
        the new logic can attempt to over files over into the new scheme 
        if at all possible.
        
        :param bundle: App, Engine or Framework instance
        :param url: Path to a thumbnail
        :returns: Path as a string.        
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




    @staticmethod
    def _get_thumbnail_path(url, bundle):
        """
        Returns the location on disk suitable for a thumbnail given its url.
        
        :param bundle: App, Engine or Framework instance
        :param url: Path to a thumbnail
        :returns: Path as a string.
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


    ############################################################################################
    # main thread loop

    def run(self):
        """
        Main thread loop
        """

        if self.__sg is None:
            # create our own private shotgun connection. This is because
            # the shotgun API isn't threadsafe, so running multiple models in parallel
            # (common) may result in side effects if a single connection is shared
            self.__sg = tank.util.shotgun.create_sg_connection()

            # set the maximum timeout for this connection for fluency
            self.__sg.config.timeout_secs = CONNECTION_TIMEOUT_SECS

        # keep running until thread is terminated
        while self._process_queue:

            # Step 1. get the next item to process.
            # We check things in the following priority order:
            # - If there is anything in the thumb check queue, do that first
            # - Then check sg queue
            # - Lastly, check thumb downloads
            item_to_process = None
            item_type = None
            self._queue_mutex.lock()
            try:

                if len(self._thumb_check_queue) > 0:
                    item_to_process = self._thumb_check_queue.pop(0)
                    item_type = ShotgunDataRetriever._THUMB_CHECK

                elif len(self._sg_find_queue) > 0:
                    item_to_process = self._sg_find_queue.pop(0)
                    item_type = ShotgunDataRetriever._SG_FIND_QUERY

                elif len(self._thumb_download_queue) > 0:
                    item_to_process = self._thumb_download_queue.pop(0)
                    item_type = ShotgunDataRetriever._THUMB_DOWNLOAD

                else:
                    # no work to be done!
                    # wait for some more work - this unlocks the mutex
                    # until the wait condition is signalled where it
                    # will then attempt to obtain a lock before returning
                    self._wait_condition.wait(self._queue_mutex)
                    # once the wait condition is triggered (usually by something
                    # inserted into one of the queues), trigger the check to happen again
                    continue

            finally:
                self._queue_mutex.unlock()

            # Step 2. Process next item and send signals.
            try:

                # process the item:

                if item_type == ShotgunDataRetriever._SG_FIND_QUERY:
                    # get stuff from shotgun
                    sg = self.__sg.find(item_to_process["entity_type"],
                                          item_to_process["filters"],
                                          item_to_process["fields"],
                                          item_to_process["order"])
                    # need to wrap it in a dict not to confuse pyqt's signals and type system
                    self.work_completed.emit(item_to_process["id"], "find", {"sg": sg } )


                elif item_type == ShotgunDataRetriever._THUMB_CHECK:
                    # check if a thumbnail exists on disk. If not, fall back onto
                    # a thumbnail download from shotgun/s3
                    url = item_to_process["url"]
                    path_to_cached_thumb = self._get_thumbnail_path(url, self._bundle)
                    if os.path.exists(path_to_cached_thumb):
                        # thumbnail already here! yay!
                        self.work_completed.emit(item_to_process["id"], "find", {"thumb_path": path_to_cached_thumb} )
                    else:
                        # no thumb here. Stick the data into the thumb download queue to request download
                        self._queue_mutex.lock()
                        try:
                            self._thumb_download_queue.append(item_to_process)
                        finally:
                            self._queue_mutex.unlock()

                elif item_type == ShotgunDataRetriever._THUMB_DOWNLOAD:
                    # download the actual thumbnail. Because of S3, the url
                    # has most likely expired, so need to re-fetch it via a sg find
                    entity_id = item_to_process["entity_id"]
                    entity_type = item_to_process["entity_type"]
                    field = item_to_process["field"]

                    sg_data = self.__sg.find_one(entity_type, [["id", "is", entity_id]], [field])

                    if sg_data is None or sg_data.get(field) is None:
                        # no thumbnail! This is possible if the thumb has changed
                        # while we were queueing it for download. In this case
                        # simply don't do anything
                        pass

                    else:
                        # download from sg
                        url = sg_data[field]
                        path_to_cached_thumb = self._get_thumbnail_path(url, self._bundle)
                        self._bundle.ensure_folder_exists(os.path.dirname(path_to_cached_thumb))
                        tank.util.download_url(self._bundle.shotgun, url, path_to_cached_thumb)
                        # modify the permissions of the file so it's writeable by others
                        old_umask = os.umask(0)
                        try:
                            os.chmod(path_to_cached_thumb, 0666)
                        finally:
                            os.umask(old_umask)

                        self.work_completed.emit(item_to_process["id"], "find", {"thumb_path": path_to_cached_thumb} )


                else:
                    raise Exception("Unknown task type!")


            except Exception, e:
                self.work_failure.emit(item_to_process["id"], "An error occurred: %s" % e)

