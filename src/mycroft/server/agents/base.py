"""BaseAgent: conversation loop with Anthropic streaming and tool dispatch."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import anthropic

from mycroft.shared.protocol import StepId
from mycroft.server.settings import settings
from mycroft.server.state.project import ProjectState
from mycroft.server.state import conversation as conv
from mycroft.server.pipeline.state import get_all_previous_documents, get_step_documents
from mycroft.server.agents.streaming import StreamRelay

logger = logging.getLogger(__name__)

# Max messages before we start trimming old ones
MAX_MESSAGES = 40
KEEP_RECENT = 20


class BaseAgent(ABC):
    """Base class for all pipeline step agents."""

    step_id: StepId

    def __init__(self, project: ProjectState) -> None:
        self.project = project
        self.relay = StreamRelay(project.project_id)
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    def tools(self) -> list[dict[str, Any]]:
        """Return tool definitions for this agent. Override in subclasses."""
        return []

    async def execute_tool(self, name: str, input_data: dict[str, Any]) -> str:
        """Execute a tool and return result. Override in subclasses."""
        return json.dumps({"error": f"Unknown tool: {name}"})

    def _build_system_prompt(self) -> str:
        """Build full system prompt including document context."""
        parts = [self.system_prompt()]

        # Include previous step documents as context
        prev_docs = get_all_previous_documents(self.project)
        if prev_docs:
            parts.append("\n\n---\n## Documents from previous steps\n")
            for filename, content in prev_docs.items():
                parts.append(f"\n### {filename}\n```\n{content}\n```\n")

        # Include current step's document if it exists (for accumulator pattern)
        current_docs = get_step_documents(self.project, self.step_id)
        if current_docs:
            parts.append("\n\n---\n## Current step documents (work in progress)\n")
            for filename, content in current_docs.items():
                parts.append(f"\n### {filename}\n```\n{content}\n```\n")

        return "".join(parts)

    def _load_conversation(self) -> list[dict[str, Any]]:
        """Load conversation history, trimming if near context limit."""
        messages = conv.load_messages(self.project.project_dir, self.step_id)

        if len(messages) > MAX_MESSAGES:
            # Keep only recent messages
            messages = messages[-KEEP_RECENT:]

        return messages

    async def run(self, user_text: str) -> None:
        """Run one agent turn: send user message, stream response, handle tools."""
        messages = self._load_conversation()

        # The user message is already appended by the WS handler, but we need it in our list
        if not messages or messages[-1].get("content") != user_text:
            messages.append({"role": "user", "content": user_text})

        system = self._build_system_prompt()
        tool_defs = self.tools()

        # Agent loop: keep going while model wants to use tools
        while True:
            response_text, tool_calls = await self._stream_response(
                system, messages, tool_defs
            )

            # Save assistant message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": []}

            if response_text:
                assistant_msg["content"].append({"type": "text", "text": response_text})

            if tool_calls:
                for tc in tool_calls:
                    assistant_msg["content"].append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["input"],
                    })

            conv.append_message(self.project.project_dir, self.step_id, assistant_msg)
            messages.append(assistant_msg)

            if not tool_calls:
                break

            # Execute tools and continue
            tool_results_msg: dict[str, Any] = {"role": "user", "content": []}
            for tc in tool_calls:
                await self.relay.on_tool_start(tc["name"])
                try:
                    result = await self.execute_tool(tc["name"], tc["input"])
                    await self.relay.on_tool_complete(tc["name"], result[:100])
                except Exception as e:
                    result = json.dumps({"error": str(e)})
                    await self.relay.on_tool_error(tc["name"], str(e))

                tool_results_msg["content"].append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result,
                })

            conv.append_message(self.project.project_dir, self.step_id, tool_results_msg)
            messages.append(tool_results_msg)

    async def _stream_response(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tool_defs: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Stream a response from Anthropic, relaying text deltas. Returns (text, tool_calls)."""
        kwargs: dict[str, Any] = {
            "model": settings.anthropic_model,
            "max_tokens": settings.anthropic_max_tokens,
            "system": system,
            "messages": messages,
        }
        if tool_defs:
            kwargs["tools"] = tool_defs

        full_text = ""
        tool_calls: list[dict[str, Any]] = []
        current_tool: dict[str, Any] | None = None
        tool_input_json = ""

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        await self.relay.on_text_start()
                    elif block.type == "tool_use":
                        current_tool = {
                            "id": block.id,
                            "name": block.name,
                            "input": {},
                        }
                        tool_input_json = ""

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        full_text += delta.text
                        await self.relay.on_text_delta(delta.text)
                    elif delta.type == "input_json_delta":
                        tool_input_json += delta.partial_json

                elif event.type == "content_block_stop":
                    if current_tool is not None:
                        if tool_input_json:
                            current_tool["input"] = json.loads(tool_input_json)
                        tool_calls.append(current_tool)
                        current_tool = None
                        tool_input_json = ""
                    else:
                        await self.relay.on_text_end()

        return full_text, tool_calls
