External Configuration Management
######################################

.. currentmodule:: external_config

Introduction
======================================

This module contains classes and methods for doing inspection
of external environments. The typical scenario when this is helpful is if you
are creating an environment with mixed contexts - for example a
Shotgun 'My Tasks' tool which lists different items from different
projects and presents a list of available commands, apps or similar
for each one of them. Building this would require Toolkit to load
up the different configurations for each task and introspect them.

The following classes contains a collection of operations useful
when you want to inspect and execute across projects and configurations.

The classes are aggressively cached and asynchronous, fetching data
in the background and using QT signals to signal when it is available.

Configurations are bootstrapped in separate background processes, thereby
ensuring complete stability of the runtime environment - no context
switching or core changes take place.


Class ExternalConfigurationLoader
============================================
.. autoclass:: ExternalConfigurationLoader
    :members:
    :inherited-members:

Class ExternalConfiguration
============================================

.. autoclass:: ExternalConfiguration
    :members:
    :inherited-members:

Class ExternalCommand
============================================

.. autoclass:: ExternalCommand
    :members:
    :inherited-members:
    :exclude-members: create



