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
import urllib
import tank
import uuid
import sys
import urlparse
import tempfile
import os
import urllib
import shutil

# timeout when connection fails
CONNECTION_TIMEOUT_SECS = 20

from tank.platform.qt import QtCore, QtGui

class ShotgunAsyncDataRetriever(QtCore.QThread):
    """
    Note: This is part of the internals of the Shotgun Utils Framework and 
    should not be called directly.
    
    Async worker class which is used by the ShotgunModel to retrieve data 
    and thumbnails from Shotgun and from disk thumbnail cache.
    
    Tasks are queued up using the execute_find() and request_thumbnail() methods.
    
    Tasks are executed in the following priority order:
    
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
    
    # async task types
    THUMB_CHECK, SG_FIND_QUERY, THUMB_DOWNLOAD = range(3)
    
    work_completed = QtCore.Signal(str, dict)
    work_failure = QtCore.Signal(str, str)
    
    def __init__(self, parent=None):
        """
        Construction
        """
        QtCore.QThread.__init__(self, parent)
        self._app = tank.platform.current_bundle()
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
        
    def set_shotgun_connection(self, sg):
        """
        Specify the shotgun api instance this model should use to communicate
        with Shotgun. If not specified, each model instance will instantiante its
        own connection, via toolkit. The behaviour where each model has its own
        connection is generally recommended for thread safety reasons since 
        the Shotgun API isn't natively threadsafe.
        
        :param sg: Shotgun API instance
        """
        self.__sg = sg
        
    def clear(self):
        """
        Clears the queue. Any currently processing item will complete without interruption.
        """
        self._queue_mutex.lock()
        try:
            self._app.log_debug("%s: Clearing queue. Discarded items: SG api requests: [%s] Thumb checks: [%s] "
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
        Gracefully stop the thread. Will synchronounsly wait until any potential
        currently processing item is completing.
        """
        self._process_queue = False
        self._wait_condition.wakeAll()
        self.wait()
        
    def execute_find(self, entity_type, filters, fields, order = None):    
        """
        Adds a find query to the queue. 
        
        :param entity_type: Shotgun entity type
        :param filters: List of find filters to pass to Shotgun find call
        :param fields: List of fields to pass to Shotgun find call
        :param order: List of order dicts to pass to Shotgun find call
        :returns: A unique identifier representing this request 
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
        
        :param url: The thumbnail url that is associated with this thumbnail
        :param entity_type: Shotgun entity type with which the thumb is associated.
        :param entity_id: Shotgun entity id with which the thumb is associated.
        :param field: Thumbnail field. Normally 'image' but could also for example
                      be a deep link field such as 'sg_sequence.Sequence.image'
        
        :returns: A unique identifier representing this request 
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
    
    def _get_thumbnail_path(self, url):
        """
        Returns the location on disk suitable for a thumbnail given its url.
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
        cache_path_items = [self._app.cache_location, "thumbnails"]        
        # append the folders
        cache_path_items.extend(new_chunks)
        # and append the file name
        # all sg thumbs are jpegs so append extension too - some url forms don't have this.
        cache_path_items.append("%s.jpeg" % path_chunks[-1])
        
        # join up the path
        path_to_cached_thumb = os.path.join(*cache_path_items)
        
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
                    item_type = ShotgunAsyncDataRetriever.THUMB_CHECK
                    
                elif len(self._sg_find_queue) > 0:
                    item_to_process = self._sg_find_queue.pop(0)
                    item_type = ShotgunAsyncDataRetriever.SG_FIND_QUERY
                    
                elif len(self._thumb_download_queue) > 0:
                    item_to_process = self._thumb_download_queue.pop(0)
                    item_type = ShotgunAsyncDataRetriever.THUMB_DOWNLOAD
                    
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
                
                if item_type == ShotgunAsyncDataRetriever.SG_FIND_QUERY:
                    # get stuff from shotgun
                    sg = self.__sg.find(item_to_process["entity_type"],
                                          item_to_process["filters"],
                                          item_to_process["fields"],
                                          item_to_process["order"])
                    # need to wrap it in a dict not to confuse pyqt's signals and type system
                    self.work_completed.emit(item_to_process["id"], {"sg": sg } )
                
                
                elif item_type == ShotgunAsyncDataRetriever.THUMB_CHECK:
                    # check if a thumbnail exists on disk. If not, fall back onto
                    # a thumbnail download from shotgun/s3
                    url = item_to_process["url"]
                    path_to_cached_thumb = self._get_thumbnail_path(url)
                    if os.path.exists(path_to_cached_thumb):
                        # thumbnail already here! yay!
                        self.work_completed.emit(item_to_process["id"], {"thumb_path": path_to_cached_thumb} )
                    else:
                        # no thumb here. Stick the data into the thumb download queue to request download
                        self._queue_mutex.lock()
                        try:
                            self._thumb_download_queue.append(item_to_process)
                        finally:
                            self._queue_mutex.unlock()
                
                elif item_type == ShotgunAsyncDataRetriever.THUMB_DOWNLOAD:
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
                        path_to_cached_thumb = self._get_thumbnail_path(url)
                        self._app.ensure_folder_exists(os.path.dirname(path_to_cached_thumb))
                        tank.util.download_url(self._app.shotgun, url, path_to_cached_thumb)
                        # modify the permissions of the file so it's writeable by others
                        old_umask = os.umask(0)
                        try:
                            os.chmod(path_to_cached_thumb, 0666)
                        finally:
                            os.umask(old_umask)
                        
                        self.work_completed.emit(item_to_process["id"], {"thumb_path": path_to_cached_thumb} )
                        
                
                else:
                    raise Exception("Unknown task type!")
                    
                
            except Exception, e:
                self.work_failure.emit(item_to_process["id"], "An error occurred: %s" % e)
                
                