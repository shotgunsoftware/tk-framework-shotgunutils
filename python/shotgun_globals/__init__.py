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

register_data_retriever = _cs.CachedShotgunSchema.register_data_retriever
unregister_data_retriever = _cs.CachedShotgunSchema.unregister_data_retriever
get_type_display_name = _cs.CachedShotgunSchema.get_type_display_name
get_field_display_name = _cs.CachedShotgunSchema.get_field_display_name
get_empty_phrase = _cs.CachedShotgunSchema.get_empty_phrase
get_status_display_name = _cs.CachedShotgunSchema.get_status_display_name
get_status_color = _cs.CachedShotgunSchema.get_status_color

    
