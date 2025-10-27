from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, root_validator

from lib.ai.llm import DEFAULT_CHAT_MODEL


class ChatContentPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


Content = Union[str, List[ChatContentPart]]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Content
    name: Optional[str] = None
    tool_call_id: Optional[str] = Field(
        default=None, description="Identifier linking a tool response to its call."
    )

    @root_validator(pre=True)
    def normalize_content(cls, values: dict) -> dict:
        content = values.get("content")
        if isinstance(content, str):
            return values
        if isinstance(content, list):
            if all(isinstance(item, dict) for item in content):
                return values
        if content is None:
            values["content"] = ""
        return values


class QueryRequest(BaseModel):
    model: str = Field(default=DEFAULT_CHAT_MODEL)
    input: Union[str, List[ChatMessage]]
    stream: bool = False


class ChatRequest(BaseModel):
    model: str = Field(default=DEFAULT_CHAT_MODEL)
    messages: List[ChatMessage]
    stream: bool = False
