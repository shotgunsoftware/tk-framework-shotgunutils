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
from sgtk.platform.qt import QtCore


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

    # Both will be sent along with the project id.
    schema_loaded = QtCore.Signal(int)
    status_loaded = QtCore.Signal(int)

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

        self._sg_schema_query_ids = {}
        self._sg_status_query_ids = {}

        # load cached values from disk
        self._load_cached_schema()
        self._load_cached_status()

    def _is_schema_loaded(self, project_id=None):
        """
        Whether the schema has been loaded into memory.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        :returns:           bool
        """
        project_id = project_id or self._get_current_project_id()
        return project_id in self._field_schema

    def _is_status_loaded(self, project_id=None):
        """
        Whether statuses have been loaded into memory.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        :returns:           bool
        """
        project_id = project_id or self._get_current_project_id()
        return project_id in self._status_data

    def _get_current_project_id(self):
        """
        Return the id of the current project.

        :returns: The project id associated with the current context, or ``None``
            if operating in a site-level context.
        :rtype: ``int`` or ``None``
        """

        if self._bundle.tank.pipeline_configuration.is_site_configuration():
            # site configuration (no project id). Return None which is
            # consistent with core.
            project_id = None
        else:
            project_id = self._bundle.tank.pipeline_configuration.get_project_id()

        return project_id

    def _get_cache_root_path(self, project_id=None):
        """
        Gets the parent bundle's cache location.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        :returns:           str
        """
        if project_id is None:
            return self._bundle.cache_location
        else:
            # Backwards compatible here with pre-v0.18.1 tk-core. If we don't
            # have access to the get_project_cache_location method on the bundle,
            # then we just get the current project's cache location and suffer
            # the minor consequences. This is unlikely to happen, because apps
            # that make use of the project_id feature are almost certainly going
            # to also require a modern version of core.
            try:
                return self._bundle.get_project_cache_location(project_id)
            except AttributeError:
                self._bundle.log_debug(
                    "Bundle.get_project_cache_location() is not available. "
                    "Falling back on Bundle.cache_location instead."
                )
                return self._bundle.cache_location

    def _get_schema_cache_path(self, project_id=None):
        """
        Gets the path to the schema cache file.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        :returns:           str
        """
        return os.path.join(self._get_cache_root_path(project_id), "sg_schema.pickle")

    def _get_status_cache_path(self, project_id=None):
        """
        Gets the path to the status cache file.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        :returns:           str
        """
        return os.path.join(self._get_cache_root_path(project_id), "sg_status.pickle")

    def _load_cached_status(self, project_id=None):
        """
        Load cached status from disk if it exists.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used.
        :returns bool: True if loaded, False if not.
        """
        project_id = project_id or self._get_current_project_id()
        status_cache_path = self._get_status_cache_path(project_id)

        if os.path.exists(status_cache_path):
            try:
                self._bundle.log_debug(
                    "Loading cached status from '%s'" % status_cache_path
                )
                with open(status_cache_path, "rb") as fh:
                    status_data = sgtk.util.pickle.load(fh)
                    # Check to make sure the structure of the data
                    # is what we expect. If it isn't then we don't
                    # accept the data which will force it to be
                    # recached.
                    if "statuses" in status_data and "status_order" in status_data:
                        self._status_data[project_id] = status_data
            except Exception as e:
                self._bundle.log_warning(
                    "Could not open cached status "
                    "file '%s': %s" % (status_cache_path, e)
                )
            else:
                self.status_loaded.emit(project_id)
                return True

        return False

    def _load_cached_schema(self, project_id=None):
        """
        Load cached metaschema from disk if it exists.

        :param project_id:  The project Entity id. If None, the current
                            context's project will be used.
        :returns bool: True if loaded, False if not.
        """
        project_id = project_id or self._get_current_project_id()
        schema_cache_path = self._get_schema_cache_path(project_id)

        if os.path.exists(schema_cache_path):
            try:
                self._bundle.log_debug(
                    "Loading cached schema from '%s'" % schema_cache_path
                )
                with open(schema_cache_path, "rb") as fh:
                    data = sgtk.util.pickle.load(fh)
                    self._field_schema[project_id] = data["field_schema"]
                    self._type_schema[project_id] = data["type_schema"]
            except Exception as e:
                self._bundle.log_warning(
                    "Could not open cached schema "
                    "file '%s': %s" % (schema_cache_path, e)
                )
            else:
                self.schema_loaded.emit(project_id)
                return True

        return False

    def _check_schema_refresh(self, entity_type=None, field_name=None, project_id=None):
        """
        Check and potentially trigger a cache refresh.

        :param str entity_type: Shotgun entity type
        :param str field_name: Shotgun field name
        :param int project_id: The project Entity id. If None, the current
                               context's project will be used.
        """
        current_project_id = self._get_current_project_id()
        project_id = project_id or current_project_id

        # TODO: currently, this only checks if there is a full cache in memory
        # or not. Later on, when we have the ability to check the current
        # metaschema generation via the shotgun API, this can be handled in a
        # more graceful fashion.
        if (
            not self._is_schema_loaded(project_id)
            and project_id not in self._sg_schema_query_ids.values()
        ):
            # schema is not requested and not loaded.
            # If a schema was requested for a project that isn't the current project,
            # then let's check to see if we can get it from disk before we resort to
            # going to Shotgun.
            if project_id != current_project_id:
                if self._load_cached_schema(project_id=project_id):
                    # If we were able to load the cached schema from disk then we don't
                    # have anything else to do.
                    return

            # so download it from shotgun!
            self._bundle.log_debug(
                "Starting to download new metaschema from ShotGrid..."
            )

            if self.__sg_data_retrievers:
                data_retriever = self.__sg_data_retrievers[0]["data_retriever"]
                self._sg_schema_query_ids[
                    data_retriever.get_schema(project_id)
                ] = project_id
            else:
                self._bundle.log_warning(
                    "No data retrievers registered with this schema manager. "
                    "Cannot load shotgun schema."
                )

    def _check_status_refresh(self, project_id=None):
        """
        Request status data from Shotgun.

        :param int project_id: The project Entity id. If None, the current
                               context's project will be used.
        """
        current_project_id = self._get_current_project_id()
        project_id = project_id or current_project_id

        if (
            not self._is_status_loaded(project_id)
            and project_id not in self._sg_status_query_ids.values()
        ):
            # If statuses were requested for a project that isn't the current project,
            # then  let's check to see if we can get it from disk before we resort
            # to going to Shotgun.
            if project_id != current_project_id:
                if self._load_cached_status(project_id=project_id):
                    # If we were able to load the cached schema from disk then we don't
                    # have anything else to do.
                    return

            fields = ["bg_color", "code", "name"]
            self._bundle.log_debug("Starting to download status list from ShotGrid...")

            if self.__sg_data_retrievers:
                # pick the first one
                data_retriever = self.__sg_data_retrievers[0]["data_retriever"]
                self._sg_status_query_ids[
                    data_retriever.execute_find("Status", [], fields)
                ] = project_id
            else:
                self._bundle.log_warning(
                    "No data retrievers registered with this schema manager. "
                    "Cannot load ShotGrid statuses."
                )

    def _on_worker_failure(self, uid, msg):
        """
        Asynchronous callback - the worker thread errored.
        """

        shotgun_model = self._bundle.import_module("shotgun_model")

        if uid in self._sg_schema_query_ids:
            msg = shotgun_model.sanitize_qt(msg)  # qstring on pyqt, str on pyside
            self._bundle.log_warning("Could not load sg schema: %s" % msg)
            del self._sg_schema_query_ids[uid]
        elif uid in self._sg_status_query_ids:
            msg = shotgun_model.sanitize_qt(msg)  # qstring on pyqt, str on pyside
            self._bundle.log_warning("Could not load sg status: %s" % msg)
            del self._sg_status_query_ids[uid]

    def _on_worker_signal(self, uid, request_type, data):
        """
        Signaled whenever the worker completes something.
        This method will dispatch the work to different methods
        depending on what async task has completed.
        """

        shotgun_model = self._bundle.import_module("shotgun_model")

        uid = shotgun_model.sanitize_qt(uid)  # qstring on pyqt, str on pyside
        data = shotgun_model.sanitize_qt(data)

        if uid in self._sg_schema_query_ids:
            self._bundle.log_debug("Metaschema arrived from ShotGrid...")
            project_id = self._sg_schema_query_ids[uid]

            # store the schema in memory
            self._field_schema[project_id] = data["fields"]
            self._type_schema[project_id] = data["types"]

            # job done!
            del self._sg_schema_query_ids[uid]
            self.schema_loaded.emit(project_id)

            # and write out the data to disk
            self._bundle.log_debug(
                "Saving schema to '%s'..." % self._get_schema_cache_path(project_id)
            )
            try:
                with open(self._get_schema_cache_path(project_id), "wb") as fh:
                    data = dict(
                        field_schema=self._field_schema[project_id],
                        type_schema=self._type_schema[project_id],
                    )
                    sgtk.util.pickle.dump(data, fh)
                    self._bundle.log_debug("...done")
            except Exception as e:
                self._bundle.log_warning(
                    "Could not write schema "
                    "file '%s': %s" % (self._get_schema_cache_path(project_id), e)
                )

        elif uid in self._sg_status_query_ids:
            self._bundle.log_debug("Status list arrived from ShotGrid...")
            project_id = self._sg_status_query_ids[uid]

            # store status in memory
            self._status_data[project_id] = dict(status_order=[], statuses={})
            for x in data["sg"]:
                self._status_data[project_id]["statuses"][x["code"]] = x
                self._status_data[project_id]["status_order"].append(x["code"])

            # job done!
            del self._sg_status_query_ids[uid]
            self.status_loaded.emit(project_id)

            # and write out the data to disk
            self._bundle.log_debug(
                "Saving status to '%s'..." % self._get_status_cache_path(project_id)
            )
            try:
                with open(self._get_status_cache_path(project_id), "wb") as fh:
                    sgtk.util.pickle.dump(self._status_data[project_id], fh)
                    self._bundle.log_debug("...done")
            except Exception as e:
                raise
                self._bundle.log_warning(
                    "Could not write status "
                    "file '%s': %s" % (self._get_status_cache_path(project_id), e)
                )

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
        data_retriever = shotgun_data.ShotgunDataRetriever(
            self, bg_task_manager=task_manager
        )
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
                self._bundle.log_debug(
                    "Unregistering %r from schema manager" % task_manager
                )
                data_retriever = dr["data_retriever"]
                data_retriever.stop()

                # make sure we don't get exceptions trying to disconnect if the
                # signals were never connected or somehow disconnected externally
                try:
                    data_retriever.work_completed.disconnect(self._on_worker_signal)
                except (TypeError, RuntimeError) as e:  # was never connected
                    self._bundle.log_warning(
                        "Could not disconnect '_on_worker_signal' slot from "
                        "the task manager's 'work_completed' signal: %s" % (e,)
                    )

                try:
                    data_retriever.work_failure.disconnect(self._on_worker_failure)
                except (TypeError, RuntimeError) as e:  # was never connected
                    self._bundle.log_warning(
                        "Could not disconnect '_on_worker_failure' slot from "
                        "the task manager's 'work_failure' signal: %s" % (e,)
                    )
            else:
                culled_retrievers.append(dr)

        self.__sg_data_retrievers = culled_retrievers

    @classmethod
    def run_on_schema_loaded(cls, callback, project_id=None):
        """
        Run the given callback once the schema is loaded.

        :param callback:    Method with no argument to run when the schema is loaded
        :param project_id:  The id of the project entity to load the schema for. If
                            None, the current context's project will be used.
        """

        self = cls.__get_instance()

        if self._is_schema_loaded(project_id=project_id):
            callback()
        else:
            self.schema_loaded.connect(callback)

            # kick off full schema loading
            self._check_schema_refresh(project_id=project_id)

    @classmethod
    def is_valid_entity_type(cls, sg_entity_type, project_id=None):
        """
        Check if the given `sg_entity_type` is in the schema.

        :param sg_entity_type:  Shotgun entity type
        :param project_id:      The id of the project entity to get fields from.
                                If None, the current context's project will be used.

        :returns: True if the entity is valid, else False.
        :rtype: bool
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_schema_refresh(sg_entity_type, project_id=project_id)

        return (
            project_id in self._field_schema
            and sg_entity_type in self._field_schema[project_id]
        )

    @classmethod
    def get_entity_fields(cls, sg_entity_type, project_id=None):
        """
        Returns the fields for a Shotgun entity type.

        :param sg_entity_type:  Shotgun entity type
        :param project_id:      The id of the project entity to get fields from.
                                If None, the current context's project will be used.

        :returns: List of field names
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_schema_refresh(sg_entity_type, project_id=project_id)

        if (
            project_id in self._field_schema
            and sg_entity_type in self._field_schema[project_id]
        ):
            return list(self._field_schema[project_id][sg_entity_type].keys())
        else:
            return []

    @classmethod
    def get_type_display_name(cls, sg_entity_type, project_id=None):
        """
        Returns the display name for a Shotgun entity type.
        If no display name is known for this object, the system
        name is returned, e.g. the same that's being passed in
        via the sg_entity_type parameter.

        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.

        :param sg_entity_type:  Shotgun entity type
        :param project_id:      The id of the project entity to get a name from.
                                If None, the current context's project will be used.

        :returns: Entity type display name
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_schema_refresh(sg_entity_type, project_id=project_id)

        if (
            project_id in self._type_schema
            and sg_entity_type in self._type_schema[project_id]
        ):
            # cache contains our item
            data = self._type_schema[project_id][sg_entity_type]
            display_name = data["name"]["value"]
        else:
            display_name = sg_entity_type

        return display_name

    @classmethod
    def get_field_display_name(cls, sg_entity_type, field_name, project_id=None):
        """
        Returns the display name for a given Shotgun field. If the field
        cannot be found or the value is not yet cached, the system name
        for the field is returned.

        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.

        :param sg_entity_type:  Shotgun entity type
        :param field_name:      Shotgun field name
        :param project_id:      The id of the project entity to get a name from.
                                If None, the current context's project will be used.

        :returns: Field display name
        """

        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        if field_name == "type":
            # type doesn't seem to exist in the schema
            # so treat as a special case
            return "Type"
        elif (
            project_id in self._type_schema
            and sg_entity_type in self._type_schema[project_id]
        ):
            if field_name in self._field_schema[project_id][sg_entity_type]:
                data = self._field_schema[project_id][sg_entity_type][field_name]
                return data["name"]["value"]

        return field_name

    @classmethod
    def get_empty_phrase(cls, sg_entity_type, field_name, project_id=None):
        """
        Get an appropriate phrase to describe the fact that
        a given Shotgun field is empty. The phrase will differ depending on
        the data type of the field.

        :param sg_entity_type:  Shotgun entity type
        :param field_name:      Shotgun field name
        :param project_id:      The id of the project entity to get a phrase from.
                                If None, the current context's project will be used.

        :returns: Empty phrase string
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        empty_value = "Not set"
        try:
            data_type = cls.get_data_type(
                sg_entity_type, field_name, project_id=project_id
            )

            if data_type == "Entity":
                empty_value = "Not set"
        except Exception:
            pass

        return empty_value

    @classmethod
    def get_data_type(cls, sg_entity_type, field_name, project_id=None):
        """
        Return the data type for the given Shotgun field.

        :param sg_entity_type:  Shotgun entity type
        :param field_name:      Shotgun field name
        :param project_id:      The id of the project entity to get a type from.
                                If None, the current context's project will be used.

        :returns: Data type string
        """

        source_field_name = field_name

        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        if (
            project_id in self._type_schema
            and sg_entity_type in self._type_schema[project_id]
        ):
            if field_name in self._field_schema[project_id][sg_entity_type]:
                data = self._field_schema[project_id][sg_entity_type][field_name]
                return data["data_type"]["value"]

        raise ValueError(
            "Could not find the schema for %s.%s" % (sg_entity_type, source_field_name)
        )

    @classmethod
    def get_valid_types(cls, sg_entity_type, field_name, project_id=None):
        """
        Return the valid entity types that the given Shotgun field can link to.

        :param sg_entity_type:  Shotgun entity type
        :param field_name:      Shotgun field name
        :param project_id:      The id of the project entity to get types from.
                                If None, the current context's project will be used.

        :returns: List of entity types
        """

        source_field_name = field_name

        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        if (
            project_id in self._type_schema
            and sg_entity_type in self._type_schema[project_id]
        ):
            if field_name in self._field_schema[project_id][sg_entity_type]:
                data = self._field_schema[project_id][sg_entity_type][field_name]
                valid_types = (
                    data.get("properties", {}).get("valid_types", {}).get("value")
                )

                if valid_types is None:
                    raise ValueError(
                        "The data type for %s.%s does not have valid types"
                        % (sg_entity_type, source_field_name)
                    )

                return valid_types

        raise ValueError(
            "Could not find the schema for %s.%s" % (sg_entity_type, source_field_name)
        )

    @classmethod
    def get_valid_values(cls, sg_entity_type, field_name, project_id=None):
        """
        Returns valid values for fields with a list of choices.

        :param str sg_entity_type:  The entity type.
        :param str field_name:      The name of the field on the entity
        :param project_id:          The id of the project entity to get a name from.
                                    If None, the current context's project will be used.

        :return:                    A :obj:`list` of valid values defined by the schema

        :raises: ``ValueError`` if the field has no valid values.
        """

        source_field_name = field_name

        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        if project_id in self._type_schema and project_id in self._field_schema:
            if sg_entity_type in self._type_schema[project_id]:
                if field_name in self._field_schema[project_id][sg_entity_type]:
                    data = self._field_schema[project_id][sg_entity_type][field_name]
                    valid_values = (
                        data.get("properties", {}).get("valid_values", {}).get("value")
                    )

                    if valid_values is None:
                        raise ValueError(
                            "The data type for %s.%s does not have valid values"
                            % (sg_entity_type, source_field_name)
                        )

                    return valid_values
        raise ValueError(
            "Could not find the schema for %s.%s" % (sg_entity_type, source_field_name)
        )

    @classmethod
    def get_status_display_name(cls, status_code, project_id=None):
        """
        Returns the display name for a given status code.
        If the status code cannot be found or haven't been loaded,
        the status code is returned back.

        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.

        :param status_code: Status short code (e.g 'ip')
        :param project_id:  The id of the project entity to get a name from.
                            If None, the current context's project will be used.

        :returns: string with descriptive status name
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_status_refresh(project_id=project_id)

        display_name = status_code

        if (
            project_id in self._status_data
            and status_code in self._status_data[project_id]["statuses"]
        ):
            data = self._status_data[project_id]["statuses"][status_code]
            display_name = data.get("name") or status_code

        return display_name

    @classmethod
    def get_status_color(cls, status_code, project_id=None):
        """
        Returns the color for a given status code.
        If the status code cannot be found or haven't been loaded,
        None is returned.

        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.

        :param status_code: Status short code (e.g 'ip')
        :param project_id:  The id of the project entity to get a color from.
                            If None, the current context's project will be used.

        :returns: string with r,g,b values, e.g. ``"123,255,10"``
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_status_refresh(project_id=project_id)

        status_color = None

        if (
            project_id in self._status_data
            and status_code in self._status_data[project_id]["statuses"]
        ):
            data = self._status_data[project_id]["statuses"][status_code]
            # color is in the form of "123,255,10"
            status_color = data.get("bg_color")

        return status_color

    @classmethod
    def field_is_editable(cls, sg_entity_type, field_name, project_id=None):
        """
        Returns a boolean identifying the editability of the entity's field.

        :param str sg_entity_type: the entity type
        :param str field_name: the field name to check editibility
        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        The ``field_name`` may be in "bubble" notation. This method will account
        for it and return the editability setting for the evaluated entity type
        and field defined in the bubble noation. For example, if the field is
        defined as "sg_sequence.Sequence.code", this method will return the
        editability of the `code` field on the `Sequence` entity.

        :returns: ``True`` if the field is ediable, ``False`` otherwise.
        """
        self = cls.__get_instance()

        source_field_name = field_name

        project_id = project_id or self._get_current_project_id()
        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        # make sure the project id is found in each of the type and file schemas
        # and that the entity type and field name are found in their respective
        # project caches
        if (
            project_id in self._type_schema
            and project_id in self._field_schema
            and sg_entity_type in self._type_schema[project_id]
            and field_name in self._field_schema[project_id][sg_entity_type]
        ):

            data = self._field_schema[project_id][sg_entity_type][field_name]
            try:
                return data["editable"]["value"]
            except KeyError:
                raise ValueError("Could not determine editability from the schema.")

        raise ValueError(
            "Could not find the schema for %s.%s" % (sg_entity_type, source_field_name)
        )

    @classmethod
    def field_is_visible(cls, sg_entity_type, field_name, project_id=None):
        """
        Returns a boolean identifying the visibility of the entity's field.

        :param sg_entity_type: the entity type
        :param field_name: the field name to check visibility
        :param project_id:  The project Entity id. If None, the current
                            context's project will be used, or the "site"
                            cache location will be returned if the current
                            context does not have an associated project.

        The ``field_name`` may be in "bubble" notation. This method will account
        for it and return the visibility setting for the evaluated entity type
        and field defined in the bubble noation. For example, if the field is
        defined as "sg_sequence.Sequence.code", this method will return the
        visibility of the `code` field on the `Sequence` entity.

        :returns: ``True`` if the field is visible, ``False`` otherwise.
        """

        source_field_name = field_name

        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_schema_refresh(sg_entity_type, field_name, project_id=project_id)

        (sg_entity_type, field_name) = _account_for_bubble_fields(
            sg_entity_type, field_name
        )

        # make sure the project id is found in each of the type and file schemas
        # and that the entity type and field name are found in their respective
        # project caches
        if (
            project_id in self._type_schema
            and project_id in self._field_schema
            and sg_entity_type in self._type_schema[project_id]
            and field_name in self._field_schema[project_id][sg_entity_type]
        ):

            data = self._field_schema[project_id][sg_entity_type][field_name]
            try:
                return data["visible"]["value"]
            except KeyError:
                raise ValueError("Could not determine visibility from the schema.")

        raise ValueError(
            "Could not find the schema for %s.%s" % (sg_entity_type, source_field_name)
        )

    @classmethod
    def get_ordered_status_list(cls, display_names=False, project_id=None):
        """
        Returns a list of statuses in their order as defined by the
        Shotgun site preferences.

        If the data is not present locally, a cache reload
        will be triggered, meaning that subsequent cache requests may
        return valid data.

        :param display_names:   If True, returns status display names. If
                                False, status codes are returned. Default is
                                False.
        :param project_id:      The id of the project entity to get statuses from.
                                If None, the current context's project will be used.

        :returns:               list of string display names in order
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()
        self._check_status_refresh(project_id=project_id)

        if project_id not in self._status_data:
            raise ValueError(
                "Could not find the statuses for project %i" % (project_id)
            )

        statuses = self._status_data[project_id]["statuses"]

        if display_names:
            return [
                cls.get_status_display_name(s)
                for s in self._status_data[project_id]["status_order"]
            ]
        else:
            return self._status_data[project_id]["status_order"]

    @classmethod
    def clear_cached_data(cls, project_id=None):
        """
        Remove both the schema and status cache files from disk for
        the specified project_id. If no project_id is specified, then
        use the current context project.

        :param project_id: The id of the project entity to remove
                           schema and status cache files for. If
                           None, the current context's project will
                           be used.
        """
        self = cls.__get_instance()
        project_id = project_id or self._get_current_project_id()

        schema_cache = self._get_schema_cache_path(project_id)
        if os.path.isfile(schema_cache):
            self._bundle.log_debug("Removing schema cache file : %s" % schema_cache)
            try:
                os.remove(schema_cache)
            except Exception as e:
                self._bundle.log_error(
                    "Caught error attempting to remove schema cache file [%s] :\n%s"
                    % (schema_cache, e)
                )
                raise

        status_cache = self._get_status_cache_path(project_id)
        if os.path.isfile(status_cache):
            self._bundle.log_debug("Removing status cache file : %s" % status_cache)
            try:
                os.remove(status_cache)
            except Exception as e:
                self._bundle.log_error(
                    "Caught error attempting to remove status cache file [%s] :\n%s"
                    % (status_cache, e)
                )
                raise


def _account_for_bubble_fields(sg_entity_type, field_name):
    """Detect bubble fields and return the proper entity type and field name.

    :param str sg_entity_type: The intput entity type name. If the field name
        is a bubbled field notation, this value will be replaced by the
        parsed entity type in the field string.
    :param str field_name: The name of the field. This may be in "bubble"
        notation: "sg_sequence.Sequence.code"

    If field_name is in bubble notation (example: "sg_sequence.Sequence.code")
    this method will return "code" as the field name and "Sequence" as the
    entity type.

    If the field name is not in bubble notation, this method simply returns a
    tuple containing the supplied arguments.

    :returns: A tuple (str, str) where the first item is the evaluated entity
        type name and the second is the evaluated field name.
    :rtype: tuple
    """

    if "." in field_name:
        (sg_entity_type, field_name) = field_name.split(".")[-2:]

    return (sg_entity_type, field_name)
