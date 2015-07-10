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

class Threaded(object):
    def __init__(self):
        self._lock = threading.Lock()

    @staticmethod
    def exclusive(func):
        """
        function decorator to ensure exclusive access to the function

        :param func:    The function to wrap
        :returns:       The return value from func
        """
        def wrapper(self, *args, **kwargs):
            """
            Decorator inner function - executes the function within a lock.
            :returns:    The return value from func
            """
            self._lock.acquire()
            try:
                return func(self, *args, **kwargs)
            finally:
                self._lock.release()
        return wrapper


class _BackgroundTask(Threaded):
    """
    """
    READY_TO_START, RUNNING, COMPLETED, FAILED = range(4)
    
    def __init__(self, task_id, func, group, priority, upstream_task_ids, **kwargs):
        """
        """
        Threaded.__init__(self)

        # read-only properties - no need to be thread exclusive
        self._uid = task_id
        self._func = func
        self._kwargs = kwargs
        self._group = group
        self._priority = priority
        self._upstream_task_ids = upstream_task_ids or []

        # read-write information - need to be thread exclusive
        self._status = _BackgroundTask.READY_TO_START
        self._result = None
        self._error_msg = None
        self._traceback = None

    def __repr__(self):
        return "[%d, G:%s, P:%s] %s" % (self._uid, self._group, self._priority, self._func.__name__)

    @property
    def uid(self):
        return self._uid

    @property
    def group(self):
        return self._group

    @property
    def priority(self):
        return self._priority
    
    @property
    def upstream_task_ids(self):
        return self._upstream_task_ids

    @property
    @Threaded.exclusive
    def status(self):
        return self._status

    @status.setter
    @Threaded.exclusive
    def status(self, value):
        self._status = value

    @property
    @Threaded.exclusive
    def result(self):
        return self._result
    
    @property
    @Threaded.exclusive
    def exception_msg(self):
        return self._error_msg
    
    @property
    @Threaded.exclusive
    def exception_traceback(self):
        return self._traceback

    @Threaded.exclusive
    def append_upstream_result(self, upstream_task):
        """
        """
        if upstream_task.uid not in self._upstream_task_ids:
            return
        # append result:
        self._kwargs = dict(self._kwargs.items() + upstream_task.result.items())
        # and remove from list:
        idx = self._upstream_task_ids.index(upstream_task.uid())
        del self._upstream_task_ids[idx]

    @Threaded.exclusive
    def set_completed(self, res):
        """
        """
        self._status = _BackgroundTask.COMPLETED
        self._result = res

    @Threaded.exclusive
    def set_failed(self, error_msg, tb):
        """
        """
        self._result = _BackgroundTask.FAILED
        self._error_msg = error_msg
        self._traceback = tb

    def run(self, shotgun_connection=None):
        """
        """
        res = None
        status = _BackgroundTask.FAILED
        error_msg = None
        tb = None

        try:
            # run the task:
            res = self._func(shotgun_connection = shotgun_connection, **self._kwargs) or {}
            self.set_completed(res)
        except Exception, e:
            # something went wrong so emit failed signal:
            self.set_failed(str(e), traceback.format_exc())


def monitor_lifetime(obj):
    obj.destroyed.connect(lambda: on_destroyed(type(obj).__name__))

def on_destroyed(name):
    print "%s destroyed" % name

#class _WorkerThread(QtCore.QThread):
class _WorkerThread(threading.Thread):
    """
    """
    _SGTK_IMPLEMENTS_QTHREAD_CRASH_FIX_=True
    
    #work = QtCore.Signal(object)
    #task_completed = QtCore.Signal(object, object)# task, result
    #task_failed = QtCore.Signal(object, object, object)# task, message, stacktrace
    #task_finished = QtCore.Signal()
    
    def __init__(self, task_manager, parent=None):
        """
        """
        threading.Thread.__init__(self)
        #QtCore.QThread.__init__(self, parent)

        self._task_manager = task_manager
        self._shotgun = None#sgtk.util.shotgun.create_sg_connection()
        #self._shotgun.connect()

    def run(self):
        """
        """
        while True:
            task = self._task_manager.get_next_task()
            if not task:
                # if get_next_task returns without a task then processing should stop
                break

            # run the task - all exception handling is handled by the task but just in case!
            try:
                task.run(self._shotgun)
            except:
                pass

