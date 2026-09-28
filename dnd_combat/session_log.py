"""Append-only local playtest records and a readable session report."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from .narrator import Narrator


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class SessionRecorder:
    """Write one inspectable JSON object per event, outside the repository by default."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.session_id = uuid4().hex
        if path is None:
            directory = Path(os.getenv(
                "DND_SESSION_LOG_DIR",
                Path.home() / ".local" / "state" / "dnd-bot-interface" / "sessions",
            )).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
            path = directory / f"{stamp}_{self.session_id}.jsonl"
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **fields: object) -> None:
        item = {
            "session_id": self.session_id,
            "timestamp": timestamp(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    def input(self, player_input: str, game, *, action=None, outcome=None, details=None) -> None:
        self.record(
            "player_input",
            input=player_input,
            room_id=game.current_room_id,
            room=game.room.name,
            action=action,
            outcome=outcome,
            details=details or {},
            state={
                "hp": game.hero.hp,
                "inventory": list(game.hero.inventory),
                "game_state": game.state,
            },
        )

    @staticmethod
    def report(path: str | Path | None = None) -> str:
        if path is None:
            directory = Path(os.getenv(
                "DND_SESSION_LOG_DIR",
                Path.home() / ".local" / "state" / "dnd-bot-interface" / "sessions",
            )).expanduser()
            candidates = sorted(directory.glob("*.jsonl"), key=lambda item: item.stat().st_mtime)
            if not candidates:
                return f"No playtest sessions found in {directory}."
            selected = candidates[-1]
        else:
            selected = Path(path).expanduser()
        try:
            events = [json.loads(line) for line in selected.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, json.JSONDecodeError) as error:
            return f"Could not read session report {selected}: {error}"
        if not events:
            return f"Session log is empty: {selected}"

        first, last = events[0], events[-1]
        inputs = [event for event in events if event.get("event") == "player_input"]
        suggestions = [event for event in events if event.get("event") == "room_suggestion"]
        rooms = list(dict.fromkeys(
            event.get("room") for event in inputs if event.get("room")
        ))
        model_events = [event for event in events if event.get("event") in {"narration", "room_suggestion"} and event.get("llm")]
        durations = [event.get("latency_ms", 0) for event in model_events]
        models = sorted({event["model"] for event in model_events if event.get("model")})
        lines = [
            f"Playtest session {first.get('session_id', 'unknown')}",
            f"Started: {first.get('timestamp', 'unknown')}",
            f"Ended:   {last.get('timestamp', 'unknown')}",
            f"Log:     {selected}",
            f"Inputs: {len(inputs)} | Rooms visited: {len(rooms)} | Model requests: {len(model_events)}",
        ]
        if models:
            lines.append("Models: " + ", ".join(models))
        if rooms:
            lines.append("Route: " + " -> ".join(rooms))
        if suggestions:
            accepted = sum(event.get("accepted_count", 0) for event in suggestions)
            rejected = sum(event.get("rejected_count", 0) for event in suggestions)
            lines.append(f"Room proposals: {accepted} accepted, {rejected} rejected")
        if durations:
            lines.append(f"LLM latency: {', '.join(f'{value:.0f} ms' for value in durations)}")
        lines.append("\nPlay log:")
        for event in events:
            at = event.get("timestamp", "")
            clock = at[11:19] if len(at) >= 19 else at
            if event.get("event") == "player_input":
                action = event.get("action") or "unrecognized"
                outcome = event.get("outcome") or "no resolved action"
                lines.append(f"{clock} [{event.get('room', '?')}] {event.get('input', '')} → {action}: {outcome}")
                details = event.get("details") or {}
                if details.get("rolls"):
                    lines.append(f"  Rolls: {details['rolls']}")
                if details.get("response"):
                    lines.append(f"  World response: {details['response']}")
            elif event.get("event") == "enemy_action":
                lines.append(
                    f"{clock} [{event.get('room', '?')}] {event.get('enemy', 'Enemy')} attack: "
                    f"{event.get('outcome')} ({event.get('rolls')})"
                )
            elif event.get("event") == "narration":
                if event.get("response"):
                    lines.append(f"{clock} DM ({event.get('category')}): {event['response']}")
                elif event.get("fallback"):
                    lines.append(f"{clock} DM ({event.get('category')}): deterministic fallback")
            elif event.get("event") == "room_suggestion":
                if event.get("llm"):
                    lines.append(
                        f"{clock} Room dressing: {event.get('accepted_count', 0)} accepted, "
                        f"{event.get('rejected_count', 0)} rejected"
                        + (", fallback" if event.get("fallback") else "")
                    )
        fallbacks = sum(event.get("fallback", False) for event in model_events)
        if fallbacks:
            lines.append(f"Narrator fallbacks: {fallbacks}")
        return "\n".join(lines)


class RecordingNarrator(Narrator):
    """Capture optional narrator requests without letting them alter game rules."""

    def __init__(self, narrator: Narrator, recorder: SessionRecorder) -> None:
        self.narrator = narrator
        self.recorder = recorder
        self._pending_proposal: list[dict] = []
        self._pending_llm = False

    def narrate(self, event: str, facts: dict, plain_text: str) -> str:
        is_llm = hasattr(self.narrator, "adapter")
        request_facts = deepcopy(facts)
        started = time.perf_counter()
        try:
            rendered = self.narrator.narrate(event, deepcopy(request_facts), plain_text)
            narrator_failed = not isinstance(rendered, str)
        except Exception:
            narrator_failed = True
        if narrator_failed:
            rendered = plain_text
        latency_ms = (time.perf_counter() - started) * 1000
        response = rendered.partition("\nDM: ")[2] if "\nDM: " in rendered else ""
        fallback = getattr(self.narrator, "last_narration_fallback", is_llm and not response)
        self.recorder.record(
            "narration",
            category=event,
            llm=is_llm,
            model=getattr(self.narrator, "model", None) if is_llm else None,
            request_facts=request_facts,
            response=response or None,
            fallback=is_llm and (narrator_failed or fallback),
            latency_ms=round(latency_ms, 1) if is_llm else None,
        )
        return rendered

    def suggest_room_objects(self, facts: dict) -> list[dict]:
        is_llm = hasattr(self.narrator, "adapter")
        started = time.perf_counter()
        proposals = self.narrator.suggest_room_objects(facts)
        self._pending_proposal = proposals
        self._pending_llm = is_llm
        self._pending_latency = (time.perf_counter() - started) * 1000
        self._pending_fallback = getattr(
            self.narrator, "last_suggestion_fallback", is_llm and not proposals
        )
        return proposals

    def record_suggestion_validation(self, accepted: list) -> None:
        rejected_count = max(0, len(self._pending_proposal) - len(accepted))
        self.recorder.record(
            "room_suggestion",
            category="room_dressing",
            llm=self._pending_llm,
            model=getattr(self.narrator, "model", None) if self._pending_llm else None,
            proposals=self._pending_proposal,
            accepted=[item.name for item in accepted],
            accepted_count=len(accepted),
            rejected_count=rejected_count,
            fallback=self._pending_llm and self._pending_fallback,
            latency_ms=round(self._pending_latency, 1) if self._pending_llm else None,
        )
        self._pending_proposal = []
        self._pending_llm = False
        self._pending_fallback = False
