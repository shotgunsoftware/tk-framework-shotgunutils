# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import tank
from .shotgunmodel import ShotgunModel

from tank.platform.qt import QtCore, QtGui

class SimpleShotgunModel(ShotgunModel):
    """
    Convenience wrapper around the Shotgun model for quick and easy access
    """
 
    def __init__(self, parent):
        """
        Constructor.
        
        The simple shotgun model will put the load spinner on top of the specified parent
        """
        ShotgunModel.__init__(self, parent, download_thumbs=True)
        self.set_overlay_parent(parent)
        
    def load_data(self, entity_type, fields):
        """
        Loads shotgun data into the model, using the cache if possible.
        """
        ShotgunModel._load_data(self, 
                               entity_type=entity_type, 
                               filters=filters, 
                               hierarchy=["code"],
                               fields=fields,
                               order=[])
        
        self._refresh_data()
        