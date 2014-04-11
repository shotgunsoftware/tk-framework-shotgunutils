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

from tank.platform.qt import QtCore, QtGui
from .ui.dialog import Ui_Dialog

def show_help_screen(parent):
    """
    Show help screen window
    """
    gui = Dialog(parent)    
    gui.show()
    # center on top of parent window
    gui.move(gui.parent().window().frameGeometry().center() - gui.window().rect().center())
    gui.repaint()

class Dialog(QtGui.QDialog):
    """
    Simple list widget which hosts a square thumbnail, header text
    and body text. It has a fixed size.
    
    This class is typically used in conjunction with a QT View and the 
    ShotgunDelegate class. 
    """
    
    def __init__(self, parent):
        """
        Constructor
        """
        QtGui.QDialog.__init__(self, parent, QtCore.Qt.SplashScreen | QtCore.Qt.WindowStaysOnTopHint)

        # set up the UI
        self.ui = Ui_Dialog() 
        self.ui.setupUi(self)
        
        
        
