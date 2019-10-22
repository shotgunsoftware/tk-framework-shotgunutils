# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk


class ShotgunModelError(sgtk.TankError):
    """Base class for all shotgun model exceptions"""

    pass


class CacheReadVersionMismatch(ShotgunModelError):
    """Indicates that a cache file is incompatible with this code"""

    pass


class ShotgunModelDataError(ShotgunModelError):
    """Error used for all data storage related issues."""

    pass
