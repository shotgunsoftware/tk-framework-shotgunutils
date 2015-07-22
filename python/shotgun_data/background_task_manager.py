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
import copy
import gc
import threading

import sgtk
from sgtk.platform.qt import QtCore
from sgtk import TankError

def monitor_lifetime(obj):
    obj.destroyed.connect(lambda: on_destroyed(type(obj).__name__))
def on_destroyed(name):
    pass
    #fw = sgtk.platform.current_bundle()
    #fw.log_debug("%s destroyed" % name)

class _BackgroundTask(object):
    """
    Container class for a single task.
    """
    def __init__(self, task_id, func, group, priority, *args, **kwargs):
        """
        Construction.

        :param task_id:     The unique id for this task
        :param func:        Function to execute to perform the task
        :param group:       The group that this task belongs to
        :param priority:    The priority this task should be run with
        :param args:        Additional arguments that should be passed to func
        :param kwargs:      Additional named arguments that should be passed to func
        """
        self._uid = task_id

        self._func = func
        self._args = args
        self._kwargs = kwargs

        self._group = group
        self._priority = priority

    def __repr__(self):
        """
        Create a string representation of this instance
        :returns:   A string representation of this instance
        """
        return "[%d, G:%s, P:%s] %s" % (self._uid, self._group, self._priority, self._func.__name__)

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
        Append the result from an upstream task to this tasks kwargs.

        :param result:  A dictionary containing the result from an upstream task
        """
        if result and isinstance(result, dict):
            self._kwargs = dict(self._kwargs.items() + result.items())

    def run(self):
        """
        Perform this task

        :returns:   The result of performing the task
        """
        return self._func(*self._args, **self._kwargs)

class _WorkerThreadA(QtCore.QThread):
    """
    Asynchrounous worker thread that can run tasks in a separate thread.  This implementation
    implements a custom run method that loops over tasks until asked to quit.
    """
    # Signal emitted when a task has completed successfully
    task_completed = QtCore.Signal(object, object)# task, result
    # Signal emitted when a task has failed
    task_failed = QtCore.Signal(object, object, object)# task, message, stacktrace

    def __init__(self, parent=None):
        """
        Construction

        :param parent:  The parent QObject for this thread
        """
        QtCore.QThread.__init__(self, parent)

        self._task = None
        self._process_tasks = True
        self._mutex = QtCore.QMutex()
        self._wait_condition = QtCore.QWaitCondition()

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
                    self.task_completed.emit(task_to_process, result)
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
                    self.task_failed.emit(task_to_process, str(e), tb)
                finally:
                    self._mutex.unlock()

class _WorkerThreadB(QtCore.QThread):
    """
    Asynchrounous worker thread that can run tasks in a separate thread.  This implementation
    uses a separate worker object that exists in the new thread and then uses signals to
    communicate back and forth.
    """
    class _Worker(QtCore.QObject):
        """
        Thread worker that just does work when requested.
        """
        # Signal emitted when a task has completed successfully
        task_completed = QtCore.Signal(object, object)# task, result
        # Signal emitted when a task has failed
        task_failed = QtCore.Signal(object, object, object)# task, message, stacktrace

        def __init__(self):
            """
            Construction
            """
            QtCore.QObject.__init__(self, None)

        def do_task(self, task):
            """
            Run a single task.
            """
            try:
                # run the task:
                result = task.run()
                # emit result:
                self.task_completed.emit(task, result)
            except Exception, e:
                # something went wrong so emit failed signal:
                tb = traceback.format_exc()
                self.task_failed.emit(task, str(e), tb)

    # Signal used to tell the worker that a task should be run
    work = QtCore.Signal(object)# task
    # Signal emitted when a task has completed successfully
    task_completed = QtCore.Signal(object, object)# task, result
    # Signal emitted when a task has failed
    task_failed = QtCore.Signal(object, object, object)# task, message, stacktrace

    def __init__(self, parent=None):
        """
        Construction

        :param parent:  The parent QObject for this thread
        """
        QtCore.QThread.__init__(self, parent)

        # create the worker instance:
        self._worker = _WorkerThreadB._Worker()
        monitor_lifetime(self._worker)

        # move the worker to the thread and then connect up the signals 
        # that are used to communicate with it: 
        self._worker.moveToThread(self)
        self.work.connect(self._worker.do_task)
        self._worker.task_failed.connect(self.task_failed)
        self._worker.task_completed.connect(self.task_completed)

    def run_task(self, task):
        """
        Run the specified task

        :param task:    The task to run
        """
        # signal the worker to run the task
        self.work.emit(task)

    def shut_down(self):
        """
        Shut down the thread and wait for it to exit before returning
        """
        self.quit()
        self.wait()
        # the worker has now been moved back into the main thread so lets
        # parent it to this thread so that it gets safely cleaned up
        self._worker.setParent(self)
        self._worker = None

    def run(self):
        """
        Normally we wouldn't need to override the run method as by default it just runs the event
        loop for the thread but due to a but in Qt pre-4.8 we have to do some extra stuff to make
        sure everything gets cleaned up properly!
        """
        # run the event loop:
        self.exec_()

        # before we quit, we need to move the worker back to the main thread.  This is to work around
        # issues with Qt pre-4.8 where any QObject.deleteLater's aren't executed on thread exit
        # which would result in the worker not being cleaned up correctly!
        self._worker.moveToThread(QtCore.QCoreApplication.instance().thread())

class BackgroundTaskManager(QtCore.QObject):
    """
    """
    # timeout when Shotgun connection fails
    _SG_CONNECTION_TIMEOUT_SECS = 20
    
    task_completed = QtCore.Signal(int, object, object)# uid, group, result
    task_failed = QtCore.Signal(int, object, str, str)# uid, group, msg, traceback
    task_group_finished = QtCore.Signal(object)# group

    def __init__(self, parent, start_processing=False, max_threads=8):
        """
        """
        QtCore.QObject.__init__(self, parent)

        #self._bundle = sgtk.platform.current_bundle()

        self._next_task_id = 0
        self._next_group_id = 0

        self._can_process_tasks = start_processing

        # the pending tasks, organized by priority
        self._pending_tasks_by_priority = {}

        # available threads and running tasks:
        self._max_threads = max_threads or 8
        self._all_threads = []
        self._available_threads = []
        self._running_tasks = {}

        # various task look-up maps:
        self._tasks_by_id = {}
        self._group_task_map = {}

        # track downstream dependencies for tasks:
        self._upstream_task_map = {}
        self._downstream_task_map = {}

        self._threadlocal_storage = threading.local()

        self._dbg_file = None#open("/Users/Alan_Dann/worfiles_v2_dbg_id%d.txt" % id(self), "w")
        
        monitor_lifetime(self)

    @property
    def shotgun_connection(self):
        """
        Get a Shotgun connection to use.  Creates a new Shotgun connection if the
        instance doesn't already have one.
        
        :returns:    The Shotgun connection for this instance
        """
        if not hasattr(self._threadlocal_storage, "shotgun"):
            # create our own private shotgun connection. This is because
            # the shotgun API isn't threadsafe, so running multiple models in parallel
            # (common) may result in side effects if a single connection is shared
            self._threadlocal_storage.shotgun = sgtk.util.shotgun.create_sg_connection()

            # set the maximum timeout for this connection for fluency
            self._threadlocal_storage.shotgun.config.timeout_secs = BackgroundTaskManager._SG_CONNECTION_TIMEOUT_SECS

        return self._threadlocal_storage.shotgun

    def next_group_id(self):
        """
        """
        group_id = self._next_group_id
        self._next_group_id += 1
        return group_id

    def _log(self, msg):
        """
        """
        #return
        #self._bundle.log_debug(msg)
        if self._dbg_file:
            self._dbg_file.write("%s\n" % msg)
            self._dbg_file.flush()
            
    def start_processing(self):
        """
        """
        self._can_process_tasks = True
        self._start_tasks()

    def pause_processing(self):
        """
        """
        self._can_process_tasks = False
        # and just let the current threads complete...

    def shut_down(self):
        """
        """
        self._log("Shutting down background task manager...")
        self._can_process_tasks = False

        # clear out all storage:
        self._running_tasks = {}
        self._available_threads = []
        self._pending_tasks_by_priority = {}
        self._tasks_by_id = {}
        self._group_task_map = {}
        self._upstream_task_map = {}
        self._downstream_task_map = {}

        # stop all worker threads and then wait for them to complete:
        #for thread in self._all_threads:
        #    #thread.stop(wait_for_completion = False)
        #    thread.quit()
        self._log("Waiting for %d background task manager threads to stop..." % len(self._all_threads))
        for thread in self._all_threads:
            thread.shut_down()
            #thread.deleteLater()
            #thread = None
            #thread.stop(wait_for_completion = True)
        self._log("Background task manager shut down successfully!")
        self._all_threads = []

    def add_task(self, func, priority=None, group=None, upstream_task_ids=None, **kwargs):
        """
        """
        upstream_task_ids = set(upstream_task_ids or [])

        # create a new task instance:
        task_id = self._next_task_id
        self._next_task_id += 1
        new_task = _BackgroundTask(task_id, func, group, priority, **kwargs)

        # add the task to the pending queue:
        self._pending_tasks_by_priority.setdefault(priority, []).append(new_task)

        # add tasks to various look-ups:
        self._tasks_by_id[new_task.uid] = new_task
        self._group_task_map.setdefault(group, set()).add(new_task.uid)

        # keep track of the task dependencies:
        self._upstream_task_map[new_task.uid] = upstream_task_ids
        for us_task_id in upstream_task_ids:
            self._downstream_task_map.setdefault(us_task_id, set()).add(new_task.uid)

        self._log("Added Task %s to be processed" % new_task)

        # and start the next task:
        self._start_tasks()

        return new_task.uid

    def add_pass_through_task(self, priority=None, group=None, upstream_task_ids=None, **kwargs):
        """
        """
        return self.add_task(self._task_pass_through, priority, group, upstream_task_ids, **kwargs)

    def stop_task(self, task_id, stop_upstream=True, stop_downstream=True):
        """
        """
        task = self._tasks_by_id.get(task_id)
        if task is None:
            return

        self._log("Stopping Task %s..." % task)
        self._stop_tasks([task], stop_upstream, stop_downstream)
        self._log(" > Task %s stopped!" % task)

    def stop_task_group(self, group, stop_upstream=True, stop_downstream=True):
        """
        """
        task_ids = self._group_task_map.get(group)
        if task_ids is None:
            return

        self._log("Stopping Task group %s..." % group)

        tasks_to_stop = []
        for task_id in task_ids:
            task = self._tasks_by_id.get(task_id)
            if task:
                tasks_to_stop.append(task)
        del self._group_task_map[group]
        self._stop_tasks(tasks_to_stop, stop_upstream, stop_downstream)
        
        self._log(" > Task group %s stopped!" % group)

    def stop_all_tasks(self):
        """
        """
        self._log("Stopping all tasks...")

        # we just need to clear all the lookups:
        self._running_tasks = {}
        self._pending_tasks_by_priority = {}
        self._tasks_by_id = {}
        self._group_task_map = {}
        self._upstream_task_map = {}
        self._downstream_task_map = {}
        
        self._log(" > All tasks stopped!")

    def _stop_tasks(self, tasks_to_stop, stop_upstream, stop_downstream):
        """
        """
        if not tasks_to_stop:
            return

        # copy the task list as we'll be modifying it:
        tasks_to_stop = list(tasks_to_stop)
        # and make sure we only stop each task once!!
        stopped_task_ids = set([task.uid for task in tasks_to_stop])

        while tasks_to_stop:
            task_to_stop = tasks_to_stop.pop(0)

            # get the up & downstream tasks to also stop depending on the flags:
            if stop_upstream and task_to_stop.uid in self._upstream_task_map:
                for us_task_id in self._upstream_task_map[task_to_stop.uid]:
                    us_task = self._tasks_by_id.get(us_task_id)
                    if not us_task or us_task.uid in stopped_task_ids:
                        # no task or already found
                        continue

                    tasks_to_stop.append(us_task)
                    stopped_task_ids.add(us_task_id)

            if stop_downstream and task_to_stop.uid in self._downstream_task_map:
                for ds_task_id in self._downstream_task_map[task_to_stop.uid]:
                    ds_task = self._tasks_by_id.get(ds_task_id)
                    if not ds_task or ds_task.uid in stopped_task_ids:
                        # no task or already found
                        continue

                    tasks_to_stop.append(ds_task)
                    stopped_task_ids.add(ds_task_id)

            # remove the task:
            self._remove_task(task_to_stop)

    def _get_worker_thread(self):
        """
        """
        if self._available_threads:
            # we can just use one of the available threads:
            return self._available_threads.pop()

        # no available threads so lets check our thread count:
        thread_count = len(self._all_threads)
        if thread_count >= self._max_threads:
            # no available threads left!
            return None

        # create a new worker thread:
        #thread = _WorkerThreadA(self)  # overriden run-method
        thread = _WorkerThreadB(self)   # separate thread-specific worker object
        monitor_lifetime(thread)
        thread.task_failed.connect(self._on_task_failed)
        thread.task_completed.connect(self._on_task_completed)
        self._all_threads.append(thread)

        # start the thread - this will just put it into wait mode:
        thread.start()

        # log some debug:
        self._log("Started new background worker thread (num threads=%d)" % len(self._all_threads))

        return thread

    def _start_tasks(self):
        """
        """
        # start tasks until we fail to start one for whatever reason:
        started = True
        while started:
            started = self._start_next_task()

    def _start_next_task(self):
        """
        """
        if not self._can_process_tasks:
            return False

        # figure out next task to start from the priority queue:
        task_to_process = None
        task_index = 0
        priorities = sorted(self._pending_tasks_by_priority.keys(), reverse=True)
        for priority in priorities:
            # iterate through the tasks and make sure we aren't waiting on the
            # completion of any upstream tasks:
            for ti, task in enumerate(self._pending_tasks_by_priority[priority]):
                awaiting_upstream_task_completion = False
                for us_task_id in self._upstream_task_map.get(task.uid, []):
                    if us_task_id in self._tasks_by_id:
                        # if the task is still in the tasks list then we're still awaiting
                        # completion of it!
                        awaiting_upstream_task_completion = True
                        break
                if awaiting_upstream_task_completion:
                    continue

                # ok, we've found the next task to process:
                task_to_process = task
                task_index = ti
                break

            if task_to_process:
                # no need to look any further!
                break

        if not task_to_process:
            # nothing to do!
            return False

        # we need a thread to do the work with:
        thread = self._get_worker_thread()
        if not thread:
            # looks like we can't do anything!
            return False

        self._log("Starting task %r with args: %s" % (task_to_process, task_to_process._kwargs.keys()))

        # ok, we have a thread so lets move the task from the priority queue to the running list:
        self._pending_tasks_by_priority[priority] = (self._pending_tasks_by_priority[priority][:task_index] 
                                                     + self._pending_tasks_by_priority[priority][task_index+1:])
        if not self._pending_tasks_by_priority[priority]:
            # no more tasks with this priority so also clean up the list
            del self._pending_tasks_by_priority[priority]
        self._running_tasks[task_to_process.uid] = (task_to_process, thread)

        num_tasks_left = 0
        for pending_tasks in self._pending_tasks_by_priority.values():
            num_tasks_left += len(pending_tasks)
        self._log(" > Currently running tasks: '%s' - %d left in queue" % (self._running_tasks.keys(), num_tasks_left))

        # and run the task
        thread.run_task(task_to_process)
        
        return True

    def _on_task_completed(self, task, result):
        """
        """
        try:
            # check that we should process this result:
            if task.uid in self._running_tasks:
                self._log("Task %r - completed" % (task))
                
                # if we have dependent tasks then update them:
                for ds_task_id in self._downstream_task_map.get(task.uid) or []:
                    ds_task = self._tasks_by_id.get(ds_task_id)
                    if not ds_task:
                        continue

                    # update downstream task with result
                    ds_task.append_upstream_result(result)

                # remove the task:
                group_finished = self._remove_task(task)

                # emit signal that this task is completed:
                self._log(" > [%d] Emitting task completed signal..." % task.uid)
                self.task_completed.emit(task.uid, task.group, result)
                self._log(" > [%d] Emitted task completed signal!" % task.uid)
                
                if group_finished:
                    self._log(" > [%s] Emitting group finished signal..." % task.group)
                    # also emit signal that the entire group is completed:
                    self.task_group_finished.emit(task.group)
                    self._log(" > [%s] Emitted group finished signal!" % task.group)
        finally:
            # move this task thread to the available threads list:
            self._available_threads.append(self.sender())

        # start processing of the next task:
        self._start_tasks()

    def _on_task_failed(self, task, msg, tb):
        """
        """
        try:
            # check that we should process this task:
            if task.uid in self._running_tasks:
                self._log("Task %r - failed: %s\n%s" % (task, msg, tb))

                # we need to emit the failed message for this task as well as any that have
                # upstream dependencies on this task!
                failed_tasks = [task]
                failed_task_ids = set([task.uid])
                finished_groups = set()
                while failed_tasks:
                    failed_task = failed_tasks.pop(0)

                    # find any downstream tasks:
                    for ds_task_id in self._downstream_task_map.get(failed_task.uid) or []:
                        ds_task = self._tasks_by_id.get(ds_task_id)
                        if not ds_task or ds_task.uid in failed_task_ids:
                            # no task or already found
                            continue
                        failed_tasks.append(ds_task)
                        failed_task_ids.add(ds_task.uid)

                    # remove the task:
                    group_finished = self._remove_task(failed_task)

                    # emit failed signal for the failed task:
                    self._log(" > [%d] Emitting task failed signal..." % failed_task.uid)
                    self.task_failed.emit(failed_task.uid, failed_task.group, msg, tb)
                    self._log(" > [%d] Emitted task failed signal!" % failed_task.uid)

                    if group_finished and failed_task.group not in finished_groups:
                        self._log(" > [%s] Emitting group finished signal..." % failed_task.group)
                        self.task_group_finished.emit(failed_task.group)
                        self._log(" > [%s] Emitted group finished signal!" % failed_task.group)
                        finished_groups.add(failed_task.group)
        finally:
            # move this task thread to the available threads list:
            self._available_threads.append(self.sender())

        # start processing of the next task:
        self._start_tasks()

    def _remove_task(self, task):#, is_dead=False):
        """
        """
        group_completed = False

        # fist remove from the running tasks - this will stop any signals being handled for this task
        if task.uid in self._running_tasks:
            del self._running_tasks[task.uid]

        # find and remove the task from the pending queue:
        if task.priority in self._pending_tasks_by_priority:
            for ti, p_task in enumerate(self._pending_tasks_by_priority.get(task.priority, [])):
                if p_task.uid == task.uid:
                    self._pending_tasks_by_priority[task.priority] = (self._pending_tasks_by_priority[task.priority][:ti] 
                                                                      + self._pending_tasks_by_priority[task.priority][ti+1:])
                    break 

            if not self._pending_tasks_by_priority[task.priority]:
                del self._pending_tasks_by_priority[task.priority]

        # remove this task from all other maps:
        if (task.group in self._group_task_map 
            and task.uid in self._group_task_map[task.group]):
            self._group_task_map[task.group].remove(task.uid)
            if not self._group_task_map[task.group]:
                group_completed = True
                del self._group_task_map[task.group]
        if task.uid in self._tasks_by_id:
            del self._tasks_by_id[task.uid]
        if task.uid in self._upstream_task_map:
            del self._upstream_task_map[task.uid]
        if task.uid in self._downstream_task_map:
            del self._downstream_task_map[task.uid]

        return group_completed

    def _task_pass_through(self, **kwargs):
        """
        """
        return kwargs
