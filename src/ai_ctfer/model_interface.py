import importlib.util
import os
import time
from pathlib import Path

from openai import OpenAI


Message = dict
MODEL_RETRY_DELAYS_SEC = [2, 5]


# This module is the bridge between the agent and the user-editable provider
# config in ./model_providers.py. Advanced users should usually edit that file,
# not this one. Keep API-call mechanics here.
_PROVIDER_SETTINGS = None
DEFAULT_MODEL_PROVIDER = None
MODEL_PROVIDERS = None


def load_provider_settings():
    config_path = Path(__file__).resolve().parents[2] / "model_providers.py"
    if not config_path.exists():
        raise RuntimeError(f"Missing model provider config: {config_path}")

    spec = importlib.util.spec_from_file_location("ai_ctfer_user_model_providers", config_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load model provider config: {config_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refresh_provider_settings():
    global _PROVIDER_SETTINGS, DEFAULT_MODEL_PROVIDER, MODEL_PROVIDERS
    _PROVIDER_SETTINGS = load_provider_settings()
    DEFAULT_MODEL_PROVIDER = _PROVIDER_SETTINGS.DEFAULT_MODEL_PROVIDER
    MODEL_PROVIDERS = _PROVIDER_SETTINGS.MODEL_PROVIDERS
    return _PROVIDER_SETTINGS


refresh_provider_settings()


def get_model_provider(provider):
    config = MODEL_PROVIDERS.get(provider)
    if not config:
        raise RuntimeError(f"Unknown model provider: {provider}")
    return config


def default_model_provider():
    return DEFAULT_MODEL_PROVIDER


def model_provider_names():
    return list(MODEL_PROVIDERS)


def model_names_help():
    return ", ".join(model_provider_names())


def normalize_model_name(value=None):
    raw = str(value or DEFAULT_MODEL_PROVIDER).strip().lower()
    for provider, config in MODEL_PROVIDERS.items():
        aliases = [provider] + list(config.get("aliases", []))
        if raw in {str(alias).strip().lower() for alias in aliases}:
            return provider
    raise ValueError(f"model.name must be one of: {model_names_help()}")


def get_api_model(provider):
    return get_model_provider(provider)["api_model"]


def get_reasoning_effort(provider):
    return get_model_provider(provider).get("reasoning_effort")


def get_api_key_env(provider):
    return get_model_provider(provider)["api_key_env"]


def get_base_url(provider):
    return get_model_provider(provider).get("base_url")


def get_api_style(provider):
    return get_model_provider(provider).get("api_style", "chat_completions")


def get_supports_temperature(provider):
    config = get_model_provider(provider)
    if "supports_temperature" in config:
        return bool(config["supports_temperature"])
    return get_api_style(provider) != "responses"


def get_default_temperature(provider):
    if not get_supports_temperature(provider):
        return None
    return get_model_provider(provider).get("default_temperature", 0.1)


def model_sample_comment_lines():
    lines = [f"  # name options: {model_names_help()}"]
    for provider, config in MODEL_PROVIDERS.items():
        comment = config.get("sample_comment")
        if comment:
            lines.append(f"  # {comment}")
        else:
            lines.append(f"  # {provider} => {config.get('api_model')}")
    return "\n".join(lines)


def provider_api_key_statuses():
    statuses = []
    for provider, config in MODEL_PROVIDERS.items():
        env_name = config.get("api_key_env")
        statuses.append(
            {
                "provider": provider,
                "env": env_name,
                "ok": bool(env_name and os.environ.get(env_name)),
            }
        )
    return statuses


class ChatCall:
    def __init__(
        self,
        provider,
        model,
        messages,
        temperature,
        reasoning_effort=None,
        supports_temperature=None,
    ):
        self.provider = provider
        self.model = model
        self.messages = messages
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.api_style = get_api_style(provider)
        if supports_temperature is None:
            supports_temperature = get_supports_temperature(provider)
        self.supports_temperature = supports_temperature

    def without_temperature(self):
        return ChatCall(
            provider=self.provider,
            model=self.model,
            messages=self.messages,
            temperature=None,
            reasoning_effort=self.reasoning_effort,
            supports_temperature=False,
        )


def get_api_key(provider, explicit_api_key=None):
    if explicit_api_key:
        return explicit_api_key
    env_name = get_api_key_env(provider)
    api_key = os.environ.get(env_name)
    if not api_key:
        raise RuntimeError(f"{env_name} is not set")
    return api_key


def create_chat_client(provider, api_key=None):
    kwargs = {"api_key": get_api_key(provider, api_key)}
    base_url = get_base_url(provider)
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def build_chat_completion_kwargs(call):
    kwargs = {
        "model": call.model,
        "messages": call.messages,
        "stream": False,
    }
    add_temperature_kwarg(kwargs, call)
    if call.reasoning_effort:
        kwargs["reasoning_effort"] = call.reasoning_effort
    return kwargs


def build_responses_kwargs(call):
    kwargs = {
        "model": call.model,
        "input": call.messages,
        "stream": False,
    }
    add_temperature_kwarg(kwargs, call)
    if call.reasoning_effort:
        kwargs["reasoning"] = {"effort": call.reasoning_effort}
    return kwargs


def add_temperature_kwarg(kwargs, call):
    if call.supports_temperature and call.temperature is not None:
        kwargs["temperature"] = call.temperature


def create_chat_completion(client, call):
    kwargs = build_chat_completion_kwargs(call)
    return client.chat.completions.create(**kwargs)


def create_responses_completion(client, call):
    kwargs = build_responses_kwargs(call)
    return client.responses.create(**kwargs)


def create_model_response(client, call):
    if call.api_style == "responses":
        return create_responses_completion(client, call)
    if call.api_style == "chat_completions":
        return create_chat_completion(client, call)
    raise RuntimeError(f"Unknown API style for {call.provider}: {call.api_style}")


def extract_model_text(response, provider):
    content = extract_responses_text(response) or extract_chat_completion_text(response)
    if not content:
        raise RuntimeError(f"{provider} returned an empty response")
    return str(content)


def extract_chat_completion_text(response):
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    return getattr(choices[0].message, "content", None)


def extract_responses_text(response):
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    parts = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts) if parts else None


def call_chat_model(client, call):
    last_error = None
    retried_without_temperature = False
    for attempt in range(len(MODEL_RETRY_DELAYS_SEC) + 1):
        try:
            response = create_model_response(client, call)
            return extract_model_text(response, call.provider)
        except Exception as exc:
            last_error = exc
            if (
                not retried_without_temperature
                and call.temperature is not None
                and is_unsupported_temperature_error(exc)
            ):
                call = call.without_temperature()
                retried_without_temperature = True
                continue
            if attempt >= len(MODEL_RETRY_DELAYS_SEC) or not is_retryable_model_error(exc):
                raise
            time.sleep(MODEL_RETRY_DELAYS_SEC[attempt])
    raise last_error


def is_unsupported_temperature_error(exc):
    text = str(exc).lower()
    return "unsupported parameter" in text and "temperature" in text


def is_retryable_model_error(exc):
    text = str(exc).lower()
    if "flagged" in text or "cybersecurity risk" in text or "invalid_request_error" in text:
        return False
    retry_markers = [
        "error code: 408",
        "error code: 409",
        "error code: 429",
        "error code: 500",
        "error code: 502",
        "error code: 503",
        "error code: 504",
        "overloaded",
        "rate limit",
        "timeout",
        "temporarily unavailable",
    ]
    return any(marker in text for marker in retry_markers)
