import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from web_agent.ai.llm import (
    DEFAULT_CHAT_MODEL,
    SUMMARY_TOKEN_LIMIT as LLM_SUMMARY_TOKEN_LIMIT,
    canonical_chat_model,
    conversation_summary_update,
    llm_call,
    llm_chat,
)
from web_agent.ai.prompts import reflection_prompt_template
from web_agent.ai.system_prompts import agent_system_prompt
from web_agent.ai.utils import content_to_text
from web_agent.ai.token_utils import count_tokens
from web_agent.tools import BaseTool, ToolExecution, ToolRegistry, default_tooling


@dataclass
class ToolCallRecord:
    name: str
    arguments: Dict[str, Any]
    output_preview: str


@dataclass
class ReflectionRecord:
    requires_more_context: bool
    reason: str
    follow_up_instruction: str
    suggested_query: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    answer: str
    refined_query: str
    tool_calls: List[ToolCallRecord]
    reflections: List[ReflectionRecord]


class ReflectionAgent:
    """Secondary reasoning step to validate answers and steer additional tool use."""

    def __init__(self, model: str = DEFAULT_CHAT_MODEL):
        self.model = model

    def evaluate(
        self,
        question: str,
        answer: str,
        tool_history: List[ToolCallRecord],
    ) -> ReflectionRecord:
        tool_summaries = [
            {
                "name": record.name,
                "arguments": record.arguments,
                "output_preview": record.output_preview,
            }
            for record in tool_history
        ]

        reflection_input = json.dumps(
            {
                "question": question,
                "answer": answer,
                "tool_history": tool_summaries,
            }
        )
        system_prompt = reflection_prompt_template()
        reflection_raw = llm_call(
            system_prompt=system_prompt,
            query=reflection_input,
            model=self.model,
        )

        try:
            reflection_data = json.loads(reflection_raw)
        except json.JSONDecodeError:
            logging.warning("Failed to parse reflection response; defaulting to accept.")
            reflection_data = {
                "requires_more_context": False,
                "reason": "Could not parse reflection JSON.",
                "follow_up_instruction": "",
            }

        requires_more_context = bool(
            reflection_data.get("requires_more_context", False)
        )
        reason = reflection_data.get("reason", "")
        follow_up_instruction = reflection_data.get(
            "follow_up_instruction",
            "No further action required." if not requires_more_context else "",
        )
        suggested_query = reflection_data.get("suggested_query")

        return ReflectionRecord(
            requires_more_context=requires_more_context,
            reason=reason,
            follow_up_instruction=follow_up_instruction,
            suggested_query=suggested_query,
            raw=reflection_data,
        )


