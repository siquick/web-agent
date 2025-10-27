from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from lib.web_search import (
    fetch_url_content,
    refine_web_search_into_context,
    web_search,
)


@dataclass
class ToolExecution:
    """Represents the outcome of a tool invocation."""

    name: str
    arguments: Dict[str, Any]
    content: str


class BaseTool(ABC):
    """Lightweight protocol each tool must satisfy."""

    name: str
    description: str
    parameters: Dict[str, Any]

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolExecution:
        """Execute the tool with keyword arguments originating from the LLM."""

    def to_openai_schema(self) -> Dict[str, Any]:
        """Return the OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Runtime registry that mediates between the agent and individual tools."""

    def __init__(self, tools: Iterable[BaseTool]):
        self._tools = {tool.name: tool for tool in tools}

    def definitions(self) -> List[Dict[str, Any]]:
        """Expose tool metadata in the format expected by the Cerebras/OpenAI APIs."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolExecution:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' is not registered.")
        return tool.run(**arguments)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Execute a real-time web search and return contextualized snippets suitable "
        "for grounding responses with citations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The refined search query to look up.",
            },
            "num_results": {
                "type": "integer",
                "description": "Maximum number of search results to fetch.",
                "default": 5,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def run(self, **kwargs: Any) -> ToolExecution:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("web_search requires a non-empty string 'query'.")

        num_results = kwargs.get("num_results", 5)
        search_response = web_search(query=query, num_results=int(num_results))
        context_blob = refine_web_search_into_context(search_response)

        return ToolExecution(
            name=self.name,
            arguments={"query": query, "num_results": num_results},
            content=context_blob,
        )


class CurrentTimeTool(BaseTool):
    name = "current_time_utc"
    description = (
        "Return the current UTC timestamp in ISO-8601 format for temporal grounding."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def run(self, **kwargs: Any) -> ToolExecution:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"current_time": now})
        return ToolExecution(name=self.name, arguments={}, content=payload)


class EchoTool(BaseTool):
    """Debug utility that simply echoes arguments back to the model."""

    name = "echo"
    description = (
        "Diagnostic tool: returns the provided arguments so you can reason step-by-step."
    )
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Arbitrary text to echo back.",
            }
        },
        "required": ["message"],
        "additionalProperties": False,
    }

    def run(self, **kwargs: Any) -> ToolExecution:
        message = kwargs.get("message", "")
        payload = json.dumps({"echo": message})
        return ToolExecution(name=self.name, arguments={"message": message}, content=payload)


class UrlContentTool(BaseTool):
    name = "fetch_url_content"
    description = "Retrieve the contents of a URL and return it as markdown for grounding or summarisation."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "max_characters": {
                "type": "integer",
                "description": "Maximum number of characters to retrieve from the page text.",
                "default": 8000,
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }

    def run(self, **kwargs: Any) -> ToolExecution:
        url = kwargs.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("fetch_url_content requires a non-empty string 'url'.")

        max_characters = kwargs.get("max_characters", 8000)
        content = fetch_url_content(url=url, max_characters=int(max_characters))
        return ToolExecution(
            name=self.name,
            arguments={"url": url, "max_characters": max_characters},
            content=content,
        )


def default_tooling(extra_tools: Optional[Iterable[BaseTool]] = None) -> ToolRegistry:
    """Convenience helper to build a registry with common utilities."""
    tools: List[BaseTool] = [WebSearchTool(), UrlContentTool(), CurrentTimeTool(), EchoTool()]
    if extra_tools:
        tools.extend(extra_tools)
    return ToolRegistry(tools)
