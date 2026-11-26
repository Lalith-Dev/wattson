from datetime import UTC, datetime

from wattson.evals import (
    FROZEN_NOW,
    Case,
    ReplayCarbon,
    ReplayOctopus,
    check,
    load_cases,
)
from wattson.llm import FunctionCall, Message, ToolCall
from wattson.tools import EnergyTools


def trace_with(tool: str, result: str) -> list[Message]:
    call = ToolCall(id="c1", function=FunctionCall(name=tool, arguments="{}"))
    return [
        Message(role="user", content="question"),
        Message(role="assistant", content="", tool_calls=[call]),
        Message(role="tool", tool_call_id="c1", content=result),
    ]


CASE = Case(
    id="t",
    question="q",
    expect_tools=["get_cheapest_times"],
    must_include=["32.92"],
)


def test_good_answer_passes():
    trace = trace_with("get_cheapest_times", '{"pence_per_kwh": 32.92}')

    assert check(CASE, "Charge at 22:30 for 32.92p.", trace) == []


def test_invented_number_fails():
    trace = trace_with("get_cheapest_times", '{"pence_per_kwh": 32.92}')

    failures = check(CASE, "32.92p tonight, or 12.50p on Saturday.", trace)

    assert any("invented number '12.50'" in f for f in failures)


def test_wrong_tool_and_missing_phrase_fail():
    trace = trace_with("get_greenest_times", "{}")

    failures = check(CASE, "No idea.", trace)

    assert any(f.startswith("tools:") for f in failures)
    assert "missing '32.92'" in failures


def test_case_file_loads():
    ids = [case.id for case in load_cases()]

    assert len(ids) == len(set(ids))  # no duplicate ids
    assert "unpublished_saturday" in ids


def test_frozen_world_matches_expected_answers():
    tools = EnergyTools(
        carbon=ReplayCarbon(), octopus=ReplayOctopus(), now=lambda: FROZEN_NOW
    )

    assert tools.cheapest_times("L1")["slots"][0]["pence_per_kwh"] == 32.92
    assert tools.greenest_times("L1")["slots"][0]["gco2_per_kwh"] == 69
    assert "later slots are unknown" in tools.cheapest_times("L1", 48)["note"]
    assert FROZEN_NOW == datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
