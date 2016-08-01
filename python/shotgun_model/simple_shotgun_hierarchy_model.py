# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from .shotgun_hierarchy_model import ShotgunHierarchyModel


class SimpleShotgunHierarchyModel(ShotgunHierarchyModel):
    """
    Convenience wrapper around the Shotgun Hierarchy model for quick and easy
    access.

    All you need to do is to instantiate the class (typically once, in your
    constructor) and then call :meth:`load_data` to specify which shotgun
    ``nav_expand()`` query to load up the top-level items in the hierarchy. The
    remaining items will be queried asynchronously as items are expanded.

    Subsequently call :meth:`load_data` whenever you wish to change the
    ``nav_expand()`` query associated with the model.

    This class derives from :class:`ShotgunHierarchyModel` so all the
    customization methods available in the normal :class:`ShotgunHierarchyModel`
    can also be subclassed from this class.
    """

    def load_data(self, path, seed_entity_field, entity_fields=None):
        """
        Loads shotgun data into the model, using the cache if possible.

        :param str path: The path (url) to the root of the hierarchy to display.
            This corresponds to the ``path`` argument of the ``nav_expand()``
            api method. For example, ``/Project/65`` would correspond to a
            project on you shotgun site with id of ``65``.

        :param str seed_entity_field: This is a string that corresponds to the
            field on an entity used to seed the hierarchy. For example, a value
            of ``Version.entity`` would cause the model to display a hierarchy
            where the leaves match the entity value of Version entities.

        :param dict entity_fields: A dictionary that identifies what fields to
            include on returned entities. Since the hierarchy can include any
            entity structure, this argument allows for specification of
            additional fields to include as these entities are returned. The
            dict's keys correspond to the entity type and the value is a list
            of field names to return.

        .. note:: For additional information on the ``path``,
            ``seed_entity_field``, and ``entity_fields`` arguments, please see
            the `<python-api docs http://developer.shotgunsoftware.com/python-api/reference.html#shotgun>`_.

        """

        super(SimpleShotgunHierarchyModel, self)._load_data(
            path,
            seed_entity_field,
            entity_fields=entity_fields
        )
        self._refresh_data()