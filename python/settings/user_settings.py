# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from tank_vendor import six
from sgtk.platform.qt import QtCore
from sgtk import TankError
from ..shotgun_model import sanitize_qt


class UserSettings(object):
    """
    Handles settings per user. This class is a toolkit specific wrapper
    around QSettings, making it easy to store and retrieve settings.

    Each setting is handled using a *Scope* which allows the client code
    to determine the scale of the setting. Using the scope, you can define
    global settings (which is the default), per project, per site, per
    configuration and per app instance.
    """

    # scope constants
    SCOPE_GLOBAL = 0  # one setting to rule them all!
    SCOPE_SITE = 1  # one setting per site
    SCOPE_PROJECT = 2  # one setting per project
    SCOPE_CONFIG = 3  # one setting per pipeline config
    SCOPE_INSTANCE = 4  # one setting per app instance
    SCOPE_ENGINE = 5  # one setting per engine (name, not instance)

    def __init__(self, bundle):
        """
        Constructor

        :param bundle: app, engine or framework object to associate the settings with.
        """

        self.__fw = sgtk.platform.current_bundle()

        self.__settings = QtCore.QSettings("Shotgun Software", bundle.name)
        self.__fw.log_debug("Initialized settings manager for '%s'" % bundle.name)

        # now organize various keys

        # studio level settings - base it on the server host name
        _, sg_hostname, _, _, _ = six.moves.urllib.parse.urlsplit(
            self.__fw.sgtk.shotgun_url
        )
        self.__site_key = sg_hostname

        # project level settings
        pc = self.__fw.sgtk.pipeline_configuration
        self.__project_key = "%s:%s" % (self.__site_key, pc.get_project_disk_name())

        # config level settings
        self.__pipeline_config_key = "%s:%s" % (self.__project_key, pc.get_name())

        # instance level settings
        if isinstance(bundle, sgtk.platform.Application):
            # based on the environment name, engine instance name and app instance name
            self.__instance_key = "%s:%s:%s:%s" % (
                self.__pipeline_config_key,
                bundle.engine.environment["name"],
                bundle.engine.instance_name,
                bundle.instance_name,
            )
            self.__engine_key = bundle.engine.name

        elif isinstance(bundle, sgtk.platform.Engine):
            # based on the environment name & engine instance name
            self.__instance_key = "%s:%s:%s" % (
                self.__pipeline_config_key,
                bundle.environment["name"],
                bundle.instance_name,
            )
            self.__engine_key = bundle.name

        elif isinstance(bundle, sgtk.platform.Framework):
            # based on the environment name & framework name
            self.__instance_key = "%s:%s:%s" % (
                self.__pipeline_config_key,
                bundle.engine.environment["name"],
                bundle.name,
            )
            self.__engine_key = bundle.engine.name

        else:
            raise TankError(
                "Not sure how to handle bundle type %s. "
                "Please pass an App, Engine or Framework object." % bundle
            )

    ########################################################################################
    # public methods

    def store(self, name, value, scope=SCOPE_GLOBAL):
        """
        Stores a setting for an app. This setting is tied to the current login.

        :param name: Name of the setting to store
        :param value: Value to store. Use simple types such as ints, strings, dicts etc.
                      In the interest of cross pyside/pyqt compatibility, any QStrings or QVariants
                      passed in via value will be converted to strs and native python types. Unicode
                      strs will be converted to utf-8.
        :param scope: The scope for this settings value, as defined by the constants belonging to this class.

        """
        full_name = self.__resolve_settings_name(name, scope)
        self.__fw.log_debug("User Settings Manager: Storing %s" % full_name)
        try:
            # Weird behaviour incoming:
            # When QSettings sees a value that it deems to complicated for Qt,
            # it pickles it!
            # Pickling a class for example would force QSetting to pickle the value
            # first. But so does passing in a bytes object!
            # If you are running Python 3, then the protocol used will be 3, which
            # becomes an issue if you're switching to Python 2 to read the same setting
            # since QSetting will first try to unpickle the value and protocol 3
            # didn't exist in Python 2.
            #
            # This very small scripts reproduces that weird behavior:
            #
            # from PySide2 import QtCore
            # import sys
            #
            # settings = QtCore.QSettings("test")
            #
            # if sys.version_info[0] == 2:
            #     print(settings.value("test_value"))
            # else:
            #     settings.setValue(
            #         "test_value",
            #         b"binary value"
            #     )
            #
            # Running this script once with Python 3 will write to QSettings and running
            # it with Python 2 will read it and raise a pickler error, even tough we
            # never used the pickler in our code in the first place.
            #
            # To get around this, we need to write a string inside the QSettings, so
            # use sgtk.util.pickle
            value_str = sgtk.util.pickle.dumps(sanitize_qt(value))
            self.__settings.setValue(full_name, six.ensure_str(value_str))
        except Exception as e:
            self.__fw.log_warning(
                "Error storing user setting '%s'. Error details: %s" % (full_name, e)
            )

    def retrieve(self, name, default=None, scope=SCOPE_GLOBAL):
        """
        Retrieves a setting for a particular app for the current login.

        :param name: Name of the setting to store.
        :param default: Default value to return if the setting is not stored.
        :param scope: The scope associated with this setting.
        :returns: The stored value, default if the value is not available
        """
        full_name = self.__resolve_settings_name(name, scope)

        self.__fw.log_debug("User Settings Manager: Retrieving %s" % full_name)

        try:
            raw_value = self.__settings.value(full_name)

            if raw_value is None:
                resolved_val = default
            else:
                resolved_val = sgtk.util.pickle.loads(six.ensure_binary(raw_value))
                resolved_val = sanitize_qt(resolved_val)
        except Exception as e:
            self.__fw.log_warning(
                "Error retrieving value for stored user setting '%s' - reverting to "
                "to default value. Error details: %s" % (full_name, e)
            )
            resolved_val = default

        return resolved_val

    ########################################################################################
    # private methods

    def __resolve_settings_name(self, name, scope):
        """
        Resolve the settings name to use depending on the given scope.

        :param name: settings name
        :param scope: settings scope
        :returns: string with a settings name including scope
        """
        if scope == self.SCOPE_GLOBAL:
            return name
        elif scope == self.SCOPE_SITE:
            return "%s:%s" % (self.__site_key, name)
        elif scope == self.SCOPE_PROJECT:
            return "%s:%s" % (self.__project_key, name)
        elif scope == self.SCOPE_CONFIG:
            return "%s:%s" % (self.__pipeline_config_key, name)
        elif scope == self.SCOPE_ENGINE:
            return "%s:%s" % (self.__engine_key, name)
        elif scope == self.SCOPE_INSTANCE:
            return "%s:%s" % (self.__instance_key, name)
        else:
            raise TankError("Unknown scope id %s!" % scope)
