import re
import logging
from typing import Any, Dict
from google.adk.tools import BaseTool, ToolContext

logger = logging.getLogger("code_review_agent.guardrails")

def secret_detector_callback(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext) -> None:
    """Guardrail callback to inspect proposed code content for hardcoded API keys/secrets.

    If a secret is detected, it raises a ValueError to prevent tool execution.

    Args:
        tool: The ADK tool being executed.
        args: The arguments passed to the tool.
        tool_context: The ADK ToolContext.

    Raises:
        ValueError: If a potential secret or credentials are found in the code content.
    """
    # We only inspect 'propose_code_modification'
    if tool.name == "propose_code_modification":
        # Extract content argument
        input_data = args.get("input_data")
        if not input_data:
            return

        # input_data can be a Pydantic model or a dictionary
        content = getattr(input_data, "content", None) or input_data.get("content", "")
        
        # Check for Google API keys
        if re.search(r"AIzaSy[A-Za-z0-9_-]{35}", content):
            logger.warning("Guardrail Triggered: Hardcoded Google API Key found in proposal.")
            raise ValueError(
                "Guardrail Violation: Potential Google API key detected. "
                "Hardcoded credentials must not be committed to code. "
                "Please rewrite the code using environment variables (e.g. os.environ.get('API_KEY')) "
                "and ensure all secrets are securely fetched."
            )
            
        # Check for OpenAI/Generic sk- API keys
        if re.search(r"sk-[A-Za-z0-9]{32,48}", content):
            logger.warning("Guardrail Triggered: Hardcoded OpenAI key found in proposal.")
            raise ValueError(
                "Guardrail Violation: Potential OpenAI/Generic API key detected. "
                "Hardcoded credentials must not be committed to code. "
                "Please rewrite the code using environment variables (e.g. os.environ.get('OPENAI_API_KEY')) "
                "and ensure all secrets are securely fetched."
            )


def tool_error_recovery_callback(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, error: Exception) -> Dict[str, Any]:
    """Formats tool exceptions into recovery instructions that are returned to the LLM.

    Args:
        tool: The ADK tool.
        args: The arguments.
        tool_context: The ADK ToolContext.
        error: The exception raised.

    Returns:
        A dictionary containing the error message and recovery suggestions for the LLM.
    """
    logger.error(f"Tool {tool.name} failed with exception: {error}")
    
    # Custom recovery instructions based on the exception type
    if isinstance(error, ValueError) and "Guardrail Violation" in str(error):
        return {
            "error": f"Tool Execution Blocked by Policy:\n{str(error)}\n"
                     f"Action Required: Modify the code to use secure environment variables or a configuration file. "
                     f"Do not write the API key explicitly."
        }
        
    return {
        "error": f"Tool '{tool.name}' execution failed.\n"
                 f"Exception Details: {type(error).__name__}: {str(error)}\n"
                 f"Recovery Tip: Please verify the inputs you passed to this tool. "
                 f"Ensure all file paths are valid, and code content is formatted correctly."
    }

