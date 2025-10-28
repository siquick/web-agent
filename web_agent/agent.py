import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

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


def build_agent_metadata(
    refined_query: str,
    tool_calls: Iterable[ToolCallRecord],
    reflections: Iterable[ReflectionRecord],
) -> Dict[str, Any]:
    tool_meta = [
        {
            "name": call.name,
            "arguments": call.arguments,
            "output_preview": call.output_preview,
        }
        for call in tool_calls
    ]
    reflection_meta = [
        {
            "requires_more_context": reflection.requires_more_context,
            "reason": reflection.reason,
            "follow_up_instruction": reflection.follow_up_instruction,
            "suggested_query": reflection.suggested_query,
        }
        for reflection in reflections
    ]
    return {
        "refined_query": refined_query,
        "tool_calls": tool_meta,
        "reflections": reflection_meta,
    }


class ReflectionAgent:
    """Secondary reasoning step to validate answers and steer additional tool use."""

    def __init__(self, model: str = DEFAULT_CHAT_MODEL):
        self.model = model

    @staticmethod
    def _strip_code_fence(payload: str) -> str:
        trimmed = payload.strip()
        matcher = re.match(r"^```(?:json)?\s*(?P<body>.*)\s*```$", trimmed, re.DOTALL)
        if matcher:
            return matcher.group("body").strip()
        return trimmed

    @staticmethod
    def _extract_json_object(payload: str) -> Optional[str]:
        depth = 0
        start_index: Optional[int] = None
        for index, char in enumerate(payload):
            if char == "{":
                if depth == 0:
                    start_index = index
                depth += 1
            elif char == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start_index is not None:
                        return payload[start_index : index + 1]
        return None

    def _parse_reflection_payload(self, payload: str) -> Optional[Dict[str, Any]]:
        candidates = [payload, self._strip_code_fence(payload)]
        extracted = self._extract_json_object(payload)
        if extracted:
            candidates.append(extracted)

        for candidate in candidates:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

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

        parsed_reflection = self._parse_reflection_payload(reflection_raw)
        if parsed_reflection is None:
            logging.warning(
                "Failed to parse reflection response; defaulting to accept. Raw output: %s",
                reflection_raw,
            )
            reflection_data = {
                "requires_more_context": False,
                "reason": "Could not parse reflection JSON.",
                "follow_up_instruction": "",
            }
        else:
            reflection_data = parsed_reflection

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
        canonical_model = canonical_chat_model(model)
        if reflection_agent:
            reflection_agent.model = canonical_model
            self.reflection_agent = reflection_agent
        else:
            self.reflection_agent = ReflectionAgent(model=canonical_model)
        self.max_turns = max_turns
        self.max_reflection_rounds = max_reflection_rounds
        self.default_model = canonical_model

    def run(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        *,
        model: Optional[str] = None,
        event_handler: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResult:
        active_model = canonical_chat_model(model or self.default_model)
        if self.reflection_agent.model != active_model:
            self.reflection_agent.model = active_model
        refined_query = question
        history_context = self._build_history_context(chat_history or [])

        def emit(event: Dict[str, Any]) -> None:
            if event_handler:
                try:
                    event_handler(event)
                except Exception as exc:  # pragma: no cover - defensive
                    logging.warning("Agent event handler raised an exception: %s", exc)

        emit({"type": "run", "status": "start", "model": active_model, "question": question})

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
            stream = llm_chat(
                messages,
                tools=self.tool_registry.definitions(),
                model=active_model,
                stream=True,
                temperature=0.1,
                top_p=0.95,
                max_tokens=2000,
            )

            assistant_content = ""
            assistant_role = "assistant"
            tool_call_states: Dict[int, Dict[str, Any]] = {}

            def _parse_arguments(raw: str) -> Dict[str, Any]:
                if not raw:
                    return {}
                candidate = raw.strip()
                if not candidate:
                    return {}

                def _patch_brackets(value: str) -> List[str]:
                    attempts: List[str] = [value]
                    brace_delta = value.count("{") - value.count("}")
                    bracket_delta = value.count("[") - value.count("]")
                    patched = value
                    if brace_delta > 0:
                        patched = patched + ("}" * brace_delta)
                        attempts.append(patched)
                    if bracket_delta > 0:
                        patched = patched + ("]" * bracket_delta)
                        attempts.append(patched)
                    if attempts[-1].endswith(","):
                        attempts.append(attempts[-1].rstrip(",") + "}")
                    return attempts

                attempts = _patch_brackets(candidate)
                for attempt in attempts:
                    try:
                        return json.loads(attempt)
                    except json.JSONDecodeError:
                        continue

                logging.warning("Failed to parse tool arguments: %s", raw)
                return {}

            for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue

                if getattr(delta, "role", None):
                    assistant_role = delta.role

                content_piece = getattr(delta, "content", None)
                if content_piece:
                    if isinstance(content_piece, list):
                        for part in content_piece:
                            if isinstance(part, dict):
                                text_value = str(part.get("text", ""))
                            else:
                                text_value = str(part)
                            if not text_value:
                                continue
                            assistant_content += text_value
                            emit({"type": "answer", "status": "stream", "text": text_value})
                    else:
                        assistant_content += str(content_piece)
                        emit({"type": "answer", "status": "stream", "text": str(content_piece)})

                tool_call_deltas = getattr(delta, "tool_calls", None) or []
                for tool_delta in tool_call_deltas:
                    index = getattr(tool_delta, "index", 0)
                    state = tool_call_states.setdefault(
                        index,
                        {
                            "id": getattr(tool_delta, "id", None) or f"tool_call_{index}",
                            "name": None,
                            "arguments": "",
                            "emitted_start": False,
                        },
                    )
                    if getattr(tool_delta, "id", None):
                        state["id"] = tool_delta.id
                    function = getattr(tool_delta, "function", None)
                    if function:
                        if getattr(function, "name", None):
                            state["name"] = function.name
                        if getattr(function, "arguments", None):
                            state["arguments"] += function.arguments
                    if not state["emitted_start"] and state.get("name"):
                        emit(
                            {
                                "type": "tool_call",
                                "status": "start",
                                "call_id": state["id"],
                                "name": state["name"],
                                "arguments": {},
                            }
                        )
                        state["emitted_start"] = True

                if choice.finish_reason in {"stop", "tool_calls"}:
                    # The stream ends after the API reports a finish_reason
                    break

            assistant_message: Dict[str, Any] = {
                "role": assistant_role,
                "content": assistant_content,
            }

            sorted_tool_states = [
                tool_call_states[index] for index in sorted(tool_call_states.keys())
            ]
            if sorted_tool_states:
                assistant_message["tool_calls"] = [
                    {
                        "id": state["id"],
                        "type": "function",
                        "function": {
                            "name": state.get("name") or "",
                            "arguments": state.get("arguments") or "{}",
                        },
                    }
                    for state in sorted_tool_states
                ]

            messages.append(assistant_message)

            if sorted_tool_states:
                for state in sorted_tool_states:
                    arguments_dict = _parse_arguments(state.get("arguments") or "{}")
                    tool_name = state.get("name") or ""
                    if not tool_name:
                        logging.warning("Tool call missing function name; skipping execution.")
                        continue
                    if not state.get("emitted_start"):
                        emit(
                            {
                                "type": "tool_call",
                                "status": "start",
                                "call_id": state["id"],
                                "name": tool_name,
                                "arguments": arguments_dict,
                            }
                        )
                    execution: ToolExecution = self.tool_registry.execute(
                        tool_name, arguments_dict
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
                            "tool_call_id": state["id"],
                            "name": tool_name,
                            "content": execution.content,
                        }
                    )
                    emit(
                        {
                            "type": "tool_call",
                            "status": "finish",
                            "call_id": state["id"],
                            "name": execution.name,
                            "output": execution.content,
                        }
                    )
                continue

            answer = assistant_content

            should_reflect = tool_calls and reflection_attempts < self.max_reflection_rounds
            if should_reflect:
                reflection = self.reflection_agent.evaluate(
                    question=question, answer=answer, tool_history=tool_calls
                )
                reflections.append(reflection)
                reflection_attempts += 1

                if reflection.requires_more_context and reflection_attempts <= self.max_reflection_rounds:
                    logging.info("Reflection requested additional context.")
                    emit(
                        {
                            "type": "reflection",
                            "requires_more_context": reflection.requires_more_context,
                            "reason": reflection.reason,
                            "follow_up_instruction": reflection.follow_up_instruction,
                            "suggested_query": reflection.suggested_query,
                        }
                    )
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

        metadata = build_agent_metadata(refined_query, tool_calls, reflections)
        emit(
            {
                "type": "answer",
                "status": "final",
                "text": answer,
                "metadata": metadata,
            }
        )

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
