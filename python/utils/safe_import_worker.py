import importlib
import json
import sys


def main():
    """
    Reads JSON input from stdin containing a module name and an expression.
    Dynamically imports the module and evaluates the expression in its context.
    Outputs a JSON object to stdout with the result or an error message.
    """
    try:
        input_data = json.loads(sys.stdin.read())
        module_name = input_data.get("module")
        expression = input_data.get("expression")

        if not module_name or not expression:
            raise ValueError("Missing module name or expression")

        # Import the requested module
        mod = importlib.import_module(module_name)

        # Evaluate the expression using the module
        result = eval(expression, {module_name: mod})

        # Attempt to serialize the result; fallback to repr if serialization fails
        try:
            json.dumps(result)  # test if result is JSON serializable
            safe_result = result
        except Exception:
            safe_result = repr(result)

        # Output the successful result as JSON
        print(json.dumps({"success": True, "result": safe_result}))

    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))


if __name__ == "__main__":
    main()
