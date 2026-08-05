"""OpenAI provider configuration for the Day 9 multi-agent pipeline."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# Keep the model name in source code so the active model is auditable.
MODEL_NAME = "gpt-4o-mini"


def get_client() -> OpenAI:
    """Create an OpenAI client."""

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and set it."
        )

    return OpenAI(api_key=api_key)


def chat_completion(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Run one chat completion using the configured OpenAI model."""

    client = get_client()
    return client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        **kwargs,
    )
