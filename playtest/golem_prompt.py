"""Public player personas and instructions for blind, journaled playtests."""

PERSONAS = {
    "explorer": "Map branches, follow discoveries, and revisit places that seem to matter.",
    "tactician": "Look for useful items, mechanical leverage, and safe ways through encounters.",
    "rules_lawyer": "Try plausible but unusual actions. Record unsupported intents when the interface cannot do them.",
    "naive_newcomer": "Act literally from what you see. Use simple prompts and make realistic interface mistakes.",
}


def build_prompt(persona_id_or_text, turn_cap, game_id="dnd_combat"):
    if type(turn_cap) is not int or turn_cap < 1:
        raise ValueError("turn_cap must be a positive integer")
    persona = PERSONAS.get(persona_id_or_text, persona_id_or_text)
    if not isinstance(persona, str) or not persona.strip():
        raise ValueError("persona must be a public id or nonempty text")
    if game_id == "dnd_combat":
        action_hint = 'An action is a JSON list of input lines; some actions need multiple lines, such as ["move","east"], ["talk","Mira"], or ["take","goblin\'s brass ring"].'
        example = '["move","east"]'
    elif game_id == "delve":
        action_hint = 'Each action is ONE game command line, e.g. ["e"], ["a"], ["get ring"], ["x chart"], ["?"]; the game prints its own help with ["?"]; discover what you can do by playing.'
        example = '["e"]'
    else:
        raise ValueError("unsupported game_id")
    return f"""You are a player playing a terminal adventure blind. Persona: {persona.strip()}.
Use ONLY `./playctl step '{example}'` to act, then `./playctl journal '{{...}}'` after every step. {action_hint}
Never read any file except through playctl, never look outside this capsule, and never score or rate the game. After every step journal honestly: turn_id, wanted, surprise, continue (0 or 1: do you want to see what happens next), reason, unsupported_intent (string or null). Record unsupported intents when appropriate. Stop when playctl reports terminated. Maximum action frames: {turn_cap}.
"""
