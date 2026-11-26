"""The agent loop: the brain thinks, the hands act, repeat until it answers."""

import json
from collections.abc import Callable
from typing import Any

from wattson.llm import LLMClient, Message, ToolCall
from wattson.tools import TOOL_SPECS, EnergyTools, uk_time

MAX_STEPS = 5  # a safety brake so a confused model can't loop forever

SYSTEM_PROMPT = """You are Wattson, a friendly UK home energy advisor.
The current UK time is {now}.
- Always use the tools for carbon or price data. Never guess or invent numbers.
- If a tool result includes a "note", pass it on to the user.
- If a tool result includes an "error", explain the problem simply.
- Answer in a few short sentences, using the UK times the tools give you.
- If the user asks about a time the data doesn't cover, say so first.
- Only offer things you can actually do; you can't remember, schedule or follow up."""


class Agent:
    def __init__(
        self, llm: LLMClient | None = None, tools: EnergyTools | None = None
    ) -> None:
        self.llm = llm or LLMClient()
        self.tools = tools or EnergyTools()
        self.handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "get_greenest_times": self.tools.greenest_times,
            "get_cheapest_times": self.tools.cheapest_times,
        }
        self.trace: list[Message] = []  # the full conversation, for debugging/evals

    def ask(self, question: str) -> str:
        now = uk_time(self.tools.now())
        messages = [
            Message(role="system", content=SYSTEM_PROMPT.format(now=now)),
            Message(role="user", content=question),
        ]
        self.trace = messages

        for _ in range(MAX_STEPS):
            choice = self.llm.chat(messages, tools=TOOL_SPECS)
            messages.append(choice.message)

            if not choice.message.tool_calls:  # no request for hands: final answer
                return choice.message.content or ""

            for call in choice.message.tool_calls:
                result = self.run_tool(call)
                messages.append(
                    Message(
                        role="tool", tool_call_id=call.id, content=json.dumps(result)
                    )
                )

        return "Sorry, I couldn't finish working that out. Please try rephrasing."

    def run_tool(self, call: ToolCall) -> dict[str, Any]:
        handler = self.handlers.get(call.function.name)
        if handler is None:
            return {"error": f"Unknown tool {call.function.name!r}"}
        try:
            return handler(**call.function.parsed_arguments())
        except Exception as exc:  # noqa: BLE001 - deliberate: report every failure
            return {"error": f"{type(exc).__name__}: {exc}"}
