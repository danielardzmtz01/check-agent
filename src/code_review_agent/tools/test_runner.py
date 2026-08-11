import subprocess
import os
import ast
from pydantic import BaseModel, Field

class RunLocalPytestInput(BaseModel):
    test_path: str = Field(
        default="tests", 
        description="Path to the test file or directory to run. Defaults to 'tests'."
    )

class RunPythonSyntaxCheckInput(BaseModel):
    filepath: str = Field(
        ..., 
        description="Relative path of the Python file to inspect for syntax errors."
    )

def run_local_pytest(input_data: RunLocalPytestInput) -> str:
    """Runs pytest on the specified test file or directory.

    Args:
        input_data: The target path for pytest execution.

    Returns:
        The stdout/stderr of the test run, or descriptive recovery instructions on error.
    """
    test_path = input_data.test_path
    if ".." in test_path or test_path.startswith("/"):
        return f"Error: Invalid test path '{test_path}'."
    
    if not os.path.exists(test_path):
        return (
            f"Error: The path '{test_path}' does not exist. "
            f"Please verify the test path. If you want to run all tests, keep 'tests' as the default."
        )

    try:
        # Run pytest inside a subprocess
        result = subprocess.run(
            ["python3", "-m", "pytest", test_path, "-v"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = f"Pytest Execution Finished.\n"
        output += f"Exit Code: {result.returncode}\n\n"
        output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
            
        if result.returncode != 0:
            output += (
                "\nRecovery Tip: Some tests failed or pytest encountered an error. "
                "Inspect the STDOUT above to identify failed test cases, tracebacks, and assertion mismatches. "
                "Update the code or tests and rerun the suite."
            )
        else:
            output += "\nSuccess: All tests passed successfully."
            
        return output
    except subprocess.TimeoutExpired:
        return "Error: Pytest execution timed out after 30 seconds. Please check for infinite loops in the code."
    except Exception as e:
        return (
            f"Error: Failed to run pytest. Reason: {str(e)}. "
            f"Ensure 'pytest' is installed in the environment (e.g. run 'pip install pytest') and try again."
        )

def run_python_syntax_check(input_data: RunPythonSyntaxCheckInput) -> str:
    """Parses a Python file to check for compilation or syntax errors.

    Args:
        input_data: The target Python file path.

    Returns:
        A success message if no syntax errors were found, or a detailed error trace with line numbers.
    """
    filepath = input_data.filepath
    if not os.path.exists(filepath):
        return f"Error: File '{filepath}' does not exist."
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source_code = f.read()
            
        # Parse the syntax tree to check for compilation errors
        ast.parse(source_code, filename=filepath)
        return f"Success: Syntax check passed for '{filepath}'. The file compiles without syntax errors."
    except SyntaxError as e:
        return (
            f"Syntax Error in '{filepath}':\n"
            f" - Message: {e.msg}\n"
            f" - Line: {e.lineno}\n"
            f" - Offset: {e.offset}\n"
            f" - Code snippet: {e.text.strip() if e.text else ''}\n"
            f"Recovery Tip: Please fix the syntax error at line {e.lineno} before running test cases."
        )
    except Exception as e:
        return f"Error: Unable to analyze syntax for '{filepath}'. Reason: {str(e)}"
