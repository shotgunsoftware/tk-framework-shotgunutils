The Shotgun Utilities Framework
==================================================

The Shotgun Utils Framework contains a collection of helpers and tools to make it easy and
painless to build consistent looking applications. It contains several modules which can each
be used independently:

- Shotgun Data and Shotgun Hierarchy models deriving from
  :class:`~PySide.QtGui.QStandardItemModel` which makes it easy to quickly build
  responsive, rich applications with data from your Shotgun site.

- A settings system handles per-user preferences and makes it easy to work with the
  :class:`~PySide.QtCore.QSettings` class from within your app code.

- An asynchronous Shotgun data receiver which makes it easy to work with background queries
  and thumbnail retrieval.

- A background processing manager to help schedule background worker threads.

- A ``globals`` helper module which provides cached access to various global data
  in Shotgun, including status names, display names for fields and schema data.

In the following documentation sections, each module is presented in detail with API
reference and code examples.


Contents:

.. toctree::
   :maxdepth: 2

   shotgun_model
   shotgun_hierarchy_model
   shotgun_data
   task_manager
   settings
   shotgun_globals

