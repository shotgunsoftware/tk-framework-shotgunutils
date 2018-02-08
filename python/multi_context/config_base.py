# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sgtk
import tempfile
import cPickle
from sgtk.platform.qt import QtCore, QtGui
from . import file_cache
from . import command

logger = sgtk.platform.get_logger(__name__)


class BaseConfiguration(QtCore.QObject):
    """
    Base class for a remote pipeline configuration
    """
    TASK_GROUP = "remote_pipeline_configuration_resolves"

    commands_loaded = QtCore.Signal(list)

    def __init__(
            self,
            parent,
            bg_task_manager,
            plugin_id,
            project_id,
            pipeline_config_id,
            pipeline_config_name,
            pipeline_config_uri,
            pipeline_config_interpreter,
            local_path
    ):
        """
        """
        super(BaseConfiguration, self).__init__(parent)

        self._plugin_id = plugin_id
        self._project_id = project_id
        self._pipeline_config_id = pipeline_config_id
        self._pipeline_config_name = pipeline_config_name
        self._pipeline_config_uri = pipeline_config_uri
        self._pipeline_config_interpreter = pipeline_config_interpreter
        self._path = local_path

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()


        self._bg_task_manager = bg_task_manager
        self._bg_task_manager.task_completed.connect(self._task_completed)
        self._bg_task_manager.task_failed.connect(self._task_failed)

    def __repr__(self):
        return "<Config %s@%s>" % (self._pipeline_config_name, self._pipeline_config_uri)

    @property
    def name(self):
        """
        The name of the associated pipeline configuration
        """
        return self._pipeline_config_name

    def is_primary(self):
        return self._pipeline_config_name == "Primary"

    def is_default(self):
        return False

    @property
    def id(self):
        return self._pipeline_config_id

    @property
    def descriptor_uri(self):
        return self._pipeline_config_uri

    @property
    def project_id(self):
        return self._project_id

    @property
    def plugin_id(self):
        return self._plugin_id

    @property
    def path(self):
        return self._path

    def request_commands(self, engine, entity_type, entity_id, link_entity_type):
        """
        Fast cached raw access
        """
        logger.debug("Requested commands for %s: %s %s %s" %  (self, entity_type, entity_id, link_entity_type))
        #self.commands_loaded.emit([])

        hash = self._compute_config_hash(engine, entity_type, entity_id, link_entity_type)
        cached_data = file_cache.load_cache(hash)

        if cached_data:
            # got some cached data.
            self.commands_loaded.emit(cached_data["commands"])

        else:
            # no cached version exists. Request a bg load
            self._bg_task_manager.add_task(
                self._cache_commands,
                group=self.TASK_GROUP,
                task_kwargs={
                    "engine": engine,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "cache_hash": cache_path,
                }
            )

    def _compute_config_hash(self, engine, entity_type, entity_id, link_entity_type):
        """
        hash.
        """
        raise NotImplementedError("_compute_config_hash is not implemented.")



    @sgtk.LogManager.log_timing
    def _cache_commands(self, engine, entity_type, entity_id, cache_hash):
        """
        Triggers the caching or recaching of engine commands.
        """
        logger.debug("Begin caching commands")

        cache_path = file_cache.get_cache_path(cache_hash)

        if os.path.exists(cache_path):
            # no need to cache
            return

        script = os.path.join(
            os.path.dirname(__file__),
            "scripts",
            "cache_commands.py"
        )

        args_file = self._get_arguments_file(
            dict(
                sys_path=self._compute_sys_path(),
                cache_path=cache_path,
                configuration_uri=self.descriptor_uri,
                pipeline_config_id=self.id,
                plugin_id=self.plugin_id,
                engine_name=engine,
                entity_type=entity_type,
                entity_id=entity_id,
                bundle_cache_fallback_paths=self._bundle.engine.sgtk.bundle_cache_fallback_paths,
            )
        )

        args = [self._pipeline_config_interpreter, script, args_file]
        logger.debug("Command arguments: %s", args)

        retcode, stdout, stderr = command.Command.call_cmd(args)

        if retcode == 0:
            logger.debug("Command stdout: %s", stdout)
            logger.debug("Command stderr: %s", stderr)
        else:
            logger.error("Command failed: %s", args)
            logger.error("Failed command stdout: %s", stdout)
            logger.error("Failed command stderr: %s", stderr)
            logger.error("Failed command retcode: %s", retcode)
            raise Exception("%s\n\n%s" % (stdout, stderr))

        logger.debug("Caching complete.")
        return cache_hash

    def _task_completed(self, unique_id, group, result):
        """
        When a task completes
        """
        if group != self.TASK_GROUP:
            # not for us
            return

        logger.debug("Got configuration info!")
        cache_hash = result
        cached_data = file_cache.load_cache(cache_hash)

        if cached_data:
            # got some cached data.
            self.commands_loaded.emit(cached_data["commands"])


    def _task_failed(self, unique_id, group, message, traceback_str):
        """
        When a task fails
        @param unique_id:
        @param group:
        @param message:
        @param traceback_str:
        @return:
        """
        if group != self.TASK_GROUP:
            # not for us
            return

        logger.error("TASK FAILED")







    @sgtk.LogManager.log_timing
    def _get_entity_parent_project(self, entity):
        """
        Gets the project entity that the given entity is linked to.

        :param dict entity: A standard Shotgun entity dictionary.

        :returns: A standard Shotgun Project entity.
        :rtype: dict
        """
        logger.debug("Attempting lookup of project from entity: %s", entity)

        if entity.get("project") is not None:
            return entity["project"]

        if entity["type"] == "Project":
            return entity

        project_cache = self._cache.setdefault(self.ENTITY_PARENT_PROJECTS, dict())

        if entity["id"] not in project_cache:
            project = None
            try:
                sg_entity = self._engine.shotgun.find_one(
                    entity["type"],
                    [["id", "is", entity["id"]]],
                    fields=["project"],
                )
            except Exception:
                pass
            else:
                project = sg_entity["project"]

            project_cache[entity["id"]] = project
        return project_cache[entity["id"]]



    @sgtk.LogManager.log_timing
    def _get_task_parent_entity_type(self, task_id):
        """
        Gets the Task entity's parent entity type.

        :param int task_id: The id of the Task entity to find the parent of.

        :returns: The Task's parent entity type.
        :rtype: str
        """
        cache = self._cache

        if self.TASK_PARENT_TYPES in cache and task_id in cache[self.TASK_PARENT_TYPES]:
            logger.debug("Parent entity type found in cache for Task %s.", task_id)
        else:
            context = sgtk.context.from_entity(
                self._engine.sgtk,
                "Task",
                task_id,
            )

            if context.entity is None:
                raise TankTaskNotLinkedError("Task is not linked to an entity.")
            else:
                entity_type = context.entity["type"]
            cache.setdefault(self.TASK_PARENT_TYPES, dict())[task_id] = entity_type

        return cache[self.TASK_PARENT_TYPES][task_id]


    def _compute_sys_path(self):
        """
        :returns: Path to the current core.
        """
        # While core swapping, the Python path is not updated with the new core's
        # Python path, so make sure the current core is at the front of the Python
        # path for our subprocesses.
        python_folder = sgtk.bootstrap.ToolkitManager.get_core_python_path()
        logger.debug("Adding %s to sys.path for subprocesses.", python_folder)
        return python_folder



    def _get_arguments_file(self, args_data):
        """
        Dumps out a temporary file containing the provided data structure.

        :param args_data: The data to serialize to disk.

        :returns: File path
        :rtype: str
        """
        args_file = tempfile.mkstemp()[1]

        with open(args_file, "wb") as fh:
            cPickle.dump(
                args_data,
                fh,
                cPickle.HIGHEST_PROTOCOL,
            )

        return args_file
