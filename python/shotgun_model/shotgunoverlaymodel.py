# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import tank
from .shotgunmodel import ShotgunModel
from tank.platform.qt import QtCore, QtGui
overlay_module = tank.platform.import_framework("tk-framework-qtwidgets", "overlay_widget") 


class ShotgunOverlayModel(ShotgunModel):
    """
    Convenience wrapper around the ShotgunModel which adds
    spinner and error reporting overlay functionality. 
    """
    
    # signal that gets emitted whenever the model deems it appropriate to 
    # indicate that data is being loaded. Note that this signal is not 
    # emitted every time data is loaded from Shotgun, but only when there 
    # is no cached data available to display. This signal can be useful if
    # an implementation wants to set up a custom overlay system instead
    # of or in addition to the built in one that is provided via 
    # the set_overlay_parent() method.
    progress_spinner_start = QtCore.Signal()
    
    # conversely, an end signal is being emitted every time a progress spinner
    # should be deactivated. 
    progress_spinner_end = QtCore.Signal()

    def __init__(self, parent, overlay_widget, download_thumbs=True, schema_generation=0, bg_load_thumbs=False):
        """
        Constructor. This will create a model which can later be used to load
        and manage Shotgun data.
        
        :param parent: Parent object.
        :param overlay_widget: Widget on which the spinner/info overlay should be positioned.
        :param download_thumbs: Boolean to indicate if this model should attempt 
                                to download and process thumbnails for the downloaded data.
        :param schema_generation: Schema generation index. If you are changing the format 
                                  of the data you are retrieving from Shotgun, and therefore
                                  want to invalidate any cache files that may already exist
                                  in the system, you can increment this integer.
        :param bg_load_thumbs: If set to True, thumbnails will be loaded in the background.
        
        """
        ShotgunModel.__init__(self, parent, download_thumbs, schema_generation, bg_load_thumbs)
        
        # set up our spinner UI handling
        self.__overlay = overlay_module.ShotgunOverlayWidget(overlay_widget)
        self._is_in_spin_state = False
        self._cache_loaded = False
        
        # set up some model signals etc.
        self.data_refreshed.connect(self.__on_data_refreshed)
        self.data_refresh_fail.connect(self.__on_data_refresh_fail)
        
    ########################################################################################
    # protected methods not meant to be subclassed but meant to be called by subclasses
    
    def _load_data(self, entity_type, filters, hierarchy, fields, order=None, seed=None, limit=None):
        """
        Overridden from ShotgunModel. 
        """
        # reset overlay
        self.__overlay.hide(hide_errors=True)
        # call base class
        self._cache_loaded = ShotgunModel._load_data(self, 
                                                     entity_type, 
                                                     filters, 
                                                     hierarchy, 
                                                     fields, 
                                                     order, 
                                                     seed,
                                                     limit)
        return self._cache_loaded        
    
    def _refresh_data(self):
        """
        Overridden from ShotgunModel.
        """
        if not self._cache_loaded:
            # we are doing asynchronous loading into an uncached model.            
            # start spinning
            self._show_overlay_spinner()
        # call base class
        return ShotgunModel._refresh_data(self)
    
    def _show_overlay_spinner(self):
        """
        Shows the overlay spinner
        """
        self.__overlay.start_spin()    
        # signal to any external listeners
        self.progress_spinner_start.emit()
        self._is_in_spin_state = True        
    
    def _hide_overlay_info(self):
        """
        Hides any overlay that is currently shown, except for error messages.
        """
        self.__overlay.hide(hide_errors=False)
        
    def _show_overlay_pixmap(self, pixmap):
        """
        Show an overlay status message in the form of a pixmap.
        This is for example useful if a particular query doesn't return any results.
        If an error message is already being shown, the pixmap will not 
        replace the error message. 
        
        :param pixmap: QPixmap object containing graphic to show.
        """
        self.__overlay.show_message_pixmap(pixmap)

    def _show_overlay_info_message(self, msg):
        """
        Show an overlay status message.
        If an error is already displayed, 
        this info message will not be shown.
        
        :param msg: message to display
        :returns: True if the message was shown, False if not.
        """
        self.__overlay.show_message(msg)
        
    def _show_overlay_error_message(self, msg):
        """
        Show an overlay error message.
        
        :param msg: error message to display
        """
        self.__overlay.show_error_message(msg)

    ########################################################################################
    # private methods

    def __on_data_refreshed(self):
        """
        Callback when async data has arrived successfully
        """
        self._cache_loaded = True
        if self._is_in_spin_state:
            self.__overlay.hide(hide_errors=True)
            # we are spinning, so signal the spin to end
            self._is_in_spin_state = False
            self.progress_spinner_end.emit()        
        
    def __on_data_refresh_fail(self, msg):
        """
        Callback when async data has failed to arrive 
        """
        self.__overlay.show_error_message(msg)
        if self._is_in_spin_state:
            # we are spinning, so signal the spin to end
            self._is_in_spin_state = False
            self.progress_spinner_end.emit()        
