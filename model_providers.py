# User-editable model provider configuration for ai-ctfer.
#
# Add or edit entries here to expose new values for:
#
#   model:
#     name: ...
#
# Supported api_style values:
# - "responses" uses client.responses.create(...)
# - "chat_completions" uses client.chat.completions.create(...)

DEFAULT_MODEL_PROVIDER = "gpt"

MODEL_PROVIDERS = {
    "gpt": {
        "aliases": ["gpt", "openai", "gpt-5.5", "gpt-5.5-xhigh"],
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "api_model": "gpt-5.5",
        "api_style": "responses",
        "reasoning_effort": "xhigh",
        "sample_comment": "gpt => gpt-5.5 with xhigh reasoning",
    },
    "deepseek": {
        "aliases": ["deepseek", "deepseek-v4-pro", "deepseek-v4-flash"],
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "api_model": "deepseek-v4-pro",
        "api_style": "chat_completions",
        "reasoning_effort": None,
        "sample_comment": "deepseek => deepseek-v4-pro",
    }
}
