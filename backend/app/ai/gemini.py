"""Gemini API access (Phase 5 decision: Gemini 2.5 Flash + gemini-embedding-001).

Three thin async wrappers; the pipeline and tests monkeypatch these, so all
provider detail stays in this one file.
"""

import json

from google import genai
from google.genai import types

from app.config import get_settings
from app.models import EMBEDDING_DIM


def _client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


async def embed(text: str) -> list[float]:
    result = await _client().aio.models.embed_content(
        model=get_settings().gemini_embedding_model,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
    )
    values = list(result.embeddings[0].values)
    # Dimensions other than 3072 are not pre-normalized by the API
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]


async def generate_json(prompt: str, schema: dict) -> dict:
    response = await _client().aio.models.generate_content(
        model=get_settings().gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=schema
        ),
    )
    return json.loads(response.text)


async def generate_text(prompt: str) -> str:
    response = await _client().aio.models.generate_content(
        model=get_settings().gemini_model, contents=prompt
    )
    return response.text or ""
