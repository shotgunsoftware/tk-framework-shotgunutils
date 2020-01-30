Shotgun Asynchronous Data Retriever
######################################


Introduction
======================================

The Shotgun data retriever makes it easy to pull in shotgun data and
thumbnails in a background thread. It also manages caching of thumbnails
on disk so that they don't need to be retrieved over and over again.

You start the worker thread, then you can submit a series of requests which
will be handled by the data object. Each time data arrives, a signal is emitted with
the details of the data. Each object will by default have its own Shotgun API connection.
Requests are prioritized so according to their priority. For example, Shotgun ``find()`` queries will
always take precedence over shotgun thumbnail downloads.


Sample Code
======================================

The sample code below shows how you can use the data retriever in your Toolkit App Code::

    # import the module - note that this is using the special
    # import_framework code so it won't work outside an app
    sg_data = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_data")

    class ExampleWidget(QtGui.QWidget):

        def __init__(self):

            QtGui.QWidget.__init__(self)

            self.ui = Ui_Dialog()
            self.ui.setupUi(self)

            # set up data retriever
            self.__sg_data = sg_data.ShotgunDataRetriever(self)
            self.__sg_data.work_completed.connect( self.__on_worker_signal)
            self.__sg_data.work_failure.connect( self.__on_worker_failure)

            # and start its thread!
            self.__sg_data.start()

            # do an async request
            self._find_uid = self.__sg_data.execute_find("Shot", [], ["code"])


        def closeEvent(self, event):
            """
            Executed when the widget dialog is closed.
            """
            # gracefully stop our data retriever. This call
            # will block util the currently processing request has completed.
            self.__sg_data.stop()

            # okay to close dialog
            event.accept()

        def __on_worker_failure(self, uid, msg):
            """
            Asynchronous callback - the worker thread errored.
            """
            print "Error: %s" % msg

        def __on_worker_signal(self, uid, request_type, data):
            """
            Signaled whenever the worker completes something.
            """
            print "Data arrived: %s" % data


Class ShotgunDataRetriever
============================================

.. note::

    Import the module into your Toolkit App using the following statement::

        shotgun_data = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_data")

.. currentmodule:: shotgun_data


.. autoclass:: ShotgunDataRetriever
    :members:
    :inherited-members:
