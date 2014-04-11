# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'dialog.ui'
#
#      by: pyside-uic 0.2.13 running on PySide 1.1.0
#
# WARNING! All changes made in this file will be lost!

from tank.platform.qt import QtCore, QtGui

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(802, 532)
        Dialog.setStyleSheet("#Dialog {\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/bg.png); \n"
"}\n"
"\n"
"")
        self.horizontalLayout_2 = QtGui.QHBoxLayout(Dialog)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.left_arrow = QtGui.QToolButton(Dialog)
        self.left_arrow.setMinimumSize(QtCore.QSize(34, 34))
        self.left_arrow.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.left_arrow.setStyleSheet("QToolButton{\n"
"width: 12px;\n"
"height: 20px;\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/left_arrow.png);\n"
"border: none;\n"
"background-color: none;\n"
"}\n"
"\n"
"\n"
"QToolButton:hover{\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/left_arrow_hover.png);\n"
"}\n"
"\n"
"QToolButton:Pressed {\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/left_arrow_pressed.png);\n"
"}\n"
"")
        self.left_arrow.setText("")
        self.left_arrow.setAutoRaise(True)
        self.left_arrow.setObjectName("left_arrow")
        self.horizontalLayout_2.addWidget(self.left_arrow)
        self.verticalLayout_2 = QtGui.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.groupBox = QtGui.QGroupBox(Dialog)
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.verticalLayout = QtGui.QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName("verticalLayout")
        self.stackedWidget = QtGui.QStackedWidget(self.groupBox)
        self.stackedWidget.setMinimumSize(QtCore.QSize(650, 400))
        self.stackedWidget.setMaximumSize(QtCore.QSize(650, 400))
        self.stackedWidget.setObjectName("stackedWidget")
        self.page_1 = QtGui.QWidget()
        self.page_1.setObjectName("page_1")
        self.stackedWidget.addWidget(self.page_1)
        self.page_2 = QtGui.QWidget()
        self.page_2.setObjectName("page_2")
        self.stackedWidget.addWidget(self.page_2)
        self.verticalLayout.addWidget(self.stackedWidget)
        self.verticalLayout_2.addWidget(self.groupBox)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtGui.QSpacerItem(248, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.view_documentation = QtGui.QToolButton(Dialog)
        self.view_documentation.setObjectName("view_documentation")
        self.horizontalLayout.addWidget(self.view_documentation)
        self.close = QtGui.QToolButton(Dialog)
        self.close.setObjectName("close")
        self.horizontalLayout.addWidget(self.close)
        self.verticalLayout_2.addLayout(self.horizontalLayout)
        self.horizontalLayout_2.addLayout(self.verticalLayout_2)
        self.right_arrow = QtGui.QToolButton(Dialog)
        self.right_arrow.setMinimumSize(QtCore.QSize(34, 34))
        self.right_arrow.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.right_arrow.setStyleSheet("QToolButton{\n"
"width: 12px;\n"
"height: 20px;\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/right_arrow.png);\n"
"border: none;\n"
"background-color: none;\n"
"}\n"
"\n"
"\n"
"QToolButton:hover{\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/right_arrow_hover.png);\n"
"}\n"
"\n"
"QToolButton:Pressed {\n"
"background-image: url(:/tk_framework_shotgunutils.help_screen/right_arrow_pressed.png);\n"
"}\n"
"")
        self.right_arrow.setText("")
        self.right_arrow.setAutoRaise(True)
        self.right_arrow.setObjectName("right_arrow")
        self.horizontalLayout_2.addWidget(self.right_arrow)

        self.retranslateUi(Dialog)
        self.stackedWidget.setCurrentIndex(1)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QtGui.QApplication.translate("Dialog", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.left_arrow.setToolTip(QtGui.QApplication.translate("Dialog", "Click for App Details", None, QtGui.QApplication.UnicodeUTF8))
        self.view_documentation.setText(QtGui.QApplication.translate("Dialog", "Jump to Documentation", None, QtGui.QApplication.UnicodeUTF8))
        self.close.setText(QtGui.QApplication.translate("Dialog", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.right_arrow.setToolTip(QtGui.QApplication.translate("Dialog", "Click for App Details", None, QtGui.QApplication.UnicodeUTF8))

from . import resources_rc
