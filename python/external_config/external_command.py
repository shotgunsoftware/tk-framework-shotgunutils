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
import sys
import cPickle
import sgtk
from sgtk.util.process import subprocess_check_output, \
    SubprocessCalledProcessError

logger = sgtk.platform.get_logger(__name__)



class ExternalCommand(object):
    """
    Represents an external Toolkit command (e.g. menu option).

    These objects are emitted by :class:`ExternalConfiguration`
    and are independent, decoupled, light weight objects that
    can be serialized and brought back easily.

    A command is executed via its :meth:`execute` method, which
    will launch it in the given engine.
    """

    # file format magic number
    FORMAT_GENERATION = 3

    @classmethod
    def serialize_command(cls, entity_type, command_name, properties):
        """
        Generates a data chunk given a set of standard
        Toolkit command data, as obtained from engine.commands.

        This can be passed to :meth:`create` in order to construct a
        :class:`ExternalCommand` instance.

        :param str entity_type: Shotgun entity type that the
            command is associated with.
        :param str command_name: Command name (the key
            name for an entry in engine.commands)
        :param dict properties: Properties dictionary
            as returned by the ``Engine.commands`` dictionary property.
        :returns: dictionary suitable to pass to :meth:`create`.
        """
        data = {
            "entity_type": entity_type,
            "callback_name": command_name,
            "display_name": properties.get("title") or command_name,
            "tooltip": properties.get("description") or "",
            "type": properties.get("type"),
            "icon": properties.get("icon"),
            "group": properties.get("group"),
            "group_default": properties.get("group_default") or False,

            # special for shotgun
            "sg_deny_permissions": properties.get("deny_permissions"),
            "sg_supports_multiple_selection": properties.get("supports_multiple_selection"),
        }

        return data

    @classmethod
    def enabled_on_current_os(cls, properties):
        """
        Checks toolkit command properties to determine
        if a command is enabled on the current os or Not.

        :param dict properties: Properties dictionary
            as returned by the ``Engine.commands`` dictionary property.
        :return: True if enabled, False if not.
        """
        if "deny_platforms" in properties:
            # setting can be Linux, Windows or Mac
            curr_os = {"linux2": "Linux", "darwin": "Mac", "win32": "Windows"}[sys.platform]
            if curr_os in properties["deny_platforms"]:
                # not enabled on this platform
                return False

        return True

    @classmethod
    def is_compatible(cls, data):
        """
        Determines if the given data is compatible.

        :param dict data: Serialized data
        :returns: True if the given data can be loaded, False if not.
        """
        try:
            return data.get("generation") == cls.FORMAT_GENERATION
        except Exception as e:
            return False

    @classmethod
    def create(cls, external_configuration, data, entity_id):
        """
        Creates a new :class:`ExternalCommand` instance based on the
        data in data. This data is generated by :meth:`serialize_command`.

        :param external_configuration: associated :class:`ExternalConfiguration` instance.
        :param dict data: Serialized data to be turned into an instance
        :param int entity_id: The data is cached in a general form, suitable for
            all entities. This means that the entity_id cached as part of the
            ``data`` parameter reflects the entity for which the caching process
            was executed and not necessarily the one we are after. This parameter
            indicates the actual entity id for which we want the commands to be
            assoiated.
        :returns: :class:`ExternalCommand` instance.
        """
        return ExternalCommand(
            callback_name=data["callback_name"],
            display_name=data["display_name"],
            tooltip=data["tooltip"],
            group=data["group"],
            is_group_default=data["group_default"],
            plugin_id=external_configuration.plugin_id,
            engine_name=external_configuration.engine_name,
            interpreter=external_configuration.interpreter,
            descriptor_uri=external_configuration.descriptor_uri,
            pipeline_config_id=external_configuration.pipeline_configuration_id,
            entity_type=data["entity_type"],
            entity_id=entity_id,
            pipeline_config_name=external_configuration.pipeline_configuration_name,
            sg_deny_permissions=data["sg_deny_permissions"],
            sg_supports_multiple_selection=data["sg_supports_multiple_selection"],
        )

    def __init__(
            self,
            callback_name,
            display_name,
            tooltip,
            group,
            is_group_default,
            plugin_id,
            interpreter,
            engine_name,
            descriptor_uri,
            pipeline_config_id,
            entity_type,
            entity_id,
            pipeline_config_name,
            sg_deny_permissions,
            sg_supports_multiple_selection,
    ):
        """
        .. note:: This class is constructed by :class:`ExternalConfigurationLoader`.
            Do not construct objects by hand.

        :param str callback_name: Name of the associated Toolkit command callback
        :param str display_name: Display name for command
        :param str tooltip: Tooltip
        :param str group: Group that this command belongs to
        :param bool is_group_default: Indicates that this is a group default
        :param str plugin_id: Plugin id
        :param str interpreter: Associated Python interpreter
        :param str engine_name: Engine name to execute command in
        :param str descriptor_uri: Associated descriptor URI
        :param int pipeline_config_id: Associated pipeline configuration id
        :param str entity_type: Associated entity type
        :param int entity_id: Associated entity id
        :param str pipeline_config_name: Associated pipeline configuration name
        :param list sg_deny_permissions: (Shotgun specific, legacy) List of permission
            groups to eclude this action from.
        :param bool sg_supports_multiple_selection: (Shotgun specific, legacy) Action
            supports multiple selection.
        """
        super(ExternalCommand, self).__init__()

        # keep a handle to the current app/engine/fw bundle for convenience
        self._bundle = sgtk.platform.current_bundle()

        self._callback_name = callback_name
        self._display_name = display_name
        self._tooltip = tooltip
        self._group = group
        self._is_group_default = is_group_default
        self._plugin_id = plugin_id
        self._interpreter = interpreter
        self._descriptor_uri = descriptor_uri
        self._pipeline_config_id = pipeline_config_id
        self._engine_name = engine_name
        self._entity_type = entity_type
        self._entity_id = entity_id
        self._pipeline_config_name = pipeline_config_name
        self._sg_deny_permissions = sg_deny_permissions
        self._sg_supports_multiple_selection = sg_supports_multiple_selection

    def __repr__(self):
        """
        String representation
        """
        return "<ExternalCommand %s @ %s %s %s>" % (
            self._display_name,
            self._engine_name,
            self._entity_type,
            self._entity_id
        )

    @classmethod
    def deserialize(cls, data):
        """
        Creates a :class:`ExternalCommand` instance given some serialized data.

        :param str data: Data created by :meth:`serialize`
        :returns: External Command instance.
        :rtype: :class:`ExternalCommand`
        :raises: :class:`RuntimeError` if data is not valid
        """
        data = cPickle.loads(data)

        return ExternalCommand(
            callback_name=data["callback_name"],
            display_name=data["display_name"],
            tooltip=data["tooltip"],
            group=data["group"],
            is_group_default=data["is_group_default"],
            plugin_id=data["plugin_id"],
            engine_name=data["engine_name"],
            interpreter=data["interpreter"],
            descriptor_uri=data["descriptor_uri"],
            pipeline_config_id=data["pipeline_config_id"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            pipeline_config_name=data["pipeline_config_name"],
            sg_deny_permissions=data["sg_deny_permissions"],
            sg_supports_multiple_selection=data["sg_supports_multiple_selection"],
        )

    def serialize(self):
        """
        Serializes the current object into a string.

        For use with :meth:`deserialize`.

        :returns: String representing the current instance.
        :rtype: str
        """
        data = {
            "callback_name": self._callback_name,
            "display_name": self._display_name,
            "group": self._group,
            "is_group_default": self._is_group_default,
            "tooltip": self._tooltip,
            "plugin_id": self._plugin_id,
            "engine_name": self._engine_name,
            "interpreter": self._interpreter,
            "descriptor_uri": self._descriptor_uri,
            "pipeline_config_id": self._pipeline_config_id,
            "entity_type": self._entity_type,
            "entity_id": self._entity_id,
            "pipeline_config_name": self._pipeline_config_name,
            "sg_deny_permissions": self._sg_deny_permissions,
            "sg_supports_multiple_selection": self._sg_supports_multiple_selection
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
    def system_name(self):
        """
        The system name for the command
        """
        return self._callback_name

    @property
    def display_name(self):
        """
        Display name, suitable for display in a menu.
        """
        return self._display_name

    @property
    def group(self):
        """
        Group command belongs to or None if not defined.
        """
        return self._group

    @property
    def is_group_default(self):
        """
        True if this command is a default action for a group.
        """
        return self._is_group_default

    @property
    def excluded_permission_groups_hint(self):
        """
        Legacy option used by some older Shotgun toolkit apps.
        Apps may hint a list of permission groups for which
        the app command should not be displayed.

        Returns a list of Shotgun permission groups (as strings)
        where this command is not appropriate.
        """
        return self._sg_deny_permissions or []

    @property
    def support_shotgun_multiple_selection(self):
        """
        Legacy flag indicated by some older Toolkit apps,
        indicating that the app can accept a list of
        entity ids to operate on rather than a single item.
        """
        return self._sg_supports_multiple_selection

    @property
    def tooltip(self):
        """
        Associated help text tooltip.
        """
        return self._tooltip

    def execute(self):
        """
        Executes the external command in a separate process.

        .. note:: The process will be launched in an synchronous way.
            It is recommended that this command is executed in a worker thread::

                # execute external command in a thread to not block
                # main thread execution
                worker = threading.Thread(target=action.execute)
                # if the python environment shuts down, no need
                # to wait for this thread
                worker.daemon = True
                # launch external process
                worker.start()

        :raises: :class:`RuntimeError` on execution failure.
        """
        # local imports because this is executed from runner scripts
        from .util import create_parameter_file

        logger.debug("%s: Execute command" % self)

        # prepare execution of the command in an external process
        # this will bootstrap Toolkit and execute the command.
        script = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "scripts",
                "external_runner.py"
            )
        )
        # pass arguments via a pickled temp file.
        args_file = create_parameter_file(
            dict(
                action="execute_command",
                callback_name=self._callback_name,
                configuration_uri=self._descriptor_uri,
                pipeline_config_id=self._pipeline_config_id,
                plugin_id=self._plugin_id,
                engine_name=self._engine_name,
                entity_type=self._entity_type,
                entity_id=self._entity_id,
                bundle_cache_fallback_paths=self._bundle.engine.sgtk.bundle_cache_fallback_paths,
                # the engine icon becomes the process icon
                icon_path=self._bundle.engine.icon_256,
            )
        )
        # compose the command we want to run
        args = [
            self._interpreter,
            script,
            sgtk.bootstrap.ToolkitManager.get_core_python_path(),
            args_file
        ]
        logger.debug("Command arguments: %s", args)

        try:
            output = subprocess_check_output(args)
            logger.debug("External execution complete. Output: %s" % output)
        except SubprocessCalledProcessError as e:
            # caching failed!
            raise RuntimeError("Error executing remote command %s: %s" % (self, e.output))
        finally:
            # clean up temp file
            sgtk.util.filesystem.safe_delete_file(args_file)



