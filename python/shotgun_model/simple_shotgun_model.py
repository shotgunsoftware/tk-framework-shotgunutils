# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

from .shotgun_model import ShotgunModel


class SimpleShotgunModel(ShotgunModel):
    """
    Convenience wrapper around the Shotgun model for quick and easy access.
    
    Use this when you want to prototype data modeling or if your are looking 
    for a simple flat data set reflecting a shotgun query. All you need to do 
    is to instantiate the class (typically once, in your constructor) and then 
    call :meth:`load_data` to specify which shotgun query to load up in the model. 
    Subsequently call :meth:`load_data` whenever you wish to change the Shotgun 
    query associated with the model.

    This class derives from :class:`ShotgunModel` so all the customization methods 
    available in the normal :class:`ShotgunModel` can also be subclassed from this class.    
    """
 
    def __init__(self, parent, bg_task_manager=None):
        """
        :param parent: QWidget which this model will be parented under.
        :type parent: :class:`~PySide.QtGui.QWidget`                   
        :param bg_task_manager:     Background task manager to use for any asynchronous work.  If
                                    this is None then a task manager will be created as needed.
        :type bg_task_manager: :class:`~task_manager.BackgroundTaskManager`                                    
        """
        ShotgunModel.__init__(self, 
            parent=parent, 
            download_thumbs=True,
            bg_load_thumbs=True, 
            bg_task_manager=bg_task_manager)

    def load_data(
        self, entity_type, filters=None, fields=None, order=None, limit=None,
        columns=None, additional_filter_presets=None, editable_columns=None
    ):
        """
        Loads shotgun data into the model, using the cache if possible.
        The model is not nested and the first field that is specified
        via the fields parameter (``code`` by default) will be used as the default
        name for all model items.

        :param entity_type: Shotgun Entity Type to load data for
        :param filters: Shotgun API find-style filter list. If no list is specified, all records
                  for the given entity type will be retrieved.
        :param fields: List of Shotgun fields to retrieve. If not spefified, the 'code' field
                  will be retrieved.
        :param order: Order clause for the Shotgun data. Standard Shotgun API syntax.
                  Note that this is an advanced parameter which is meant to be used
                  in subclassing only. The model itself will be ordered by its
                  default display name, and if any other type of ordering is desirable,
                  use for example a QProxyModel to handle this. However, knowing in which
                  order results will arrive from Shotgun can be beneficial if you are doing
                  grouping, deferred loading and aggregation of data as part of your
                  subclassed implementation.
        :param limit: Limit the number of results returned from Shotgun. In conjunction with the order
                  parameter, this can be used to effectively cap the data set that the model
                  is handling, allowing a user to for example show the twenty most recent notes or
                  similar.
        :param list columns: List of Shotgun fields names to use to populate the model columns
        :param additional_filter_presets: List of Shotgun filter presets to apply, e.g.
                  ``[{"preset_name":"LATEST","latest_by":"BY_PIPELINE_STEP_NUMBER_AND_ENTITIES_CREATED_AT"}]``
        :param list editable_columns: A subset of ``columns`` that will be editable in views that use this model.
        """
        filters = filters or []
        fields = fields or ["code"]
        hierarchy = [fields[0]]
        ShotgunModel._load_data(
            self,
            entity_type,
            filters,
            hierarchy,
            fields,
            order=order,
            limit=limit,
            columns=columns,
            additional_filter_presets=additional_filter_presets,
            editable_columns=editable_columns,
        )
        self._refresh_data()
