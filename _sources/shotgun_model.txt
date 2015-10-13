Shotgun Model
######################################

Introduction
======================================

The shotgun data model helps you build responsive, data rich applications quickly and leverage
QT's build in model/view framework

.. image:: images/model_overview.png


The Shotgun Model is a custom QT Model specialized for Shotgun Queries. It uses a disk based cache
and runs queries asynchronously to Shotgun in the background for performance. In a nut shell, you
derive your own model class from it, set up a query, and then hook up your model to a QT View which
will draw the data. The class contains several callbacks and allows for extensive customization, yet
tries to shadow and encapsulate a lot of the details.


.. image:: images/model_inheritance.png



For convenience, three different classes are provided, allowing you to choose the right level of encapsulation.

.. image:: images/model_classes.png



Why should I use the Shotgun Model?
---------------------------------------

Using the Shotgun Model means switching to Model/View based programming. While there is perhaps slightly more
overhead to get started with this, there are many benefits. The Shotgun Model (and the corresponding delegates
and Shotgun View components) is an attempt to bridge this gap and make it quick and painless to get started
with QT Model/View programming.

QT provides a strong and mature Model/View hierarchy which is robust and easy to work with. If you are not
familiar with it, please check the following links:

- Tutorial: http://qt-project.org/doc/qt-4.8/modelview.html
- Technical details: http://qt-project.org/doc/qt-4.8/model-view-programming.html

The benefits with this approach will become evident as you scale your UIs and their complexity. Developing code
and tools where the data and the UI is combined will work in simple scenarios but for data rich applications
this approach becomes hard to maintain, difficult to reuse and typically scales poorly as the dataset complexity grows.
By leveraging QTs built-in functionality, you get access to a mature and well documented toolbox that makes
it quick to develop tools:

- A Shotgun model instance represents a single shotgun query. With two lines of code you can connect the resultset
  of such a query with a standard Qt list, tree or table.
- The Shotgun model is cached, meaning that all data is fetched in the background in a worker thread. This means that
  the data in your UI will load up instantly and you never have to wait for shotgun. If the query result is different
  than the cached result, the view will be updated on the fly as the data arrives.
- With QT you have access to SelectionModels, making it easy to create consistent selection behavior, even across
  multiple views. With full keyboard support.
- With QT proxy models you can easily create interactive searching and filtering on the client side.
- Views and models are optimized and will perform nicely even if you have thousands of items loaded.
- Through the shotgun view module, you can easily control the QT *delegates* system, making it easy to
  draw custom UIs for each cell in your view.

Shotgun Model Hello World
------------------------------------

A hello world style example would look something like this, assuming this code is inside a
toolkit app::

    # Import the shotgun_model module from the shotgun utils framework
    shotgun_model = tank.platform.import_framework("tk-framework-shotgunutils", "shotgun_model")
    # Set up alias
    ShotgunModel = shotgun_model.ShotgunModel

    # Create a standard QT Tree View
    view = QtGui.QTreeView(parent_widget)

    # Set up our data backend
    model = shotgun_model.SimpleShotgunModel(parent_widget)

    # Tell the view to pull data from the model
    view.setModel(model)

    # load all assets from Shotgun
    model.load_data(entity_type="Asset")


The above code will create a standard QT tree view of all assets in Shotgun.

Beyond Hello World
---------------------------------

The simple setup outlined above could be extended in the following ways:

- If you need more control of how the data is being retrieved, consider instead creating
  your own class and derive from :class:`~shotgun_model.ShotgunOverlayModel`. This makes it possible to customize
  the shotgun data as it arrives from Shotgun, control the hierarchy grouping and many other
  things.
- If you want to retrieve results from your view, connect signals to the view's selection model.
- If you want to cull out items from the model, for example only to show items matching a particular
  search criteria, use a Proxy Model (typically :class:`~PySide.QtGui.QSortFilterProxyModel`).
- If you want to control the way items are displayed in the view, consider using the Shotgun delegates
  module which is part of the QT widgets framework. For more information, see
  :class:`~tk-framework-qtwidgets:views.WidgetDelegate`


.. _sg-model-data-items:

Data Items
----------------------


The Shotgun Model derives from :class:`~PySide.QtGui.QStandardItemModel` which is a base model which managed the storage
of model data inside a collection of :class:`~PySide.QtGui.QStandardItem` objects. Each of these objects have a number of
standard property and so called *roles*, holding various pieces of data such as icons, colors etc.
The Shotgun Model introduces two new standard roles which can be used by both subclassing and calling
code:

- ``ShotgunModel.SG_DATA_ROLE`` holds the shotgun data associated with an object. In a tree view, only
  leaf nodes have this data defined - other nodes have it set to None. For leaf nodes, it is a standard
  shotgun dictionary containing all the items that were returned by the Shotgun query.
