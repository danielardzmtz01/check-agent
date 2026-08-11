import os
from pydantic import BaseModel, Field
from google.adk.tools import ToolContext

class FetchLocalFileContentInput(BaseModel):
    filepath: str = Field(
        ..., 
        description="Relative path of the project file to read (from the repository root)."
    )

class ProposeCodeModificationInput(BaseModel):
    filepath: str = Field(
        ..., 
        description="Relative path of the project file to write or update (from the repository root)."
    )
    content: str = Field(
        ..., 
        description="The complete, updated file content to write. Placeholders are not allowed."
    )
    rationale: str = Field(
        ..., 
        description="The reasoning behind why this change is being made."
    )

def fetch_local_file_content(input_data: FetchLocalFileContentInput) -> str:
    """Reads the contents of a local project file.

    Args:
        input_data: The input containing the target file path.

    Returns:
        The content of the file or a descriptive error message with recovery instructions.
    """
    filepath = input_data.filepath
    # Prevent directory traversal attacks
    if ".." in filepath or filepath.startswith("/"):
        return (
            f"Error: Invalid file path '{filepath}'. "
            f"Only relative paths within the project workspace are allowed. "
            f"Please specify a path relative to the repository root (e.g., 'src/main.py')."
        )
    
    if not os.path.exists(filepath):
        # Guided error handling
        files_in_dir = []
        for root, _, files in os.walk("."):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), ".")
                if not rel_path.startswith(".") and "node_modules" not in rel_path and "__pycache__" not in rel_path:
                    files_in_dir.append(rel_path)
        
        file_list_str = "\n".join(files_in_dir[:15])
        return (
            f"Error: The file '{filepath}' does not exist. "
            f"Here are some of the files currently available in the project:\n{file_list_str}\n"
            f"Please verify the filepath and try again with an existing path."
        )

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: Unable to read file '{filepath}'. Reason: {str(e)}. Please check file permissions."

def propose_code_modification(input_data: ProposeCodeModificationInput, tool_context: ToolContext) -> str:
    """Proposes a code modification to a file. 

    This tool requires human approval. If approved, it will update the file content.

    Args:
        input_data: The target file path, complete content, and rationale.
        tool_context: ADK ToolContext to interact with session/approval mechanisms.

    Returns:
        A confirmation message if the write succeeded, or an error message.
    """
    filepath = input_data.filepath
    if ".." in filepath or filepath.startswith("/"):
        return (
            f"Error: Invalid file path '{filepath}'. "
            f"Only relative paths within the project workspace are allowed."
        )
    
    # Ensure parent directory exists
    dir_name = os.path.dirname(filepath)
    if dir_name and not os.path.exists(dir_name):
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception as e:
            return f"Error: Failed to create directories for '{filepath}'. Reason: {str(e)}."

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(input_data.content)
        return f"Success: Successfully updated file '{filepath}' with the proposed changes."
    except Exception as e:
        return f"Error: Failed to write to file '{filepath}'. Reason: {str(e)}."
