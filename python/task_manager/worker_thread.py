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
Worker thread for the background manager.
"""

import traceback

from sgtk.platform.qt import QtCore


class WorkerThread(QtCore.QThread):
    """
    Asynchronous worker thread that can run tasks in a separate thread.  This implementation
    implements a custom run method that loops over tasks until asked to quit.
    """

    def __init__(self, rp, parent=None):
        """
        Construction

        :param trp: Results poller from the background task manager.
        :param parent:  The parent QObject for this thread
        """
        QtCore.QThread.__init__(self, parent)

        self._task = None
        self._process_tasks = True
        self._mutex = QtCore.QMutex()
        self._wait_condition = QtCore.QWaitCondition()

        self._result_poller = rp

    def run_task(self, task):
        """
        Run the specified task

        :param task:    The task to run
        """
        self._mutex.lock()
        try:
            self._task = task
        finally:
            self._mutex.unlock()
        self._wait_condition.wakeAll()

    def shut_down(self):
        """
        Shut down the thread and wait for it to exit before returning
        """
        self._result_poller = None
        self._mutex.lock()
        try:
            self._process_tasks = False
        finally:
            self._mutex.unlock()
        self._wait_condition.wakeAll()
        self.wait()

    def run(self):
        """
        The main thread run function.  Loops over tasks until asked to exit.
        """
        while True:
            # get the next task to process:
            task_to_process = None
            self._mutex.lock()
            try:
                while self._process_tasks and not task_to_process:
                    task_to_process = self._task
                    self._task = None
                    if not task_to_process:
                        # wait until we have something to do...
                        self._wait_condition.wait(self._mutex)

                if not self._process_tasks:
                    # stop processing
                    break
            finally:
                self._mutex.unlock()

            # run the task:
            try:
                result = task_to_process.run()

                self._mutex.lock()
                try:
                    if not self._process_tasks:
                        break
                    # emit the result (non-blocking):
                    self._result_poller.queue_task_completed(self, task_to_process, result)
                finally:
                    self._mutex.unlock()
            except Exception, e:
                # something went wrong so emit failed signal:
                self._mutex.lock()
                try:
                    if not self._process_tasks:
                        break
                    tb = traceback.format_exc()
                    # emit failed signal (non-blocking):
                    self._result_poller.queue_task_failed(self, task_to_process, str(e), tb)
                finally:
                    self._mutex.unlock()


# class WorkerThreadSeparateThread(QtCore.QThread):
#     """
#     Asynchronous worker thread that can run tasks in a separate thread.  This implementation
#     uses a separate worker object that exists in the new thread and then uses signals to
#     communicate back and forth.
#
#     Note, this recipe exhibits odd behaviour in PyQt.  When initially created, the instance returned
#     in the assignment isn't always of type WorkerThreadB!, e.g.:
#
#         thread = WorkerThreadB()
#         assert isinstance(thread, WorkerThreadB) # this should never assert!
#
#     Although this recipe is recommended in Qt as it is arguably a more 'correct' use of QThreads, it
#     is currently advised that the the overridden run recipe (WorkerThreadA) be used instead whilst
#     Toolkit needs to support PyQt.
#     """
#     class _Worker(QtCore.QObject):
#         """
#         Thread worker that just does work when requested.
#         """
#         # Signal emitted when a task has completed successfully
#         task_completed = QtCore.Signal(object, object)# task, result
#         # Signal emitted when a task has failed
#         task_failed = QtCore.Signal(object, object, object)# task, message, stacktrace
#
#         def __init__(self):
#             """
#             Construction
#             """
#             QtCore.QObject.__init__(self, None)
#
#         def do_task(self, task):
#             """
#             Run a single task.
#             """
#             try:
#                 # run the task:
#                 result = task.run()
#                 # emit result:
#                 self.task_completed.emit(task, result)
#             except Exception, e:
#                 # something went wrong so emit failed signal:
#                 tb = traceback.format_exc()
#                 self.task_failed.emit(task, str(e), tb)
#
#     # Signal used to tell the worker that a task should be run
#     work = QtCore.Signal(object)# task
#     # Signal emitted when a task has completed successfully
#     task_completed = QtCore.Signal(object, object)# task, result
#     # Signal emitted when a task has failed
#     task_failed = QtCore.Signal(object, object, object)# task, message, stacktrace
#
#     def __init__(self, parent=None):
#         """
#         Construction
#
#         :param parent:  The parent QObject for this thread
#         """
#         QtCore.QThread.__init__(self, parent)
#
#         # create the worker instance:
#         self._worker = WorkerThreadB._Worker()
#
#         # move the worker to the thread and then connect up the signals
#         # that are used to communicate with it:
#         self._worker.moveToThread(self)
#         self.work.connect(self._worker.do_task)
#         self._worker.task_failed.connect(self.task_failed)
#         self._worker.task_completed.connect(self.task_completed)
#
#     def run_task(self, task):
#         """
#         Run the specified task
#
#         :param task:    The task to run
#         """
#         # signal the worker to run the task
#         self.work.emit(task)
#
#     def shut_down(self):
#         """
#         Shut down the thread and wait for it to exit before returning
#         """
#         self.quit()
#         self.wait()
#         # the worker has now been moved back into the main thread so lets
#         # parent it to this thread so that it gets safely cleaned up
#         self._worker.setParent(self)
#         self._worker = None
#
#     def run(self):
#         """
#         Normally we wouldn't need to override the run method as by default it just runs the event
#         loop for the thread but due to a but in Qt pre-4.8 we have to do some extra stuff to make
#         sure everything gets cleaned up properly!
#         """
#         # run the event loop:
#         self.exec_()
#
#         # before we quit, we need to move the worker back to the main thread.  This is to work around
#         # issues with Qt pre-4.8 where any QObject.deleteLater's aren't executed on thread exit
#         # which would result in the worker not being cleaned up correctly!
#         self._worker.moveToThread(QtCore.QCoreApplication.instance().thread())