class ToolUseAgent:
    """Coordinates the LLM with tools and reflection to answer user questions."""

    SUMMARY_TOKEN_BUDGET = LLM_SUMMARY_TOKEN_LIMIT
    SUMMARY_CHUNK_TOKEN_LIMIT = 4000
    RECENT_CONTEXT_TOKEN_BUDGET = 20000
    SUMMARY_MIN_MESSAGE_COUNT = 6

    def __init__(
        self,
        tools: Optional[List[BaseTool]] = None,
        tool_registry: Optional[ToolRegistry] = None,
        reflection_agent: Optional[ReflectionAgent] = None,
        max_turns: int = 6,
        max_reflection_rounds: int = 1,
        model: str = DEFAULT_CHAT_MODEL,
    ):
        if tool_registry:
            self.tool_registry = tool_registry
        else:
            self.tool_registry = default_tooling(tools or [])
        self.reflection_agent = reflection_agent or ReflectionAgent(model=model)
        self.max_turns = max_turns
        self.max_reflection_rounds = max_reflection_rounds
        self.model = canonical_chat_model(model)

    def run(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResult:
        refined_query = question
        history_context = self._build_history_context(chat_history or [])

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": agent_system_prompt(),
            },
            {
                "role": "user",
                "content": (
                    (history_context if history_context else "")
                    + f"User question: {question}\n"
                    f"Suggested starting web search query: {refined_query}\n"
                    "Call tools when additional information is required."
                ),
            },
        ]

        tool_calls: List[ToolCallRecord] = []
        reflections: List[ReflectionRecord] = []
        answer: Optional[str] = None
        reflection_attempts = 0

        for turn in range(self.max_turns):
            response = llm_chat(
                messages,
                tools=self.tool_registry.definitions(),
                model=self.model,
                stream=False,
                temperature=0.1,
                top_p=0.95,
                max_tokens=2000,
            )

            choice = response.choices[0]
            message = choice.message

            if getattr(message, "tool_calls", None):
                assistant_message = {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in message.tool_calls
                    ],
                }
                messages.append(assistant_message)

                for tool_call in message.tool_calls:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    execution: ToolExecution = self.tool_registry.execute(
                        tool_call.function.name, arguments
                    )
                    tool_calls.append(
                        ToolCallRecord(
                            name=execution.name,
                            arguments=execution.arguments,
                            output_preview=execution.content[:500],
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": execution.content,
                        }
                    )
                continue

            answer = message.content or ""
            messages.append({"role": "assistant", "content": answer})

            should_reflect = tool_calls and reflection_attempts < self.max_reflection_rounds
            if should_reflect:
                reflection = self.reflection_agent.evaluate(
                    question=question, answer=answer, tool_history=tool_calls
                )
                reflections.append(reflection)
                reflection_attempts += 1

                if reflection.requires_more_context and reflection_attempts <= self.max_reflection_rounds:
                    logging.info("Reflection requested additional context.")
                    feedback_lines = [
                        "Reflection feedback indicates more work is needed.",
                        f"Reason: {reflection.reason}",
                    ]
                    if reflection.follow_up_instruction:
                        feedback_lines.append(
                            f"Instruction: {reflection.follow_up_instruction}"
                        )
                    if reflection.suggested_query:
                        feedback_lines.append(
                            f"Suggested query: {reflection.suggested_query}"
                        )
                    messages.append(
                        {
                            "role": "system",
                            "content": "\n".join(feedback_lines),
                        }
                    )
                    if reflection.suggested_query:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Follow the reflection guidance. "
                                    f"Consider searching for: {reflection.suggested_query}"
                                ),
                            }
                        )
                    continue

            break

        if answer is None:
            logging.error("Agent failed to produce an answer within allotted turns.")
            raise RuntimeError("Agent could not generate a final answer.")

        return AgentResult(
            answer=answer,
            refined_query=refined_query,
            tool_calls=tool_calls,
            reflections=reflections,
        )

    def _build_history_context(
        self, chat_history: Iterable[Dict[str, Any]]
    ) -> str:
        normalized: List[Dict[str, str]] = []
        for message in chat_history:
            role = message.get("role")
            if role not in {"system", "user", "assistant"}:
                continue
            content = content_to_text(message.get("content"))
            content = content.strip()
            if not content:
                continue
            normalized.append({"role": role, "content": content})

        if not normalized:
            return ""

        summary = ""
        if len(normalized) >= self.SUMMARY_MIN_MESSAGE_COUNT:
            try:
                for chunk in self._transcript_chunks(
                    normalized, self.SUMMARY_CHUNK_TOKEN_LIMIT
                ):
                    summary = conversation_summary_update(
                        summary,
                        chunk,
                        max_tokens=self.SUMMARY_TOKEN_BUDGET,
                    )
            except Exception as exc:
                logging.warning("Failed to generate conversation summary: %s", exc)
                summary = ""

        recent_lines: List[str] = []
        running_tokens = 0
        for entry in reversed(normalized):
            line = f"{entry['role'].capitalize()}: {entry['content']}"
            line_tokens = count_tokens(line)
            if recent_lines and running_tokens + line_tokens > self.RECENT_CONTEXT_TOKEN_BUDGET:
                break
            recent_lines.append(line)
            running_tokens += line_tokens
        recent_lines.reverse()

        sections: List[str] = []
        if summary:
            sections.append("Conversation summary:\n" + summary.strip())
        if recent_lines:
            sections.append("Recent exchanges:\n" + "\n".join(recent_lines))

        context = "\n\n".join(sections).strip()
        if context:
            context += "\n"
        return context

    @staticmethod
    def _transcript_chunks(
        messages: List[Dict[str, str]], chunk_token_limit: int
    ) -> Iterable[str]:
        chunk_lines: List[str] = []
        current_tokens = 0
        for entry in messages:
            line = f"{entry['role'].capitalize()}: {entry['content']}"
            line_tokens = count_tokens(line)
            if chunk_lines and current_tokens + line_tokens > chunk_token_limit:
                yield "\n".join(chunk_lines)
                chunk_lines = []
                current_tokens = 0
            chunk_lines.append(line)
            current_tokens += line_tokens
        if chunk_lines:
            yield "\n".join(chunk_lines)
