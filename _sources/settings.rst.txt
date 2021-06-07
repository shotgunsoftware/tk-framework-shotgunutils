Shotgun Toolkit Qt Settings Wrapper
######################################


The settings module makes it easy to store things like user preferences, app related state etc.
For example, if you want your app to remember the state of a checkbox across sessions, you can
use the settings module to store this value. Adding persisting settings to an app can quickly
drastically improve the user experience at a very low cost.

This settings module wraps around `QSettings`. This means that the settings data will be stored
on your local machine and that they are for the current user only. If you need to share a preference
or setting between multiple users, this module is most likely *not* the right one to use.

Settings can have different scope. This indicates how the setting should be shared between
instances of apps, shotgun setups etc. Please note that the setting is still per-user and per-machine,
so if it is scoped to be "global", it means that it will be shared across all different apps, engines,
configurations, projects and shotgun sites for the current user on their local machine.

- ``SCOPE_GLOBAL`` - No restriction.
- ``SCOPE_SITE`` - Settings are per Shotgun site.
- ``SCOPE_PROJECT`` - Settings are per Shotgun project.
- ``SCOPE_CONFIG`` - Settings are per Shotgun Pipeline Configuration.
- ``SCOPE_INSTANCE`` - Settings are per app or engine instance. For example, if your app
  contains a set of filters, and you want these to be remembered across sessions, you would
  typically use this scope. Each instance of the app will remember its own filters, so when you
  run it in the asset environment, one set of filters are remembered, when you run it in the shot
  environment, another set of filters etc.
- ``SCOPE_ENGINE`` - One setting per engine. This makes it possible to store one set of preferences
  for apps running in Photoshop, Maya, Nuke etc. This makes it possible to for example store a setting
  that remembers if a "welcome screen" for your app has been displayed - so that it is only displayed
  once in Maya, once in Nuke etc.

The following code illustrates typical use of the settings module::

    # example of how the settings module can be used within your app code
    # import the module - note that this is using the special
    # import_framework code so it won't work outside an app
    settings = sgtk.platform.import_framework("tk-framework-shotgunutils", "settings")

    # typically in the constructor of your main dialog or in the app, create a settings object:
    self._settings_manager = settings.UserSettings(sgtk.platform.current_bundle())

    # the settings system will handle serialization and management of data types
    # so you can pass simple types such as strings, ints and lists and dicts of these.
    #
    # retrieve a settings value and default to a value if no settings was found
    scale_val = self._settings_manager.retrieve("thumb_size_scale", 140)

    # or store the same value
    self._settings_manager.store("thumb_size_scale", 140)

    # by default, things are scoped with `SCOPE_GLOBAL`.
    # If you want to specify another scope, add a scope parameter.

    # Fetch a preference with a specific scope
    ui_launched = self._settings_manager.retrieve("ui_launched", False, self._settings_manager.SCOPE_ENGINE)

    # And store a preference with a specific scope
    self._settings_manager.store("ui_launched", True, self._settings_manager.SCOPE_ENGINE)
