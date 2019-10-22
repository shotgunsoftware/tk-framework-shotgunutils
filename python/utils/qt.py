# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


def safe_delete_later(widget):
    """
    Will call the deleteLater method on the given widget, but only if
    running in a Qt4 environment. This allows us to proactively delete
    widgets in Qt4, but protects us from garbage collection issues
    associated with doing the same in PySide2/Qt5.

    :param widget: The widget to potentially call deleteLater on.
    """
    from sgtk.platform.qt import QtCore

    if QtCore.__version__.startswith("4."):
        widget.deleteLater()
