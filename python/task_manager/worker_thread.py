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
from threading import Lock, Condition, Thread


class WorkerThread(Thread):
    """
    Asynchronous worker thread that can run tasks in a separate thread.  This implementation
    implements a custom run method that loops over tasks until asked to quit.
    """

    def __init__(self, results_dispatcher):
        """
        Construction

        :param results_dispatcher: Results dispatcher from the background task manager.
        :param parent:  The parent QObject for this thread
        """
        super(WorkerThread, self).__init__()

        self._task = None
        self._process_tasks = True
        self._mutex = Lock()
        self._wait_condition = Condition(self._mutex)
        self._results_dispatcher = results_dispatcher

    def run_task(self, task):
        """
        Run the specified task

        :param task:    The task to run
        """
        with self._mutex:
            self._task = task
            self._wait_condition.notify_all()

    def shut_down(self):
        """
        Shut down the thread and wait for it to exit before returning
        """
        with self._mutex:
            self._results_dispatcher = None
            self._process_tasks = False
            self._wait_condition.notify_all()
        self.join()

    def run(self):
        """
        The main thread run function.  Loops over tasks until asked to exit.
        """
        try:
            while True and self._results_dispatcher is not None:
                # get the next task to process:
                task_to_process = None
                with self._mutex:
                    while self._process_tasks and not task_to_process:
                        task_to_process = self._task
                        self._task = None
                        if not task_to_process:
                            # wait until we have something to do...
                            self._wait_condition.wait()

                    if not self._process_tasks:
                        # stop processing
                        break

                # run the task:
                try:
                    result = task_to_process.run()

                    with self._mutex:
                        if not self._process_tasks:
                            break
                        # emit the result (non-blocking):
                        self._results_dispatcher.emit_completed(
                            self, task_to_process, result
                        )
                except Exception as e:
                    # something went wrong so emit failed signal:
                    with self._mutex:
                        if not self._process_tasks:
                            break
                        tb = traceback.format_exc()
                        # emit failed signal (non-blocking):
                        self._results_dispatcher.emit_failure(
                            self, task_to_process, str(e), tb
                        )
        except RuntimeError as e:
            # We have a situation in Qt5 where it appears that the thread
            # is being garbage collected more quickly than in Qt4. In this
            # case, we can be pretty sure that we're being shut down, and
            # can simply return out of the run loop.
            return
