# Copyright (c) 2018 Shotgun Software Inc.
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

# if this key is found in the cache, a folder
# will this name will be generated as part of
# the cache path
FOLDER_PREFIX_KEY = "prefix"

def load_cache(identifier_dict):
    """
    Loads a cache from disk given a dictionary of identifiers,
    e.g. ``{shot: 123, project: 345}`` etc. A hash value will
    be computed based on the identifier and used to find and
    load a cached payload.

    :param dict identifier_dict: Dictionary of identifying data.
    :returns: Cached data as generated by :meth:`write_cache`.
    """
    cache_path = get_cache_path(identifier_dict)
    return load_cache_file(cache_path)

@sgtk.LogManager.log_timing
def load_cache_file(cache_path):
    """
    Loads a cache from disk given a file path generated by
    :meth:`get_cache_path`. If the file is not found,
    ``None`` is returned.

    :param str cache_path: Path to a cache file on disk.
    :returns: Cached data as generated by :meth:`write_cache`
        or ``None`` if file is not found.
    """
    logger.debug("Loading from disk: %s" % cache_path)
    content = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as fh:
                content = pickle.load(fh)
        except Exception as e:
            logger.debug("Cache '%s' not valid - ignoring. Details: %s" % (cache_path, e), exec_info=True)
    else:
        logger.debug("No cache found on disk.")

    return content

@sgtk.LogManager.log_timing
def delete_cache(identifier_dict):
    """
    Deletes a cache given its identifier.
    If no cache file exists, nothing is executed.

    :param dict identifier_dict: Dictionary of identifying data.
    """
    cache_path = get_cache_path(identifier_dict)
    logger.debug("Deleting from disk: %s" % cache_path)
    sgtk.util.filesystem.safe_delete_file(cache_path)


def write_cache(identifier_dict, data):
    """
    Writes cache data to disk given a dictionary of identifiers,
    e.g. ``{shot: 123, project: 345}`` etc. A hash value will
    be computed based on the identifier and used to determine
    the location for where the cache file will be saved

    :param dict identifier_dict: Dictionary of identifying data.
    :param data: Data to save.
    """
    cache_path = get_cache_path(identifier_dict)
    return write_cache_file(cache_path, data)


@sgtk.LogManager.log_timing
@sgtk.util.filesystem.with_cleared_umask
def write_cache_file(path, data):
    """
    Writes a cache to disk given a file path generated by
    :meth:`get_cache_path`.

    :param str path: Path to a cache file on disk.
    :param data: Data to save.
    """
    logger.debug("Saving cache to disk: %s" % path)

    # try to create the cache folder with as open permissions as possible
    cache_dir = os.path.dirname(path)
    sgtk.util.filesystem.ensure_folder_exists(cache_dir)

    try:
        with open(path, "wb") as fh:
            pickle.dump(data, fh)

        # and ensure the cache file has got open permissions
        os.chmod(path, 0o666)

    except Exception as e:
        logger.debug("Could not write '%s'. Details: %s" % (path, e), exec_info=True)
    else:
        logger.debug("Completed save of %s. Size %s bytes" % (path, os.path.getsize(path)))


def get_cache_path(identifier_dict):
    """
    Create a file name given a dictionary of identifiers,
    e.g. ``{shot: 123, project: 345}`` etc. A hash value will
    be computed based on the identifier and used to determine
    the path. The current user will be added to the hash in
    order to make it user-centric.

    If the hash key 'prefix' is detected, this will be added
    to the path as a parent folder to the cache file. This provides
    a simple way to organize different caches into different folders.

    :param dict identifier_dict: Dictionary of identifying data.
    :retuns: path on disk, relative to the current bundle's cache location.
    """
    params_hash = hashlib.md5()
    for (k, v) in identifier_dict.iteritems():
        params_hash.update(str(k))
        params_hash.update(str(v))

    # add current user to hash
    user = sgtk.get_authenticated_user()
    if user and user.login:
        params_hash.update(user.login)

    cache_location = sgtk.platform.current_bundle().cache_location

    if FOLDER_PREFIX_KEY in identifier_dict:
        # if FOLDER_PREFIX_KEY is found in the hash,
        # this will be added as a folder to the path
        data_cache_path = os.path.join(
            cache_location,
            "external_cfg",
            identifier_dict[FOLDER_PREFIX_KEY],
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
