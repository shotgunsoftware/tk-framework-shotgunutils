# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from .util import sanitize_qt

from tank.platform.qt import QtGui


class ShotgunStandardItemBase(QtGui.QStandardItem):
    """
    Special implementation of StandardItem which bridges PyQt and PySide.
    """

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns: A string representation of this instance
        """
        return "<%s %s>" % (self.__class__.__name__, self.text())

    ########################################################################################
    # overridden methods

    def statusTip(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).statusTip(*args, **kwargs)
        return sanitize_qt(val)

    def text(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).text(*args, **kwargs)
        return sanitize_qt(val)

    def toolTip(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).toolTip(*args, **kwargs)
        return sanitize_qt(val)

    def whatsThis(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).whatsThis(*args, **kwargs)
        return sanitize_qt(val)

    def accessibleDescription(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).accessibleDescription(*args, **kwargs)
        return sanitize_qt(val)

    def accessibleText(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).accessibleText(*args, **kwargs)
        return sanitize_qt(val)

    def data(self, *args, **kwargs):
        """
        Base class override which runs sanitize_qt() on the returned data
        """
        val = super(ShotgunStandardItemBase, self).data(*args, **kwargs)
        return sanitize_qt(val)
