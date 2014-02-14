# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Shotgun Utils Framework
-----------------------------

This framework contains a collection of utilities to make it easier to 
write Shotgun based User Interfaces. In summary, these are the contents
of this framework:

Shotgun Model
-------------

Inside the shotgun_model module you'll find the ShotgunModel class which 
is a QT Model class which makes it easy to hook up a particular Shotgun
query to a view container in QT. This makes it easy to show a list of 
shotgun objects in a UI. The model is cached and responsive and loads
data in the background for performance.


Shotgun View Utilities
----------------------

If you feel that the visuals that you get back from a standard
QTreeView or QListView are not sufficient, for your needs, 
the view utilities provide a collection of tools to help you quickly build
consistent and nice looking user QViews. These are typically used in conjunction
with the ShotgunModel but this is not a requirement.

- The WidgetDelegate helper class makes it easy to connect a QWidget of
  your choice with a View. The WidgetDelegate will use your specified 
  widget when the view is drawn and updated. This allows for full control
  of the visual appearance of any view.
- For consistency reasons we also supply a couple of simple widget classes
  that are meant to be used in conjunction with the WidgetDelegate. By
  using these widgets in your code you get the same look and feel as all
  other apps that use the widgets.  
"""

import sgtk

class WidgetFramework(sgtk.platform.Framework):
    
    ##########################################################################################
    # init and destroy
            
    def init_framework(self):
        self.log_debug("%s: Initializing..." % self)
    
    def destroy_framework(self):
        self.log_debug("%s: Destroying..." % self)
    
    
