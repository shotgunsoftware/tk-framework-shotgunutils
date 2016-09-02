# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


from tank.platform.qt import QtGui

from .util import sanitize_qt
from .util import get_sg_data as util_get_sg_data

class ShotgunStandardItem(QtGui.QStandardItem):
    """
    Special implementation of StandardItem which bridges PyQt and PySide.

    .. warning:: Do *NOT* construct instances of this class and then manually
        them to an existing ``ShotgunQueryModel`` (or one of its subclasses).
        Doing so will likely causes memory issues or issues centered around
        garbage collection as the model classes take a lot of care to know
        exactly which items exist, when they're added/removed etc.
    """

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns: A string representation of this instance
        """
        return "<%s %s>" % (self.__class__.__name__, self.text())

    def get_sg_data(self):
        """
        Retrieves the shotgun data associated with this item.
        Only leaf nodes have shotgun data associated with them.
        On intermediate nodes, None will be returned.

        :returns: Shotgun data or None if no data was associated
        """
        return util_get_sg_data(self)

    ########################################################################################
    # overridden methods

    def statusTip(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).statusTip(*args, **kwargs)
        return sanitize_qt(val)

    def text(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).text(*args, **kwargs)
        return sanitize_qt(val)

    def toolTip(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).toolTip(*args, **kwargs)
        return sanitize_qt(val)

    def whatsThis(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).whatsThis(*args, **kwargs)
        return sanitize_qt(val)

    def accessibleDescription(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).accessibleDescription(*args, **kwargs)
        return sanitize_qt(val)

    def accessibleText(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).accessibleText(*args, **kwargs)
        return sanitize_qt(val)

    def data(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItem, self).data(*args, **kwargs)
        return sanitize_qt(val)
