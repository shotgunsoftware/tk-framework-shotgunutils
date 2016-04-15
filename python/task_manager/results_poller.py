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
Results dispatcher for the background task manager.
"""

import Queue
from sgtk.platform.qt import QtCore
import sgtk


class TaskCompletedEvent(object):
    """
    Event sent when a task is succesfully completed.
    """

    def __init__(self, worker_thread, task, result, results_queue):
        """
        Constructor.

        :param worker_thread: Worker thread that completed sucessfully.
        :param task: Task id of the completed task.
        :param result: Result published by the task.
        :param results_queue: Results queue to signal task completion.
        """
        self._worker_thread = worker_thread
        self._task = task
        self._result = result
        self._results_queue = results_queue

    def execute(self):
        """
        Signals the task_completed event on the results queue.
        """
        self._results_queue.task_completed.emit(self._worker_thread, self._task, self._result)


class TaskFailedEvent(object):
    """
    Event sent when a task is succesfully completed.
    """

    def __init__(self, worker_thread, task, msg, traceback_, results_queue):
        """
        Constructor.

        :param worker_thread: Worker thread that completed sucessfully.
        :param task: Task id of the completed task.
        :param msg: Error message from the worker thread.
        :param traceback_: Traceback from  the worker thread error.
        :param results_queue: Results queue to signal task failure.
        """
        self._worker_thread = worker_thread
        self._task = task
        self._msg = msg
        self._traceback = traceback_
        self._results_queue = results_queue

    def execute(self):
        """
        Signals the task_failed event on the results queue.
        """
        self._results_queue.task_failed.emit(self._worker_thread, self._task, self._msg, self._traceback)


class ResultsDispatcher(QtCore.QThread):
    """
    Dispatches events synchronously to the thread that owns this object.

    Signalling between two different threads in PySide is broken in several versions
    of PySide. There are very subtle race conditions that arise when there is a lot
    of signalling between two threads. Some of these things have been fixed in later
    versions of PySide, but most hosts integrate PySide 1.2.2 and lower, which are
    victim of this race condition.

    The background task manager does a lot on inter-threads communications and
    therefore can easily fall pray to these deadlocks that exist within PySide.

    Therefore, we instead use Qt's QMetaObject invokeMethod to carry information
    to the background task manager thread in a thread-safe manner, since it
    doesn't exhibit the bad behaviour from PySide's signals.
    """

    class _ShutdownHint(object):
        """
        Hint to dispatcher that it should shut down.
        """

    # Emitted when a task is completed.
    task_completed = QtCore.Signal(object, object, object)
    # Emitted when a task has failed.
    task_failed = QtCore.Signal(object, object, object, object)

    def __init__(self, parent=None):
        """
        Constructor.

        :param parent:  The parent QObject for this thread
        """
        QtCore.QThread.__init__(self, parent)
        # Results that will need to be dispatched to the background task
        # manager.
        self._results = Queue.Queue()
        self._bundle = sgtk.platform.current_bundle()

    def _log(self, msg):
        """
        Logs a message at the debug level.
        """
        self._bundle.log_debug("Results Queue: %s" % msg)

    def shut_down(self):
        """
        Shuts down the result dispatcher thread.
        """
        # Add an event in the queue that will tell the thread to terminate.
        self._results.put(self._ShutdownHint())
        self._log("Sent _ShutdownHint to consumer thread.")
        # Do not wait for the thread here!!! The backgroud thread is invoking
        # the main thread synchronously. Waiting here would introduce
        # a deadlock because the main thread would be waiting for the dispatcher
        # to end and the dispatcher would be waiting for his events to
        # be processed by the main thread.

    def run(self):
        """
        Executes callbacks for each task result.
        """
        while True:
            # Wait for the next result
            self._event = self._results.get(block=True)
            # If we're told that we need to quit, do it.
            if isinstance(self._event, self._ShutdownHint):
                self._log("Consumer thread received ShutdownHint.")
                break

            # In order to keep this loop simple, we will assume that the background
            # task manager is always opened for business. The manager already ignores
            # out of bounds events so no need to complicate the code here as well.

            # A thread's object self.thread() is actually the thread that created
            # the thread object. In this case, self's thread affinity is the
            # same as the background task manager. Therefore, using QMetaObject
            # to invoke a method in the thread of self means invoking it
            # in the thread of the background manager as well. self._fn will
            # therefore be executed in the correct thread.

            # A note on thread safety. We could have used a QueuedConnection here
            # in order to implement a fire and forget scheme, which would be ideal.
            # However, this wouldn't bring a lot of advantages. Since the only communication
            # channel between the dispatcher and the backgroud manager is the self._fn
            # variable, it means that the access to that variable must be made thread-safe
            # so that it is not updated before the event is executed in the main thread.
            # Doing so would require adding locks and complicate the code further.
            # Using the builtin lock from the invoker here is much easier to understand.

            # We could also add the events to invoke into a second queue meant to
            # be consumed by the background task manager, but it would only add
            # complexity to the design and it wouldn't provide any significant speed gain.
            QtCore.QMetaObject.invokeMethod(self, "_do_invoke", QtCore.Qt.BlockingQueuedConnection)

    @QtCore.Slot()
    def _do_invoke(self):
        """
        Executes the event to dispatch.
        """
        try:
            self._event.execute()
            self._event
        except Exception:
            self._bundle.log_exception("Exception thrown while reporting ended task.")

    def produce_event(self, event):
        """
        Called by background threads to notify that a task has ended.

        :param event: Event to notify
        """
        self._results.put(event)
