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
    """REAL_HARNESS: a wizard dies in real combat; patch only death wording."""
    def emit_with_wording(narrator, event, facts, fallback):
        print(message if event == "player_death" else fallback)

    return _real_harness_frames([["attack"], ["attack"], ["attack"]], seed=2,
                                character="wizard", termination="dead",
                                emit_patch=emit_with_wording)


def death_wording_real_harness_twin():
    """Default-prose REAL_HARNESS twin used by the provenance receipt table."""
    return death_wording_real_harness("You have fallen. The adventure ends here.")


def _real_harness_frames(actions, seed=0, character="fighter", termination="playing",
                         emit_patch=None):
    """Replay each action prefix and retain its actual output and state witness."""
    calls = ["Ada", character]
    prior_output = ""
    outputs, states = [], []
    for action in actions:
        calls.extend(action)
        if emit_patch is None:
            result = replay(seed, calls)
        else:
            with patch.object(game_main, "emit", side_effect=emit_patch):
                result = replay(seed, calls)
        if result.error:
            raise AssertionError(f"real game replay failed: {result.error}")
        if result.witness is None:
            raise AssertionError("real game replay produced no witness")
        outputs.append(result.output[len(prior_output):])
        prior_output = result.output
        states.append(snapshot(result.witness))
    if termination == "dead" and (not states or states[-1].get("game_state") != "dead"):
        raise AssertionError("real death fixture did not reach the dead state")
    return _records(outputs, [list(action) for action in actions], states, termination)


def repeated_response_real_harness():
    """REAL_HARNESS: three real looks in one reachable room, wording patched."""
    actions = [["attack"], ["move", "east"], ["move", "east"], ["move", "north"],
               ["look"], ["look"], ["look"]]
    with patch.object(RealAdventure, "look", return_value="That does nothing."):
        return _real_harness_frames(actions)


def no_consequence_stall_real_harness():
    """REAL_HARNESS: accepted repeated dialogue leaves canonical state unchanged."""
    actions = [["attack"], ["take", "goblin's brass ring"], ["move", "east"],
               ["move", "east"], ["move", "north"],
               ["talk", "Mira"], ["talk", "Mira"]]
    return _real_harness_frames(actions)


def hollow_consequence_real_harness():
    """REAL_HARNESS: kill, loot, movement, and Mira's vault opening are real."""
    actions = [["attack"], ["take", "goblin's brass ring"], ["move", "east"],
               ["move", "east"], ["move", "north"], ["talk", "Mira"]]
    return _real_harness_frames(actions)


def world_state_contradiction_real_harness():
    """REAL_HARNESS: reach the shrine through game movement; patch look text only."""
    message = "Rootbound Shrine: The sealed vault waits east."
    actions = [["attack"], ["move", "east"], ["move", "east"], ["move", "north"],
               ["move", "east"], ["look"]]
    with patch.object(RealAdventure, "look", return_value=message):
        return _real_harness_frames(actions)


def repeated_response_after_state_change_real_harness():
    """REAL_HARNESS: the same look text appears in gallery/shrine/gallery."""
    actions = [["attack"], ["move", "east"], ["move", "east"], ["move", "north"],
               ["look"], ["move", "east"], ["look"], ["move", "west"], ["look"]]
    with patch.object(RealAdventure, "look", return_value="That does nothing."):
        return _real_harness_frames(actions)


def informative_action_real_harness():
    """REAL_HARNESS: accepted talk reveals actionable info with stable final state."""
    actions = [["attack"], ["move", "east"], ["move", "east"], ["move", "north"],
               ["talk", "Mira"], ["talk", "Mira"]]
    return _real_harness_frames(actions)


def informative_look_real_harness():
    """REAL_HARNESS: normal room examination is informative without mutation."""
    actions = [["attack"], ["move", "east"], ["move", "east"], ["move", "north"], ["look"]]
    return _real_harness_frames(actions)


REAL_HARNESS_PROVENANCE = (
    ("repeated response", "repeated_response_real_harness", "REPEATED_RESPONSE"),
    ("no-consequence action", "no_consequence_stall_real_harness", "NO_CONSEQUENCE_STALL"),
    ("hollow consequence", "hollow_consequence_real_harness", "HOLLOW_CONSEQUENCE"),
    ("world-state contradiction", "world_state_contradiction_real_harness", "WORLD_STATE_CONTRADICTION"),
    ("death wording", "death_wording_real_harness_twin", "FAIL_WITH_NOTHING"),
)


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
