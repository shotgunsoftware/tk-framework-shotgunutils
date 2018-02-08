# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
import os
import datetime
import json
import time
import hashlib

# toolkit imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

logger = sgtk.platform.get_logger(__name__)


@sgtk.LogManager.log_timing
def load_cache(identifier_dict):
    """
    Loads a cache from disk and returns it
    """
    # try to load
    cache_path = get_cache_path(identifier_dict)
    logger.debug("Loading from disk: %s" % cache_path)
    content = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as fh:
                content = json.load(fh)
        except Exception, e:
            logger.debug("Cache '%s' not valid - ignoring. Details: %s" % (cache_path, e))
    else:
        logger.debug("No cache found on disk.")

    return content


@sgtk.LogManager.log_timing
@sgtk.util.filesystem.with_cleared_umask
def save_cache(identifier_dict, data):
    """
    Saves the current cache to disk.
    """
    cache_path = get_cache_path(identifier_dict)
    logger.debug("Saving cache to disk: %s" % cache_path)

    # try to create the cache folder with as open permissions as possible
    cache_dir = os.path.dirname(cache_path)
    sgtk.util.filesystem.ensure_folder_exists(cache_dir)

    try:
        with open(cache_path, "wb") as fh:
            json.dump(data, fh)

        # and ensure the cache file has got open permissions
        os.chmod(cache_path, 0666)

    except Exception, e:
        logger.debug("Could not write '%s'. Details: %s" % (cache_path, e))

    logger.debug("Completed save of %s. Size %s bytes" % (cache_path, os.path.getsize(cache_path)))



def get_cache_path(identifier_dict):
    """
    Create a filename
    """
    params_hash = hashlib.md5()
    for (k, v) in identifier_dict.iteritems():
        params_hash.update(str(k))
        params_hash.update(str(v))

    cache_location = sgtk.platform.current_bundle().cache_location
    data_cache_path = os.path.join(
        cache_location,
        "multi_context",
        "%s.json" % params_hash.hexdigest()
    )
    logger.debug(
        "Resolved cache path for %s to %s" % (identifier_dict, data_cache_path)
    )
    return data_cache_path
