# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.


from . import cached_schema as _cs

from .icon import get_entity_type_icon, get_entity_type_icon_url

register_bg_task_manager = _cs.CachedShotgunSchema.register_bg_task_manager
unregister_bg_task_manager = _cs.CachedShotgunSchema.unregister_bg_task_manager
get_type_display_name = _cs.CachedShotgunSchema.get_type_display_name
get_field_display_name = _cs.CachedShotgunSchema.get_field_display_name
get_empty_phrase = _cs.CachedShotgunSchema.get_empty_phrase
get_status_display_name = _cs.CachedShotgunSchema.get_status_display_name
get_status_color = _cs.CachedShotgunSchema.get_status_color

    
