# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from tank.platform.qt import QtCore

from tank_vendor import six
from tank_vendor.six.moves import range

# precalculated for performance
HAS_QVARIANT = hasattr(QtCore, "QVariant")
HAS_QSTRING = hasattr(QtCore, "QString")
HAS_QBYTEARRAY = hasattr(QtCore, "QByteArray")


def get_sg_data(item):
    """
    Helper method.

    Retrieves the shotgun data associated with the object passed in.
    The object passed in is typically a QStandardItem or a QModelIndex
    or any other object which implements a data(ROLE) method signature.

    :param item: QStandardItem or QModelIndex or similar
    :returns: Shotgun data or None if no data was associated
    """
    from .shotgun_model import ShotgunModel

    return get_sanitized_data(item, ShotgunModel.SG_DATA_ROLE)


def get_sanitized_data(item, role):
    """
    Alternative method to the data() methods offered on
    QStandardItem and QModelIndex. This helper method ensures
    that complex data is returned in a correct and consistent
    fashion. All string data is returned as utf-8 encoded byte
    streams and complex data structures are returned as
    python native objects (rather than QVariants).

    Using this method whenever working with complex model data
    ensures that the code behaves consistently across pyside
    and pyqt and is using utf-8 encoded strings rather than
    unicode.

    :param item: QStandardItem or QModelIndex or similar
    :param role: Role identifier to be passed to the item object's data() method.
    :returns: native python objects
    """
    try:
        return sanitize_qt(item.data(role))
    except AttributeError:
        return None


def sanitize_for_qt_model(val):
    """
    Useful when you have shotgun (or other) data and want to
    prepare it for storage as role data in a model.

    Qt/pyside/pyqt automatically changes the data to be unicode
    according to internal rules of its own, sometimes resulting in
    unicode errors. A safe strategy for storing unicode data inside
    Qt model roles is therefore to ensure everything is converted to
    unicode prior to insertion into the model. This method ensures
    that. All string values will be coonverted to unicode. UTF-8
    is assumed for all strings:

    in:  {"a":"aaa", "b": 123, "c": {"x":"y", "z":"aa"}, "d": [ {"x":"y", "z":"aa"} ] }
    out: {'a': u'aaa', 'c': {'x': u'y', 'z': u'aa'}, 'b': 123, 'd': [{'x': u'y', 'z': u'aa'}]}

    This method is the counterpart to sanitize_qt() which is the reciprocal
    of this operation. When working with Qt models and shotgun data,
    we recommend the following best practices:

    - when sg data is inserted into a role in model, run it through
      sanitize_for_qt_model() first
    - When taking it back out again, run it through sanitize_qt()

    :param val: value to convert
    :returns: sanitized data
    """

    if isinstance(val, list):
        return [sanitize_for_qt_model(d) for d in val]

    elif isinstance(val, dict):
        new_val = {}
        for (k, v) in six.iteritems(val):
            # go through dictionary and convert each value separately
            new_val[k] = sanitize_for_qt_model(v)
        return new_val

    elif six.PY2 and isinstance(val, str):
        return val.decode("UTF-8")

    # for everything else, just pass through
    return val


def sanitize_qt(val):
    """
    Converts a value to a tk friendly and consistent representation.
    - QVariants are converted to native python structures
    - QStrings are coverted to utf-8 encoded strs
    - unicode objets are converted to utf-8 encoded strs

    :param val: input object
    :returns: cleaned up data
    """

    # test things in order of probable occurrence for speed
    if val is None:
        return None

    elif six.PY2 and isinstance(val, unicode):
        return val.encode("UTF-8")

    elif HAS_QSTRING and isinstance(val, QtCore.QString):
        # convert any QStrings to utf-8 encoded strings
        # note the cast to str because pyqt returns a QByteArray
        return str(val.toUtf8())

    elif HAS_QBYTEARRAY and isinstance(val, QtCore.QByteArray):
        # convert byte arrays to strs
        return str(val)

    elif HAS_QVARIANT and isinstance(val, QtCore.QVariant):
        # convert any QVariant to their python native equivalents
        val = val.toPyObject()
        # and then sanitize this
        return sanitize_qt(val)

    elif isinstance(val, list):
        return [sanitize_qt(d) for d in val]

    elif isinstance(val, dict):
        new_val = {}
        for (k, v) in six.iteritems(val):
            # both keys and values can be bad
            safe_key = sanitize_qt(k)
            safe_val = sanitize_qt(v)
            new_val[safe_key] = safe_val
        return new_val

    # QT Version: 5.9.5
    # PySide Version: 5.9.0a1
    # The value should be `int` but it is `long`.
    # longs do not exist in Python 3, so we need to cast those.
    elif six.PY2 and isinstance(val, long):
        val = int(val)
        return val
    else:
        return val


def compare_shotgun_data(a, b):
    """
    Compares two shotgun data structures.
    Both inputs are assumed to contain utf-8 encoded data.

    :returns: True if a is same as b, false otherwise
    """
    if isinstance(a, dict):
        # input is a dictionary
        if isinstance(a, dict) and isinstance(b, dict) and len(a) == len(b):
            # dicts are symmetrical. Compare items recursively.
            for a_key in a.keys():
                if not compare_shotgun_data(a.get(a_key), b.get(a_key)):
                    return False
        else:
            # dicts are misaligned
            return False

    elif isinstance(a, list):
        # input is a list
        if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            # lists are symmetrical. Compare items recursively.
            for idx in range(len(a)):
                if not compare_shotgun_data(a[idx], b[idx]):
                    return False
        else:
            # list items are misaligned
            return False

    # handle thumbnail fields as a special case
    # thumbnail urls are (typically, there seem to be several standards!)
    # on the form:
    # https://sg-media-usor-01.s3.amazonaws.com/xxx/yyy/
    #   filename.ext?lots_of_authentication_headers
    #
    # the query string changes all the times, so when we check if an item
    # is out of date, omit it.
    elif (
        isinstance(a, str)
        and isinstance(b, str)
        and a.startswith("http")
        and b.startswith("http")
        and ("amazonaws" in a or "AccessKeyId" in a)
    ):
        # attempt to parse values are urls and eliminate the querystring
        # compare hostname + path only
        url_obj_a = six.moves.urllib.parse.urlparse(a)
        url_obj_b = six.moves.urllib.parse.urlparse(b)
        compare_str_a = "%s/%s" % (url_obj_a.netloc, url_obj_a.path)
        compare_str_b = "%s/%s" % (url_obj_b.netloc, url_obj_b.path)
        if compare_str_a != compare_str_b:
            # url has changed
            return False

    elif a != b:
        # compare all other values using simple equality
        return False

    return True
