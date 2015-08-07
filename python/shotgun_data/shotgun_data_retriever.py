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

import sgtk
from sgtk.platform.qt import QtCore
from sgtk import TankError

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

        Because Shotgun thumbnail urls have an expiry time, make sure to only
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

    # default individual task priorities
    _SG_DOWNLOAD_SCHEMA_PRIORITY    = 10
    _DOWNLOAD_THUMB_PRIORITY        = 20
    _EXECUTE_METHOD_PRIORITY        = 30
    _SG_DELETE_PRIORITY             = 40
    _SG_CREATE_PRIORITY             = 40
    _SG_UPDATE_PRIORITY             = 40
    _SG_FIND_PRIORITY               = 40
    _CHECK_THUMB_PRIORITY           = 40

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

        # set up the background task manager:
        self._task_manager = bg_task_manager or BackgroundTaskManager(parent=self, max_threads=1)
        self._owns_task_manager = (bg_task_manager is None)
        self._bg_tasks_group = self._task_manager.next_group_id()
        self._task_manager.task_completed.connect(self._on_task_completed)
        self._task_manager.task_failed.connect(self._on_task_failed)

        self._thumb_task_id_map = {}

    # ------------------------------------------------------------------------------------------------
    # Public interface

    @property
    def _shotgun_connection(self):
        """
        Returns the Shotgun connection currently being used.  Note that this will be thread
        specific.

        :returns:    The Shotgun connection for this instance in the current thread
        """
        return self._task_manager.shotgun_connection

    def start(self):
        """
        Start the retriever thread.

        :raises:    TankError if there is no BackgroundTaskManager associated with this instance
        """
        if not self._task_manager:
            raise TankError("Unable to start the ShotgunDataRetriever as it has no BackgroundTaskManager!")
        self._task_manager.start_processing()

    def stop(self):
        """
        Stop the retriever thread.

        Note that once stopped the data retriever can't be restarted as the handle to the
        BackgroundTaskManager instance is released.
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

    def clear(self):
        """
        Clear the retriever thread job queue
        """
        if not self._task_manager:
            return
        # stop any tasks running in the task group:
        self._task_manager.stop_task_group(self._bg_tasks_group)

    def stop_work(self, task_id):
        """
        Stop the specified task

        :param task_id: The task to stop
        """
        if not self._task_manager:
            return
        # stop the task:
        self._task_manager.stop_task(task_id)

    def get_schema(self, project_id=None):
        """
        Execute the schema_read and schema_entity_read methods asynchronously

        :param project_id:  If specified, the schema listing returned will
                            be constrained by the schema settings for 
                            the given project.
        :returns:           A unique task id representing this request.
        """
        return self._add_task(self._task_get_schema, 
                              priority = ShotgunDataRetriever._SG_DOWNLOAD_SCHEMA_PRIORITY,
                              task_kwargs = {"project_id":project_id})

    def execute_find(self, *args, **kwargs):
        """
        Executes a Shotgun find query asyncronously.

        This method takes the same parameters as the Shotgun find() call.

        :param *args:       args to be passed to the Shotgun find() call
        :param **kwargs:    Named parameters to be passed to the Shotgun find() call
        :returns:           A unique task id representing this request. 
        """
        return self._add_task(self._task_execute_find, 
                              priority = ShotgunDataRetriever._SG_FIND_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_update(self, *args, **kwargs):
        """
        Execute a Shotgun update call asyncronously

        This method takes the same parameters as the Shotgun update() call.

        :param *args:       args to be passed to the Shotgun update() call
        :param **kwargs:    Named parameters to be passed to the Shotgun update() call
        :returns:           A unique task id representing this request.
        """
        return self._add_task(self._task_execute_update, 
                              priority = ShotgunDataRetriever._SG_UPDATE_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_create(self, *args, **kwargs):
        """
        Execute a Shotgun create call asyncronously

        This method takes the same parameters as the Shotgun create() call.

        :param *args:       args to be passed to the Shotgun create() call
        :param **kwargs:    Named parameters to be passed to the Shotgun create() call
        :returns:           A unique task id representing this request.
        """
        return self._add_task(self._task_execute_create, 
                              priority = ShotgunDataRetriever._SG_CREATE_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_delete(self, *args, **kwargs):
        """
        Execute a Shotgun delete call asyncronously

        This method takes the same parameters as the Shotgun delete() call.

        :param *args:       args to be passed to the Shotgun delete() call
        :param **kwargs:    Named parameters to be passed to the Shotgun delete() call
        :returns:           A unique task id representing this request.
        """
        return self._add_task(self._task_execute_delete, 
                              priority = ShotgunDataRetriever._SG_DELETE_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_method(self, method, *args, **kwargs):
        """
        Executes a generic execution of a method asyncronously.  This is pretty much a
        wrapper for executing a task through the BackgroundTaskManager.

        The specified method will be called with the form

        > method(sg, data) 

        Where sg is a shotgun API instance. Data is typically
        a dictionary with specific data that the method needs.

        :param method:      The method that should be executed.
        :param *args:       args to be passed to the method
        :param **kwargs:    Named parameters to be passed to the method
        :returns:           A unique task id representing this request.
        """
        # note that as the 'task' is actually going to call through to another method, we
        # encode the method name, args and kwargs in the task's kwargs dictionary as this
        # keeps them nicely encapsulated.
        task_kwargs = {"method":method, "method_args":args, "method_kwargs":kwargs}
        return self._add_task(self._task_execute_method, 
                              priority = ShotgunDataRetriever._EXECUTE_METHOD_PRIORITY,
                              task_kwargs = task_kwargs)

    def _add_task(self, task_cb, priority, task_args=None, task_kwargs=None):
        """
        Simplified wrapper to add a task to the task manager.  All tasks get added into
        the same group (self._bg_tasks_group) and the returned task_id is case to a string
        to retain backwards compatibility (it used to return a uuid string).

        :param task_cb:     The function to execute for the task
        :param priority:    The priority the task should be run with
        :param task_args:   Arguments that should be passed to the task callback
        :param task_kwargs: Named arguments that should be passed to the task callback
        :returns:           String representation of the task id
        :raises:            TankError if there is no task manager available to add the task to!
        """
        if not self._task_manager:
            raise TankError("Data retriever does not have a task manager to add the task to!")

        task_id = self._task_manager.add_task(task_cb, 
                                              priority, 
                                              group = self._bg_tasks_group,
                                              task_args = task_args,
                                              task_kwargs = task_kwargs)
        return str(task_id)


    def request_thumbnail(self, url, entity_type, entity_id, field, load_image=False):
        """
        Downloads a thumbnail form Shotgun asyncronously or returns the cached thumbnail 
        if found.  Optionally loads the thumbnail into a QImage.

        :param url:         The thumbnail url string that is associated with this thumbnail. This is
                            the field value as returned by a Shotgun query.
        :param entity_type: Shotgun entity type with which the thumb is associated.
        :param entity_id:   Shotgun entity id with which the thumb is associated.
        :param field:       Thumbnail field. Normally 'image' but could also for example be a deep 
                            link field such as 'sg_sequence.Sequence.image'
        :param load_image:  If set to True, the return data structure will contain a QImage object 
                            with the image data loaded.

        :returns:           A unique task id representing this request.
        """
        if not self._task_manager:
            return

        # always add check for thumbnail already downloaded:
        check_task_id = self._task_manager.add_task(self._task_check_thumbnail,
                                                    priority = ShotgunDataRetriever._CHECK_THUMB_PRIORITY,
                                                    group = self._bg_tasks_group,
                                                    task_kwargs = {"url":url, 
                                                                   "load_image":load_image})

        # add download thumbnail task
        dl_task_id = self._task_manager.add_task(self._task_download_thumbnail,
                                                 upstream_task_ids = [check_task_id],
                                                 priority = ShotgunDataRetriever._DOWNLOAD_THUMB_PRIORITY,
                                                 group = self._bg_tasks_group,
                                                 task_kwargs = {"url":url,
                                                                "entity_type":entity_type, 
                                                                "entity_id":entity_id,
                                                                "field":field,
                                                                "load_image":load_image})

        # all results for requesting a thumbnail should be returned with the same id so use
        # a mapping to track the 'primary' task id:
        self._thumb_task_id_map[dl_task_id] = check_task_id

        return str(check_task_id)



    # ------------------------------------------------------------------------------------------------
    # Background task management and methods

    def _task_get_schema(self, project_id):
        """
        Method that gets executed in a background task/thread to retrieve the fields
        and types schema from Shotgun

        :param project_id:  The id of the project to query the schema for or None to 
                            retrieve for all projects
        :returns:           Dictionary containing the 'action' together with the schema 
                            fields and types
        """
        if project_id is not None:
            project = {"type": "Project", "id": project_id}
        else:
            project = None

        # read in details about all fields
        sg_field_schema = self._shotgun_connection.schema_read(project)

        # and read in details about all entity types
        sg_type_schema = self._shotgun_connection.schema_entity_read(project)

        # need to wrap it in a dict not to confuse pyqt's signals and type system
        return {"action":"schema", "fields":sg_field_schema, "types":sg_type_schema}

    def _task_execute_find(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        find query

        :param *args:       Unnamed arguments to be passed to the find() call
        :param **kwargs:    Named arguments to be passed to the find() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the find() call
        """
        sg_res = self._shotgun_connection.find(*args, **kwargs)
        return {"action":"find", "sg_result":sg_res}

    def _task_execute_update(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        update call

        :param *args:       Unnamed arguments to be passed to the update() call
        :param **kwargs:    Named arguments to be passed to the update() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the update() call
        """
        sg_res = self._shotgun_connection.update(*args, **kwargs)
        return {"action":"update", "sg_result":sg_res}

    def _task_execute_create(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        create call

        :param *args:       Unnamed arguments to be passed to the create() call
        :param **kwargs:    Named arguments to be passed to the create() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the create() call
        """
        sg_res = self._shotgun_connection.create(*args, **kwargs)
        return {"action":"create", "sg_result":sg_res}

    def _task_execute_delete(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        delete call

        :param *args:       Unnamed arguments to be passed to the delete() call
        :param **kwargs:    Named arguments to be passed to the delete() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the delete() call
        """
        sg_res = self._shotgun_connection.delete(*args, **kwargs)
        return {"action":"delete", "sg_result":sg_res}

    def _task_execute_method(self, method, method_args, method_kwargs):
        """
        Method that gets executed in a background task/thread to execute a method
        with a thread-specific shotgun connection.

        :param method:          The method to be run asyncronously
        :param method_args:     Arguments to be passed to the method
        :param method_kwargs:   Named arguments to be passed to the method 
        :returns:               Dictionary containing the 'action' together with the result
                                returned by the method
        """
        res = method(self._shotgun_connection, *method_args, **method_kwargs)
        return {"action":"method", "result":res}

    def _task_check_thumbnail(self, url, load_image):
        """
        Check to see if a thumbnail exists for the specified url.  If it does then it is returned.

        :param url:         The url to return the cached path for
        :param load_image:  If True then if the thumbnail is found in the cache then the file will 
                            be loaded into a QImage
        :returns:           A dictionary containing the cached path for the specified url and a QImage
                            if load_image is True and the thumbnail exists in the cache.
        """
        # first look up the path in the cache:
        thumb_path = ShotgunDataRetriever._get_thumbnail_path(url, self._bundle)
        thumb_image = None
        if thumb_path and os.path.exists(thumb_path):
            if load_image:
                # load the thumbnail into a QImage:
                thumb_image = QtGui.QImage()
                thumb_image.load(thumb_path)
        else:
            thumb_path = None

        return {"action":"check_thumbnail", "thumb_path":thumb_path, "image":thumb_image}

    def _task_download_thumbnail(self, thumb_path, url, entity_type, entity_id, field, load_image, **kwargs):
        """
        Download the thumbnail for the specified entity type, id and field.  This downloads the
        thumbnail into the thumbnail cache directory and returns the cached path.

        If thumb_path already contains a path then this method does nothing and just returns the path 
        without further checking/work.

        :param thumb_path:  Path to an existing thumbnail or None.
        :param url:         The url for the thumbnail which may or may not still be valid!
        :param entity_type: Type of the entity to retrieve the thumbnail for
        :param entity_id:   Id of the entity to retrieve the thumbnail for
        :param field:       The field on the entity that holds the url for the thumbnail to retrieve
        :param load_image:  If True then if the thumbnail is downloaded from Shotgun then the file will 
                            be loaded into a QImage
        :returns:           A dictionary containing the cached path for the specified url and a QImage
                            if load_image is True and the thumbnail exists in the cache.
        """
        if thumb_path:
            # no need to do anything as the thumbnail was previously
            # found when we ran the check!
            return {}

        # download the actual thumbnail. Because of S3, the url
        # may have expired - in that case fall back, get a fresh url
        # from shotgun and try again
        thumb_path = self._get_thumbnail_path(url, self._bundle)
        self._bundle.ensure_folder_exists(os.path.dirname(thumb_path))

        # there may be a case where another process has alrady downloaded the thumbnail for us, so 
        # make sure that we aren't doing any extra work :)
        if not os.path.exists(thumb_path):

            # try to download based on the path we have
            try:
                sgtk.util.download_url(self._shotgun_connection, url, thumb_path)
            except TankError, e:
                # Note: Unfortunately, the download_url will re-cast 
                # all exceptions into tankerrors.
                # get a fresh url from shotgun and try again
                sg_data = self._shotgun_connection.find_one(entity_type, [["id", "is", entity_id]], [field])

                if sg_data is None or sg_data.get(field) is None:
                    # no thumbnail! This is possible if the thumb has changed
                    # while we were queueing it for download.
                    # indicate the fact that the thumbnail no longer exists on the server
                    # by setting the path to None
                    thumb_path = None

                else:
                    # download from sg
                    url = sg_data[field]
                    sgtk.util.download_url(self._shotgun_connection, url, thumb_path)

            if thumb_path:
                # now we have a thumbnail on disk, either via the direct download, or via the 
                # url-fresh-then-download approach.  Because the file is downloaded with user-only 
                # permissions we have to modify the permissions so that it's writeable by others
                old_umask = os.umask(0)
                try:
                    os.chmod(thumb_path, 0666)
                finally:
                    os.umask(old_umask)

        # finally, see if we should also load in the image
        thumb_image = None
        if thumb_path and os.path.exists(thumb_path):
            if load_image:
                # load the thumbnail into a QImage:
                thumb_image = QtGui.QImage()
                thumb_image.load(thumb_path)
        else:
            thumb_path = None

        return {"action":"download_thumbnail", "thumb_path":thumb_path, "image":thumb_image}

    def _on_task_completed(self, task_id, group, result):
        """
        Slot triggered when a task is completed.

        :param task_id: The id of the task that has completed
        :param group:   The group the task belongs to
        :param result:  The task result
        """
        if group != self._bg_tasks_group:
            # ignore - it isn't our task!
            return

        action = result.get("action")
        if action in ["find", "create", "delete", "update"]:
            self.work_completed.emit(str(task_id), action, {"sg":result["sg_result"]})
        elif action == "schema":
            self.work_completed.emit(str(task_id), "schema", {"fields":result["fields"], "types":result["types"]})
        elif action == "method":
            self.work_completed.emit(str(task_id), "method", {"return_value":result["result"]})
        elif action == "check_thumbnail":
            path = result.get("thumb_path", "")
            if path:
                # check found a thumbnail!
                self.work_completed.emit(str(task_id), "find", {"thumb_path": path, "image":result["image"]})
        elif action == "download_thumbnail":
            # look up the primary thumbnail task id in the map:
            thumb_task_id = self._thumb_task_id_map.get(task_id)
            if thumb_task_id is not None:
                del self._thumb_task_id_map[task_id]
                self.work_completed.emit(str(thumb_task_id), 
                                         "find", 
                                         {"thumb_path": result["thumb_path"], "image":result["image"]})

    def _on_task_failed(self, task_id, group, msg, tb):
        """
        Slot triggered when a task fails for some reason

        :param task_id: The id of the task that failed
        :param msg:     The error/exception message for the failed task
        :param tb:      The stack trace of the exception raised by the failed task
        """
        if group != self._bg_tasks_group:
            # ignore - it isn't our task!
            return

        # remap task ids for thumbnails:
        if task_id in self._thumb_task_id_map:
            orig_task_id = task_id
            task_id = self._thumb_task_id_map[task_id]
            del self._thumb_task_id_map[orig_task_id]

        # emit failure signal:
        self.work_failure.emit(str(task_id), msg)

