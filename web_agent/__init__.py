"""
web_agent package: agentic FastAPI service components.
"""

from .agent import AgentResult, ToolUseAgent, build_agent_metadata

__all__ = ["AgentResult", "ToolUseAgent", "build_agent_metadata"]
