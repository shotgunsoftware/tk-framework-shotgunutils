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
from tank.platform.qt import QtCore, QtGui

# precalculated for performance
HAS_QVARIANT = hasattr(QtCore, "QVariant")
HAS_QSTRING = hasattr(QtCore, "QString")

def get_sg_data(item):
    """
    Helper method.
    
    Retrieves the shotgun data associated with the object passed in.
    The object passed in is typically a QStandardItem or a QModelIndex
    or any other object which implements a data(ROLE) method signature.
    
    :param item: QStandardItem or QModelIndex or similar
    :returns: Shotgun data or None if no data was associated
    """
    from .shotgunmodel import ShotgunModel
    return get_sanitized_data(item, ShotgunModel.SG_DATA_ROLE)

def get_sanitized_data(item, role):
    """
    Alternative method to the data() methods offered on 
    QStandardItem and QModelIndex. This helper method ensures
    that complex data is returned in a correct and consistent 
    fashion. All string data is returned as utf-8 encoded byte
    streams and complex data structures are returned as 
    python native objects (rather than QVariants).

    Using this method whenever working with complex model data
    ensures that the code behaves consistently across pyside
    and pyqt and is using utf-8 encoded strings rather than
    unicode.
    
    :param item: QStandardItem or QModelIndex or similar
    :param role: Role identifier to be passed to the item object's data() method.
    :returns: native python objects
    """
    try:
        return sanitize_qt(item.data(role))
    except AttributeError:
        return None
    
def sanitize_qt(val):
    """
    Converts a value to a tk friendly and consistent representation.
    - QVariants are converted to native python structures
    - QStrings are coverted to utf-8 encoded strs
    - unicode objets are converted to utf-8 encoded strs
    
    :param val: input object
    :returns: cleaned up data 
    """
    
    # test things in order of probable occurrence for speed
    if val is None:
        # optimisation
        pass
    
    elif isinstance(val, unicode):
        # unicode object
        val = val.encode("UTF-8")

    elif HAS_QSTRING and isinstance(val, QtCore.QString):
        # convert any QStrings to utf-8 encoded strings
        val = val.toUtf8()
    
    elif HAS_QVARIANT and isinstance(val, QtCore.QVariant):
        # convert any QVariant to their python native equivalents
        val = val.toPyObject()
        val = __unicode_to_utf8(val)    
    
    else:
        # recursively go through the value and convert all 
        # unicode objects into utf-8 encoded strings.
        val = __unicode_to_utf8(val)
    
    return val


def __unicode_to_utf8(val):
    """
    Recursive conversion of all unicode strings to utf-8      
    """
    if isinstance(val, unicode):
        return val.encode("UTF-8")
    
    elif isinstance(val, list):
        return [ __unicode_to_utf8(d) for d in val ]
    
    elif isinstance(val, dict):
        new_val = {}
        for (k,v) in val.iteritems():
            new_val[k] = __unicode_to_utf8(v)
        return new_val

    else:
        return val        
