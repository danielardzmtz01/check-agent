from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, AgentTool
from google.genai import types

from code_review_agent.tools.file_tools import (
    fetch_local_file_content,
    propose_code_modification,
)
from code_review_agent.tools.test_runner import (
    run_local_pytest,
    run_python_syntax_check,
)
from code_review_agent.guardrails import (
    secret_detector_callback,
    tool_error_recovery_callback,
)
from code_review_agent.telemetry import (
    before_model_logging_callback,
    after_model_logging_callback,
    before_tool_logging_callback,
    after_tool_logging_callback,
)

import os
from dotenv import load_dotenv

# Try loading .env variables locally
load_dotenv()

def resolve_api_key():
    """Resolves Gemini API Key, attempting Secret Manager fallback if not in env."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key
        
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    secret_name = os.environ.get("GEMINI_API_KEY_SECRET_NAME", "gemini-api-key")
    
    if project_id:
        try:
            from google.adk.integrations.secret_manager.secret_client import SecretManagerClient
            print(f"Attempting to fetch API key from Google Secret Manager (project={project_id}, secret={secret_name})...")
            client = SecretManagerClient()
            resource_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            secret_val = client.get_secret(resource_path)
            if secret_val:
                os.environ["GEMINI_API_KEY"] = secret_val
                return secret_val
        except Exception as e:
            print(f"Warning: Could not fetch secret from Secret Manager: {e}")
            
    return None

# Resolve key before any ADK agents are initialized
resolve_api_key()

def create_agent_system(

    pro_model: str = "gemini-pro-latest",
    flash_model: str = "gemini-3.5-flash"
) -> LlmAgent:

    """Creates the Code Review & Bug Fixer Multi-Agent System.

    Uses Strategic Model Routing (Pro for Coordinator, Flash for sub-agents)
    and attaches Guardrail and Telemetry callbacks.

    Args:
        pro_model: The name of the model to use for high-level orchestration.
        flash_model: The name of the model to use for specialized tasks.

    Returns:
        The root Coordinator agent.
    """
    
    # 1. REVIEWER SUB-AGENT (Flash Model)
    reviewer_agent = LlmAgent(
        name="reviewer_agent",
        description="Senior software engineer specialized in code review and finding bugs.",
        instruction=(
            "You are a Senior Software Engineer specializing in code review.\n"
            "Your task is to analyze code files to identify bugs, performance bottlenecks, security concerns, "
            "and style violations. Use the fetch_local_file_content tool to read code files.\n\n"
            "Produce a structured Markdown review report detailing:\n"
            "- File Path\n"
            "- Severity Level (High, Medium, Low)\n"
            "- Description of the issue\n"
            "- Suggested fix\n"
            "Be specific and direct. If the code looks correct and has no issues, state that clearly."
        ),
        model=flash_model,
        tools=[
            FunctionTool(fetch_local_file_content),
        ],
        before_model_callback=before_model_logging_callback,
        after_model_callback=after_model_logging_callback,
        before_tool_callback=before_tool_logging_callback,
        after_tool_callback=after_tool_logging_callback,
        on_tool_error_callback=tool_error_recovery_callback,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=4096,
        ),
    )

    # 2. FIXER SUB-AGENT (Flash Model)
    fixer_agent = LlmAgent(
        name="fixer_agent",
        description="Automated software developer specialized in applying code fixes.",
        instruction=(
            "You are an Automated Code Fixer Agent.\n"
            "Your job is to apply code modifications to address bugs, linter issues, or code reviews.\n\n"
            "Workflow:\n"
            "1. Read the target file using fetch_local_file_content to see the current code.\n"
            "2. Plan your modifications to resolve the issues.\n"
            "3. Propose the updated code using the propose_code_modification tool (requires human approval).\n"
            "4. Verify the syntax using the run_python_syntax_check tool to ensure there are no syntax errors.\n"
            "5. If syntax issues are reported, modify your code and propose the update again.\n\n"
            "Return a clean summary of the modification, explain the changes made, and show a diff-like explanation."
        ),
        model=flash_model,
        tools=[
            FunctionTool(fetch_local_file_content),
            FunctionTool(propose_code_modification, require_confirmation=True),
            FunctionTool(run_python_syntax_check),
        ],
        before_model_callback=before_model_logging_callback,
        after_model_callback=after_model_logging_callback,
        # Chain before_tool_logging_callback and secret_detector_callback
        before_tool_callback=[before_tool_logging_callback, secret_detector_callback],
        after_tool_callback=after_tool_logging_callback,
        on_tool_error_callback=tool_error_recovery_callback,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=8192,
        ),
    )

    # 3. TESTER SUB-AGENT (Flash Model)
    tester_agent = LlmAgent(
        name="tester_agent",
        description="Automated QA engineer specialized in writing and running unit tests.",
        instruction=(
            "You are an Automated Quality Assurance Engineer Agent.\n"
            "Your job is to run unit tests and ensure that the codebase is stable.\n\n"
            "Workflow:\n"
            "1. Run existing unit tests using run_local_pytest.\n"
            "2. If tests fail, analyze the failures and report them back to help the fixer.\n"
            "3. If new test cases are needed to cover the changes, add or modify the test file using propose_code_modification.\n"
            "4. Rerun run_local_pytest to verify that all tests pass.\n\n"
            "Report the outcome of the test run, highlighting if any tests are passing, failing, or added."
        ),
        model=flash_model,
        tools=[
            FunctionTool(fetch_local_file_content),
            FunctionTool(propose_code_modification, require_confirmation=True),
            FunctionTool(run_local_pytest),
        ],
        before_model_callback=before_model_logging_callback,
        after_model_callback=after_model_logging_callback,
        before_tool_callback=[before_tool_logging_callback, secret_detector_callback],
        after_tool_callback=after_tool_logging_callback,
        on_tool_error_callback=tool_error_recovery_callback,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=4096,
        ),
    )

    # 4. COORDINATOR AGENT (Pro Model)
    coordinator_agent = LlmAgent(
        name="code_review_coordinator",
        description="Main coordinator agent for code reviews, code fixes, and unit tests.",
        instruction=(
            "You are the Code Review & Bug Fixer Coordinator agent.\n"
            "Your role is to orchestrate a team of specialized sub-agents to review, modify, and test Python code.\n"
            "You have access to three sub-agents:\n"
            "- reviewer_agent: Performs code review analysis.\n"
            "- fixer_agent: Applies modifications to solve bugs or reviews.\n"
            "- tester_agent: Runs pytest and manages test cases.\n\n"
            "When the user requests an action, analyze their request and delegate to the appropriate agent(s).\n"
            "Typically, a full workflow looks like this:\n"
            "1. Run reviewer_agent on the file to find bugs.\n"
            "2. Present reviewer findings to the user.\n"
            "3. If the user wishes to proceed with the fixes, invoke fixer_agent to modify the file.\n"
            "4. After the fixer finishes, invoke tester_agent to run the test suite and confirm everything works.\n\n"
            "Always state which sub-agent you are calling before doing so."
        ),
        model=pro_model,
        tools=[
            AgentTool(reviewer_agent),
            AgentTool(fixer_agent),
            AgentTool(tester_agent),
        ],
        before_model_callback=before_model_logging_callback,
        after_model_callback=after_model_logging_callback,
        before_tool_callback=before_tool_logging_callback,
        after_tool_callback=after_tool_logging_callback,
        on_tool_error_callback=tool_error_recovery_callback,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=8192,
        ),
    )

    return coordinator_agent

from google.adk.apps.app import App
from google.adk.apps.compaction import EventsCompactionConfig, LlmEventSummarizer
from google.adk.models import Gemini

# Create the singleton root agent instance for ADK runner
root_agent = create_agent_system()

# Create compaction configuration (Category 2: Context & Memory - History Compaction)
gemini_flash_compaction = Gemini(model="gemini-3.5-flash")
summarizer = LlmEventSummarizer(llm=gemini_flash_compaction)


compaction_config = EventsCompactionConfig(
    summarizer=summarizer,
    compaction_interval=5,
    overlap_size=3,
    token_threshold=5000,
    event_retention_size=10
)

# Define the main application configuration
app = App(
    name="code_review_app",
    root_agent=root_agent,
    events_compaction_config=compaction_config
)


