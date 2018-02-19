# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


class RemoteConfigParseError(RuntimeError):
    """
    Indicates that the given serialized data is not usable
    """
    pass


class RemoteConfigNotAccessibleError(RuntimeError):
    """
    Indicates that a configuration is not accessible
    """
    pass
