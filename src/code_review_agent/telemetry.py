import json
import logging
import time
from typing import Any, Dict
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from google.adk.tools import BaseTool, ToolContext
from google.adk.models import LlmRequest, LlmResponse


# Set up global OpenTelemetry tracer
provider = TracerProvider()
# For local run, we can export traces to console or use default provider
processor = SimpleSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("code-review-agent")

# Set up structured JSON logger
logger = logging.getLogger("code_review_agent.telemetry")
logger.setLevel(logging.INFO)

class JSONFormatter(logging.Formatter):
    """Custom logging formatter that outputs logs as structured JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra attributes if passed via logging.info(..., extra={...})
        if record.__dict__.get("extra_metadata"):
            log_data["metadata"] = record.__dict__["extra_metadata"]
            
        # PII Secret Scrubbing in logs
        log_str = json.dumps(log_data)
        # Scrub potential Google API keys (AIzaSy...)
        log_str = re_scrub(r"AIzaSy[A-Za-z0-9_-]{35}", "[REDACTED_API_KEY]", log_str)
        # Scrub OpenAI/Generic sk- API keys
        log_str = re_scrub(r"sk-[A-Za-z0-9]{32,48}", "[REDACTED_API_KEY]", log_str)
        
        return log_str

def re_scrub(pattern: str, replacement: str, text: str) -> str:
    import re
    return re.sub(pattern, replacement, text)

# Configure console handler with JSON formatter
ch = logging.StreamHandler()
ch.setFormatter(JSONFormatter())
logger.addHandler(ch)
logger.propagate = False # Prevent double logging

# Active spans dictionary to link before/after callbacks
active_spans = {}

# INTENT VS OUTCOME LOGGING CALLBACKS
def before_model_logging_callback(callback_context: Any, llm_request: LlmRequest) -> None:
    """Logs the agent's intent to call the LLM model (Before Model Callback)."""
    # callback_context holds invocation_context
    invocation_context = getattr(callback_context, "invocation_context", None)
    agent_name = "unknown"
    if invocation_context and getattr(invocation_context, "agent", None):
        agent_name = invocation_context.agent.name
        
    extra = {
        "event": "llm_call_intent",
        "agent_name": agent_name,
        "model": llm_request.model,
    }
    logger.info(
        f"Agent '{agent_name}' is intending to call model '{llm_request.model}'", 
        extra={"extra_metadata": extra}
    )
    
    # Start OpenTelemetry span
    span = tracer.start_span(f"llm_call_{agent_name}")
    span.set_attribute("model", llm_request.model)
    span.set_attribute("agent", agent_name)
    span_id = f"model_{id(llm_request)}"
    active_spans[span_id] = span

def after_model_logging_callback(callback_context: Any, llm_response: LlmResponse) -> None:
    """Logs the outcome of the LLM model call (After Model Callback)."""
    invocation_context = getattr(callback_context, "invocation_context", None)
    agent_name = "unknown"
    if invocation_context and getattr(invocation_context, "agent", None):
        agent_name = invocation_context.agent.name
        
    extra = {
        "event": "llm_call_outcome",
        "agent_name": agent_name,
        "finish_reason": getattr(llm_response, "finish_reason", "completed"),
    }
    logger.info(
        f"Agent '{agent_name}' received model response successfully.",
        extra={"extra_metadata": extra}
    )
    
    # Retrieve and end span
    for key, span in list(active_spans.items()):
        if key.startswith("model_"):
            span.set_attribute("finish_reason", extra["finish_reason"])
            span.end()
            active_spans.pop(key)

def before_tool_logging_callback(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext) -> None:
    """Logs the agent's intent to execute a tool (Before Tool Callback)."""
    # tool_context holds agent details
    agent_name = "unknown"
    if hasattr(tool_context, "agent") and tool_context.agent:
        agent_name = tool_context.agent.name
    
    # PII Scrubbing of args before logging
    clean_args = json.loads(json.dumps(args, default=str))
    if "input_data" in clean_args and isinstance(clean_args["input_data"], dict):
        if "content" in clean_args["input_data"]:
            # Truncate content to avoid log bloating and scrub keys
            clean_args["input_data"]["content"] = clean_args["input_data"]["content"][:100] + "... (truncated)"
            
    extra = {
        "event": "tool_execution_intent",
        "agent_name": agent_name,
        "tool_name": tool.name,
        "arguments": clean_args,
    }
    logger.info(
        f"Agent '{agent_name}' is executing tool '{tool.name}'", 
        extra={"extra_metadata": extra}
    )
    
    # Start OpenTelemetry span
    span = tracer.start_span(f"tool_exec_{tool.name}")
    span.set_attribute("tool_name", tool.name)
    span.set_attribute("agent", agent_name)
    span_id = f"tool_{tool.name}_{id(tool_context)}"
    active_spans[span_id] = span


def after_tool_logging_callback(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Any) -> Any:
    """Logs the outcome of the tool execution (After Tool Callback)."""
    agent_name = "unknown"
    if hasattr(tool_context, "agent") and tool_context.agent:
        agent_name = tool_context.agent.name
    
    # Safe result rendering for logs
    clean_result = str(tool_response)[:300] + "... (truncated)" if len(str(tool_response)) > 300 else str(tool_response)
    
    extra = {
        "event": "tool_execution_outcome",
        "agent_name": agent_name,
        "tool_name": tool.name,
        "outcome": "success" if not isinstance(tool_response, dict) or "error" not in tool_response else "failed",
        "result_preview": clean_result,
    }
    logger.info(
        f"Agent '{agent_name}' completed tool '{tool.name}' execution with status: {extra['outcome']}",
        extra={"extra_metadata": extra}
    )
    
    # End OpenTelemetry span
    span_id = f"tool_{tool.name}_{id(tool_context)}"
    span = active_spans.pop(span_id, None)
    if span:
        span.set_attribute("outcome", extra["outcome"])
        span.end()
        
    return tool_response

