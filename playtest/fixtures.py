"""Hash-chained detector examples, including explicitly patched game runs.

The local chain catches accidental or partial changes. It is not proof against
an actor who can rewrite both the records and their local chain anchor.
"""
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from dnd_combat.adventure import Adventure as RealAdventure
import dnd_combat.__main__ as game_main
from .harness import replay, snapshot
from .transcript import TranscriptWriter, load_transcript


def _records(outputs, actions=None, states=None, termination="playing"):
    actions = actions or [[] for _ in outputs]
    states = states or [{"room_id": "entry", "room": "Mossy Entry", "rooms": {}, "canonical_state_hash": "0" * 64} for _ in outputs]
    with tempfile.TemporaryDirectory() as folder:
        writer = TranscriptWriter(folder)
        full = ""
        for i, text in enumerate(outputs):
            full += text
            writer.append_verified({"run_id": "fixture", "turn_id": i, "frame_id": i,
                "input_calls": actions[i], "new_output": text, "full_output": full,
                "full_output_sha256": hashlib.sha256(full.encode()).hexdigest(),
                "snapshot": states[i], "termination": termination if i == len(outputs)-1 else "playing",
                "game_sha": "fixture", "harness_sha": "fixture"})
        return load_transcript(Path(folder) / "transcript.jsonl")


def unrecognized_command():
    return _records(["Choose move, look, status, take, use, or talk."], [["nonsense"]])


def unsupported_intent():
    return _records(["There is no one here to talk to."], [["talk", "rock"]])


def repeated_response():
    """SYNTHETIC_TEXT+twin: calibrated shorthand; see real harness twin."""
    text = "That does nothing."
    states = [{"room_id": "entry", "rooms": {}, "canonical_state_hash": "same"} for _ in range(3)]
    return _records([text] * 3, [["look"], ["look"], ["look"]], states)


def no_consequence_stall():
    """SYNTHETIC_TEXT+twin: calibrated shorthand; see real harness twin."""
    state = {"room_id": "entry", "rooms": {}, "canonical_state_hash": "same"}
    return _records(["You wait.", "You wait."], [["wait"], ["wait"]], [state, state])


def hollow_consequence():
    """SYNTHETIC_TEXT+twin: graph edge case; real-harness text twin below."""
    before = {"room_id": "gallery", "vault_opened": False, "rooms": {
        "gallery": {"exits": {"east": "shrine"}}, "shrine": {"exits": {"west": "gallery", "east": "sanctum"}}, "sanctum": {"exits": {"west": "shrine"}}}, "canonical_state_hash": "a"}
    after = {"room_id": "gallery", "vault_opened": True, "rooms": {
        "gallery": {"exits": {"east": "shrine", "west": "sanctum"}}, "shrine": {"exits": {"west": "gallery", "east": "sanctum"}}, "sanctum": {"exits": {"west": "shrine"}}}, "canonical_state_hash": "b"}
    return _records(["Ready.", "Mira opens the hidden door west."], [[], ["talk", "Mira"]], [before, after])


def world_state_contradiction():
    """SYNTHETIC_TEXT+twin: state/text edge case; real-harness text twin below."""
    state = {"room_id": "shrine", "rooms": {"shrine": {"name": "Rootbound Shrine", "exits": {"east": "sanctum"}}}, "canonical_state_hash": "x"}
    return _records(["Rootbound Shrine: The sealed vault waits east."], [["look"]], [state])


def dominant_action():
    # Reuse actual combat output from a recorded game; only the hash-chained
    # fixture sequence is synthesized to exercise the percentage boundary.
    real = load_transcript(Path(__file__).parent / "fixtures" / "real" / "pilot1_explorer" / "transcript.jsonl")
    sample = next(r["new_output"] for r in real if "Your turn." in r["new_output"] and " rolls " in r["new_output"])
    return _records([sample] * 5, [["attack"]] * 5)


def fail_with_nothing():
    real = load_transcript(Path(__file__).parent / "fixtures" / "real" / "pilot4_newcomer" / "transcript.jsonl")
    death = real[-1]["new_output"]
    return _records([death], [["attack"]], termination="dead")


def clean_death():
    real = load_transcript(Path(__file__).parent / "fixtures" / "real" / "pilot4_newcomer" / "transcript.jsonl")
    death = real[-1]["new_output"].replace(
        "You have fallen. The adventure ends here.",
        "You have fallen because the captain struck you down. Retry the adventure to try again.")
    return _records([death], [["attack"]], termination="dead")


def death_wording(message, prefix=""):
    """Synthetic terminal wording for structural detector edge cases."""
    return _records([prefix + message], [["attack"]],
                    [{"game_state": "dead", "room_id": "sanctum"}], termination="dead")


