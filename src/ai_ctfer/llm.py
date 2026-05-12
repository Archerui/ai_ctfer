from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from .schema import LLMConfig


Message = dict[str, str]


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        ...


def create_llm_client(model_config: LLMConfig) -> LLMClient:
    if model_config.provider == "gpt":
        return OpenAIClient()
    return DeepSeekClient()


class DeepSeekClient:
    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek returned an empty response")
        return content


class OpenAIClient:
    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=api_key)

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        kwargs: dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned an empty response")
        return content


@dataclass
class StaticLLMClient:
    response: str

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        return self.response
