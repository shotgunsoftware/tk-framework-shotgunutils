# Copyright (c) 2019 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from tank_vendor import six

from tank_test.tank_test_base import setUpModule  # noqa
from base_test import TestShotgunUtilsFramework


class TestShotgunModelUtil(TestShotgunUtilsFramework):
    """
    Tests the Shotgun Model utilities
    """

    def setUp(self):
        """
        Fixtures setup
        """
        super(TestShotgunModelUtil, self).setUp()
        self.shotgun_model = self.framework.import_module("shotgun_model")
        self.has_qstring = hasattr(sgtk.platform.qt.QtCore, "QString")
        self.has_qbytearray = hasattr(sgtk.platform.qt.QtCore, "QByteArray")
        self.has_qvariant = hasattr(sgtk.platform.qt.QtCore, "QVariant")

    def _test_sanitize_qt(self, input, expected):
        """
        Test shotgun_model.util.sanitize_qt

        :param input: Value to sanitize.
        :param expected: Expected value after sanitization.
        """
        result = self.shotgun_model.util.sanitize_qt(input)
        # Test that both types and values are equal, because
        # in Python 2 "text" == u"text" and 1 == 1L
        assert type(result) == type(expected)
        assert result == expected

    def test_sanitize_qt(self):
        """
        Ensure values received from Qt are sanitized properly.
        """
        self._test_sanitize_qt(None, None)
        self._test_sanitize_qt(True, True)
        self._test_sanitize_qt(1, 1)
        self._test_sanitize_qt(1.5, 1.5)
        self._test_sanitize_qt(b"Bytes", b"Bytes")
        self._test_sanitize_qt("Allo", "Allo")
        self._test_sanitize_qt(["one", 2, 3.0], ["one", 2, 3.0])
        self._test_sanitize_qt(
            {"key": "value", "another_key": 1, "third_key": 3.0},
            {"key": "value", "another_key": 1, "third_key": 3.0},
        )
        # In Python 2 we have extra data types to worry about, like unicode and long
        if six.PY2:
            self._test_sanitize_qt(unicode("Something"), "Something")
            self._test_sanitize_qt(long(1), int(1))
            self._test_sanitize_qt([unicode("one"), 2, 3.0], [unicode("one"), 2, 3.0])
            self._test_sanitize_qt(
                {
                    unicode("key"): unicode("value"),
                    unicode("another_key"): 1,
                    unicode("third_key"): 3.0,
                },
                {"key": "value", "another_key": 1, "third_key": 3.0},
            )

        # TODO: This hasn't been tested with PyQt5, as tk-core doesn't support it yet.
        # Maybe there will be some issues, as QString is only available on PyQtn
        if self.has_qstring:
            self._test_sanitize_qt(
                sgtk.platform.qt.QtCore.QString("Something"), "Something"
            )
        if self.has_qbytearray:
            if six.PY2:
                self._test_sanitize_qt(
                    sgtk.platform.qt.QtCore.QByteArray(b"Something"), "Something"
                )
            else:
                # FIXME: Under Python 3, PySide2's QByteArray doesn't have any way on
                # extracting a str out of a QByteArray. The __str__ method is actually
                # broken.
                pass

        if self.has_qvariant:
            self._test_sanitize_qt(sgtk.platform.qt.QtCore.QVariant(1), 1)
            self._test_sanitize_qt(sgtk.platform.qt.QtCore.QVariant("text"), "text")
            self._test_sanitize_qt(sgtk.platform.qt.QtCore.QVariant(3.2), 3.2)
            if six.PY2:
                self._test_sanitize_qt(
                    sgtk.platform.qt.QtCore.QVariant(unicode("text")), "text"
                )
                self._test_sanitize_qt(sgtk.platform.qt.QtCore.QVariant(long(1)), 1)

    def _test_sanitize_for_qt_model(self, input, expected):
        """
        Test shotgun_model.util.sanitize_for_qt_model

        :param input: Value to sanitize.
        :param expected: Expected value after sanitization.
        """
        result = self.shotgun_model.util.sanitize_for_qt_model(input)
        assert type(result) == type(expected)
        assert result == expected

    def test_sanitize_for_qt_model(self):
        """
        Ensure values about to be stored into a Qt model will be
        sanitized properly.
        """
        if six.PY2:
            self._test_sanitize_for_qt_model(unicode("text"), unicode("text"))
            self._test_sanitize_for_qt_model("text", unicode("text"))
            self._test_sanitize_for_qt_model(
                {unicode("text"): unicode("text2")}, {unicode("text"): unicode("text2")}
            )
            self._test_sanitize_for_qt_model(
                {"text": "text2"}, {unicode("text"): unicode("text2")}
            )
            self._test_sanitize_for_qt_model(
                ["text", unicode("text2")], [unicode("text"), unicode("text2")]
            )
        else:
            self._test_sanitize_for_qt_model("text", "text")
            self._test_sanitize_for_qt_model({"text": "text2"}, {"text": "text2"})
            self._test_sanitize_for_qt_model(["text", "text2"], ["text", "text2"])

        self._test_sanitize_for_qt_model(None, None)
        self._test_sanitize_for_qt_model(1, 1)
        self._test_sanitize_for_qt_model(3.1, 3.1)
        self._test_sanitize_for_qt_model(True, True)
