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
import os
import sys
import urlparse
import cPickle as pickle
from sgtk.platform.qt import QtCore
from sgtk import TankError
from ..shotgun_model import sanitize_qt

class UserSettings(object):
    """
    Handles global settings per user
    """

    SCOPE_GLOBAL = 0
    SCOPE_SITE = 1
    SCOPE_PROJECT = 2
    SCOPE_CONFIG = 3
    SCOPE_INSTANCE = 4

    def __init__(self, bundle):
        """
        Creates a settings manager. Using this manager you have easy access to
        saved settings. 
        
        :param bundle: app, engine or framework object to associate the settings with.
        """
        
        self.__fw = sgtk.platform.current_bundle()
        
        self.__settings = QtCore.QSettings("Shotgun Software", bundle.name)
        self.__fw.log_debug("Initialized settings manager for '%s'" % bundle.name)
        
        # now organize various keys
        
        # studio level settings - base it on the server host name
        _, sg_hostname, _, _, _ = urlparse.urlsplit(self.__fw.shotgun.base_url)
        self.__site_key = sg_hostname
        
        # project level settings
        pc = self.__fw.sgtk.pipeline_configuration
        self.__project_key = "%s:%s" % (self.__site_key, pc.get_project_disk_name()) 
        
        # config level settings
        self.__pipeline_config_key = "%s:%s" % (self.__project_key, pc.get_name())
        
        # instance level settings
        if isinstance(bundle, sgtk.platform.Application):
            # based on the environment name, engine instance name and app instance name
            self.__instance_key = "%s:%s:%s:%s" % (self.__pipeline_config_key,
                                                   bundle.engine.environment["name"], 
                                                   bundle.engine.instance_name, 
                                                   bundle.instance_name)
            
        elif isinstance(bundle, sgtk.platform.Engine):
            # based on the environment name & engine instance name
            self.__instance_key = "%s:%s:%s" % (self.__pipeline_config_key,
                                                bundle.engine.environment["name"], 
                                                bundle.instance_name)
            
        elif isinstance(bundle, sgtk.platform.Framework):
            # based on the environment name & framework name
            self.__instance_key = "%s:%s:%s" % (self.__pipeline_config_key,
                                                bundle.engine.environment["name"], 
                                                bundle.name)
            
        else:
            raise TankError("Not sure how to handle bundle type %s. "
                            "Please pass an App, Engine or Framework object." % bundle)
            
    ########################################################################################
    # public methods
            
    def store(self, name, value, scope=SCOPE_GLOBAL):
        """
        Stores a setting for an app. This setting is tied to the current login.
        
        :param name: Name of the setting to store
        :param value: Value to store. Use simple types such as ints, strings, dicts etc.
        :param scope: The scope for this settings value, as defined by the constants belonging to this class.
          
        """
        full_name = self.__resolve_settings_name(name, scope)
        self.__fw.log_debug("User Settings Manager: Storing %s" % full_name)
        value_str = pickle.dumps(value)
        self.__settings.setValue(full_name, value_str)
    
    def retrieve(self, name, default=None, scope=SCOPE_GLOBAL):
        """
        Retrieves a setting for a particular app for the current login.
        
        :param name: Name of the setting to store
        :param default: Default value to return if the setting is not stored.
        :param scope: The scope associated with this setting
        :returns: The stored value, None if no value is available  
        """
        full_name = self.__resolve_settings_name(name, scope)
        
        try:
            raw_value = sanitize_qt(self.__settings.value(full_name))

            if raw_value is None:
                resolved_val = default
            else:
                resolved_val = pickle.loads(raw_value)
        except Exception, e:
            self.__fw.log_warning("Error retrieving value for stored user setting '%s' - reverting to "
                                  "to default value. Error details: %s" % (full_name, e))
            resolved_val = default
        
        self.__fw.log_debug("User Settings Manager: Retrieving %s" % full_name)
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
        elif scope == self.SCOPE_INSTANCE:
            return "%s:%s" % (self.__instance_key, name)
        else:
            raise TankError("Unknown scope id %s!" % scope)
