"""Player command boundary: normalize and resolve terminal command phrases."""

from __future__ import annotations

from .matching import DeterministicMatcher, MatchCandidate


EXPLORATION_COMMANDS = DeterministicMatcher(
    (
        MatchCandidate("move", "move", ("m",)),
        MatchCandidate("look", "look", ("l",)),
        MatchCandidate("status", "status", ("s",)),
        MatchCandidate("take", "take", ("t",)),
        MatchCandidate("use", "use", ("u", "use potion")),
    )
)

COMBAT_COMMANDS = DeterministicMatcher(
    (
        MatchCandidate("attack", "attack", ("a",)),
        MatchCandidate("use", "use", ("u", "potion", "use potion")),
        MatchCandidate("status", "status", ("s",)),
    )
)

CHARACTER_COMMANDS = DeterministicMatcher(
    (
        MatchCandidate("fighter", "fighter", ("f",)),
        MatchCandidate("rogue", "rogue", ("r",)),
        MatchCandidate("wizard", "wizard", ("w",)),
    )
)


def resolve_exploration_command(raw: str) -> str | None:
    return EXPLORATION_COMMANDS.match(raw)


def resolve_combat_command(raw: str) -> str | None:
    return COMBAT_COMMANDS.match(raw)


def resolve_character_command(raw: str) -> str | None:
    return CHARACTER_COMMANDS.match(raw)
