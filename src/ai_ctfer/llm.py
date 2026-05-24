from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model_interface import ChatCall, Message, call_chat_model, create_chat_client
from .schema import LLMConfig


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float | None,
        reasoning_effort: str | None = None,
    ) -> str:
        ...


def create_llm_client(model_config: LLMConfig) -> LLMClient:
    return OpenAICompatibleClient(model_config.provider)


class OpenAICompatibleClient:
    def __init__(self, provider: str, api_key: str | None = None) -> None:
        self.provider = provider
        self.client = create_chat_client(provider, api_key)

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float | None,
        reasoning_effort: str | None = None,
    ) -> str:
        return call_chat_model(
            self.client,
            ChatCall(
                provider=self.provider,
                model=model,
                messages=messages,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            ),
        )


class DeepSeekClient(OpenAICompatibleClient):
    def __init__(self, api_key: str | None = None) -> None:
        super().__init__("deepseek", api_key)


class OpenAIClient(OpenAICompatibleClient):
    def __init__(self, api_key: str | None = None) -> None:
        super().__init__("gpt", api_key)


@dataclass
class StaticLLMClient:
    response: str

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float | None,
        reasoning_effort: str | None = None,
    ) -> str:
        return self.response
