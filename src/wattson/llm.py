"""A small client for any OpenAI-compatible chat API (Ollama, Groq, Gemini...)."""

import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Read from env vars LLM_BASE_URL, LLM_MODEL, LLM_API_KEY (or a .env file)."""

    model_config = SettingsConfigDict(
        env_prefix="LLM_", env_file=".env", extra="ignore"
    )

    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:8b"
    api_key: str = "ollama"  # Ollama ignores it; hosted providers need a real key
    timeout: float = 120.0  # local models can be slow, especially while "thinking"


class FunctionCall(BaseModel):
    name: str
    arguments: str  # a JSON *string*, not a dict

    def parsed_arguments(self) -> dict[str, Any]:
        return json.loads(self.arguments) if self.arguments else {}


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    reasoning: str | None = None  # the model's "thinking"; we never send it back
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # links a tool result to the call it answers


class Choice(BaseModel):
    message: Message
    finish_reason: str  # "stop" = final answer, "tool_calls" = wants a tool run


class ChatResponse(BaseModel):
    choices: list[Choice]


class LLMClient:
    def __init__(
        self, settings: LLMSettings | None = None, http: httpx.Client | None = None
    ) -> None:
        self.settings = settings or LLMSettings()
        self._http = http or httpx.Client(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout,
        )

    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> Choice:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                m.model_dump(exclude_none=True, exclude={"reasoning"}) for m in messages
            ],
        }
        if tools:
            payload["tools"] = tools

        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        response = self._http.post("/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        return ChatResponse.model_validate(response.json()).choices[0]
