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

    .. warning:: Do *NOT* construct instances of this class and then manually
        them to an existing ``ShotgunHierarchyModel``. Doing so will likely
        causes memory issues or issues centered around garbage collection as
        the model class takes a lot of care to know exactly which items exist,
        when they're added/removed etc.
    """

    # constant values to refer to the fields where the paths are stored in the
    # returned navigation data.
    SG_PATH_FIELD = "path"

    def has_children(self):
        """
        Returns ``True`` if the item has children, ``False`` otherwise.

        :rtype: `bool`
        """

        data = self.data()
        if not data:
            return False

        return data.get("has_children", False)

    def is_entity_related(self):
        """
        Returns ``True`` if the item is entity related, ``False`` otherwise.

        Being "entity related" means it represents an entity, an entity type,
        a list of entities, or a generic container for entities.

        Some items returned from the SG hierarchy are merely placeholders that
        tell the user that there are no associated entities. For these items,
        this method will return ``False``.

        :return: ``True`` if entity related, ``False`` otherwise.
        :rtype: ``bool``
        """
        return self.kind() is not None

    def kind(self):
        """
        Returns the "kind" of the item.

        The current "kinds" are:

        * "entity": A concrete entity instance
        * "entity_type": A container for the type of entity (ex: "Asset", "Shot",
            etc)
        * "list": A container for other items
        * "no_entity": A container for items with no parent entity (ex: "Shots
            with no Sequence")
        * None: A placeholder that represents no items (ex: "No Shots")

        :rtype: `str` or `None`
        """

        data = self.data()
        if not data:
            return None

        # the "ref" should always be populated, and there should always be a
        # "kind". If not, just default to `None`.
        return data.get("ref", {}).get("kind", None)

    def path(self):
        """Returns the path for this item in the hierarchy.

        May return ``None`` if the item has no data or does not have
        a ``path``.

        Most items in the model will store a ``path`` which identifies their
        location in the hierarchy. This is the same value used by
        ``nav_expand()`` in the python-api to query a Shotgun hierarchy.

        An example path::

            'path': '/Project/65/Asset/sg_asset_type/Character',
        """

        data = self.data()
        if not data or not self.kind():
            return None

        return data.get(self.SG_PATH_FIELD)

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
        if not data or not self.kind():
            return None

        return data.get("target_entities")

    def entity_type(self):
        """
        Returns the entity type of the item.

        There are two kinds of items that are associated with entity types.

        The first is the actual "entity_type" item. These are typically parent
        items in the hierarchy like `Shots` or `Assets` which have children
        that correspond to actual entities.

        The entity items themselves also have an entity type.

        This method will return the entity type for either of these kinds of
        items. To find out the kind of the item, use the ``kind()`` method.

        If the item has no associated entity type, ``None`` will be returned.

        :rtype: `str` or `None`
        """

        data = self.data()
        if not data:
            return None

        ref = data.get("ref") or {}

        entity_type = None

        if self.kind() == "entity":
            if ref.get("value"):
                entity_type = ref.get("value").get("type")
        elif self.kind() == "entity_type":
            return data.get("value")

        return entity_type


