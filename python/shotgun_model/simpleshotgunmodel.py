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
    
    Use this when you want to prototype data modeling or if your are looking 
    for a simple flat data set reflecting a shotgun query. All you need to do 
    is to instantiate the class (typically once, in your constructor) and then 
    call :meth:`load_data` to specify which shotgun query to load up in the model. 
    Subsequently call :meth:`load_data` whenever you wish to change the Shotgun 
    query associated with the model.

    This class derives from :class:`ShotgunModel` so all the customization methods 
    available in the normal :class:`ShotgunModel` can also be subclassed from this class.
    
    The simple shotgun model contains a progress spinner which will appear 
    whenever the object is doesn't have any data to display. This progress 
    spinner will be placed on top of the parent object specified in the 
    parent constructor parameter
    """
 
    def __init__(self, parent):
        """
        :param parent: QWidget which this model will be parented under. This widget will
                       also be used to paint a spinner and display error messages.
        :type parent: :class:`~PySide.QtGui.QWidget`                   
        """
        ShotgunOverlayModel.__init__(self, parent, parent, download_thumbs=True)
        
    def load_data(self, entity_type, filters=None, fields=None):
        """
        Loads shotgun data into the model, using the cache if possible.
        The model is not nested and the first field that is specified
        via the fields parameter (``code`` by default) will be used as the default
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
        
