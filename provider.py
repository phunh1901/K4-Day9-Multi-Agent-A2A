"""OpenRouter provider configuration for the Day 9 multi-agent pipeline."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# Keep the model name in source code: the assignment requires it to be auditable
# and not hidden in .env. Qwen3.5-9B is within the <=10B parameter limit.
MODEL_NAME = "qwen/qwen3.5-9b"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_client() -> OpenAI:
    """Create an OpenRouter-backed OpenAI-compatible client."""

    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Copy .env.example to .env and set it."
        )

    default_headers: dict[str, str] = {}
    site_url = os.getenv("OPENROUTER_SITE_URL")
    site_name = os.getenv("OPENROUTER_SITE_NAME")
    if site_url:
        default_headers["HTTP-Referer"] = site_url
    if site_name:
        default_headers["X-Title"] = site_name

    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers=default_headers or None,
    )


def chat_completion(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Run one chat completion using the configured Qwen model."""

    client = get_client()
    return client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        **kwargs,
    )
