# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

# make sure that py25 has access to with statement
from __future__ import with_statement

import os
import sgtk
from sgtk.platform.qt import QtCore, QtGui
import cPickle as pickle

class CachedShotgunSchema(QtCore.QObject):
    """
    Wraps around the shotgun schema and caches it for fast lookups.

    Singleton-style setup, so all access method happen via class methods:
    
    - get_type_display_name     - Display name for entity type
    - get_field_display_name    - Display name for field
    - get_empty_phrase          - String to denote 'no value' for item
    - get_status_display_name   - Display name for status code
    
    This caches the shotgun schema to disk *once* and doesn't check for 
    further updates. If the cache fails to find a value, the technical 
    name rather than the display name is returned, so there is graceful
    fallback.

    :signal schema_loaded: Fires when the schema has been loaded
    :signal status_loaded: Fires when the status list has been loaded
    """
    __instance = None
    schema_loaded = QtCore.Signal()
    status_loaded = QtCore.Signal()

    @classmethod
    def __get_instance(cls):
        """
        Singleton access
        """
        if cls.__instance is None:
            cls.__instance = CachedShotgunSchema()
        return cls.__instance
    
    def __init__(self):
        """
        Constructor
        """
        QtCore.QObject.__init__(self)
        
        self._bundle = sgtk.platform.current_bundle()
        self._field_schema = {}
        self._type_schema = {}
        self.__sg_data_retrievers = []
        self._status_data = {}
        
        self._sg_schema_query_id = None
        self._sg_status_query_id = None
        
        self._schema_cache_path = os.path.join(self._bundle.cache_location, "sg_schema.pickle")
        self._status_cache_path = os.path.join(self._bundle.cache_location, "sg_status.pickle")

        # load cached values from disk
        self._schema_loaded = self._load_cached_schema()
        if self._schema_loaded:
            self.schema_loaded.emit()
        self._status_loaded = self._load_cached_status()
        if self._status_loaded:
            self.status_loaded.emit()

        self._schema_requested = False
        self._status_requested = False        
        
        
    def _load_cached_status(self):
        """
        Load cached status from disk if it exists
        """
        cache_loaded = False
        if os.path.exists(self._status_cache_path):
            try:
                self._bundle.log_debug("Loading cached status from '%s'" % self._status_cache_path)
                with open(self._status_cache_path, "rb") as fh:
                    self._status_data = pickle.load(fh)
                    cache_loaded = True
            except Exception, e:
                self._bundle.log_warning("Could not open cached status "
                                         "file '%s': %s" % (self._status_cache_path, e))       
        return cache_loaded
        
    def _load_cached_schema(self):
        """
        Load cached metaschema from disk if it exists
        
        :returns: true if cache was loaded, false if not
        """
        cache_loaded = False
        if os.path.exists(self._schema_cache_path):
            try:
                self._bundle.log_debug("Loading cached schema from '%s'" % self._schema_cache_path)
                with open(self._schema_cache_path, "rb") as fh:
                    data = pickle.load(fh)
                    self._field_schema = data["field_schema"]
                    self._type_schema = data["type_schema"]
                    cache_loaded = True
            except Exception, e:
                self._bundle.log_warning("Could not open cached schema "
                                         "file '%s': %s" % (self._schema_cache_path, e))
        return cache_loaded            
            
    def _check_schema_refresh(self, entity_type=None, field_name=None):
        """
        Check and potentially trigger a cache refresh
        
        :param entity_type: Shotgun entity type
        :param field_name: Shotgun field name
        """
        
        # TODO: currently, this only checks if there is a full cache in memory
        # or not. Later on, when we have the ability to check the current 
        # metaschema generation via the shotgun API, this can be handled in a 
        # more graceful fashion.
        
        if not self._schema_loaded and not self._schema_requested: 
            # schema is not requested and not loaded.
            # so download it from shotgun!
            sg_project_id = self._bundle.context.project and self._bundle.context.project["id"] or None
                    
            self._bundle.log_debug("Starting to download new metaschema from Shotgun...")
            
            if len(self.__sg_data_retrievers) == 0:
                self._bundle.log_warning("No data retrievers registered with this " 
                                         "schema manager. Cannot load shotgun schema.")
            else:
                # flag that we have submitted a request
                # to avoid flooding of requests.
                self._schema_requested = True
                # pick the first one
                dr = self.__sg_data_retrievers[0]["data_retriever"]
                self._sg_schema_query_id = dr.get_schema(sg_project_id)
        
    def _check_status_refresh(self):
        """
        Request status data from shotgun
        """
        
        if not self._status_loaded and not self._status_requested:
        
            fields = ["bg_color", "code", "name"]
    
            self._bundle.log_debug("Starting to download status list from Shotgun...")
            
            if len(self.__sg_data_retrievers) == 0:
                self._bundle.log_warning("No data retrievers registered with this " 
                                      "schema manager. Cannot load shotgun status.")
            else:
                # flag that we have submitted a request
                # to avoid flooding of requests.
                self._status_requested = True
                
                # pick the first one
                dr = self.__sg_data_retrievers[0]["data_retriever"]
                self._sg_status_query_id = dr.execute_find("Status", [], fields)        
        
    def _on_worker_failure(self, uid, msg):
        """
        Asynchronous callback - the worker thread errored.
        """
        
        shotgun_model = self._bundle.import_module("shotgun_model")
        
        if uid == self._sg_schema_query_id:
            msg = shotgun_model.sanitize_qt(msg) # qstring on pyqt, str on pyside
            self._bundle.log_warning("Could not load sg schema: %s" % msg)
            self._schema_requested = False
        
        elif uid == self._sg_status_query_id:
            msg = shotgun_model.sanitize_qt(msg) # qstring on pyqt, str on pyside
            self._bundle.log_warning("Could not load sg status: %s" % msg)
            self._status_requested = False
        
    def _on_worker_signal(self, uid, request_type, data):
        """
        Signaled whenever the worker completes something.
        This method will dispatch the work to different methods
        depending on what async task has completed.
        """
        
        shotgun_model = self._bundle.import_module("shotgun_model")
        
        uid = shotgun_model.sanitize_qt(uid) # qstring on pyqt, str on pyside
        data = shotgun_model.sanitize_qt(data)

        if self._sg_schema_query_id == uid:
            self._bundle.log_debug("Metaschema arrived from Shotgun...")
            # store the schema in memory
            self._field_schema = data["fields"]
            self._type_schema = data["types"]
            # job done! set our load flags accordingly.
            self._schema_loaded = True
            self._schema_requested = True
            self.schema_loaded.emit()

            # and write out the data to disk
            self._bundle.log_debug("Saving schema to '%s'..." % self._schema_cache_path)
            try:
                with open(self._schema_cache_path, "wb") as fh:
                    data = {"field_schema": self._field_schema, 
                            "type_schema": self._type_schema}
                    pickle.dump(data, fh)
                    self._bundle.log_debug("...done")
            except Exception, e:
                self._bundle.log_warning("Could not write schema "
                                         "file '%s': %s" % (self._schema_cache_path, e))            
        
        elif uid == self._sg_status_query_id:
            self._bundle.log_debug("Status list arrived from Shotgun...")
            # store status in memory
            self._status_data = {}            
            for x in data["sg"]:
                self._status_data[ x["code"] ] = x

            # job done! set our load flags accordingly.
            self._status_loaded = True
            self._status_requested = True
            self.status_loaded.emit()

            # and write out the data to disk
            self._bundle.log_debug("Saving status to '%s'..." % self._status_cache_path)
            try:
                with open(self._status_cache_path, "wb") as fh:
                    pickle.dump(self._status_data, fh)
                    self._bundle.log_debug("...done")
            except Exception, e:
                self._bundle.log_warning("Could not write status "
                                         "file '%s': %s" % (self._status_cache_path, e))            

    ##########################################################################################
    # public methods
    
    @classmethod
    def register_bg_task_manager(cls, task_manager):
        """
        Register a background task manager with the singleton.
        Once a background task manager has been registered, the schema 
        singleton can refresh its cache.
        
        :param task_manager: Background task manager to use
        :type task_manager: :class:`~tk-framework-shotgunutils:task_manager.BackgroundTaskManager` 
        """
        self = cls.__get_instance()
        
        # create a data retriever
        shotgun_data = self._bundle.import_module("shotgun_data")
        data_retriever = shotgun_data.ShotgunDataRetriever(self, bg_task_manager=task_manager)        
        data_retriever.start()
        data_retriever.work_completed.connect(self._on_worker_signal)
        data_retriever.work_failure.connect(self._on_worker_failure)
        
        dr = {"data_retriever": data_retriever, "task_manager": task_manager}        
        self.__sg_data_retrievers.append(dr)
        
    @classmethod
    def unregister_bg_task_manager(cls, task_manager):
        """
        Unregister a previously registered data retriever with the singleton.
        
        :param task_manager: Background task manager to use
        :type task_manager: :class:`~tk-framework-shotgunutils:task_manager.BackgroundTaskManager` 
        """     
        self = cls.__get_instance()
        
        culled_retrievers = []
        
        for dr in self.__sg_data_retrievers:
            
            if dr["task_manager"] == task_manager:
                self._bundle.log_debug("Unregistering %r from schema manager" % task_manager)
                data_retriever = dr["data_retriever"]
                data_retriever.stop()
                data_retriever.work_completed.disconnect(self._on_worker_signal)
                data_retriever.work_failure.disconnect(self._on_worker_failure)
                
            else:
                culled_retrievers.append(dr)

        self.__sg_data_retrievers = culled_retrievers        

    @classmethod
    def run_on_schema_loaded(cls, callback):
        """
        Run the given callback once the schema is loaded.

        :param callback: Method with no argument to run when the schema is loaded
        """
        self = cls.__get_instance()

        if self._schema_loaded:
            callback()
        else:
            self.schema_loaded.connect(callback)

            # kick off full schema loading
            self._check_schema_refresh()

    @classmethod
    def get_entity_fields(cls, sg_entity_type):
        """
        Returns the fields for a Shotgun entity type.

        :param sg_entity_type: Shotgun entity type
        :returns: List of field names
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type)

        if sg_entity_type in self._field_schema:
            return self._field_schema[sg_entity_type].keys()
        else:
            return []

    @classmethod
    def get_type_display_name(cls, sg_entity_type):
        """
        Returns the display name for a Shotgun entity type.
        If no display name is known for this object, the system
        name is returned, e.g. the same that's being passed in 
        via the sg_entity_type parameter. 
        
        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.
        
        :param sg_entity_type: Shotgun entity type
        :returns: Entity type display name
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type)
        
        if sg_entity_type in self._type_schema:
            # cache contains our item
            data = self._type_schema[sg_entity_type]
            display_name = data["name"]["value"]
        
        else:
            display_name = sg_entity_type
        
        return display_name
        
    @classmethod
    def get_field_display_name(cls, sg_entity_type, field_name):
        """
        Returns the display name for a given Shotgun field. If the field
        cannot be found or the value is not yet cached, the system name 
        for the field is returned.
        
        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.
        
        :param sg_entity_type: Shotgun entity type
        :param field_name: Shotgun field name
        :returns: Field display name        
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)        

        if field_name == "type":
            # type doesn't seem to exist in the schema
            # so treat as a special case
            display_name = "Type"
        
        elif sg_entity_type in self._type_schema and field_name in self._field_schema[sg_entity_type]:
            # cache contains our item
            data = self._field_schema[sg_entity_type][field_name]
            display_name = data["name"]["value"]

        else:
            display_name = field_name


        return display_name
        

    @classmethod
    def get_empty_phrase(cls, sg_entity_type, field_name):
        """
        Get an appropriate phrase to describe the fact that 
        a given Shotgun field is empty. The phrase will differ depending on 
        the data type of the field.

        :param sg_entity_type: Shotgun entity type
        :param field_name: Shotgun field name
        :returns: Empty phrase string        
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)
        
        empty_value = "Not set"
        try:
            data_type = self.get_data_type(sg_entity_type, field_name)
            if data_type == "Entity":
                empty_value = "Not set"
        except Exception:
            pass

        return empty_value

    @classmethod
    def get_data_type(cls, sg_entity_type, field_name):
        """
        Return the data type for the given Shotgun field.

        :param sg_entity_type: Shotgun entity type
        :param field_name: Shotgun field name
        :returns: Data type string
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)

        if sg_entity_type in self._type_schema and field_name in self._field_schema[sg_entity_type]:
            data = self._field_schema[sg_entity_type][field_name]
            return data["data_type"]["value"]

        raise ValueError("Could not find the schema for %s.%s" % (sg_entity_type, field_name))

    @classmethod
    def get_valid_types(cls, sg_entity_type, field_name):
        """
        Return the valid entity types that the given Shotgun field can link to.

        :param sg_entity_type: Shotgun entity type
        :param field_name: Shotgun field name
        :returns: List of entity types
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)

        if sg_entity_type in self._type_schema and field_name in self._field_schema[sg_entity_type]:
            data = self._field_schema[sg_entity_type][field_name]
            valid_types = data.get("properties", {}).get("valid_types", {}).get("value")

            if valid_types is None:
                raise ValueError("The data type for %s.%s does not have valid types" % (sg_entity_type, field_name))

            return valid_types

        raise ValueError("Could not find the schema for %s.%s" % (sg_entity_type, field_name))

    @classmethod
    def get_valid_values(cls, sg_entity_type, field_name):
        """
        Returns valid values for fields with a list of choices.

        :param str sg_entity_type: The entity type.
        :param str field_name: The name of the field on the entity

        :return: A :obj:`list` of valid values defined by the schema
        :rtype list:

        :raises: ``ValueError`` if the field has no valid values.
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)

        if sg_entity_type in self._type_schema and field_name in self._field_schema[sg_entity_type]:
            data = self._field_schema[sg_entity_type][field_name]
            valid_values = data.get("properties", {}).get("valid_values", {}).get("value")

            if valid_values is None:
                raise ValueError("The data type for %s.%s does not have valid values" % (sg_entity_type, field_name))

            return valid_values

        raise ValueError("Could not find the schema for %s.%s" % (sg_entity_type, field_name))

    @classmethod
    def get_status_display_name(cls, status_code):
        """
        Returns the display name for a given status code.
        If the status code cannot be found or haven't been loaded,
        the status code is returned back.
        
        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.
        
        :param status_code: Status short code (e.g 'ip')
        :returns: string with descriptive status name 
        """
        self = cls.__get_instance()
        self._check_status_refresh()
        
        display_name = status_code
        
        if status_code in self._status_data:
            data = self._status_data[status_code]
            display_name = data.get("name") or status_code
        
        return display_name


    @classmethod
    def get_status_color(cls, status_code):
        """
        Returns the color for a given status code.
        If the status code cannot be found or haven't been loaded,
        None is returned.
        
        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.        
        
        :param status_code: Status short code (e.g 'ip')
        :returns: string with r,g,b values, e.g. ``"123,255,10"``
        """
        self = cls.__get_instance()
        self._check_status_refresh()
        
        status_color = None
        
        if status_code in self._status_data:
            data = self._status_data[status_code]
            status_color = data.get("bg_color")
            # color is on the form "123,255,10"
        
        return status_color


    @classmethod
    def field_is_editable(cls, sg_entity_type, field_name):
        """
        Returns a boolean identifying the editability of the entity's field.

        :param str sg_entity_type: the entity type
        :param str field_name: the field name to check editibility

        :returns: ``True`` if the field is ediable, ``False`` otherwise.
        :rtype: :obj:`bool`
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)

        if sg_entity_type in self._type_schema and field_name in self._field_schema[sg_entity_type]:
            data = self._field_schema[sg_entity_type][field_name]
            try:
                return data["editable"]["value"]
            except KeyError:
                raise ValueError("Could not determine editability from the schema.")


        raise ValueError("Could not find the schema for %s.%s" % (sg_entity_type, field_name))

    @classmethod
    def field_is_visible(cls, sg_entity_type, field_name):
        """
        Returns a boolean identifying the visibility of the entity's field.

        :param sg_entity_type: the entity type
        :param field_name: the field name to check visibility

        :returns: ``True`` if the field is visible, ``False`` otherwise.
        :rtype: :obj:`bool`
        """
        self = cls.__get_instance()
        self._check_schema_refresh(sg_entity_type, field_name)

        if sg_entity_type in self._type_schema and field_name in self._field_schema[sg_entity_type]:
            data = self._field_schema[sg_entity_type][field_name]
            try:
                return data["visible"]["value"]
            except KeyError:
                raise ValueError("Could not determine visibility from the schema.")

        raise ValueError("Could not find the schema for %s.%s" % (sg_entity_type, field_name))

