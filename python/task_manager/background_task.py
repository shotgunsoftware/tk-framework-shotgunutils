# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
"""
import traceback

import sgtk
from sgtk.platform.qt import QtCore
from sgtk import TankError


class BackgroundTask(object):
    """
    Container class for a single task.

    A task is a Python callable (function/method/class) that takes some arguments, does some work and returns its
    result.  Each task will be run in a thread and tasks will be executed in priority order.

    For example:

        def task_fetch_status():
            return status_of_something()
        ...
        task_manager.add_task(task_fetch_status)
        ...
        def on_task_completion(task, group, result):
            status = result
            # do something with the status

    Additionally, tasks can be chained together so that the output of one task can be passed directly to the input
    of one or more downstream tasks.  To achieve this, the upstream task must returns it's result as a dictionary
    and this dictionary is added to the named parameters of any downstream tasks by the task manager.  Care should
    be taken when constructing these tasks that the result of one upstream task doesn't unintentionally overwrite
    any existing named parameters for a downstream task.

    For example:

        def task_fetch_status():
            return {"status":status_of_something()}
        def task_do_something(status):
            result = None
            if status:
                result = result_of_doing_something()
            return result
        ...
        status_task_id = task_manager.add_task(task_fetch_status, priority=1)
        work_task_id = task_manager.add_task(task_do_something, priority=2, upstream_task_ids = [status_task_id])
        ...
        def on_task_completion(task, group, result):
            if task.id = work_task_id:
                # do something with the result
                ...

    Upstream tasks can be fed into multiple down-stream tasks and the task priority can also be different so for
    example all status fetches could be set to happen before all do-somethings by setting the priority accordingly.
    Down-stream tasks will also not start before it's upstream tasks have completed.
    """

    def __init__(self, task_id, cbl, group, priority, args, kwargs):
        """
        Construction.

        :param task_id:     The unique id for this task
        :param cbl:         Callable to execute to perform the task
        :param group:       The group that this task belongs to
        :param priority:    The priority this task should be run with
        :param args:        Additional arguments that should be passed to func
        :param kwargs:      Additional named arguments that should be passed to func
        """
        self._uid = task_id

        self._cbl = cbl
        self._args = args or []
        self._kwargs = kwargs or {}

        self._group = group
        self._priority = priority

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns:   A string representation of this instance
        """
        return "[%d, G:%s, P:%s] %s" % (
            self._uid,
            self._group,
            self._priority,
            self._cbl.__name__,
        )

    @property
    def uid(self):
        """
        :returns:   The unique id of this task
        """
        return self._uid

    @property
    def group(self):
        """
        :returns:   The group this task belongs to
        """
        return self._group

    @property
    def priority(self):
        """
        :returns:   The priority for this task
        """
        return self._priority

    def append_upstream_result(self, result):
        """
        Append the result from an upstream task to this tasks kwargs.  In order for the result to be appended
        to the task it must be a dictionary.  Each entry in the result dictionary is then added to the tasks
        named parameters so care should be taken when building the tasks that named parameters for a downstream
        task are not unintentionally overwritten by the result of an upstream task.

        :param result:  A dictionary containing the result from an upstream task.  If result is not a dictionary
                        then it will be ignored.
        """
        if result and isinstance(result, dict):
            self._kwargs = dict(list(self._kwargs.items()) + list(result.items()))

    def run(self):
        """
        Perform this task

        :returns:   The result of performing the task
        """
        return self._cbl(*self._args, **self._kwargs)
