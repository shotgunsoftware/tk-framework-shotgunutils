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
import os.path
import sgtk
from sets import Set
import tempfile

from sgtk.platform.qt import QtCore

from sgtk import TankError

from .util import sanitize_qt
from ..shotgun_data import ShotgunDataRetriever

class NoteCreator(QtCore.QObject):
    # Emitted when a Note or Reply entity is created. The
    # entity type as a string and id as an int will be
    # provided.
    #
    # dict(entity_type="Note", id=1234)
    #
    # userdata (bytes) passed in to the `submit` call
    entity_created = QtCore.Signal(object, object)

    def __init__(self):
        QtCore.QObject.__init__(self)

        # set up some handy references
        self._bundle = sgtk.platform.current_bundle()
        
        # state variables
        self._processing_ids = dict()
        self._cleanup_after_upload = []

        # create a separate sg data handler for submission
        self.__sg_data_retriever = None
        self._outgoing_tasks = None

    ###########################################################################
    # public interface

    def destroy(self):
        """
        disconnect and prepare for this object
        to be garbage collected
        """
        if self.__sg_data_retriever:
            self.__sg_data_retriever.work_completed.disconnect(self.__on_worker_signal)
            self.__sg_data_retriever.work_failure.disconnect(self.__on_worker_failure)
            self.__sg_data_retriever.stop()
            self.__sg_data_retriever = None

    def set_bg_task_manager(self, task_manager):
        """
        Specify the background task manager to use to pull
        data in the background. Data calls
        to Shotgun will be dispatched via this object.
        
        :param task_manager: Background task manager to use
        :type task_manager: :class:`~tk-framework-shotgunutils:task_manager.BackgroundTaskManager` 
        """
        self.__sg_data_retriever = ShotgunDataRetriever(self, 
                                                                     bg_task_manager=task_manager)

        self.__sg_data_retriever.start()
        self.__sg_data_retriever.work_completed.connect(self.__on_worker_signal)
        self.__sg_data_retriever.work_failure.connect(self.__on_worker_failure)

    def set_outgoing_task_tracker(self, tasks):
        self._outgoing_tasks = tasks

    def submit(self, data, userdata):
        """
        Creates items in Shotgun.
        """

        # ask the data retriever to execute an async callback
        if self.__sg_data_retriever:
            task_id = self.__sg_data_retriever.execute_method(self._async_submit, data)
            self._processing_ids[task_id] = userdata
            if self._outgoing_tasks:
                self._outgoing_tasks.add(task_id)
        else:
            raise TankError("Please associate this class with a background task processor.")

    ###########################################################################
    # internal methods

    def _async_submit(self, sg, data):
        """
        Actual payload for creating things in shotgun.
        Note: This runs in a different thread and cannot access
        any QT UI components.
        
        :param sg: Shotgun instance
        :param data: data dictionary passed in from _submit()
        """
        entity_link = data["entity"]
        if entity_link["type"] == "Note":
            # we are replying to a note - create a reply
            return self._async_submit_reply(sg, data)
        else:
            # create a new note
            return self._async_submit_note(sg, data)
        
    def _async_submit_reply(self, sg, data):
        """
        Provides functionality for creating a new Reply entity
        asynchronously by providing a signature that is friendly
        for use with :class:`~tk-framework-shotgunutils:shotgun_data.ShotgunDataRetriever`.

        :param sg:      A Shotgun API handle.
        :param data:    A dictionary as created by :meth:`NoteInputWidget._submit`

        :returns:       A Shotgun entity dictionary for the Reply that was created.
        """
        note_link = data["entity"]
        
        # this is an entity - so create a note and link it
        sg_reply_data = sg.create("Reply", {"content": data["text"], "entity": note_link})

        # if there are any recipients, make sure they are added to the note
        # but as CCs
        if data["recipient_links"]:
            existing_to = sg.find_one("Note", 
                                      [["id", "is", note_link["id"]]], 
                                      ["addressings_cc"]).get("addressings_cc")
            
            updated_links = data["recipient_links"] + existing_to 
            
            sg.update("Note", 
                      note_link["id"], 
                      {"addressings_cc": updated_links})
            
        self.__upload_thumbnail(note_link, sg, data)
        self.__upload_attachments(note_link, sg, data)

        return sg_reply_data
        
    def _async_submit_note(self, sg, data):
        """
        Provides functionality for creating a new Note entity
        asynchronously by providing a signature that is friendly
        for use with :class:`~tk-framework-shotgunutils:shotgun_data.ShotgunDataRetriever`.

        :param sg:      A Shotgun API handle.
        :param data:    A dictionary as created by :meth:`NoteInputWidget._submit`

        :returns:       A Shotgun entity dictionary for the Note that was created.
        """
        # note - no logging in here, as I am not sure how all
        # engines currently react to log_debug() async.

        # There is lots of business logic hard coded into Shotgun
        # for now, attempt to mimic this logic in this method.

        # Extend out the link dictionary according to specific logic:

        # - if link is a version, then also include the item the version
        #   is linked to and the version's task

        # - if a link is a task, find its link and use that as the main link.
        #   set the task to be linked up to the tasks field.

        # - if link is a user, group or script then address the note TO
        #   that user rather associating the user with the note.

        # - if data["project"] is None (which typically happens when running in a null-context
        #   environment, attempt to pick up the project from the associated entity.

        # first establish defaults
        project = data["project"]
        addressings_to = data["recipient_links"]
        note_links = []
        note_tasks = []

        # step 1 - business logic for linking
        # now apply specific logic
        entity_link = data["entity"]
        # as we are retrieving data for the associated
        # entity, also pull down the associated project
        entity_project_link = None

        if entity_link["type"] in ["HumanUser", "ApiUser", "Group"]:
            # for users, scripts and groups,
            # address the note TO the entity
            addressings_to.append(entity_link)

            # Also link the note to the user. This is to get the
            # activity stream logic to work.
            # note that because we don't have the display name for the entity,
            # we need to retrieve this
            sg_entity = sg.find_one(entity_link["type"],
                                    [["id", "is", entity_link["id"] ]],
                                    ["cached_display_name"])
            note_links += [{"id": entity_link["id"],
                           "type": entity_link["type"],
                           "name": sg_entity["cached_display_name"] }]


        elif entity_link["type"] == "Version":
            # if we are adding a note to a version, link it with the version
            # and the entity that the version is linked to.
            # if the version has a task, link the task to the note too.
            sg_version = sg.find_one(
                "Version",
                [["id", "is", entity_link["id"] ]],
                ["entity", "sg_task", "cached_display_name", "project"]
            )

            # first make a std sg link to the current entity - this to ensure we have a name key present
            note_links += [{"id": entity_link["id"],
                            "type": entity_link["type"],
                            "name": sg_version["cached_display_name"] }]

            # and now add the linked entity, if there is one
            if sg_version["entity"]:
                note_links += [sg_version["entity"]]

            if sg_version["sg_task"]:
                note_tasks += [sg_version["sg_task"]]

            # If we weren't able to get a project ID from the context, then
            # we know we can get it from the Version entity itself.
            if not project and sg_version["project"]:
                project = sg_version["project"]

        elif entity_link["type"] == "Task":
            # if we are adding a note to a task, link the note to the entity that is linked to the
            # task. The link the task to the note via the task link.
            sg_task = sg.find_one(
                "Task",
                [["id", "is", entity_link["id"]]],
                ["entity", "project"]
            )

            if sg_task["entity"]:
                # there is an entity link from this task
                note_links += [sg_task["entity"]]

            # If we didn't get a project ID from the context, then we know we
            # can get one from the Task entity.
            if not project and sg_task["project"]:
                project = sg_task["project"]

            # lastly, link the note's task link to this task
            note_tasks += [entity_link]

        else:
            # no special logic. Just link the note to the current entity.
            # note that because we don't have the display name for the entity,
            # we need to retrieve this
            sg_entity = sg.find_one(entity_link["type"],
                                    [["id", "is", entity_link["id"] ]],
                                    ["cached_display_name", "project"])
            note_links += [{"id": entity_link["id"],
                           "type": entity_link["type"],
                           "name": sg_entity["cached_display_name"] }]

            # store associated project for use later
            if entity_link["type"] == "Project":
                # note on a project
                entity_project_link = entity_link
            else:
                # note - some entity types may not have a project field
                # so don't assume the key exists.
                entity_project_link = sg_entity.get("project")


        # step 2 - generate the subject line. The following
        # convention exists for this:
        #
        # Tomoko's Note on aaa_00010_F004_C003_0228F8_v000 and aaa_00010
        # First name's Note on [list of entities]
        current_user = sgtk.util.get_current_user(self._bundle.sgtk)
        if current_user:
            if current_user.get("firstname"):
                # not all core versions support firstname,
                # so double check that we have that key
                first_name = current_user.get("firstname")
            else:
                # compatibility with older cores
                # for older cores, just split on the first space
                # Sorry Mary Jane Watson!
                first_name = current_user.get("name").split(" ")[0]

            title = "%s's Note" % first_name
        else:
            title = "Unknown user's Note"

        if len(note_links) > 0:
            note_names = [x["name"] for x in note_links]
            title += " on %s" % (", ".join(note_names))

        # step 3 - handle project gracefully
        if project is None:
            # attempt to pull it from the entity link
            if entity_project_link is None:
                # there is no associated project - likely this is a note
                # on a non-project entity created in the site ctx
                raise TankError(
                    "Cannot determine the project to associate the note with. "
                    "This usually happens when you submit note on a non-project "
                    "entity while running Toolkit in a Site context."
                )
            else:
                project = entity_project_link


        # this is an entity - so create a note and link it
        sg_note_data = sg.create("Note", {"content": data["text"],
                                          "subject": title,
                                          "project": project,
                                          "addressings_to": addressings_to,
                                          "note_links": note_links,
                                          "tasks": note_tasks })

        self.__upload_thumbnail(sg_note_data, sg, data)
        self.__upload_attachments(sg_note_data, sg, data)

        return sg_note_data

    def __upload_attachments(self, parent_entity, sg, data):
        """
        Uploads any generic file attachments to Shotgun, parenting
        them to the Note entity.

        :param parent_entity:   The Note entity to attach the files to in SG.
        :param sg:              A Shotgun API handle.
        :param data:            The data dict containing an "attachments" key
                                housing a list of file paths to attach.
        """
        for file_path in data.get("attachments", []):
            if os.path.exists(file_path):
                self.__upload_file(file_path, parent_entity, sg)
            else:
                self._bundle.log_warning(
                    "File does not exist and will not be uploaded: %s" % file_path
                )

    def __upload_file(self, file_path, parent_entity, sg):
        """
        Uploads any generic file attachments to Shotgun, parenting
        them to the Note entity.

        :param file_path:       The path to the file to upload to SG.
        :param parent_entity:   The Note entity to attach the files to in SG.
        :param sg:              A Shotgun API handle.
        """
        self._bundle.log_debug(
            "Uploading attachments (%s bytes)..." % os.path.getsize(file_path)
        )
        try:
            sg.upload(parent_entity["type"], parent_entity["id"], str(file_path))
            self._bundle.log_debug("Upload complete!")
        finally:
            if file_path in self._cleanup_after_upload:
                self._bundle.log_debug("Cleanup requested post upload: %s" % file_path)
                try:
                    os.remove(file_path)
                except Exception:
                    self._bundle.log_warning("Unable to remove file: %s" % file_path)

    def __upload_thumbnail(self, parent_entity, sg, data):
        
        if data["pixmap"]:
            
            # save it out to a temp file so we can upload it
            png_path = tempfile.NamedTemporaryFile(suffix=".png",
                                                   prefix="screencapture_",
                                                   delete=False).name

            data["pixmap"].save(png_path)
            
            # create file entity and upload file
            if os.path.exists(png_path):
                self.__upload_file(png_path, parent_entity, sg)           
                os.remove(png_path)

    def __on_worker_failure(self, uid, msg):
        """
        Asynchronous callback - the worker thread errored.
        
        :param uid: Unique id for request that failed
        :param msg: Error message
        """
        uid = sanitize_qt(uid) # qstring on pyqt, str on pyside
        msg = sanitize_qt(msg)

        if uid in self._processing_ids:
            self._bundle.log_error("Could not create note/reply: %s" % msg)
            full_msg = "Could not submit note update: %s" % msg
            QtGui.QMessageBox.critical(None, "Shotgun Error", msg)
            if self._outgoing_tasks and self._outgoing_tasks.has(uid):
                self._outgoing_tasks.remove(uid)
            self._processing_ids.remove(uid)

    def __on_worker_signal(self, uid, request_type, data):
        """
        Signaled whenever the worker completes something.
        This method will dispatch the work to different methods
        depending on what async task has completed.

        :param uid: Unique id for request
        :param request_type: String identifying the request class
        :param data: the data that was returned 
        """
        uid = sanitize_qt(uid) # qstring on pyqt, str on pyside
        data = sanitize_qt(data)

        if uid in self._processing_ids:
            # all done!
            self._bundle.log_debug("Update call complete! Return data: %s" % data)
            self.entity_created.emit(data["return_value"], self._processing_ids[uid])
            if self._outgoing_tasks and self._outgoing_tasks.has(uid):
                self._outgoing_tasks.remove(uid)
            del self._processing_ids[uid]
