# Copyright (c) 2016 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import datetime

def create_human_readable_timestamp(dt, postfix=""):
    """
    Return the time represented by the argument as a string where the date portion is
    displayed as "Yesterday", "Today", or "Tomorrow" if appropriate.

    By default just the date is displayed, but additional formatting can be appended
    by using the postfix argument.

    :param dt: The date and time to convert to a string
    :type dt: :class:`datetime.datetime` or float

    :param postfix: What will be displayed after the date portion of the dt argument
    :type postfix: A strftime style String

    :returns: A String representing dt appropriate for display
    """
    # shotgun_model converts datetimes to floats representing unix time so
    # handle that as a valid value as well
    if isinstance(dt, float):
        dt = datetime.datetime.fromtimestamp(dt)

    # get the delta and components
    delta = datetime.datetime.now(dt.tzinfo) - dt

    if delta.days == 1:
        format = "Yesterday%s" % postfix
    elif delta.days == 0:
        format = "Today%s" % postfix
    elif delta.days == -1:
        format = "Tomorrow%s" % postfix
    else:
        # use the date formatting associated with the current locale
        format = "%%x%s" % postfix

    time_str = dt.strftime(format)
    return time_str

