"""Deterministic matching for player-facing names and commands.

Matching deliberately does not guess.  A short phrase is accepted only when it
identifies one candidate uniquely, which keeps the Python command boundary
authoritative even when convenient abbreviations are used.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Generic, Iterable, TypeVar


T = TypeVar("T")
_WORDS = re.compile(r"[a-z0-9]+")


def normalize(phrase: str) -> str:
    """Normalize a player phrase without applying any semantic interpretation."""
    return " ".join(_WORDS.findall(phrase.lower()))


@dataclass(frozen=True)
class MatchCandidate(Generic[T]):
    """A canonical value and the phrases which explicitly identify it."""

    value: T
    name: str
    aliases: tuple[str, ...] = ()

    @property
    def phrases(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


class DeterministicMatcher(Generic[T]):
    """Resolve an exact phrase or a unique word subset to one candidate."""

    def __init__(self, candidates: Iterable[MatchCandidate[T]]) -> None:
        self.candidates = tuple(candidates)

    def match(self, phrase: str) -> T | None:
        requested = normalize(phrase)
        if not requested:
            return None

        exact = [candidate for candidate in self.candidates if requested in {
            normalize(name) for name in candidate.phrases
        }]
        if len(exact) == 1:
            return exact[0].value
        if exact:
            return None

        requested_words = set(requested.split())
        partial = [
            candidate
            for candidate in self.candidates
            if any(requested_words <= set(normalize(name).split()) for name in candidate.phrases)
        ]
        return partial[0].value if len(partial) == 1 else None
