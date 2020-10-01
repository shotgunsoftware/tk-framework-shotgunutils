# Copyright (c) 2020 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk

from tank_test.tank_test_base import setUpModule  # noqa
from base_test import TestShotgunUtilsFramework


class TestBackgroundTaskManager(TestShotgunUtilsFramework):
    """
    Test the background task manager.
    """

    def setUp(self):
        super(self.__class__, self).setUp()
        self.BackgroundTaskManager = self.framework.import_module(
            "task_manager"
        ).BackgroundTaskManager

    def test_priority_sorting(self):
        """
        Ensure priority is respected. Higher priority task get executed first.
        """
        # Use only one thread at a time so threads are launch in the order of the priority
        # we're aiming for.
        self._manager = self.BackgroundTaskManager(self._qapp, max_threads=1)
        # Callback which will validate that tasks end in the right order.
        self._manager.task_completed.connect(self._assert_priority_expected_cb)

        # Spawn a few tasks with different priorities. None should be equivalent to 0.
        self._expected_priorities = [-100, -1, None, 1, 2, 10]
        task_ids = []
        # Create the task out of order just to make sure that the background task manager
        # is actually sorting them.
        for priority in [None, 2, 10, 1, -1, -100]:
            task_id = self._manager.add_task(
                lambda prio=priority: prio, priority=priority
            )
            task_ids.append(task_id)

        self._is_stopping = False
        self._stop_background_task_manager()

        # Add a task that will shut down the background task manager.
        # Note that since the manager will be shutdown by the callback, it means
        # no task completed callback will be invoked.
        self._stop_background_task_manager_task_id = self._manager.add_task(
            self._stop_background_task_manager_task, upstream_task_ids=task_ids
        )
        # Start processing tasks and launch the main application loop.
        self._manager.start_processing()
        self._qapp.exec_()

        # If we end up here, than all tasks should have popped themselves of
        # the list in order and we should have an empty one.
        assert self._expected_priorities == []

    def _stop_background_task_manager_task(self):
        """
        Shuts down the background task manager
        """
        # Raises a flag that the single shot timer will catch
        # and close the thread.
        self._is_stopping = True

    def _stop_background_task_manager(self):
        """
        Stops the background task manager.
        """
        if not self._is_stopping:
            sgtk.platform.qt.QtCore.QTimer.singleShot(
                1000, self._stop_background_task_manager
            )
            return

        self._manager.shut_down()
        # Processes events until the dispatcher thread is done.
        while self._manager._results_dispatcher.isFinished() is False:
            sgtk.platform.qt.QtGui.QApplication.processEvents()
        # Now we can quit the app.
        self._qapp.quit()

    def _assert_priority_expected_cb(self, task_id, _, priority_result):
        """
        Ensure the task that has just finished had the expected priority.
        """
        if task_id == self._stop_background_task_manager_task_id:
            return
        assert priority_result == self._expected_priorities[-1]
        self._expected_priorities.pop()
