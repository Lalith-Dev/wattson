import json
from datetime import UTC, datetime

from wattson.agent import MAX_STEPS, Agent
from wattson.llm import Choice, FunctionCall, Message, ToolCall
from wattson.tools import EnergyTools


class ScriptedLLM:
    """A fake brain that replies from a script and remembers what it was sent."""

    def __init__(self, replies: list[Choice]) -> None:
        self.replies = replies
        self.calls: list[list[Message]] = []

    def chat(self, messages, tools=None) -> Choice:
        self.calls.append(list(messages))
        return self.replies[min(len(self.calls), len(self.replies)) - 1]


class FakeTools(EnergyTools):
    def __init__(self) -> None:
        self.now = lambda: datetime(2026, 11, 26, 9, 0, tzinfo=UTC)

    def greenest_times(self, postcode, hours_ahead=24, top=3):
        return {"region": "North Wales & Merseyside", "postcode_seen": postcode}

    def cheapest_times(self, postcode, hours_ahead=24, top=3):
        raise ValueError("Octopus is down")


def asks_for(name: str, arguments: str, call_id: str = "call_1") -> Choice:
    call = ToolCall(id=call_id, function=FunctionCall(name=name, arguments=arguments))
    message = Message(role="assistant", content="", tool_calls=[call])
    return Choice(message=message, finish_reason="tool_calls")


def answers(text: str) -> Choice:
    return Choice(message=Message(role="assistant", content=text), finish_reason="stop")


def test_runs_tool_then_answers():
    llm = ScriptedLLM(
        [
            asks_for("get_greenest_times", '{"postcode": "L1"}'),
            answers("Run it at 5am."),
        ]
    )
    agent = Agent(llm=llm, tools=FakeTools())

    assert agent.ask("Greenest time in L1?") == "Run it at 5am."

    tool_message = llm.calls[1][-1]  # what the brain saw on its second turn
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == "call_1"  # the cloakroom ticket
    assert json.loads(tool_message.content)["postcode_seen"] == "L1"


def test_system_prompt_includes_current_uk_time():
    llm = ScriptedLLM([answers("Hi!")])
    Agent(llm=llm, tools=FakeTools()).ask("hello")

    assert "Thu 26 Nov 09:00" in llm.calls[0][0].content


def test_tool_errors_are_reported_not_raised():
    llm = ScriptedLLM(
        [asks_for("get_cheapest_times", '{"postcode": "L1"}'), answers("Sorry.")]
    )
    agent = Agent(llm=llm, tools=FakeTools())

    assert agent.ask("Cheapest time?") == "Sorry."
    assert "Octopus is down" in llm.calls[1][-1].content


def test_bad_json_and_unknown_tools_become_errors():
    agent = Agent(llm=ScriptedLLM([]), tools=FakeTools())

    broken = asks_for("get_greenest_times", '{"postcode": ').message.tool_calls[0]
    unknown = asks_for("launch_rocket", "{}").message.tool_calls[0]

    assert "error" in agent.run_tool(broken)
    assert "Unknown tool" in agent.run_tool(unknown)["error"]


def test_stops_after_max_steps():
    llm = ScriptedLLM([asks_for("get_greenest_times", '{"postcode": "L1"}')])
    answer = Agent(llm=llm, tools=FakeTools()).ask("loop forever")

    assert "couldn't finish" in answer
    assert len(llm.calls) == MAX_STEPS
