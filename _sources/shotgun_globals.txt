Shotgun Globals Access
######################################

The globals module contains various accessors to Shotgun globals such as the schema, task statuses, etc.
The globals are cached locally for fast access and updated in a background worker.
Pass a data retriever object to the module in order for it to pull updates from Shotgun.
When you shut down your app or tool, make sure you unregister the data retriever.

The sample code below shows how you can use the globals in your Toolkit App Code::

    shotgun_globals = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_globals")
    sg_data = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_data")


    # typically, in your UI or app constructor, create a
    # data retriever and register it
    sg_data = sg_data.ShotgunDataRetriever(self)
    shotgun_globals.register_data_retriever(sg_data)

    # at runtime, access things
    get_type_display_name("CustomEntity01")

    # at shutdown time, unregister
    shotgun_globals.unregister_data_retriever(sg_data)
    sg_data_retriever.stop()



.. currentmodule:: shotgun_globals

.. autofunction:: register_data_retriever
.. autofunction:: unregister_data_retriever
.. autofunction:: get_type_display_name
.. autofunction:: get_field_display_name
.. autofunction:: get_empty_phrase
.. autofunction:: get_status_display_name
.. autofunction:: get_status_color
