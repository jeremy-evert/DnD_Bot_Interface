"""Terminal interface for the deterministic three-room adventure."""

from .adventure import HEALING_POTION, Adventure, make_character
from .combat import AttackResult, Creature, Roller, roll_die


def show_status(game: Adventure) -> None:
    hero = game.hero
    inventory = ", ".join(hero.inventory) if hero.inventory else "empty"
    print(f"{hero.name} the {hero.character_class}: {hero.hp}/{hero.max_hp} HP, AC {hero.armor_class}. Inventory: {inventory}.")


def describe_attack(attacker_name: str, defender_name: str, result: AttackResult) -> None:
    if result.hit:
        print(f"{attacker_name} rolls {result.roll} ({result.total}) and hits {defender_name} for {result.damage} damage!")
    else:
        print(f"{attacker_name} rolls {result.roll} ({result.total}) and misses {defender_name}.")


def choose_character() -> Creature:
    name = input("What is your hero's name? ").strip() or "Hero"
    aliases = {"f": "fighter", "fighter": "fighter", "r": "rogue", "rogue": "rogue", "w": "wizard", "wizard": "wizard"}
    while True:
        choice = input("Choose a character [F]ighter, [R]ogue, or [W]izard: ").strip().lower()
        if choice in aliases:
            return make_character(aliases[choice], name)
        print("Choose fighter, rogue, or wizard.")


def run_combat(game: Adventure, roller: Roller = roll_die) -> None:
    enemy = game.enemy
    hero_initiative, enemy_initiative = game.start_encounter(roller)
    print(f"\n{enemy.name} attacks! Initiative — {game.hero.name}: {hero_initiative}; {enemy.name}: {enemy_initiative}")
    while game.in_combat:
        enemy = game.enemy
        show_status(game)
        print(f"{enemy.name}: {enemy.hp}/{enemy.max_hp} HP, AC {enemy.armor_class}.")
        if game.combat_turn == "hero":
            choice = input("Your turn. [A]ttack, [U]se potion, [S]tatus: ").strip().lower()
            if choice in {"a", "attack"}:
                describe_attack(game.hero.name, enemy.name, game.player_attack(roller))
            elif choice in {"u", "use", "potion"}:
                used, healed = game.player_use_potion()
                print(f"You recover {healed} HP." if used else "You have no healing potion.")
            elif choice in {"s", "status"}:
                show_status(game)
            else:
                print("Choose attack, use, or status.")
        else:
            print(f"{enemy.name}'s turn...")
            describe_attack(enemy.name, game.hero.name, game.enemy_attack(roller))
    if game.state == "won":
        print("\nVictory! The hobgoblin captain falls; you have cleared the dungeon.")
    elif game.state == "dead":
        print("\nYou have fallen. The adventure ends here.")
    else:
        print(f"{enemy.name} falls.")


def main(roller: Roller = roll_die) -> None:
    print("=== D&D 0.2.5: The Mossy Delve ===")
    game = Adventure(choose_character())
    print(f"Welcome, {game.hero.name}. Find your way through three rooms and survive the final encounter.")
    while game.state == "playing":
        if game.in_combat:
            run_combat(game, roller)
            continue
        print(f"\n{game.room.name}: {game.look()}")
        choice = input("[M]ove, [L]ook, [S]tatus, [T]ake item, [U]se potion: ").strip().lower()
        if choice in {"m", "move"}:
            direction = input("Direction: ").strip().lower()
            print(game.move(direction)[1])
        elif choice in {"l", "look"}:
            print(game.look())
        elif choice in {"s", "status"}:
            show_status(game)
        elif choice in {"t", "take"}:
            item = input("Take what? ").strip().lower()
            print(game.take_item(item)[1])
        elif choice in {"u", "use"}:
            used, healed = game.use_healing_potion()
            print(f"You recover {healed} HP." if used else f"You have no {HEALING_POTION}.")
        else:
            print("Choose move, look, status, take, or use.")


if __name__ == "__main__":
    main()
