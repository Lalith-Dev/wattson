"""Run the golden eval set against the real LLM, in a frozen world.

Usage: uv run python -m wattson.evals
"""

import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from wattson.agent import Agent
from wattson.carbon import RegionalForecastResponse
from wattson.llm import Message
from wattson.octopus import UnitRate
from wattson.tools import EnergyTools

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
CASES = ROOT / "evals" / "cases.json"
FROZEN_NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)  # matches the saved data

# Decimals like 32.92, or whole numbers right before "g" like "69 gCO2/kWh"
NUMBER = re.compile(r"\d+\.\d+|\d+(?=\s*g)")


def _check_postcode(postcode: str) -> None:
    """Our frozen world only has Liverpool data."""
    if not postcode.strip().upper().startswith("L"):
        raise ValueError(f"No data for postcode {postcode!r}")


class ReplayCarbon:
    def forecast_48h(self, postcode, start=None):
        _check_postcode(postcode)
        raw = json.loads((FIXTURES / "carbon_fw48h_L1_2026-11-26.json").read_text())
        return RegionalForecastResponse.model_validate(raw).data


class ReplayOctopus:
    def region_for(self, postcode):
        _check_postcode(postcode)
        return "D"

    def agile_rates(self, region, start, end):
        raw = json.loads((FIXTURES / "agile_rates_D_2026-11-26.json").read_text())
        rates = [UnitRate.model_validate(r) for r in raw["results"]]
        return [r for r in rates if r.valid_to > start and r.valid_from < end]


@dataclass
class Case:
    id: str
    question: str
    expect_tools: list[str] | None  # exact tools to call; [] = none; None = any
    must_include: list[str] = field(default_factory=list)  # all must appear
    must_include_any: list[str] = field(default_factory=list)  # one must appear


def check(case: Case, answer: str, trace: list[Message]) -> list[str]:
    """Return a list of failures. An empty list means the case passed."""
    failures = []
    text = answer.lower()

    called = sorted(
        {call.function.name for m in trace for call in (m.tool_calls or [])}
    )
    if case.expect_tools is not None and called != sorted(case.expect_tools):
        failures.append(f"tools: expected {sorted(case.expect_tools)}, got {called}")

    for phrase in case.must_include:
        if phrase.lower() not in text:
            failures.append(f"missing {phrase!r}")

    if case.must_include_any and not any(
        p.lower() in text for p in case.must_include_any
    ):
        failures.append(f"missing any of {case.must_include_any}")

    evidence = " ".join(m.content or "" for m in trace if m.role in ("user", "tool"))
    for number in NUMBER.findall(answer):
        if number not in evidence:
            failures.append(f"invented number {number!r} (not in any tool result)")

    return failures


def load_cases(path: Path = CASES) -> list[Case]:
    return [Case(**raw) for raw in json.loads(path.read_text())]


def run(cases: list[Case]) -> int:
    passed = 0
    for case in cases:
        tools = EnergyTools(
            carbon=ReplayCarbon(), octopus=ReplayOctopus(), now=lambda: FROZEN_NOW
        )
        agent = Agent(tools=tools)

        started = time.perf_counter()
        answer = agent.ask(case.question)
        seconds = time.perf_counter() - started

        failures = check(case, answer, agent.trace)
        print(f"[{'PASS' if not failures else 'FAIL'}] {case.id} ({seconds:.0f}s)")
        for failure in failures:
            print(f"    - {failure}")
        if failures:
            print(f"    answer: {' '.join(answer.split())[:300]}")
        passed += not failures

    print(f"\nScore: {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(run(load_cases()))
