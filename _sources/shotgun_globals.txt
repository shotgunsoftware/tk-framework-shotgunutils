Shotgun Globals Access
######################################

The globals module contains various accessors to Shotgun globals such as the schema, task statuses, etc.
The globals are cached locally for fast access and updated in a background worker.
Pass a data retriever object to the module in order for it to pull updates from Shotgun.
When you shut down your app or tool, make sure you unregister the data retriever.

The sample code below shows how you can use the globals in your Toolkit App Code::

    shotgun_globals = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_globals")
    task_manager = sgtk.platform.import_framework("tk-framework-shotgunutils", "task_manager")


    # typically, in your UI or app constructor, create a
    # task manager
    task_manager = task_manager.BackgroundTaskManager(self)
    task_manager.start()
    
    # register it with the globals module so that it can
    # use it to fetch data
    shotgun_globals.register_bg_task_manager(task_manager)

    # at runtime, access things
    get_type_display_name("CustomEntity01")

    # at shutdown time, unregister
    shotgun_globals.unregister_bg_task_manager(task_manager)
    task_manager.stop()



.. currentmodule:: shotgun_globals

.. autofunction:: register_bg_task_manager
.. autofunction:: unregister_bg_task_manager
.. autofunction:: get_type_display_name
.. autofunction:: get_field_display_name
.. autofunction:: get_empty_phrase
.. autofunction:: get_status_display_name
.. autofunction:: get_status_color
.. autofunction:: get_entity_type_icon
.. autofunction:: get_entity_type_icon_url
.. autofunction:: get_valid_values
.. autofunction:: field_is_editable
.. autofunction:: field_is_visible
.. autofunction:: create_human_readable_date
