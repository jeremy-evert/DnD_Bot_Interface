"""Optional narration layer for the deterministic dungeon engine.

The narrator can decorate facts, but it never decides game state.
"""

from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "http://localhost:8080/v1/chat/completions"
DEFAULT_MODEL = "mlx-community/Qwen3.5-9B-MLX-4bit"

SYSTEM_PROMPT = """You are the narrator for a tiny fantasy dungeon adventure.

The deterministic Python game engine is the sole authority for all game facts.
Rewrite only the supplied event into 1-3 short, entertaining sentences.

Rules:
- Do not invent or change numbers.
- Do not create items, monsters, rooms, spells, rewards, exits, or outcomes.
- Do not resolve actions or make game decisions.
- Describe only the supplied facts.
- If the facts are sparse, say less rather than inventing something.
- Keep the tone vivid, playful, and concise.
"""


class Narrator:
    """Presentation-only boundary for game narration."""

    def narrate(self, event: str, facts: dict, plain_text: str) -> str:
        raise NotImplementedError


class PlainNarrator(Narrator):
    """Return the deterministic text unchanged."""

    def narrate(self, event: str, facts: dict, plain_text: str) -> str:
        return plain_text


class LocalLLMNarrator(Narrator):
    """Decorate completed game events with a local OpenAI-compatible model."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: float = 4.0,
        fallback: Narrator | None = None,
        urlopen_fn=None,
    ) -> None:
        self.endpoint = endpoint or os.getenv("DND_LLM_ENDPOINT", DEFAULT_ENDPOINT)
        self.model = model or os.getenv("DND_LLM_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        self.fallback = fallback or PlainNarrator()
        self._urlopen = urlopen_fn or urlopen

    def narrate(self, event: str, facts: dict, plain_text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "event": event,
                            "facts": facts,
                            "plain_text": plain_text,
                        },
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0.8,
            "max_tokens": 120,
            "stream": False,
        }

        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            response = self._urlopen(request, timeout=self.timeout)
            try:
                raw = response.read().decode("utf-8")
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()

            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"].strip()
            if not content:
                raise ValueError("Local narrator returned empty content.")
            return f"{plain_text}\nDM: {content}"
        except Exception:
            return self.fallback.narrate(event, facts, plain_text)


def make_narrator() -> Narrator:
    """Build the configured narrator.

    Plain deterministic narration is the default. Set DND_NARRATOR=local to
    opt into the local OpenAI-compatible endpoint.
    """
    mode = os.getenv("DND_NARRATOR", "plain").strip().lower()
    if mode in {"local", "qwen", "llm"}:
        return LocalLLMNarrator()
    return PlainNarrator()
