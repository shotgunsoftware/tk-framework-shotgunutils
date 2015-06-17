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
import uuid

import tank
from tank.platform.qt import QtCore

from .shotgun_data_retriever import ShotgunDataRetriever

class _RetrieverThread(QtCore.QThread):
    """
    Retriever thread for AsyncShotgunDataRetriever.  Maintains a job queue
    that it iterates through in a background thread, emitting a signal when
    it finishes or fails a job.
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

    def __init__(self, data_retriever=None):
        """
        Construction
        """
        QtCore.QThread.__init__(self, parent=data_retriever)
        self._data_retriever = data_retriever
        self._bundle = tank.platform.current_bundle()
        self._wait_condition = QtCore.QWaitCondition()
        self._queue_mutex = QtCore.QMutex()

        # queue data structures
        self._thumb_download_queue = []
        self._sg_find_queue = []
        self._thumb_check_queue = []

        # indicates that we should keep processing queue items
        self._process_queue = True

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

    ############################################################################################
    # main thread loop
    def run(self):
        """
        Main thread loop
        """
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
                    item_type = _RetrieverThread._THUMB_CHECK

                elif len(self._sg_find_queue) > 0:
                    item_to_process = self._sg_find_queue.pop(0)
                    item_type = _RetrieverThread._SG_FIND_QUERY

                elif len(self._thumb_download_queue) > 0:
                    item_to_process = self._thumb_download_queue.pop(0)
                    item_type = _RetrieverThread._THUMB_DOWNLOAD

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

                if item_type == _RetrieverThread._SG_FIND_QUERY:
                    # use the data retriever to execute the find:
                    sg_res = self._data_retriever._sg_find(item_to_process["entity_type"],
                                                           item_to_process["filters"],
                                                           item_to_process["fields"],
                                                           item_to_process["order"])

                    # need to wrap it in a dict not to confuse pyqt's signals and type system
                    self.work_completed.emit(item_to_process["id"], "find", {"sg": sg_res } )

                elif item_type == _RetrieverThread._THUMB_CHECK:
                    # check if a thumbnail exists on disk. If not, fall back onto
                    # a thumbnail download from shotgun/s3
                    url = item_to_process["url"]
                    path_to_cached_thumb = self._data_retriever._get_cached_thumbnail_path(url)
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

                elif item_type == _RetrieverThread._THUMB_DOWNLOAD:
                    # download the actual thumbnail. Because of S3, the url
                    # has most likely expired, so need to re-fetch it via a sg find
                    entity_id = item_to_process["entity_id"]
                    entity_type = item_to_process["entity_type"]
                    field = item_to_process["field"]
                    
                    path_to_checked_thumb = self._data_retriever._download_thumbnail(entity_type, entity_id, field)
                    if path_to_checked_thumb is None:
                        # no thumbnail! This is possible if the thumb has changed
                        # while we were queueing it for download. In this case
                        # simply don't do anything
                        pass
                    else:
                        self.work_completed.emit(item_to_process["id"], "find", {"thumb_path": path_to_cached_thumb} )

                else:
                    raise Exception("Unknown task type!")


            except Exception, e:
                self.work_failure.emit(item_to_process["id"], "An error occurred: %s" % e)


class AsyncShotgunDataRetriever(ShotgunDataRetriever):
    """
    Asyncrounous version of the Shotgun data retriever that executes all queries
    through a separate retriever thread and emits signals when the query has either
    completed or failed.
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
    
    def __init__(self, parent=None, sg=None):
        """
        Construction
        """
        ShotgunDataRetriever.__init__(self, parent, sg)

        # create the worker thread that will perform all data retrieval:
        self._retriever_thread = _RetrieverThread(self)
        # and hook up the signals:
        self._retriever_thread.work_completed.connect(self.work_completed.emit)
        self._retriever_thread.work_failure.connect(self.work_failure.emit)
    
    def start(self):
        """
        Start the retriever thread
        """
        return self._retriever_thread.start()
        
    def stop(self):
        """
        Stop the retriever thread
        """
        return self._retriever_thread.stop()

    def clear(self):
        """
        Clear the retriever thread job queue
        """
        return self._retriever_thread.clear()

    def execute_find(self, entity_type, filters, fields, order = None):
        """
        Overriden base class method.  Executes a Shotgun find query asyncronously
        """
        return self._retriever_thread.execute_find(entity_type, filters, fields, order)

    def request_thumbnail(self, url, entity_type, entity_id, field):
        """
        Overriden base class method.  Downloads a thumbnail form Shotgun asyncronously
        or returns the cached thumbnail if found.
        """
        return self._retriever_thread.request_thumbnail(url, entity_type, entity_id, field)