class TaskQueue(object):
    def __init__(self):
        self._task_queue = []
        self._tasks_by_id = {}
        self._tasks_by_group = {}

    def num_running_tasks(self):
        count = 0
        for task in self._tasks_by_id.values():
            if task.status == _BackgroundTask.RUNNING:
                count += 1
        return count

    def num_pending_tasks(self):
        return len(self._task_queue)

    def add_task(self, task):
        self._tasks_by_id[task.uid] = task
        self._task_queue.append(task.uid)
        self._tasks_by_group.setdefault(task.group, set()).add(task.uid)

    def pop(self):
        if not self._task_queue:
            return None
        task_id = self._task_queue.pop(0)
        return self._tasks_by_id[task_id]

    def remove_tasks(self, tasks, stop_upstream, stop_downstream):
        for task in tasks:
            if task.uid in self._tasks_by_id:
                del self._tasks_by_id[task.uid]
            if task.group in self._tasks_by_group:
                del self._tasks_by_group[task.group]
            if task.uid in self._task_queue:
                idx = self._task_queue.index(task.uid)
                del self._task_queue[idx]
    
    def task(self, task_id):
        return self._tasks_by_id.get(task_id)
    
    def tasks_for_group(self, group_id):
        tasks = []
        group_task_ids = self._tasks_by_group.get(group_id, [])
        for task_id in group_task_ids:
            if task_id in self._tasks_by_id:
                tasks.append(self._tasks_by_id[task_id])

    def clear(self):
        self._tasks_by_id = {}
        self._task_queue = []
        self._tasks_by_group = {}

