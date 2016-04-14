# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Results queue poller
"""

import Queue
from sgtk.platform.qt import QtCore
import sgtk


class ResultsPoller(QtCore.QObject):
    """
    Polls a queue which holds the results posted from the worker threads.
    """

    # Emitted when a task is completed.
    task_completed = QtCore.Signal(object, object, object)
    # Emitted when a task has failed.
    task_failed = QtCore.Signal(object, object, object, object)

    _POLLING_INTERVAL = 100

    def __init__(self, parent=None):
        """
        Constructor.

        :param parent:  The parent QObject for this thread
        """
        QtCore.QObject.__init__(self, parent)
        # Results queue that will be polled
        self._results = Queue.Queue()
        # Create a timer with no interval. This means the timer will be invoked
        # only when the event queue is empty.
        self._timer = QtCore.QTimer(parent=self)
        self._timer.setInterval(self._POLLING_INTERVAL)
        # Since the event will be invoked as soon as the event queue is empty,
        # we should process the queue one item at a time to not interfere with the
        # ui responsivenes
        self._timer.timeout.connect(self._flush_events)
        self._bundle = sgtk.platform.current_bundle()

    def start(self):
        """
        Start polling for tasks that ended.
        """
        self._timer.start()

    def shut_down(self):
        """
        Stop polling for tasks that ended.
        """
        self._timer.stop()

    def _flush_events(self):
        """
        Executes callbacks for each task result.
        """
        try:
            # Get everything until the queue is empty.
            while True:
                # Get the next result from the queue
                result_tuple = self._results.get_nowait()
                try:
                    # Result tuples with 3 values are coming from succesful tasks.
                    if len(result_tuple) == 3:
                        self.task_completed.emit(*result_tuple)
                    else:
                        # Result tuples with 4 values are coming from succesful tasks.
                        self.task_failed.emit(*result_tuple)
                except Exception:
                    self._bundle.log_exception(
                        "Exception thrown while reporting completed task."
                    )
                    # Do not re-raise, simply process the remaining events.
        except Queue.Empty:
            # Queue is empty, nothing to do!
            pass

    def queue_task_completed(self, worker_thread, task, result):
        """
        Called by background threads to notify that a task has completed.

        :param worker_thread: Thread that completed the task.
        :param task: Task that was completed.
        :param result: Result produced by the thread.
        """
        self._results.put(
            (worker_thread, task, result)
        )

    def queue_task_failed(self, worker_thread, task, msg, traceback_):
        """
        Called by background threads to notify that a task has failed.

        :param worker_thread: Thread that completed the task.
        :param task: Task that failed.
        :param msg: Error message from the task,
        :param traceback_: Call stack from the task.
        """
        self._results.put(
            (worker_thread, task, msg, traceback_)
        )
