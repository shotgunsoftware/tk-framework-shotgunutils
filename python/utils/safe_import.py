import json
import os
import subprocess
import sys

import sgtk

logger = sgtk.LogManager.get_logger(__name__)


def safe_import(module_name):
    """
    Safely imports a Python module by evaluating its expressions in a separate process.

    This method returns a RemoteAttribute object, which acts as a proxy to the imported
    module. Any attribute access or function call is forwarded to a subprocess
    where the actual module is imported and evaluated.

    This can be useful for avoiding import-time crashes due to binary incompatibilities
    (e.g., between Qt libraries).

    :param module_name: Name of the module to import (e.g., "opentimelineio").
    :return: A RemoteAttribute object representing the imported module.
    """
    worker_path = os.path.join(os.path.dirname(__file__), "safe_import_worker.py")

    class RemoteAttribute:
        """
        A proxy object that mimics attribute access and function calls on a module
        imported in a separate Python subprocess.
        """

        def __init__(self, module_name, worker_path, attr_path):
            """
            :param module_name: Name of the module to import.
            :param worker_path: Path to the Python subprocess worker script.
            :param attr_path: Dot-separated attribute path being accessed.
            """
            self.module_name = module_name
            self.worker_path = os.path.abspath(worker_path)
            self.attr_path = attr_path  # E.g., opentimelineio.schema.Timeline

        def _call_worker(self, expression):
            """
            Executes a Python expression in the subprocess and returns the result.

            :param expression: A string of Python code to evaluate.
            :return: Result of the evaluated expression.
            :raises RuntimeError: If the worker fails or returns an error.
            """
            env = os.environ.copy()

            process = subprocess.Popen(
                [sys.executable, self.worker_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
            )

            input_data = json.dumps(
                {"module": self.module_name, "expression": expression}
            )

            stdout, stderr = process.communicate(input=input_data)

            if stderr:
                logger.warning("safe_import worker stderr: %s", stderr)

            try:
                response = json.loads(stdout)
                if response.get("success"):
                    return response["result"]
                else:
                    raise Exception(response.get("error"))
            except Exception as e:
                raise RuntimeError(f"Worker communication failed: {e}")

        def __getattr__(self, name):
            """
            Builds a new RemoteAttribute to represent a nested attribute.

            :param name: Name of the attribute to access.
            :return: A new RemoteAttribute instance.
            """
            return RemoteAttribute(
                module_name=self.module_name,
                worker_path=self.worker_path,
                attr_path=f"{self.attr_path}.{name}",
            )

        def __call__(self, *args, **kwargs):
            """
            Invokes a callable attribute with the given arguments.

            :param args: Positional arguments for the function.
            :param kwargs: Keyword arguments for the function.
            :return: Result of the function call.
            """
            arg_str = ", ".join(repr(arg) for arg in args)
            kwarg_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
            full_call = ", ".join(filter(None, [arg_str, kwarg_str]))
            expression = f"{self.attr_path}({full_call})"
            return self._call_worker(expression)

        def __repr__(self):
            """
            Returns the string representation of the remote attribute.
            """
            return self._call_worker(f"{self.attr_path}")

    return RemoteAttribute(module_name, worker_path, module_name)
