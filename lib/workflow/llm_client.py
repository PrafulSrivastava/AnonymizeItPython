"""
Minimal client for OpenAI-compatible chat completion servers (LM Studio, vLLM, OpenAI, ...).
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    """The LLM server could not be reached or returned an unusable response."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LLMReply:
    content: str
    model: str
    tool_calls: List[ToolCall] = field(default_factory=list)


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "lm-studio")
        self.model = model if model is not None else os.getenv("LLM_MODEL", "")
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        self._transport = transport

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMReply:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                model = self.model or self._first_chat_model(client)
                payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2}
                if tools:
                    payload["tools"] = tools
                response = client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = [
                ToolCall(
                    id=call.get("id") or "",
                    name=call["function"]["name"],
                    arguments=call["function"].get("arguments") or "{}",
                )
                for call in message.get("tool_calls") or []
            ]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMError("LLM response had no usable choices[0].message") from exc

        return LLMReply(
            content=_THINK_RE.sub("", content).strip(),
            model=data.get("model") or model,
            tool_calls=tool_calls,
        )

    def _first_chat_model(self, client: httpx.Client) -> str:
        response = client.get("/models")
        response.raise_for_status()
        for entry in response.json().get("data", []):
            model_id = entry.get("id", "")
            if model_id and "embed" not in model_id.lower():
                return model_id
        raise LLMError("LLM server lists no chat models; set LLM_MODEL")
