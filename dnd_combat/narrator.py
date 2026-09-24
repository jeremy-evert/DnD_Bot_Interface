"""Optional narration layer for the deterministic dungeon engine.

The narrator can decorate facts, but it never decides game state.
"""

from __future__ import annotations

import json
import os

from .llm_adapter import LocalLLMAdapter


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

ROOM_OBJECT_PROMPT = """Suggest up to three mundane, non-takeable scenery objects for this room.
Return JSON only: {"objects":[{"name":"lowercase short name","description":"plain factual description"}]}.
Never suggest people, creatures, enemies, exits, rewards, treasure, currency, maps, keys,
weapons, armor, potions, healing, spells, bonuses, mechanics, or anything takeable.
The Python engine will reject invalid suggestions; do not add commentary."""


class Narrator:
    """Presentation-only boundary for game narration."""

    def narrate(self, event: str, facts: dict, plain_text: str) -> str:
        raise NotImplementedError

    def suggest_room_objects(self, facts: dict) -> list[dict]:
        """Optionally propose structured scenery; never mutate game state."""
        return []


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
        self.adapter = LocalLLMAdapter(self.endpoint, timeout, urlopen_fn)

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
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "chat_template_kwargs": {"enable_thinking": False},
            "max_tokens": 160,
            "stream": False,
        }

        content = self.adapter.request_content(payload, context="narrator")
        if content:
            return f"{plain_text}\nDM: {content}"
        return self.fallback.narrate(event, facts, plain_text)

    def suggest_room_objects(self, facts: dict) -> list[dict]:
        """Ask the local model once for JSON scenery, failing closed on any error."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": ROOM_OBJECT_PROMPT},
                {"role": "user", "content": json.dumps(facts, sort_keys=True)},
            ],
            "temperature": 0.4,
            "top_p": 0.8,
            "top_k": 20,
            "chat_template_kwargs": {"enable_thinking": False},
            "max_tokens": 180,
            "stream": False,
        }
        data = self.adapter.request_json(payload, context="room-object", fallback={})
        objects = data.get("objects") if isinstance(data, dict) else None
        return objects if isinstance(objects, list) else []


def make_narrator() -> Narrator:
    """Build the configured narrator.

    Plain deterministic narration is the default. Set DND_NARRATOR=local to
    opt into the local OpenAI-compatible endpoint.
    """
    mode = os.getenv("DND_NARRATOR", "plain").strip().lower()
    if mode in {"local", "qwen", "llm"}:
        return LocalLLMNarrator()
    return PlainNarrator()