def death_wording_real_harness(message):
    """REAL_HARNESS: force death after a real attack and patch only its wording."""
    original_attack = RealAdventure.player_attack

    def lethal_attack(game, roller):
        outcome = original_attack(game, roller)
        game.hero.hp = 0
        game.state = "dead"
        game.combat_turn = None
        return outcome

    def emit_with_wording(narrator, event, facts, fallback):
        print(message if event == "player_death" else fallback)

    with patch.object(RealAdventure, "player_attack", lethal_attack), \
            patch.object(game_main, "emit", side_effect=emit_with_wording):
        result = replay(9, ["Ada", "fighter", "attack"])
    assert message in result.output
    state = snapshot(result.witness)
    return _records([message], [["attack"]], [state], termination="dead")


def repeated_response_real_harness():
    """SYNTHETIC_TEXT+twin: presentation patch is emitted by the real game loop."""
    with patch.object(RealAdventure, "look", return_value="That does nothing."):
        result = replay(41, ["Ada", "fighter", "look", "look", "look"])
    assert result.output.count("That does nothing.") == 3
    state = snapshot(result.witness)
    return _records(["That does nothing."] * 3, [["look"]] * 3, [state] * 3)


def no_consequence_stall_real_harness():
    """SYNTHETIC_TEXT+twin: patched reply traverses the real dialogue command."""
    with patch.object(RealAdventure, "talk", return_value=(True, "You wait.")):
        result = replay(41, ["Ada", "fighter", "talk", "Mira", "talk", "Mira"])
    assert result.output.count("You wait.") == 2
    state = snapshot(result.witness)
    return _records(["You wait."] * 2, [["talk", "Mira"]] * 2, [state, state])


def hollow_consequence_real_harness():
    """SYNTHETIC_TEXT+twin: real game loop and patched talk response."""
    with patch.object(RealAdventure, "talk", return_value=(True, "Mira opens the hidden door west.")):
        result = replay(41, ["Ada", "fighter", "talk", "Mira"])
    assert "Mira opens the hidden door west." in result.output
    before = {"room_id": "gallery", "vault_opened": False, "rooms": {
        "gallery": {"exits": {"east": "shrine"}}, "shrine": {"exits": {"west": "gallery", "east": "sanctum"}},
        "sanctum": {"exits": {"west": "shrine"}}}, "canonical_state_hash": "a"}
    after = {"room_id": "gallery", "vault_opened": True, "rooms": {
        "gallery": {"exits": {"east": "shrine", "west": "sanctum"}}, "shrine": {"exits": {"west": "gallery", "east": "sanctum"}},
        "sanctum": {"exits": {"west": "shrine"}}}, "canonical_state_hash": "b"}
    return _records(["Ready.", "Mira opens the hidden door west."], [[], ["talk", "Mira"]], [before, after])


def world_state_contradiction_real_harness():
    """SYNTHETIC_TEXT+twin: exact wording is emitted by patched real look."""
    message = "Rootbound Shrine: The sealed vault waits east."
    with patch.object(RealAdventure, "look", return_value=message):
        result = replay(41, ["Ada", "fighter", "look"])
    assert message in result.output
    state = {"room_id": "shrine", "rooms": {"shrine": {"name": "Rootbound Shrine", "exits": {"east": "sanctum"}}}, "canonical_state_hash": "x"}
    return _records([message], [["look"]], [state])


def real_noise_cases():
    """Real transcript frames illustrating prompt/combat and potion noise."""
    combat = load_transcript(Path(__file__).parent / "fixtures" / "real" / "pilot1_explorer" / "transcript.jsonl")
    extra = next(r for r in combat if "Choose attack, use, or status." in r["new_output"])
    potion = next((r for r in combat if "You recover" in r["new_output"]), None)
    if potion is None:
        potion = next(r for r in combat if r.get("input_calls") == ["use", "potion"])
    return {"combat_extra_input": [extra], "full_hp_potion": [potion]}


def clean_route():
    frames = [["Ada", "fighter"], ["attack"], ["attack"], ["move", "east"], ["look"]]
    outputs, states, calls = [], [], []
    full_output = ""
    for frame in frames:
        calls.extend(frame)
        result = replay(41, calls)
        outputs.append(result.output[len(full_output):])
        full_output = result.output
        states.append(snapshot(result.witness))
    return _records(outputs, frames, states)


def all_broken():
    return {"UNRECOGNIZED_COMMAND": unrecognized_command(), "UNSUPPORTED_INTENT": unsupported_intent(),
            "REPEATED_RESPONSE": repeated_response(), "NO_CONSEQUENCE_STALL": no_consequence_stall(),
            "HOLLOW_CONSEQUENCE": hollow_consequence(), "WORLD_STATE_CONTRADICTION": world_state_contradiction(),
            "DOMINANT_ACTION": dominant_action(), "FAIL_WITH_NOTHING": fail_with_nothing()}
