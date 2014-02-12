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

from tank.platform.qt import QtCore, QtGui

class ShotgunAsyncDataRetriever(QtCore.QThread):
    """
    Background worker class
    """    
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
        self._queue = []
        
        self._not_found_thumb_path = os.path.join(self._app.disk_location, "resources", "thumb_not_found.png")
        
    ############################################################################################################
    # Public methods
        
    def clear(self):
        """
        Clear the queue
        """
        self._queue_mutex.lock()
        try:
            self._app.log_debug("%s: Clearing queue. %s items discarded." % (self, len(self._queue)))
            self._queue = []
        finally:
            self._queue_mutex.unlock()
        
    def execute_find(self, entity_type, filters, fields, order = None):    
        """
        Requests that a shotgun find query is executed.
        """
        uid = uuid.uuid4().hex
        
        work = {"id": uid, 
                "type": "find", 
                "entity_type": entity_type, 
                "filters": filters, 
                "fields": fields,
                "order": order }
        self._queue_mutex.lock()
        try:
            # first in the queue
            self._queue.insert(0, work)
        finally:
            self._queue_mutex.unlock()
            
        # wake up execution loop!
        self._wait_condition.wakeAll()
        
        return uid
        
        
    def request_thumbnail(self, url, entity_type, entity_id, field):
        """
        Requests a thumbnail. Returns a dict with {"id": "XXX", "path": "xxx"}
        If the thumbnail already exists on disk, the path key will be set
        with a local path to the cached thumbnail. id in this case will be none.
        
        In the case the thumbnail does not exist locally, the opposite will happen:
        the id will be populated with a request id (uuid) string and path will
        be None. 
        """
        
        uid = uuid.uuid4().hex
        path_to_cached_thumb = self._get_thumbnail_path(url)
        
        if os.path.exists(path_to_cached_thumb):
            # we already have this on disk! Pass it back to the user straight away
            return {"path": path_to_cached_thumb, "id": None }
            
        else:
            # no thumb on disk yet! Request that it is cached on disk 
            work = {"id": uid, 
                    "type": "thumbnail_download", 
                    "url": url,
                    "field": field,
                    "entity_type": entity_type,
                    "entity_id": entity_id }
            self._queue_mutex.lock()
            try:
                # last in the queue - so that we process sg queries before thumbs
                self._queue.append(work)
            finally:
                self._queue_mutex.unlock()
                
            # wake up execution loop!
            self._wait_condition.wakeAll()
            
            return {"path": None, "id": uid }

    
    ############################################################################################################
    # Internal methods
    
    def _get_thumbnail_path(self, url):
        """
        Returns the location on disk suitable for a thumbnail given its metadata
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
        cache_path_items.append(path_chunks[-1])
        
        # join up the path
        path_to_cached_thumb = os.path.join(*cache_path_items)
        
        return path_to_cached_thumb
    

    ############################################################################################
    # main thread loop
    
    def run(self):

        # keep running until thread is terminated
        while True:
            
            # Step 1. get the next item to process. 
            item_to_process = None
            self._queue_mutex.lock()
            try:
                if len(self._queue) == 0:
                    
                    # wait for some more work - this unlocks the mutex
                    # until the wait condition is signalled where it
                    # will then attempt to obtain a lock before returning
                    self._wait_condition.wait(self._queue_mutex)
                    
                    if len(self._queue) == 0:
                        # still nothing in the queue!
                        continue
                
                # take the first item in the queue
                item_to_process = self._queue.pop(0)
            finally:
                self._queue_mutex.unlock()

            # Step 2. Process next item and send signals. 
            data = None
            try:
                # process the item:
                if item_to_process["type"] == "find":
                    
                    sg = self._app.shotgun.find(item_to_process["entity_type"],
                                                  item_to_process["filters"],
                                                  item_to_process["fields"],
                                                  item_to_process["order"])
                    # need to wrap it in a dict not to confuse pyqts signals and type system
                    data = {"sg": sg}
                
                elif item_to_process["type"] == "thumbnail_download":
                    
                    # download the actual thumbnail. Because of S3, the url
                    # has most likely expired, so need to re-fetch it.
                    entity_id = item_to_process["entity_id"]
                    entity_type = item_to_process["entity_type"]
                    field = item_to_process["field"]
                    
                    sg_data = self._app.shotgun.find_one(entity_type, 
                                                         [["id", "is", entity_id]],
                                                         [field])
                    
                    if sg_data is None or sg_data.get(field) is None:
                        # no thumbnail!
                        data = {"thumb_path": self._not_found_thumb_path }
                    
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
                
                        data = {"thumb_path": path_to_cached_thumb }
                
                else:
                    raise Exception("Unknown task type!")
                    
                
            except Exception, e:
                self.work_failure.emit(item_to_process["id"], "An error occurred: %s" % e)
                
            else:
                self.work_completed.emit(item_to_process["id"], data)
                