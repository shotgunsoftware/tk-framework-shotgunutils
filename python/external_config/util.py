# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
import cPickle as pickle
import tempfile
import os
import uuid
import sgtk
import pprint

logger = sgtk.platform.get_logger(__name__)


def create_parameter_file(data):
    """
    Pickles and dumps out a temporary file containing the provided data structure.

    :param data: The data to serialize to disk.
    :returns: File path to a temporary file
    :rtype: str
    """
    param_file = os.path.join(tempfile.gettempdir(), "sgtk_%s.cmd" % uuid.uuid4().hex)

    with open(param_file, "wb") as fh:
        pickle.dump(data, fh, pickle.HIGHEST_PROTOCOL)

    logger.debug(
        "Created parameter file '%s' with the following data: %s" % (
            param_file,
            pprint.pformat(data)
        )
    )

    return param_file
