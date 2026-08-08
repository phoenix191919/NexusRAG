from __future__ import annotations

import json
import re
from typing import Any, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import get_settings


class GeminiClient:
    # Prefer configured model, then lighter/alternate free-tier models
    FALLBACK_MODELS = [
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.6-flash",
    ]

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key)

    def _chat_models(self) -> list[str]:
        primary = self.settings.gemini_model
        models = [primary]
        for m in self.FALLBACK_MODELS:
            if m not in models:
                models.append(m)
        return models

    def embed(self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = self.client.models.embed_content(
                model=self.settings.embedding_model,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.settings.embedding_dims,
                ),
            )
            for emb in result.embeddings or []:
                vectors.append(list(emb.values or []))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vecs = self.embed([text], task_type="RETRIEVAL_QUERY")
        return vecs[0] if vecs else []

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Any:
        text = self._generate(prompt, system=system, json_mode=True)
        return _parse_json(text)

    def generate_text(self, prompt: str, system: Optional[str] = None) -> str:
        return self._generate(prompt, system=system, json_mode=False)

    def _generate(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str:
        config = types.GenerateContentConfig(temperature=0.1 if json_mode else 0.2)
        if json_mode:
            config.response_mime_type = "application/json"
        if system:
            config.system_instruction = system

        last_err: Exception | None = None
        for model in self._chat_models():
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                return (response.text or "").strip()
            except genai_errors.ClientError as e:
                last_err = e
                # Try next model on quota / not found
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "404" in msg or "NOT_FOUND" in msg:
                    print(f"[gemini] {model} failed ({e}); trying fallback…")
                    continue
                raise
            except Exception as e:
                last_err = e
                print(f"[gemini] {model} failed ({e}); trying fallback…")
                continue
        raise last_err or RuntimeError("Gemini generation failed")


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if match:
            return json.loads(match.group(0))
        raise


def friendly_gemini_error(exc: Exception) -> str:
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        return (
            "Gemini API quota exceeded for now. Wait about a minute (or until daily quota resets), "
            "then try again. Free-tier limits are per model."
        )
    return f"Answer generation failed: {exc}"
