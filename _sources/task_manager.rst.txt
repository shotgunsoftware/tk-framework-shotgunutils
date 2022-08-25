Background Task Processing
######################################

.. currentmodule:: task_manager

Introduction
======================================

In order to build responsive Toolkit apps, work needs to be scheduled to run
in background threads. The :class:`BackgroundTaskManager` handles generic
background processing and is used by many of the Toolkit frameworks.

When using a :class:`~shotgun_model.ShotgunModel`, for example, the model
will internally create a :class:`~shotgun_data.ShotgunDataRetriever` to handle
background communication with Shotgun. The :class:`~shotgun_data.ShotgunDataRetriever`
in turn uses threads to handle its
background processing and uses this :class:`BackgroundTaskManager` in order
to schedule the background processing.

A centralized thread pool
-------------------------

By default, each Shotgun Model will have its own background task manager
that runs Shotgun queries in the background. If your app uses a lot of
different models or data retrievers, this becomes hard to maintain and may
lead to unpredictable states due to the fact that the Shotgun API isn't
thread safe.

.. note::

    We recommend that apps using several Shotgun Models or Data retrievers
    use a single  :class:`BackgroundTaskManager` for handling of all its
    background processing.

In these situations, you can maintain a single :class:`BackgroundTaskManager`
for your app and supply it to your :class:`~shotgun_model.ShotgunModel` and
:class:`~shotgun_data.ShotgunDataRetriever` instances when creating them.
This allows for a setup where all threaded work
is handled by a single thread pool and allows for efficient control and
prioritization of the work that needs to be carried out.

Here is an example of how the Toolkit apps typically set this up::

    # import the task manager
    task_manager = sgtk.platform.import_framework("tk-framework-shotgunutils", "task_manager")


    class AppDialog(QtGui.QWidget):
        """
        App main dialog
        """
        def __init__(self, parent):
            # in your main dialog init, create a background task manager
            self._task_manager = task_manager.BackgroundTaskManager(parent=self,
                                                                    start_processing=True,
                                                                    max_threads=2)

            # create models and request that they use the task manager
            self._model_a = shotgun_model.SimpleShotgunModel(parent=self,
                                                             bg_task_manager=self._task_manager)
            self._model_b = shotgun_model.SimpleShotgunModel(parent=self,
                                                             bg_task_manager=self._task_manager)


        def closeEvent(self, event):
            # gracefully close down threadpool
            self._task_manager.shut_down()

            # okay to close dialog
            event.accept()

Using the Task Manager directly
-------------------------------

The task manager isn't just a controllable building block used by
the internal Toolkit libraries; you can also use it directly to control
background work that your app is doing.

Simply register a task that you want it to perform and it will queue it up
and execute it once a worker becomes available. You can control how many
working threads you want the task manager to run in parallel and tasks
can easily be prioritized, grouped and organized in a hierarchical fashion.



Class BackgroundTaskManager
============================================

.. note::

    Import the module into your Toolkit App using the following statement::

        task_manager = sgtk.platform.import_framework("tk-framework-shotgunutils", "task_manager")


.. autoclass:: BackgroundTaskManager
    :members:
    :inherited-members:
