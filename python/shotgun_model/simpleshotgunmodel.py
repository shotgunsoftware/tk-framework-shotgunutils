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
from .shotgunoverlaymodel import ShotgunOverlayModel

from sgtk.platform.qt import QtCore, QtGui

class SimpleShotgunModel(ShotgunOverlayModel):
    """
    Convenience wrapper around the Shotgun model for quick and easy access.
    
    When you quickly want to display some shotgun data in a QT view of some kind,
    this class may come in handy. Simply instantiate it and call load_data whenever
    you want to load up a new shotgun query into your view.
    
    It derives from ShotgunModel so all the customization methods available in the
    normal ShotgunModel can also be subclassed from this class.
    """
 
    def __init__(self, parent):
        """
        Constructor.
        
        The simple shotgun model will put the load spinner on top of the specified parent.
        
        :param parent: QWidget which this model will be parented under. This widget will
                       also be used to paint a spinner and display error messages.
        """
        ShotgunOverlayModel.__init__(self, parent, parent, download_thumbs=True)
        
    def load_data(self, entity_type, filters=None, fields=None):
        """
        Loads shotgun data into the model, using the cache if possible.
        The model is not nested and the first field that is specified
        via the fields parameter (code by default) will be used as the default
        name for all model items. 
        
        :param entity_type: Shotgun Entity Type to load data for
        :param filters: Shotgun API find-style filter list. If no list is specified, all records
                        for the given entity type will be retrieved.
        :param fields: List of Shotgun fields to retrieve. If not spefified, the 'code' field
                       will be retrieved.
        """
        filters = filters or []
        fields = fields or ["code"]
        hierarchy = [fields[0]]
        ShotgunOverlayModel._load_data(self, entity_type, filters, hierarchy, fields)
        self._refresh_data()
        