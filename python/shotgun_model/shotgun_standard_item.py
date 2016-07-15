# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from .shotgun_standard_item_base import ShotgunStandardItemBase
from .util import get_sg_data as util_get_sg_data


class ShotgunStandardItem(ShotgunStandardItemBase):
    """
    Simple subclass of the standard item base that exposes a method to return
    the SG data for this item in the model.

    Do not construct this object directly - instead use the ShotgunModel.create_item() method.
    """

    def get_sg_data(self):
        """
        Retrieves the shotgun data associated with this item.
        Only leaf nodes have shotgun data associated with them.
        On intermediate nodes, None will be returned.

        :returns: Shotgun data or None if no data was associated
        """
        return util_get_sg_data(self)

