"""Application orchestration across rules, narration, and terminal rendering."""

from __future__ import annotations

from .adventure import Adventure
from .narrator import Narrator
from .terminal import emit, room_facts


def announce_room(game: Adventure, narrator: Narrator, recorder=None) -> None:
    """Request optional scenery, validate it in rules, then render room facts."""
    if game.request_room_object_suggestions():
        accepted = game.add_room_object_suggestions(narrator.suggest_room_objects(room_facts(game)))
        if hasattr(narrator, "record_suggestion_validation"):
            narrator.record_suggestion_validation(accepted)
        if recorder:
            recorder.record(
                "room_suggestion_validation",
                room_id=game.current_room_id,
                room=game.room.name,
                accepted=[item.name for item in accepted],
            )
    emit(narrator, "enter_room", room_facts(game), f"{game.room.name}: {game.look()}")
    for item in game.room.items:
        emit(narrator, "item_found", {"room": game.room.name, "item": item, "hero": game.hero.name}, f"You spot {item}.")
