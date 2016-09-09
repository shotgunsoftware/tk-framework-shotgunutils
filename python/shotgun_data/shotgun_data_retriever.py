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
from sgtk.platform.qt import QtCore, QtGui
from sgtk import TankError

class ShotgunDataRetriever(QtCore.QObject):
    """
    Asynchronous data retriever class which can be used to retrieve data and 
    thumbnails from Shotgun and from disk thumbnail cache. Uses the 
    :class:`~task_manager.BackgroundTaskManager` to run tasks in background 
    threads and emits signals when each query has either completed or failed.
    Requests are queued up using for example the :meth:`execute_find()` and 
    :meth:`request_thumbnail()` methods.

    Requests are executed in the following priority order:

    - First any thumbnails that are already cached on disk are handled.
    - Next, shotgun find() queries are handled.
    - Lastly thumbnail downloads are handled.
    
    The thread will emit work_completed and work_failure signals when 
    tasks are completed (or fail). The :meth:`clear()` method will 
    clear the current queue. The currently processing item will finish 
    processing and may send out signals even after a clear. Make sure you 
    call the :meth:`stop()` method prior to destruction in order for the 
    system to gracefully shut down.    
    
    :signal work_completed(uid, request_type, data_dict): Emitted every time 
        a requested task has completed. ``uid`` is a unique id which matches 
        the unique id returned by the corresponding request call. 
        ``request_type`` is a string denoting the type of request this 
        event is associated with. ``data_dict`` is a dictionary containing 
        the payload of the request. It will be different depending on what 
        type of request it is. 
    
    :signal work_failure(uid, error_message): Emitted every time a requested 
        task has failed. ``uid`` is a unique id which matches the unique 
        id returned by the corresponding request call.
    
    
    """
    
    # syntax: work_completed(uid, request_type, data_dict)
    # - uid is a unique id which matches the unique id
    #   returned by the corresponding request call.
    #
    # - request_type is a string denoting the type of request
    #   this event is associated with. It can be either "find"
    #   "find_one", "update", "create", "delete", "schema", "expand_nav"
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


    # Individual task priorities used when adding tasks to the task manager
    # Note: a higher value means more important and will get run before lower 
    # priority tasks

    # Attachment checks and downloads are more important than thumbnails,
    # as having access to that data will often be required instead of as
    # a nice-to-have. As a result, this gets a bit more priority.
    _CHECK_ATTACHMENT_PRIORITY      = 55

    # thumbnail checks are local disk checks and very fast.  These 
    # are always carried out before any shotgun calls
    _CHECK_THUMB_PRIORITY           = 50

    # the shotgun schema is often useful to have as early on as possible,
    # sometimes other shotgun operations also need the shotgun schema
    # (and it's typically also cached) so this call has a higher priority
    # than the rest of the shotgun calls
    _SG_DOWNLOAD_SCHEMA_PRIORITY    = 40
    
    # next the priority for any other Shotgun calls (e.g. find, create, 
    # update, delete, etc.)
    _SG_CALL_PRIORITY               = 30

    # Attachment downloads are not necessarily fast (but might be), but unlike
    # thumbnails they will be required for functionality in the calling code.
    # As such, we'll give these downloads a bit more priority.
    _DOWNLOAD_ATTACHMENT_PRIORITY   = 25

    # thumbnails are downloaded last as they are considered low-priority 
    # and can take a relatively significant amount of time
    _DOWNLOAD_THUMB_PRIORITY        = 20


    def __init__(self, parent=None, sg=None, bg_task_manager=None):
        """
        :param parent: Parent object
        :type parent: :class:`~PySide.QtGui.QWidget`
        :param sg: Optional Shotgun API Instance
        :param bg_task_manager: Optional Task manager
        :class bg_task_manager: :class:`~task_manager.BackgroundTaskManager`
        """
        QtCore.QObject.__init__(self, parent)
        self._bundle = sgtk.platform.current_bundle()

        # set up the background task manager:
        task_manager = self._bundle.import_module("task_manager")
        self._task_manager = bg_task_manager or task_manager.BackgroundTaskManager(parent=self, max_threads=1)
        self._owns_task_manager = (bg_task_manager is None)
        self._bg_tasks_group = self._task_manager.next_group_id()
        self._task_manager.task_completed.connect(self._on_task_completed)
        self._task_manager.task_failed.connect(self._on_task_failed)

        self._thumb_task_id_map = {}
        self._attachment_task_id_map = {}


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
            sgtk.util.download_url(bundle.shotgun, url, path_to_cached_thumb)

            # modify the permissions of the file so it's writeable by others
            old_umask = os.umask(0)
            try:
                os.chmod(path_to_cached_thumb, 0666)
            finally:
                os.umask(old_umask)

        return path_to_cached_thumb



    def start(self):
        """
        Start the retriever thread.

        :raises:    TankError if there is no :class:`~task_manager.BackgroundTaskManager` associated with this instance
        """
        if not self._task_manager:
            raise TankError("Unable to start the ShotgunDataRetriever as it has no BackgroundTaskManager!")
        self._task_manager.start_processing()

    def stop(self):
        """
        Gracefully stop the receiver.

        Once stop() has been called, the object needs to be discarded.
        This is a blocking call. It will synchronously wait
        until any potential currently processing item has completed.

        Note that once stopped the data retriever can't be restarted as the handle to the
        :class:`~task_manager.BackgroundTaskManager` instance is released.
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

            # make sure we don't get exceptions trying to disconnect if the
            # signals were never connected or somehow disconnected externally.
            try:
                self._task_manager.task_completed.disconnect(self._on_task_completed)
            except (TypeError, RuntimeError), e:  # was never connected
                self._bundle.log_warning(
                    "Could not disconnect '_on_task_completed' slot from the "
                    "task manager's 'task_completed' signal: %s" % (e,)
                )
            try:
                self._task_manager.task_failed.disconnect(self._on_task_failed)
            except (TypeError, RuntimeError), e:  # was never connected
                self._bundle.log_debug(
                    "Could not disconnect '_on_task_failed' slot from the "
                    "task manager's 'task_failed' signal: %s" % (e,)
                )

            self._task_manager = None

    def clear(self):
        """
        Clears the queue.

        Any currently processing item will complete without interruption, and signals will be
        sent out for these items.
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
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.
        """
        return self._add_task(self._task_get_schema, 
                              priority = ShotgunDataRetriever._SG_DOWNLOAD_SCHEMA_PRIORITY,
                              task_kwargs = {"project_id":project_id})

    def execute_find(self, *args, **kwargs):
        """
        Executes a Shotgun find query asynchronously.

        This method takes the same parameters as the Shotgun find() call.

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param ``*args``:       args to be passed to the Shotgun find() call
        :param ``**kwargs``:    Named parameters to be passed to the Shotgun find() call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.

        """
        return self._add_task(self._task_execute_find, 
                              priority = ShotgunDataRetriever._SG_CALL_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_find_one(self, *args, **kwargs):
        """
        Executes a Shotgun find_one query asynchronously.

        This method takes the same parameters as the Shotgun find_one() call.

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param ``*args``:       args to be passed to the Shotgun find_one() call
        :param ``**kwargs``:    Named parameters to be passed to the Shotgun find_one() call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.

        """
        return self._add_task(self._task_execute_find_one, 
                              priority = ShotgunDataRetriever._SG_CALL_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_update(self, *args, **kwargs):
        """
        Execute a Shotgun update call asynchronously

        This method takes the same parameters as the Shotgun update() call.

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param ``*args``:       args to be passed to the Shotgun update() call
        :param ``**kwargs``:    Named parameters to be passed to the Shotgun update() call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.        
        """
        return self._add_task(self._task_execute_update, 
                              priority = ShotgunDataRetriever._SG_CALL_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_create(self, *args, **kwargs):
        """
        Execute a Shotgun create call asynchronously

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        This method takes the same parameters as the Shotgun create() call.

        :param ``*args``:       args to be passed to the Shotgun create() call
        :param ``**kwargs``:    Named parameters to be passed to the Shotgun create() call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.        
        """
        return self._add_task(self._task_execute_create, 
                              priority = ShotgunDataRetriever._SG_CALL_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_delete(self, *args, **kwargs):
        """
        Execute a Shotgun delete call asynchronously

        This method takes the same parameters as the Shotgun delete() call.

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param ``*args``:       args to be passed to the Shotgun delete() call
        :param ``**kwargs``:    Named parameters to be passed to the Shotgun delete() call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.        
        """
        return self._add_task(self._task_execute_delete, 
                              priority = ShotgunDataRetriever._SG_CALL_PRIORITY,
                              task_args = args,
                              task_kwargs = kwargs)

    def execute_method(self, method, *args, **kwargs):
        """
        Executes a generic execution of a method asynchronously.  This is pretty much a
        wrapper for executing a task through the :class:`~task_manager.BackgroundTaskManager`.

        The specified method will be called on the following form::

            method(sg, data) 

        Where sg is a shotgun API instance. Data is typically
        a dictionary with specific data that the method needs.
        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param method:      The method that should be executed.
        :param ``*args``:       args to be passed to the method
        :param ``**kwargs``:    Named parameters to be passed to the method
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.        
        """
        # note that as the 'task' is actually going to call through to another method, we
        # encode the method name, args and kwargs in the task's kwargs dictionary as this
        # keeps them nicely encapsulated.
        task_kwargs = {"method":method, "method_args":args, "method_kwargs":kwargs}
        return self._add_task(self._task_execute_method, 
                              priority = ShotgunDataRetriever._SG_CALL_PRIORITY,
                              task_kwargs = task_kwargs)

    def execute_nav_expand(self, *args, **kwargs):
        """
        Executes a Shotgun ``nav_expand`` query asynchronously.

        See the python api documentation here:
            https://github.com/shotgunsoftware/python-api/wiki

        This method takes the same parameters as the Shotgun ``nav_expand()`` call.

        The query will be queued up and once processed, either a
        work_completed or work_failure signal will be emitted.

        :param ``*args``: args to be passed to the Shotgun ``nav_expand()`` call
        :param ``**kwargs``: Named parameters to be passed to the Shotgun ``nav_expand()`` call
        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.
        """
        return self._add_task(
            self._task_execute_nav_expand,
            priority=ShotgunDataRetriever._SG_CALL_PRIORITY,
            task_args=args,
            task_kwargs=kwargs
        )

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

    def request_attachment(self, attachment_entity):
        """
        Downloads an attachment from Shotgun asynchronously or returns a cached
        file path if found.

        .. note:: The provided Attachment entity definition must contain, at a
                  minimum, the "this_file" substructure.

        .. code-block:: python

            {
                "id": 597,
                "this_file": {
                    "content_type": "image/png",
                    "id": 597,
                    "link_type": "upload",
                    "name": "test.png",
                    "type": "Attachment",
                    "url": "https://abc.shotgunstudio.com/file_serve/attachment/597"
                },
                "type": "Attachment"
            }

        :param dict attachment_entity: The Attachment entity to download data from.

        :returns: A unique identifier representing this request.
        """
        if not self._task_manager:
            self._bundle.log_warning(
                "No task manager has been associated with this data retriever. "
                "Unable to request attachment."
            )
            return

        # always add check for attachments already downloaded:
        check_task_id = self._task_manager.add_task(
            self._task_check_attachment,
            priority=self._CHECK_ATTACHMENT_PRIORITY,
            group=self._bg_tasks_group,
            task_kwargs=dict(attachment_entity=attachment_entity),
        )

        # Add download thumbnail task.  This is dependent on the check task above and will be passed
        # the returned results from that task in addition to the kwargs specified below.  This allows
        # a task dependency chain to be created with different priorities for the separate tasks.
        dl_task_id = self._task_manager.add_task(
            self._task_download_attachment,
            upstream_task_ids=[check_task_id],
            priority=self._DOWNLOAD_ATTACHMENT_PRIORITY,
            group=self._bg_tasks_group,
            task_kwargs=dict(attachment_entity=attachment_entity),
        )

        # all results for requesting a thumbnail should be returned with the same id so use
        # a mapping to track the 'primary' task id:
        self._attachment_task_id_map[dl_task_id] = check_task_id
        return str(check_task_id)

    def request_thumbnail(self, url, entity_type, entity_id, field, load_image=False):
        """
        Downloads a thumbnail from Shotgun asynchronously or returns a cached thumbnail 
        if found.  Optionally loads the thumbnail into a QImage.

        :param url:         The thumbnail url string that is associated with this thumbnail. This is
                            the field value as returned by a Shotgun query.
        :param entity_type: Shotgun entity type with which the thumb is associated.
        :param entity_id:   Shotgun entity id with which the thumb is associated.
        :param field:       Thumbnail field. Normally 'image' but could also for example be a deep 
                            link field such as ``sg_sequence.Sequence.image``
        :param load_image:  If set to True, the return data structure will contain a QImage object 
                            with the image data loaded.

        :returns: A unique identifier representing this request. This
                  identifier is also part of the payload sent via the
                  work_completed and work_failure signals, making it
                  possible to match them up.
        """
        if not self._task_manager:
            self._bundle.log_warning(
                "No task manager has been associated with this data retriever. "
                "Unable to request thumbnail."
            )
            return

        # always add check for thumbnail already downloaded:
        check_task_id = self._task_manager.add_task(self._task_check_thumbnail,
                                                    priority = self._CHECK_THUMB_PRIORITY,
                                                    group = self._bg_tasks_group,
                                                    task_kwargs = {"url":url, 
                                                                   "load_image":load_image})

        # Add download thumbnail task.  This is dependent on the check task above and will be passed
        # the returned results from that task in addition to the kwargs specified below.  This allows
        # a task dependency chain to be created with different priorities for the separate tasks.
        dl_task_id = self._task_manager.add_task(self._task_download_thumbnail,
                                                 upstream_task_ids = [check_task_id],
                                                 priority = self._DOWNLOAD_THUMB_PRIORITY,
                                                 group = self._bg_tasks_group,
                                                 task_kwargs = {"url":url,
                                                                "entity_type":entity_type, 
                                                                "entity_id":entity_id,
                                                                "field":field,
                                                                "load_image":load_image
                                                                #"thumb_path":<passed from check task>
                                                                #"image":<passed from check task>
                                                                })

        # all results for requesting a thumbnail should be returned with the same id so use
        # a mapping to track the 'primary' task id:
        self._thumb_task_id_map[dl_task_id] = check_task_id

        return str(check_task_id)

    # ------------------------------------------------------------------------------------------------
    # Background task management and methods

    def _download_url(self, file_path, url, entity_type, entity_id, field):
        """
        Downloads a file located at the given url to the provided file path.

        :param str file_path: The target path.
        :param str url: The url location of the file to download.
        :param str entity_type: The Shotgun entity type that the url is
                                associated with. In the event that the
                                provided url has expired, the entity
                                type and id provided will be used to query
                                a fresh url.
        :param int entity_id: The Shotgun entity id that the url is
                              associated with. In the event that the
                              provided url has expired, the entity type and
                              id provided will be used to query a fresh url.
        :param str field: The name of the field that contains the url. If
                          the url needs to be requeried, this field will be
                          where the fresh url is pulled from.
        """
        try:
            sgtk.util.download_url(self._bundle.shotgun, url, file_path)
        except TankError, e:
            sg_data = self._bundle.shotgun.find_one(
                entity_type,
                [["id", "is", entity_id]],
                [field],
            )

            if sg_data is None or sg_data.get(field) is None:
                # This means there's nothing in Shotgun for this field, which
                # means we can't download anything.
                raise IOError(
                    "Field %s does not contain data for %s (id=%s)." % (
                        field,
                        entity_type,
                        entity_id,
                    )
                )
            else:
                url = sg_data[field]
                sgtk.util.download_url(self._bundle.shotgun, url, file_path)

        # now we have a thumbnail on disk, either via the direct download, or via the 
        # url-fresh-then-download approach.  Because the file is downloaded with user-only 
        # permissions we have to modify the permissions so that it's writeable by others
        old_umask = os.umask(0)
        try:
            os.chmod(file_path, 0666)
        finally:
            os.umask(old_umask)

    @staticmethod
    def _get_attachment_path(attachment_entity, bundle):
        """
        Returns the location on disk suitable for an attachment file.

        :param dict attachment_entity: The Attachment entity definition.
        :param bundle: App, Engine or Framework instance

        :returns: Path as a string.
        """
        url = attachment_entity["this_file"]["url"]
        file_name = attachment_entity["this_file"]["name"]

        directory_path = ShotgunDataRetriever._get_thumbnail_path(
            url,
            bundle,
            directory_only=True,
        )

        return os.path.join(directory_path, file_name)

    @staticmethod
    def _get_thumbnail_path(url, bundle, directory_only=False):
        """
        Returns the location on disk suitable for a thumbnail given its url.

        :param str url: Path to a thumbnail
        :param bundle: App, Engine or Framework instance
        :param bool directory_only: Whether to return a directory path or a
                                    full file path. Default is False, which
                                    indicates a full file path, including
                                    file name, will be returned.

        :returns: Path as a string.
        """
        # If we don't have a URL, then we know we don't
        # have a thumbnail to worry about.
        if not url:
            return None

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
        path_chunks = [first_folder, second_folder]

        # If we were only asked to give back a directory path then we can
        # skip building and appending a file name.
        if not directory_only:
            path_chunks.append("%s.jpeg" % hash_str[4:])

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
        sg_field_schema = self._bundle.shotgun.schema_read(project)

        # and read in details about all entity types
        sg_type_schema = self._bundle.shotgun.schema_entity_read(project)

        # need to wrap it in a dict not to confuse pyqt's signals and type system
        return {"action":"schema", "fields":sg_field_schema, "types":sg_type_schema}

    def _task_execute_find(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        find query

        :param ``*args``:       Unnamed arguments to be passed to the find() call
        :param ``**kwargs``:    Named arguments to be passed to the find() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the find() call
        """
        sg_res = self._bundle.shotgun.find(*args, **kwargs)
        return {"action":"find", "sg_result":sg_res}

    def _task_execute_find_one(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        find_one query

        :param ``*args``:       Unnamed arguments to be passed to the find_one() call
        :param ``**kwargs``:    Named arguments to be passed to the find_one() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the find_one() call
        """
        sg_res = self._bundle.shotgun.find_one(*args, **kwargs)
        return {"action":"find_one", "sg_result":sg_res}

    def _task_execute_update(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        update call

        :param ``*args``:       Unnamed arguments to be passed to the update() call
        :param ``**kwargs``:    Named arguments to be passed to the update() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the update() call
        """
        sg_res = self._bundle.shotgun.update(*args, **kwargs)
        return {"action":"update", "sg_result":sg_res}

    def _task_execute_create(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        create call

        :param ``*args``:       Unnamed arguments to be passed to the create() call
        :param ``**kwargs``:    Named arguments to be passed to the create() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the create() call
        """
        sg_res = self._bundle.shotgun.create(*args, **kwargs)
        return {"action":"create", "sg_result":sg_res}

    def _task_execute_delete(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        delete call

        :param ``*args``:       Unnamed arguments to be passed to the delete() call
        :param ``**kwargs``:    Named arguments to be passed to the delete() call 
        :returns:           Dictionary containing the 'action' together with result
                            returned by the delete() call
        """
        sg_res = self._bundle.shotgun.delete(*args, **kwargs)
        return {"action":"delete", "sg_result":sg_res}

    def _task_execute_method(self, method, method_args, method_kwargs):
        """
        Method that gets executed in a background task/thread to execute a method
        with a thread-specific shotgun connection.

        :param method:          The method to be run asynchronously
        :param method_args:     Arguments to be passed to the method
        :param method_kwargs:   Named arguments to be passed to the method 
        :returns:               Dictionary containing the 'action' together with the result
                                returned by the method
        """
        res = method(self._bundle.shotgun, *method_args, **method_kwargs)
        return {"action":"method", "result":res}

    def _task_execute_nav_expand(self, *args, **kwargs):
        """
        Method that gets executed in a background task/thread to perform a Shotgun
        ``nav_expand`` query

        :param ``*args``: Unnamed arguments to be passed to the ``nav_expand()`` call
        :param ``**kwargs``: Named arguments to be passed to the ``nav_expand()`` call
        :returns: Dictionary containing the 'action' together with result
            returned by the find() call
        """
        sg_res = self._bundle.shotgun.nav_expand(*args, **kwargs)
        return {"action":"nav_expand", "nav_result":sg_res}

    def _task_check_attachment(self, attachment_entity):
        """
        Check to see if an attachment file exists for the specified Attachment
        entity.

        :param dict attachment_entity: The Attachment entity definition.

        :returns: A dictionary containing the cached path for the specified
                  Attachment entity.
        """
        url = attachment_entity["this_file"]["url"]
        file_name = attachment_entity["this_file"]["name"]

        data = dict(action="check_attachment", file_path=None)

        if not url or not file_name:
            return data

        file_path = self._get_attachment_path(
            attachment_entity,
            self._bundle,
        )

        if file_path and os.path.exists(file_path):
            data["file_path"] = file_path

        return data

    def _task_check_thumbnail(self, url, load_image):
        """
        Check to see if a thumbnail exists for the specified url.  If it does then it is returned.

        :param url:         The url to return the cached path for
        :param load_image:  If True then if the thumbnail is found in the cache then the file will 
                            be loaded into a QImage
        :returns:           A dictionary containing the cached path for the specified url and a QImage
                            if load_image is True and the thumbnail exists in the cache.
        """
        # If there's no URL then we definitely won't be finding
        # a thumbnail.
        if not url:
            return {"action":"check_thumbnail", "thumb_path":None, "image":None}

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

    def _task_download_attachment(self, file_path, attachment_entity, **kwargs):
        """
        Download the specified attachment. This downloads the file associated with
        the provided Attachment entity into the framework's cache directory structure
        and returns the cached path.

        :param str file_path: The target file path to download to.
        :param dict attachment_entity: The Attachment entity definition.

        :returns: A dictionary containing the cached path for the specified
                  Attachment entity, as well as an action identifier that
                  marks the data as having come from a "download_attachment"
                  task.
        """
        if file_path:
            return {}

        file_path = self._get_attachment_path(attachment_entity, self._bundle)

        if not file_path:
            return {}

        self._bundle.ensure_folder_exists(os.path.dirname(file_path))

        if not os.path.exists(file_path):
            self._bundle.shotgun.download_attachment(
                attachment=attachment_entity,
                file_path=file_path,
            )

        return dict(
            action="download_attachment",
            file_path=file_path,
        )

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

        # If we have no path, then there's no thumbnail that exists.
        if not thumb_path:
            return {}

        self._bundle.ensure_folder_exists(os.path.dirname(thumb_path))

        # there may be a case where another process has alrady downloaded the thumbnail for us, so 
        # make sure that we aren't doing any extra work :)
        if not os.path.exists(thumb_path):

            # try to download based on the path we have
            try:
                self._download_url(thumb_path, url, entity_type, entity_id, field)
            except IOError:
                thumb_path = None

        # finally, see if we should also load in the image
        thumb_image = None
        if thumb_path and os.path.exists(thumb_path):
            if load_image:
                # load the thumbnail into a QImage:
                thumb_image = QtGui.QImage()
                thumb_image.load(thumb_path)
        else:
            thumb_path = None

        return dict(
            action="download_thumbnail",
            thumb_path=thumb_path,
            image=thumb_image,
        )

    def _on_task_completed(self, task_id, group, result):
        """
        Slot triggered when a task is completed.

        :param task_id: The id of the task that has completed
        :param group:   The group the task belongs to
        :param result:  The task result
        """
        if group != self._bg_tasks_group:
            # ignore - it isn't our task! - this slot will recieve signals for tasks started
            # by other objects/instances so we need to make sure we filter them out here
            return

        action = result.get("action")
        if action in ["find", "find_one", "create", "delete", "update"]:
            self.work_completed.emit(str(task_id), action, {"sg":result["sg_result"]})
        elif action == "nav_expand":
            self.work_completed.emit(str(task_id), "nav_expand", {"nav":result["nav_result"]})
        elif action == "schema":
            self.work_completed.emit(str(task_id), "schema", {"fields":result["fields"], "types":result["types"]})
        elif action == "method":
            self.work_completed.emit(str(task_id), "method", {"return_value":result["result"]})
        elif action == "check_thumbnail":
            path = result.get("thumb_path", "")
            if path:
                # check found a thumbnail!
                self.work_completed.emit(
                    str(task_id),
                    "find",
                    dict(
                        thumb_path=path,
                        image=result["image"],
                    ),
                )
        elif action == "download_thumbnail":
            # look up the primary thumbnail task id in the map:
            thumb_task_id = self._thumb_task_id_map.get(task_id)
            if thumb_task_id is not None:
                del self._thumb_task_id_map[task_id]
                self.work_completed.emit(
                    str(thumb_task_id),
                    "find", 
                    dict(
                        thumb_path=result["thumb_path"],
                        image=result["image"],
                    ),
                )
        elif action == "check_attachment":
            path = result.get("file_path", "")
            if path:
                self.work_completed.emit(
                    str(task_id),
                    "find",
                    dict(file_path=path),
                )
        elif action == "download_attachment":
            attachment_task_id = self._attachment_task_id_map.get(task_id)
            if attachment_task_id is not None:
                del self._attachment_task_id_map[task_id]
                self.work_completed.emit(
                    str(attachment_task_id),
                    "find",
                    dict(file_path=result["file_path"]),
                )

    def _on_task_failed(self, task_id, group, msg, tb):
        """
        Slot triggered when a task fails for some reason

        :param task_id: The id of the task that failed
        :param msg:     The error/exception message for the failed task
        :param tb:      The stack trace of the exception raised by the failed task
        """
        if group != self._bg_tasks_group:
            # ignore - it isn't our task - this slot will recieve signals for tasks started
            # by other objects/instances so we need to make sure we filter them out here
            return

        # remap task ids for thumbnails:
        if task_id in self._thumb_task_id_map:
            orig_task_id = task_id
            task_id = self._thumb_task_id_map[task_id]
            del self._thumb_task_id_map[orig_task_id]

        # remap task ids for attachments:
        if task_id in self._attachment_task_id_map:
            orig_task_id = task_id
            task_id = self._attachment_task_id_map[task_id]
            del self._attachment_task_id_map[orig_task_id]

        # emit failure signal:
        self.work_failure.emit(str(task_id), msg)

