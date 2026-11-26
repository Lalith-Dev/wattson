import json
from pathlib import Path

import httpx

from wattson.llm import LLMClient, LLMSettings, Message

FIXTURES = Path(__file__).parent / "fixtures"
SETTINGS = LLMSettings(base_url="http://test/v1", model="test-model", api_key="k")


def make_client(handler) -> LLMClient:
    http = httpx.Client(
        base_url=SETTINGS.base_url, transport=httpx.MockTransport(handler)
    )
    return LLMClient(settings=SETTINGS, http=http)


def reply_with(fixture: str):
    body = json.loads((FIXTURES / fixture).read_text())
    return lambda request: httpx.Response(200, json=body)


def test_plain_answer():
    choice = make_client(reply_with("llm_plain.json")).chat(
        [Message(role="user", content="hi")]
    )

    assert choice.finish_reason == "stop"
    assert choice.message.content
    assert choice.message.tool_calls is None


def test_tool_call_arguments_are_parsed():
    choice = make_client(reply_with("llm_tool_call.json")).chat(
        [Message(role="user", content="greenest time in L1?")]
    )

    assert choice.finish_reason == "tool_calls"
    call = choice.message.tool_calls[0]
    assert call.function.name == "get_carbon_forecast"
    assert call.function.arguments == '{"postcode":"L1"}'  # a string
    assert call.function.parsed_arguments() == {"postcode": "L1"}  # now a dict


def test_request_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return reply_with("llm_plain.json")(request)

    tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
    history = [Message(role="assistant", content="ok", reasoning="secret thoughts")]
    make_client(handler).chat(history, tools=tools)

    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["tools"] == tools
    assert seen["body"]["messages"] == [{"role": "assistant", "content": "ok"}]


def test_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b")

    assert LLMSettings().model == "llama-3.3-70b"
