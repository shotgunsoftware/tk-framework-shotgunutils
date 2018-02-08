# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import subprocess
from threading import Thread
from Queue import Queue
import tempfile
import sys
import traceback
import sgtk

logger = sgtk.platform.get_logger(__name__)


class ReadThread(Thread):
    """
    Thread that reads a pipe.
    """
    def __init__(self, p_out, target_queue):
        """
        Constructor.

        :param p_out: Pipe to read.
        :param target_queue: Queue that will accumulate the pipe output.
        """
        Thread.__init__(self)
        self.pipe = p_out
        self.target_queue = target_queue

    def run(self):
        """
        Reads the contents of the pipe and adds it to the queue until the pipe
        is closed.
        """
        while True:
            line = self.pipe.readline()         # blocking read
            if line == '':
                break
            self.target_queue.put(line)


class Command(object):

    @staticmethod
    def _create_temp_file():
        """
        :returns: Returns the path to a temporary file.
        """
        handle, path = tempfile.mkstemp(prefix="desktop_server")
        os.close(handle)
        return path

    @staticmethod
    def call_cmd(args):
        """
        Runs a command in a separate process.

        :param args: Command line tokens.

        :returns: A tuple containing (exit code, stdout, stderr).
        """
        # The commands that are being run are probably being launched from Desktop, which would
        # have a TANK_CURRENT_PC environment variable set to the site configuration. Since we
        # preserve that value for subprocesses (which is usually the behavior we want), the DCCs
        # being launched would try to run in the project environment and would get an error due
        # to the conflict.
        #
        # Clean up the environment to prevent that from happening.
        env = os.environ.copy()
        vars_to_remove = ["TANK_CURRENT_PC"]
        for var in vars_to_remove:
            if var in env:
                del env[var]

        # Launch the child process
        # Due to discrepencies on how child file descriptors and shell=True are
        # handled on Windows and Unix, we'll provide two implementations. See the Windows
        # implementation for more details.
        if sys.platform == "win32":
            ret, stdout_lines, stderr_lines = Command._call_cmd_win32(args, env)
        else:
            ret, stdout_lines, stderr_lines = Command._call_cmd_unix(args, env)

        out = ''.join(stdout_lines)
        err = ''.join(stderr_lines)

        return ret, out, err

    @staticmethod
    def _call_cmd_unix(args, env):
        """
        Runs a command in a separate process. Implementation for Unix based OSes.

        :param args: Command line tokens.
        :param env: Environment variables to set for the subprocess.

        :returns: A tuple containing (exit code, stdout, stderr).
        """
        # Note: Tie stdin to a PIPE as well to avoid this python bug on windows
        # http://bugs.python.org/issue3905
        # Queue code taken from: http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python
        stdout_lines = []
        stderr_lines = []

        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env
            )
            process.stdin.close()

            stdout_q = Queue()
            stderr_q = Queue()

            stdout_t = ReadThread(process.stdout, stdout_q)
            stdout_t.setDaemon(True)
            stdout_t.start()

            stderr_t = ReadThread(process.stderr, stderr_q)
            stderr_t.setDaemon(True)
            stderr_t.start()

            # Popen.communicate() doesn't play nicely if the stdin pipe is closed
            # as it tries to flush it causing an 'I/O error on closed file' error
            # when run from a terminal
            #
            # to avoid this, lets just poll the output from the process until
            # it's finished
            process.wait()

            try:
                process.stdout.flush()
                process.stderr.flush()
            except IOError:
                # This fails on OSX 10.7, but it looks like there's no ill side effect
                # from failing on that platform so we can ignore it.
                logger.exception("Error while flushing file descriptor:")
            stdout_t.join()
            stderr_t.join()

            while not stdout_q.empty():
                stdout_lines.append(stdout_q.get())

            while not stderr_q.empty():
                stderr_lines.append(stderr_q.get())

            ret = process.returncode
        except StandardError:
            # Do not log the command line, it might contain sensitive information!
            logger.exception("Error running subprocess:")

            ret = 1
            stderr_lines = traceback.format_exc().split()
            stderr_lines.append("%s" % args)

        return ret, stdout_lines, stderr_lines

    @staticmethod
    def _call_cmd_win32(args, env):
        """
        Runs a command in a separate process. Implementation for Windows.

        :param args: Command line tokens.
        :param env: Environment variables to set for the subprocess.

        :returns: A tuple containing (exit code, stdout, stderr).
        """
        stdout_lines = []
        stderr_lines = []
        try:
            stdout_path = Command._create_temp_file()
            stderr_path = Command._create_temp_file()

            # On Windows, file descriptors like sockets can be inherited by child
            # process and are only closed when the main process and all child
            # processes are closed. This is bad because it means that the port
            # the websocket server uses will never be released as long as any DCCs
            # or tank commands are running. Therefore, closing the Desktop and
            # restarting it for example wouldn't free the port and would give the
            # "port 9000 already in use" error we've seen before.

            # To avoid this, close_fds needs to be specified when launching a child
            # process. However, there's a catch. On Windows, specifying close_fds
            # also means that you can't share stdout, stdin and stderr with the child
            # process, which is required here because we want to capture the output
            # of the process.

            # Therefore on Windows we'll invoke the code in a shell environment. The
            # output will be redirected to two temporary files which will be read
            # when the child process is over.

            # Ideally, we'd be using this implementation on Unix as well. After all,
            # the syntax of the command line is the same. However, specifying shell=True
            # on Unix means that the following ["ls", "-al"] would be invoked like this:
            # ["/bin/sh", "-c", "ls", "-al"]. This means that only ls is sent to the
            # shell and -al is considered to be an argument of the shell and not part
            # of what needs to be launched. The naive solution would be to quote the
            # argument list and pass ["\"ls -al \""] to Popen, but that would ignore
            # the fact that there could already be quotes on that command line and
            # they would need to be escaped as well. Python 2's only utility to
            # escape strings for the command line is pipes.quote, which is deprecated.

            # Because of these reasons, we'll keep both implementations for now.

            args = args + ["1>", stdout_path, "2>", stderr_path]

            # Prevents the cmd.exe dialog from appearing on Windows.
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                args,
                close_fds=True,
                startupinfo=startupinfo,
                env=env,
                shell=True
            )
            process.wait()

            # Read back the output from the two.
            with open(stdout_path) as stdout_file:
                stdout_lines = [l for l in stdout_file]

            with open(stderr_path) as stderr_file:
                stderr_lines = [l for l in stderr_file]

            # Track the result code.
            ret = process.returncode

        except StandardError:
            logger.exception("Error running subprocess:")

            ret = 1
            stderr_lines = [traceback.format_exc().split()]
            stderr_lines.append("%s" % args)

        # Don't lose any sleep over temporary files that can't be deleted.
        try:
            os.remove(stdout_path)
        except:
            pass
        try:
            os.remove(stderr_path)
        except:
            pass

        return ret, stdout_lines, stderr_lines
