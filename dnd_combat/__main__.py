"""Terminal interface for the one-hero-versus-one-goblin combat."""

from .combat import attack, make_goblin, make_hero, roll_initiative


def show_status(hero, goblin) -> None:
    print(f"\n{hero.name}: {hero.hp} HP, AC {hero.armor_class} | {goblin.name}: {goblin.hp} HP, AC {goblin.armor_class}")


def take_attack(attacker, defender) -> None:
    result = attack(attacker, defender)
    if result.hit:
        print(f"{attacker.name} rolls {result.roll} ({result.total}) and hits {defender.name} for {result.damage} damage!")
    else:
        print(f"{attacker.name} rolls {result.roll} ({result.total}) and misses {defender.name}.")


def choose_hero_action() -> None:
    while True:
        choice = input("Your turn. [A]ttack: ").strip().lower()
        if choice in {"a", "attack"}:
            return
        print("Choose 'a' to attack.")


def main() -> None:
    hero, goblin = make_hero(), make_goblin()
    print("=== Goblin Skirmish ===")
    print("Defeat the goblin before it defeats you.")
    hero_initiative, goblin_initiative = roll_initiative(hero), roll_initiative(goblin)
    print(f"Initiative — Hero: {hero_initiative}; Goblin: {goblin_initiative}")
    # Ties go to the player, making the result clear and repeatable.
    current, other = (hero, goblin) if hero_initiative >= goblin_initiative else (goblin, hero)

    while hero.alive and goblin.alive:
        show_status(hero, goblin)
        if current is hero:
            choose_hero_action()
        else:
            print("Goblin's turn...")
        take_attack(current, other)
        current, other = other, current

    show_status(hero, goblin)
    print("\nVictory! The goblin falls." if hero.alive else "\nYou have fallen. The goblin wins.")


if __name__ == "__main__":
    main()

