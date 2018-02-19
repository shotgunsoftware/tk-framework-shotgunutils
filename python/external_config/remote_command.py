# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
import os
import cPickle
import sgtk

logger = sgtk.platform.get_logger(__name__)


class RemoteCommand(object):
    """
    Represents a remote Toolkit command (e.g. menu option).

    These objects are emitted by :class:`RemoteConfiguration`
    and are independent, decoupled, light weight objects that
    can be serialized and brought back easily.

    A command is executed via its :meth:`execute` method, which
    will launch it in the given engine.
    """

    @classmethod
    def serialize_command(cls, entity, engine_name, command_name, properties):
        """
        Generates a data chunk given a set of standard
        toolkit command data, as obtained from engine.commands.

        This can be passed to :meth:`create` in order to construct a
        :class:`RemoteCommand` instance.

        :param dict entity: Shotgun entity dictionary with keys type and id.
        :param str engine_name: Name of associated engine.
        :param str command_name: Command name (the key
            name for an entry in engine.commands)
        :param dict properties: Properties dictionary
            as returned by engine.commands.
        :returns: dictionary suitable to pass to :meth:`create`.
        """
        data = {
            "entity": entity,
            "engine_name": engine_name,
            "callback_name": command_name,
            "display_name": properties.get("title") or command_name,
            "tooltip": properties.get("description") or "",
            "type": properties.get("type"),
            "icon": properties.get("icon"),
            "group": properties.get("group"),
            "group_default": properties.get("group_default") or False,

            # special for shotgun
            "deny_permissions": properties.get("deny_permissions"),
            "deny_platforms": properties.get("deny_platforms"),
            "supports_multiple_selection": properties.get("supports_multiple_selection"),
        }

        return data

    @classmethod
    def create(cls, remote_configuration, data):
        """
        Creates a new :class:`RemoteCommand` instance based on the
        data in data. This data is generated by :meth:`serialize_command`.

        :param remote_configuration: associated :class:`RemoteConfiguration` instance.
        :param dict data: Serialized data to be turned into an instance
        :returns: :class:`RemoteCommand` instance.
        """
        return RemoteCommand(
            callback_name=data["callback_name"],
            display_name=data["display_name"],
            tooltip=data["tooltip"],
            python_interpreter=remote_configuration.associated_python_interpreter,
            descriptor_uri=remote_configuration.descriptor_uri,
            pipeline_config_id=remote_configuration.pipeline_configuration_id,
            plugin_id=remote_configuration.plugin_id,
            engine_name=data["engine_name"],
            entity_type=data["entity"]["type"],
            entity_id=data["entity"]["id"],
            pipeline_config_name=remote_configuration.pipeline_configuration_name,
        )

    def __init__(
            self,
            callback_name,
            display_name,
            tooltip,
            python_interpreter,
            descriptor_uri,
            pipeline_config_id,
            plugin_id,
            engine_name,
            entity_type,
            entity_id,
            pipeline_config_name
    ):
        """
        .. note:: This class is constructed by :class:`RemoteConfigurationLoader`.
            Do not construct objects by hand.

        :param str callback_name: Name of the associated toolkit command callback
        :param str display_name: Display name for command
        :param str tooltip: Tooltip
        :param str python_interpreter: Associated python interpreter
        :param str descriptor_uri: Associated descriptor URI
        :param int pipeline_config_id: Associated pipeline configuration id
        :param str plugin_id: Plugin id
        :param str engine_name: Engine name to execute command in
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str pipeline_config_name: Associated pipeline configuration name
        """
        super(RemoteCommand, self).__init__()

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        self._callback_name = callback_name
        self._display_name = display_name
        self._tooltip = tooltip
        self._python_interpreter = python_interpreter
        self._descriptor_uri = descriptor_uri
        self._pipeline_config_id = pipeline_config_id
        self._plugin_id = plugin_id
        self._engine_name = engine_name
        self._entity_type = entity_type
        self._entity_id = entity_id
        self._pipeline_config_name = pipeline_config_name

    def __repr__(self):
        """
        String representation
        """
        return "<RemoteCommand %s @ %s %s %s>" % (
            self._display_name,
            self._engine_name,
            self._entity_type,
            self._entity_id
        )

    @classmethod
    def from_string(cls, data):
        """
        Creates a :class:`RemoteCommand` instance given some serialized data.

        :param str data: Data created by :meth:`to_string`
        :returns: Remote Command instance.
        :rtype: :class:`RemoteCommand`
        """
        data = data.encode("utf-8")
        data = cPickle.loads(data)
        return RemoteCommand(
            callback_name=data["callback_name"],
            display_name=data["display_name"],
            tooltip=data["tooltip"],
            python_interpreter=data["python_interpreter"],
            descriptor_uri=data["descriptor_uri"],
            pipeline_config_id=data["pipeline_config_id"],
            plugin_id=data["plugin_id"],
            engine_name=data["engine_name"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            pipeline_config_name=data["pipeline_config_name"]
        )


    def to_string(self):
        """
        Serializes the current object into a string.

        For use with :meth:`from_string`.

        :returns: String representing the current instance.
        :rtype: str
        """
        data = {
            "callback_name": self._callback_name,
            "display_name": self._display_name,
            "tooltip": self._tooltip,
            "python_interpreter": self._python_interpreter,
            "descriptor_uri": self._descriptor_uri,
            "pipeline_config_id": self._pipeline_config_id,
            "plugin_id": self._plugin_id,
            "engine_name": self._engine_name,
            "entity_type": self._entity_type,
            "entity_id": self._entity_id,
            "pipeline_config_name": self._pipeline_config_name
        }
        return cPickle.dumps(data)

    @property
    def pipeline_configuration_name(self):
        """
        The name of the Shotgun pipeline configuration this command is associated with,
        or ``None`` if no association exists.
        """
        return self._pipeline_config_name

    @property
    def display_name(self):
        """
        Display name, suitable for display in a menu.
        """
        return self._display_name

    @property
    def tooltip(self):
        """
        Associated help text tooltip.
        """
        return self._tooltip

    def execute(self):
        """
        Executes the remote command in a separate process.

        .. note:: The process will be launched in an asynchronous way.
            It is recommended that this command is executed in a worker thread.
        """
        # local imports becuase this is executed from runner scripts
        from .process_execution import ProcessRunner
        from .util import create_parameter_file

        logger.debug("%s: execute command" % self)

        script = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "scripts",
                "execute_command.py"
            )
        )

        args_file = create_parameter_file(
            dict(
                callback_name=self._callback_name,
                core_path=sgtk.bootstrap.ToolkitManager.get_core_python_path(),
                configuration_uri=self._descriptor_uri,
                pipeline_config_id=self._pipeline_config_id,
                plugin_id=self._plugin_id,
                engine_name=self._engine_name,
                entity_type=self._entity_type,
                entity_id=self._entity_id,
                bundle_cache_fallback_paths=self._bundle.engine.sgtk.bundle_cache_fallback_paths,
            )
        )

        args = [self._python_interpreter, script, args_file]
        logger.debug("Command arguments: %s", args)

        retcode, stdout, stderr = ProcessRunner.call_cmd(args)

        if retcode == 0:
            logger.error("Command stdout: %s", stdout)
            logger.error("Command stderr: %s", stderr)
        else:
            logger.error("Command failed: %s", args)
            logger.error("Failed command stdout: %s", stdout)
            logger.error("Failed command stderr: %s", stderr)
            logger.error("Failed command retcode: %s", retcode)
            raise Exception("%s\n\n%s" % (stdout, stderr))

        logger.debug("Execution complete.")