class BackgroundTaskManager(QtCore.QObject, Threaded):
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
        Threaded.__init__(self)

        self._next_task_id = 0
        self._next_group_id = 0

        self._process_tasks = True
        self._can_process_tasks = start_processing
        self._wait_condition = threading.Condition(self._lock)

        self._task_queue = TaskQueue()
        self._threads = []
        self._max_threads = max_threads or 8

        self._threadlocal_storage = threading.local()

        self._dbg_file = open("/Users/Alan_Dann/worfiles_v2_dbg_id%d.txt" % id(self), "w")
        
        monitor_lifetime(self)


    def shut_down(self):
        """
        """
        self._log("Shutting down background task manager...")
        self._stop_processing()
        self._log("Waiting for %d background task manager threads to stop..." % len(self._threads))
        for thread in self._threads:
            #thread.wait()
            #thread.deleteLater()
            thread.join()

        self._log("Background task manager shut down successfully!")
        self._threads = []

    def start_processing(self):
        """
        """
        self._continue_processing()

        self._add_worker_threads()

    def _add_worker_threads(self):
        while True:
            num_threads = len(self._threads)
            if num_threads >= self._max_threads:
                break
    
            num_tasks = self._num_running_or_pending_tasks()
            if num_tasks <= num_threads:
                break
        
            # create a new thread:
            thread = _WorkerThread(self)
            self._threads.append(thread)
            #monitor_lifetime(thread)
            thread.start()
            
            self._log("Started new background worker thread (num threads=%d)" % len(self._threads))

    @Threaded.exclusive
    def _num_running_or_pending_tasks(self):
        return self._task_queue.num_running_tasks() + self._task_queue.num_pending_tasks() 

    @Threaded.exclusive
    def pause_processing(self):
        """
        """
        # threads will go into a wait state
        self._can_process_tasks = False

    @Threaded.exclusive
    def _continue_processing(self):
        """
        """
        # wake threads from their wait state
        self._can_process_tasks = True
        self._wait_condition.notify_all()

    @Threaded.exclusive
    def _stop_processing(self):
        """
        """
        # flag that processing should stop and then wake
        # all threads:
        self._can_process_tasks = False
        self._process_tasks = False
        self._task_queue.clear()
        self._wait_condition.notify_all()

    def add_task(self, func, priority=None, group=None, upstream_task_ids=None, **kwargs):
        """
        """
        upstream_task_ids = set(upstream_task_ids or [])

        # create a new task instance:
        task_id = self._next_task_id
        self._next_task_id += 1
        new_task = _BackgroundTask(task_id, func, group, priority, upstream_task_ids, **kwargs)

        # and add to the queue:
        self._add_task(new_task)
        self._add_worker_threads()

        return new_task.uid

    def add_pass_through_task(self, priority=None, group=None, upstream_task_ids=None, **kwargs):
        """
        """
        return self.add_task(self._task_pass_through, priority, group, upstream_task_ids, **kwargs)

    @Threaded.exclusive
    def _add_task(self, task):
        """
        """
        self._task_queue.add_task(task)
        self._wait_condition.notify()

    @Threaded.exclusive
    def get_next_task(self, wait_for_tasks=True):
        """
        """
        while True:
            if not self._process_tasks:
                return None

            if self._can_process_tasks:
                task = self._task_queue.pop()
                if task or not wait_for_tasks:
                    return task

            # wait for more tasks to arrive:
            self._wait_condition.wait()

    @Threaded.exclusive
    def stop_task(self, task_id, stop_upstream=True, stop_downstream=True):
        """
        """
        task = self._task_queue.task(task_id)
        if task is None:
            return
        self._log("Stopping Task %s..." % task)
        self._task_queue.remove_tasks([task], stop_upstream, stop_downstream)
        self._log(" > Task %s stopped!" % task)

    @Threaded.exclusive
    def stop_task_group(self, group, stop_upstream=True, stop_downstream=True):
        """
        """
        tasks = self._task_queue.tasks_for_group(group)
        if not tasks:
            return
        self._log("Stopping Task group %s..." % group)
        self._task_queue.remove_tasks(tasks, stop_upstream, stop_downstream)
        self._log(" > Task group %s stopped!" % group)

    @Threaded.exclusive
    def stop_all_tasks(self):
        """
        """
        self._log("Stopping all tasks...")
        self._task_queue.clear()
        self._log(" > All tasks stopped!")

    #@Threaded.exclusive
    #def _process_finished_tasks(self):
    #    """
    #    """
    #    # process failed tasks:
    #    for task in self._task_queue.failed_tasks:
    #        # remove task from queue:
    #        pass
    #    
    #    # process successful tasks:
    #    for task in self._
    #        
    #    
    #    for task in self._task_queue.finished_tasks():
    #        if task.status == _BackgroundTask.COMPLETED:
    #            # success - update downstream tasks:
    #            for ds_task in self._task_queue.downstream_tasks(task):
    #                ds_task.append_upstream_result(task)
    #        elif task.status == 

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
    #
    #def start_processing(self):
    #    """
    #    """
    #    self._can_process_tasks = True
    #    self._start_tasks()
    #
    #def pause_processing(self):
    #    """
    #    """
    #    self._can_process_tasks = False
    #    # and just let the current threads complete...
    #
    #def shut_down(self):
    #    """
    #    """
    #    self._log("Shutting down background task manager...")
    #    self._can_process_tasks = False
    #
    #    self._task_queue.stop()
    #
    #    # clear out all storage:
    #    self._running_tasks = {}
    #    self._available_threads = []
    #    self._pending_tasks_by_priority = {}
    #    self._tasks_by_id = {}
    #    self._group_task_map = {}
    #    self._upstream_task_map = {}
    #    self._downstream_task_map = {}
    #
    #    # stop all worker threads and then wait for them to complete:
    #    #for thread in self._all_threads:
    #    #    #thread.stop(wait_for_completion = False)
    #    #    thread.quit()
    #    self._log("Waiting for %d background task manager threads to stop..." % len(self._all_threads))
    #    for thread in self._all_threads:
    #        thread.wait()
    #        #thread.shut_down()
    #        #thread.deleteLater()
    #        #thread = None
    #        #thread.stop(wait_for_completion = True)
    #    self._log("Background task manager shut down successfully!")
    #    self._all_threads = []
    #    self._all_tasks = []
    #
    #def add_task(self, func, priority=None, group=None, upstream_task_ids=None, **kwargs):
    #    """
    #    """
    #    upstream_task_ids = set(upstream_task_ids or [])
    #
    #    # create a new task instance:
    #    task_id = self._next_task_id
    #    self._next_task_id += 1
    #    new_task = _BackgroundTask(task_id, func, group, priority, upstream_task_ids, **kwargs)
    #
    #    # add the task to the pending queue:
    #    self._pending_tasks_by_priority.setdefault(priority, []).append(new_task)
    #
    #    # add tasks to various look-ups:
    #    self._tasks_by_id[new_task.uid] = new_task
    #    self._group_task_map.setdefault(group, set()).add(new_task.uid)
    #
    #    # keep track of the task dependencies:
    #    self._upstream_task_map[new_task.uid] = upstream_task_ids
    #    for us_task_id in upstream_task_ids:
    #        self._downstream_task_map.setdefault(us_task_id, set()).add(new_task.uid)
    #
    #    self._log("Added Task %s to be processed" % new_task)
    #
    #    # and start the next task:
    #    #self._start_tasks()
    #    return new_task.uid
    #
    #def add_pass_through_task(self, priority=None, group=None, upstream_task_ids=None, **kwargs):
    #    """
    #    """
    #    return self.add_task(self._task_pass_through, priority, group, upstream_task_ids, **kwargs)
    #
    #def stop_task(self, task_id, stop_upstream=True, stop_downstream=True):
    #    """
    #    """
    #    task = self._tasks_by_id.get(task_id)
    #    if task is None:
    #        return
    #
    #    self._log("Stopping Task %s..." % task)
    #    self._stop_tasks([task], stop_upstream, stop_downstream)
    #    self._log(" > Task %s stopped!" % task)
    #
    #def stop_task_group(self, group, stop_upstream=True, stop_downstream=True):
    #    """
    #    """
    #    task_ids = self._group_task_map.get(group)
    #    if task_ids is None:
    #        return
    #
    #    self._log("Stopping Task group %s..." % group)
    #
    #    tasks_to_stop = []
    #    for task_id in task_ids:
    #        task = self._tasks_by_id.get(task_id)
    #        if task:
    #            tasks_to_stop.append(task)
    #    del self._group_task_map[group]
    #    self._stop_tasks(tasks_to_stop, stop_upstream, stop_downstream)
    #    
    #    self._log(" > Task group %s stopped!" % group)
    #
    #def stop_all_tasks(self):
    #    """
    #    """
    #    self._log("Stopping all tasks...")
    #
    #    # we just need to clear all the lookups:
    #    self._running_tasks = {}
    #    self._pending_tasks_by_priority = {}
    #    self._tasks_by_id = {}
    #    self._group_task_map = {}
    #    self._upstream_task_map = {}
    #    self._downstream_task_map = {}
    #    
    #    self._log(" > All tasks stopped!")
    #
    #def _stop_tasks(self, tasks_to_stop, stop_upstream, stop_downstream):
    #    """
    #    """
    #    if not tasks_to_stop:
    #        return
    #
    #    # copy the task list as we'll be modifying it:
    #    tasks_to_stop = list(tasks_to_stop)
    #    # and make sure we only stop each task once!!
    #    stopped_task_ids = set([task.uid for task in tasks_to_stop])
    #
    #    while tasks_to_stop:
    #        task_to_stop = tasks_to_stop.pop(0)
    #
    #        # get the up & downstream tasks to also stop depending on the flags:
    #        if stop_upstream and task_to_stop.uid in self._upstream_task_map:
    #            for us_task_id in self._upstream_task_map[task_to_stop.uid]:
    #                us_task = self._tasks_by_id.get(us_task_id)
    #                if not us_task or us_task.uid in stopped_task_ids:
    #                    # no task or already found
    #                    continue
    #
    #                tasks_to_stop.append(us_task)
    #                stopped_task_ids.add(us_task_id)
    #
    #        if stop_downstream and task_to_stop.uid in self._downstream_task_map:
    #            for ds_task_id in self._downstream_task_map[task_to_stop.uid]:
    #                ds_task = self._tasks_by_id.get(ds_task_id)
    #                if not ds_task or ds_task.uid in stopped_task_ids:
    #                    # no task or already found
    #                    continue
    #
    #                tasks_to_stop.append(ds_task)
    #                stopped_task_ids.add(ds_task_id)
    #
    #        # remove the task:
    #        self._remove_task(task_to_stop)
    #
    #def _get_worker_thread(self):
    #    """
    #    """
    #    if self._available_threads:
    #        # we can just use one of the available threads:
    #        return self._available_threads.pop()
    #
    #    # no available threads so lets check our thread count:
    #    thread_count = len(self._all_threads)
    #    if thread_count >= self._max_threads:
    #        # no available threads left!
    #        return None
    #
    #    # create the thread with a worker and hook up it's signals:
    #    thread = _WorkerThread(self._task_queue, self)
    #    monitor_lifetime(thread)
    #    #thread.task_failed.connect(self._on_task_failed)
    #    #thread.task_completed.connect(self._on_task_completed)
    #    #thread.task_finished.connect(self._on_task_finished)
    #    self._all_threads.append(thread)
    #
    #    # start the thread - this will just put it into wait mode:
    #    thread.start()
    #
    #    # log some debug:
    #    self._log("Started new background worker thread (num threads=%d)" % len(self._all_threads))
    #
    #    return thread
    #
    #def _start_tasks(self):
    #    """
    #    """
    #    # start tasks until we fail to start one for whatever reason:
    #    started = True
    #    while started:
    #        started = self._start_next_task()
    #
    #def _start_next_task(self):
    #    """
    #    """
    #    if not self._can_process_tasks:
    #        return False
    #
    #    # figure out next task to start from the priority queue:
    #    task_to_process = None
    #    task_index = 0
    #    priorities = sorted(self._pending_tasks_by_priority.keys(), reverse=True)
    #    for priority in priorities:
    #        # iterate through the tasks and make sure we aren't waiting on the
    #        # completion of any upstream tasks:
    #        for ti, task in enumerate(self._pending_tasks_by_priority[priority]):
    #            awaiting_upstream_task_completion = False
    #            for us_task_id in self._upstream_task_map.get(task.uid, []):
    #                if us_task_id in self._tasks_by_id:
    #                    # if the task is still in the tasks list then we're still awaiting
    #                    # completion of it!
    #                    awaiting_upstream_task_completion = True
    #                    break
    #            if awaiting_upstream_task_completion:
    #                continue
    #
    #            # ok, we've found the next task to process:
    #            task_to_process = task
    #            task_index = ti
    #            break
    #
    #        if task_to_process:
    #            # no need to look any further!
    #            break
    #
    #    if not task_to_process:
    #        # nothing to do!
    #        return False
    #
    #    # we need a thread to do the work with:
    #    thread = self._get_worker_thread()
    #    if not thread:
    #        # looks like we can't do anything!
    #        return False
    #
    #    self._log("Starting task %r with args: %s" % (task_to_process, task_to_process._kwargs.keys()))
    #
    #    # ok, we have a thread so lets move the task from the priority queue to the running list:
    #    self._pending_tasks_by_priority[priority] = (self._pending_tasks_by_priority[priority][:task_index] 
    #                                                 + self._pending_tasks_by_priority[priority][task_index+1:])
    #    if not self._pending_tasks_by_priority[priority]:
    #        # no more tasks with this priority so also clean up the list
    #        del self._pending_tasks_by_priority[priority]
    #
    #    task_to_process.status = _BackgroundTask.RUNNING
    #    self._running_tasks[task_to_process.uid] = (task_to_process, thread)
    #
    #    num_tasks_left = 0
    #    for pending_tasks in self._pending_tasks_by_priority.values():
    #        num_tasks_left += len(pending_tasks)
    #    self._log(" > Currently running tasks: '%s' - %d left in queue" % (self._running_tasks.keys(), num_tasks_left))
    #
    #    # and run the task
    #    thread.run_task(task_to_process)
    #    
    #    return True
    #
    #def _on_task_finished(self):
    #    """
    #    """
    #    # return the thread to the available pool:
    #    self._available_threads.append(self.sender())
    #    
    #    # remove running tasks from the running list:
    #    running_tasks = {}
    #    completed_tasks = []
    #    for task in self._running_tasks.values():
    #        if task[0].status == _BackgroundTask.RUNNING:
    #            running_tasks[task[0].uid] = task
    #        else:
    #            completed_tasks.append(task[0])
    #    self._running_tasks = running_tasks
    #
    #    # process success/failure for any completed tasks:
    #    self._log("Processing %d completed tasks..." % (len(completed_tasks)))
    #    for task in completed_tasks:
    #        if task.status == _BackgroundTask.COMPLETED:
    #            self._on_task_completed(task, task.result)
    #        elif task.status == _BackgroundTask.FAILED:
    #            self._on_task_failed(task, task.exception_msg, task.exception_traceback)
    #        else:
    #            # !!!
    #            pass
    #        
    #    # finally, start any new tasks:
    #    self._start_tasks()
    #
    #def _on_task_completed(self, task, result):
    #    """
    #    """
    #    try:
    #        # check that we should process this result:
    #        if True:#task.uid in self._running_tasks:
    #            self._log("Task %r - completed" % (task))
    #            
    #            # if we have dependent tasks then update them:
    #            for ds_task_id in self._downstream_task_map.get(task.uid) or []:
    #                ds_task = self._tasks_by_id.get(ds_task_id)
    #                if not ds_task:
    #                    continue
    #
    #                # update downstream task with result
    #                ds_task.append_upstream_result(result)
    #
    #            # remove the task:
    #            group_finished = self._remove_task(task)
    #
    #            # emit signal that this task is completed:
    #            self._log(" > [%d] Emitting task completed signal..." % task.uid)
    #            self.task_completed.emit(task.uid, task.group, result)
    #            self._log(" > [%d] Emitted task completed signal!" % task.uid)
    #            
    #            if group_finished:
    #                self._log(" > [%s] Emitting group finished signal..." % task.group)
    #                # also emit signal that the entire group is completed:
    #                self.task_group_finished.emit(task.group)
    #                self._log(" > [%s] Emitted group finished signal!" % task.group)
    #    finally:
    #        # move this task thread to the available threads list:
    #        #self._available_threads.append(self.sender())
    #        pass
    #
    #    # start processing of the next task:
    #    #self._start_tasks()
    #
    #def _on_task_failed(self, task, msg, tb):
    #    """
    #    """
    #    try:
    #        # check that we should process this task:
    #        if True:#task.uid in self._running_tasks:
    #            self._log("Task %r - failed: %s\n%s" % (task, msg, tb))
    #
    #            # we need to emit the failed message for this task as well as any that have
    #            # upstream dependencies on this task!
    #            failed_tasks = [task]
    #            failed_task_ids = set([task.uid])
    #            finished_groups = set()
    #            while failed_tasks:
    #                failed_task = failed_tasks.pop(0)
    #
    #                # find any downstream tasks:
    #                for ds_task_id in self._downstream_task_map.get(failed_task.uid) or []:
    #                    ds_task = self._tasks_by_id.get(ds_task_id)
    #                    if not ds_task or ds_task.uid in failed_task_ids:
    #                        # no task or already found
    #                        continue
    #                    failed_tasks.append(ds_task)
    #                    failed_task_ids.add(ds_task.uid)
    #
    #                # remove the task:
    #                group_finished = self._remove_task(failed_task)
    #
    #                # emit failed signal for the failed task:
    #                self._log(" > [%d] Emitting task failed signal..." % failed_task.uid)
    #                self.task_failed.emit(failed_task.uid, failed_task.group, msg, tb)
    #                self._log(" > [%d] Emitted task failed signal!" % failed_task.uid)
    #
    #                if group_finished and failed_task.group not in finished_groups:
    #                    self._log(" > [%s] Emitting group finished signal..." % failed_task.group)
    #                    self.task_group_finished.emit(failed_task.group)
    #                    self._log(" > [%s] Emitted group finished signal!" % failed_task.group)
    #                    finished_groups.add(failed_task.group)
    #    finally:
    #        # move this task thread to the available threads list:
    #        #self._available_threads.append(self.sender())
    #        pass
    #
    #    # start processing of the next task:
    #    #self._start_tasks()
    #
    #def _remove_task(self, task):#, is_dead=False):
    #    """
    #    """
    #    group_completed = False
    #
    #    # fist remove from the running tasks - this will stop any signals being handled for this task
    #    if task.uid in self._running_tasks:
    #        #self._dead_tasks[task.uid] = task
    #        del self._running_tasks[task.uid]
    #
    #    # find and remove the task from the pending queue:
    #    if task.priority in self._pending_tasks_by_priority:
    #        for ti, p_task in enumerate(self._pending_tasks_by_priority.get(task.priority, [])):
    #            if p_task.uid == task.uid:
    #                self._pending_tasks_by_priority[task.priority] = (self._pending_tasks_by_priority[task.priority][:ti] 
    #                                                                  + self._pending_tasks_by_priority[task.priority][ti+1:])
    #                break 
    #
    #        if not self._pending_tasks_by_priority[task.priority]:
    #            del self._pending_tasks_by_priority[task.priority]
    #
    #    # remove this task from all other maps:
    #    if (task.group in self._group_task_map 
    #        and task.uid in self._group_task_map[task.group]):
    #        self._group_task_map[task.group].remove(task.uid)
    #        if not self._group_task_map[task.group]:
    #            group_completed = True
    #            del self._group_task_map[task.group]
    #    if task.uid in self._tasks_by_id:
    #        del self._tasks_by_id[task.uid]
    #    if task.uid in self._upstream_task_map:
    #        del self._upstream_task_map[task.uid]
    #    if task.uid in self._downstream_task_map:
    #        del self._downstream_task_map[task.uid]
    #
    #    return group_completed
    #
    #def _task_pass_through(self, **kwargs):
    #    """
    #    """
    #    return kwargs