- ``ShotgunModel.SG_ASSOCIATED_FIELD_ROLE`` holds the associated field value for a node. This is contained
  in a dictionary with the keys name and value. For example, for a leaf node this is typically something
  like ``{"name": "code", "value": "AAA_123"}``. For an intermediate node, it may be something such as
  ``{"name": "sg_sequence", "value": {"id": 123, "name": "AAA", "type": "Sequence"} }``.

Datetime objects and the Shotgun API
------------------------------------------

Because of issues with serialization, please note that datetime objects returned by the Shotgun API are
automatically converted to unix timestamps by the model. A unix timestamp is the number of seconds since
1 Jan 1971, in the UTC time zone.


When you are pulling data from the shotgun model and want to convert this unix timestamp
to a *local* timezone object, which is what you would get from the Shotgun API, use the following code::


    import datetime
    from tank_vendor import shotgun_api3
    local_datetime = datetime.datetime.fromtimestamp(unix_time, shotgun_api3.sg_timezone.LocalTimezone())

Furthermore, if you want to turn that into a nicely formatted string::


    time_str = local_datetime.strftime('%Y-%m-%d %H:%M')


.. currentmodule:: shotgun_model

SimpleShotgunModel
=====================================================

Convenience wrapper around the Shotgun model for quick and easy access. Use this when you want
to prototype data modeling or if your are looking for a simple flat data set reflecting a
shotgun query. All you need to do is to instantiate the class (typically once, in your constructor)
and then call :meth:`SimpleShotgunModel.load_data()` to
specify which shotgun query to load up in the model. Subsequently call 
:meth:`~SimpleShotgunModel.load_data()` whenever you
wish to change the Shotgun query associated with the model.

This class derives from :class:`ShotgunModel` so all the 
customization methods available in the
normal ShotgunModel can also be subclassed from this class.


.. autoclass:: SimpleShotgunModel
    :show-inheritance:
    :members:




ShotgunOverlayModel
=====================================================




Convenience wrapper around the :class:`ShotgunModel` class which adds spinner and error reporting overlay functionality.
Where the :class:`ShotgunModel` is a classic model class which purely deals with data, this class connects with a
:class:`~PySide.QtGui.QWidget` in order to provide progress feedback whenever necessary. Internally, it holds an instance of
the :class:`~tk-framework-qtwidgets:overlay_widget.ShotgunOverlayWidget` widget 
(which is part of the QtWidgets framework) and will show this whenever
there is no data to display in the view. This means that it is straight forward to create shotgun views with a
spinner on top indicating when data is being loaded and where any errors are automatically reported to the user.

.. note:: Only the methods specific to the overlay model are displayed here. For
   additional methods, see the :class:`ShotgunModel`.

.. currentmodule:: shotgun_model

.. autoclass:: ShotgunOverlayModel
    :show-inheritance: 
    :members: _show_overlay_spinner, _hide_overlay_info, _show_overlay_pixmap, _show_overlay_info_message, _show_overlay_error_message


ShotgunModel
=====================================================

A QT Model representing a Shotgun query.

This class implements a standard :class:`~PySide.QtCore.QAbstractItemModel` specialized to hold the contents
of a particular Shotgun query. It is cached and refreshes its data asynchronously.

The model can either be a flat list or a tree. This is controlled by a grouping
parameter which works just like the Shotgun grouping. For example, if you pull
in assets grouped by asset type, you get a tree of data with intermediate data
types for the asset types. The leaf nodes in this case would be assets.


.. currentmodule:: shotgun_model

.. autoclass:: ShotgunModel
    :show-inheritance:
    :inherited-members:
    :members:
    :private-members: 
    :exclude-members: _ShotgunModel__add_sg_item_to_tree,
                      _ShotgunModel__add_sg_item_to_tree_r,
                      _ShotgunModel__check_constraints,
                      _ShotgunModel__do_depth_first_tree_deletion,
                      _ShotgunModel__load_from_disk,
                      _ShotgunModel__log_debug,
                      _ShotgunModel__log_warning,
                      _ShotgunModel__on_sg_data_arrived,
                      _ShotgunModel__on_worker_failure,
                      _ShotgunModel__on_worker_signal,
                      _ShotgunModel__populate_complete_tree_r,
                      _ShotgunModel__process_thumbnail_for_item,
                      _ShotgunModel__rebuild_whole_tree_from_sg_data,
                      _ShotgunModel__save_to_disk,
                      _ShotgunModel__save_to_disk_r,
                      _ShotgunModel__sg_compare_data,
                      _generate_display_name,
                      reset,
                      clear
    
