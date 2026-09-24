"""Transport and structured-response boundary for optional local LLMs."""

from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, urlopen


class LocalLLMAdapter:
    """Own HTTP, timeout, extraction, diagnostics, and fail-closed fallbacks."""

    def __init__(self, endpoint: str, timeout: float, urlopen_fn=None) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._urlopen = urlopen_fn or urlopen

    def request_content(self, payload: dict, *, context: str, fallback: str = "") -> str:
        try:
            request = Request(
                self.endpoint, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            response = self._urlopen(request, timeout=self.timeout)
            try:
                data = json.loads(response.read().decode("utf-8"))
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Local LLM returned empty content.")
            return content.strip()
        except Exception as error:
            self._debug(context, error)
            return fallback

    def request_json(self, payload: dict, *, context: str, fallback: object) -> object:
        content = self.request_content(payload, context=context)
        if not content:
            return fallback
        try:
            return json.loads(self._extract_json(content))
        except Exception as error:
            self._debug(context, error)
            return fallback

    @staticmethod
    def _extract_json(content: str) -> str:
        """Accept a JSON object/array optionally wrapped in a markdown fence."""
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return stripped

    @staticmethod
    def _debug(context: str, error: Exception) -> None:
        if os.getenv("DND_NARRATOR_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
            print(f"[{context} fallback: {type(error).__name__}: {error}]", file=sys.stderr)
