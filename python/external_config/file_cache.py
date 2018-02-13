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
import cPickle as pickle
import hashlib
import sgtk

logger = sgtk.platform.get_logger(__name__)


def load_cache(identifier_dict):
    """
    Loads a cache from disk and returns it
    """
    # try to load
    cache_path = get_cache_path(identifier_dict)
    return load_cache_file(cache_path)

@sgtk.LogManager.log_timing
def load_cache_file(cache_path):
    """
    Loads a cache from disk and returns it
    """
    # try to load
    logger.debug("Loading from disk: %s" % cache_path)
    content = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as fh:
                content = pickle.load(fh)
        except Exception, e:
            logger.debug("Cache '%s' not valid - ignoring. Details: %s" % (cache_path, e))
    else:
        logger.debug("No cache found on disk.")

    return content

@sgtk.LogManager.log_timing
def delete_cache(identifier_dict):
    """
    Deletes a cache file from disk
    """
    cache_path = get_cache_path(identifier_dict)
    logger.debug("Deleting from disk: %s" % cache_path)
    sgtk.util.filesystem.safe_delete_file(cache_path)


def write_cache_file(identifier_dict, data):
    """
    Saves the current cache to disk.
    """
    cache_path = get_cache_path(identifier_dict)
    return write_cache(cache_path, data)


@sgtk.LogManager.log_timing
@sgtk.util.filesystem.with_cleared_umask
def write_cache(path, data):
    """
    Saves the current cache to disk.
    """
    logger.debug("Saving cache to disk: %s" % path)

    # try to create the cache folder with as open permissions as possible
    cache_dir = os.path.dirname(path)
    sgtk.util.filesystem.ensure_folder_exists(cache_dir)

    try:
        with open(path, "wb") as fh:
            pickle.dump(data, fh)

        # and ensure the cache file has got open permissions
        os.chmod(path, 0666)

    except Exception, e:
        logger.debug("Could not write '%s'. Details: %s" % (path, e))

    logger.debug("Completed save of %s. Size %s bytes" % (path, os.path.getsize(path)))


def get_cache_path(identifier_dict):
    """
    Create a filename
    """
    params_hash = hashlib.md5()
    for (k, v) in identifier_dict.iteritems():
        params_hash.update(str(k))
        params_hash.update(str(v))

    cache_location = sgtk.platform.current_bundle().cache_location

    if "prefix" in identifier_dict:
        data_cache_path = os.path.join(
            cache_location,
            "external_cfg",
            identifier_dict["prefix"],
            "%s.pkl" % params_hash.hexdigest()
        )
    else:
        data_cache_path = os.path.join(
            cache_location,
            "external_cfg",
            "%s.pkl" % params_hash.hexdigest()
        )

    logger.debug(
        "Resolved cache path for %s to %s" % (identifier_dict, data_cache_path)
    )
    return data_cache_path
