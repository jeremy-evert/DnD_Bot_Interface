"""Verified small transcripts used to calibrate playtest detectors."""
import hashlib
import tempfile
from pathlib import Path

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
    text = "That does nothing."
    states = [{"room_id": "entry", "rooms": {}, "canonical_state_hash": "same"} for _ in range(3)]
    return _records([text] * 3, [["look"], ["look"], ["look"]], states)


def no_consequence_stall():
    state = {"room_id": "entry", "rooms": {}, "canonical_state_hash": "same"}
    return _records(["You wait.", "You wait."], [["wait"], ["wait"]], [state, state])


def hollow_consequence():
    before = {"room_id": "gallery", "vault_opened": False, "rooms": {
        "gallery": {"exits": {"east": "shrine"}}, "shrine": {"exits": {"west": "gallery", "east": "sanctum"}}, "sanctum": {"exits": {"west": "shrine"}}}, "canonical_state_hash": "a"}
    after = {"room_id": "gallery", "vault_opened": True, "rooms": {
        "gallery": {"exits": {"east": "shrine", "west": "sanctum"}}, "shrine": {"exits": {"west": "gallery", "east": "sanctum"}}, "sanctum": {"exits": {"west": "shrine"}}}, "canonical_state_hash": "b"}
    return _records(["Ready.", "Mira opens the hidden door west."], [[], ["talk", "Mira"]], [before, after])


def world_state_contradiction():
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
