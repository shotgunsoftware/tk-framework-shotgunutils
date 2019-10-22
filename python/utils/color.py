# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from sgtk.platform.qt import QtGui


def color_mix(c1, c1_strength, c2, c2_strength):
    """Convenience method for making a color from 2 existing colors.

    This is primarily used to prevent hardcoding of colors that don't work in
    other color palettes. The idea is that you can provide a color from the
    current widget palette and shift it toward another color. For example,
    you could get a red-shifted text color by supplying the windowText color
    for a widget as color 1, and the full red as color 2. Then use the strength
    args to weight the resulting color more toward the windowText or full red.
    It's still important to test the resulting colors in multiple color schemes.

    :param c1: QtGui.QColor 1
    :param c1_strength: int factor of the strength of this color
    :param c2: QtGui.QColor 2
    :param c2_strength: int factor of the strength of this color

    :returns: The mixed color.
    :rtype: ``QtGui.QColor``
    """

    total = c1_strength + c2_strength

    r = ((c1.red() * c1_strength) + (c2.red() * c2_strength)) / total
    g = ((c1.green() * c1_strength) + (c2.green() * c2_strength)) / total
    b = ((c1.blue() * c1_strength) + (c2.blue() * c2_strength)) / total

    return QtGui.QColor(r, g, b)
