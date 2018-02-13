External Configuration Management
######################################

.. currentmodule:: external_config

Introduction
======================================

This module contains classes and methods for efficiently inspecting
remote pipeline configurations and runtime environments.


Class BackgroundTaskManager
============================================

.. note::

    Import the module into your Toolkit App using the following statement::

        task_manager = sgtk.platform.import_framework("tk-framework-shotgunutils", "multi_context")


.. autoclass:: MultiConfigurationLoader
    :members:
    :inherited-members:

.. autofunction:: create_default

.. autofunction:: create_from_pipeline_configuration_data

.. autofunction:: serialize

.. autofunction:: deserialize

.. autoclass:: RemoteConfiguration
    :members:
    :inherited-members:

.. autoclass:: RemoteCommand
    :members:
    :inherited-members:


