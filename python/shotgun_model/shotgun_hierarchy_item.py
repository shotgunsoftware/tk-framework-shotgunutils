# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk

from .shotgun_standard_item import ShotgunStandardItem


class ShotgunHierarchyItem(ShotgunStandardItem):
    """
    A subclass of ``ShotgunStandardItem`` with access to data provided via
    the ``nav_expand()`` python API calls.
    """

    def target_entities(self):
        """
        Returns the ``target_entities`` ``dict`` as stored on the item.

        May return ``None`` if the item has no data or does not have
        ``target_entities``.

        This dictionary stores information that can be used to query the
        entities targeted when the containing hierarchy model was created.
        It includes a key called `additional_filter_presets` with a value
        that can be provided to the shotgun python-api's ``find()`` call to
        tell the server exactly which entities exist under this item's branch
        in the hierarchy. The value is a list of dictionaries with server-side
        filter presets for locating the target entities.

        The dictionary also stores a ``type`` key whose value is the type of
        entity being targeted.

        An example value returned by this method::

            'target_entities': {
                'additional_filter_presets': [
                    {
                        'path': '/Project/65/Asset/sg_asset_type/Character',
                        'preset_name': 'NAV_ENTRIES',
                        'seed': {
                            'field': 'entity',
                            'type': 'Version'
                        }
                    }
                ],
                'type': 'Version'
            },
        """

        data = self.data()
        if not data or self.__kind() == "empty":
            return None

        return data.get("target_entities")

    def url(self):
        """Returns the url for this item in the hierarchy.

        May return ``None`` if the item has no data or does not have
        a ``url``.

        Most items in the model will store a ``url`` which identifies their
        location in the hierarchy. This is the same value used by
        ``nav_expand()`` in the python-api to query a Shotgun hierarchy.

        An example url::

            'url': '/Project/65/Asset/sg_asset_type/Character',
        """

        data = self.data()
        if not data or self.__kind() == "empty":
            return None

        return data.get("url")

    # --------------------------------------------------------------------------

    def __kind(self):
        """
        Returns the "kind" of the item.

        This is currenlty internal to this class until there's justification for
        making this information public.

        The current "kinds" are:

        * entity: A concrete entity instance
        * entity_type: A container for the type of entity (ex: "Asset", "Shot",
            etc)
        * list: A container for other items
        * no_entity: A container for items with no parent entity (ex: "Shots
            with no Sequence")
        * empty: A placeholder that represents no items (ex: "No Shots")
        """

        data = self.data()
        if not data:
            return "empty"

        return data.get("ref", {}).get("kind", "empty")
