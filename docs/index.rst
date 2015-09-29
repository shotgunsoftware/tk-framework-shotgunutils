The Shotgun Utilities Framework
==================================================

The Shotgun Utils Framework contains a collection of helpers and tools to make it easy and
painless to build consistent looking applications. It contains several modules which can each
be used independently:

- A Shotgun Data Model deriving from :class:`~PySide.QtGui.QStandardItemModel` which makes it easy
  to quickly build responsive, data rich applications quickly.
- A settings system handles per-user preferences and makes it easy to work with the
  :class:`~PySide.QtCore.QSettings` class from within your app code.
- An asynchronous Shotgun data receiver which makes it easy to work with background queries
  and thumbnail retrieval.

In the following documentation sections, each module is presented in detail with API
reference and code examples.


Contents:

.. toctree::
   :maxdepth: 2

   shotgun_model
   shotgun_data
   settings
   shotgun_globals
