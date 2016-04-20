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

    def __init__(self, results_dispatcher, parent=None):
        """
        Construction

        :param results_dispatcher: Results dispatcher from the background task manager.
        :param parent:  The parent QObject for this thread
        """
        QtCore.QThread.__init__(self, parent)

        self._task = None
        self._process_tasks = True
        self._mutex = QtCore.QMutex()
        self._wait_condition = QtCore.QWaitCondition()
        self._results_dispatcher = results_dispatcher

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
        self._results_dispatcher = None
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
                    self._results_dispatcher.emit_completed(self, task_to_process, result)
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
                    self._results_dispatcher.emit_failure(self, task_to_process, str(e), tb)
                finally:
                    self._mutex.unlock()
