"""Combat rules kept independent from terminal input/output."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import randint
from typing import Callable


Roller = Callable[[int], int]


def roll_die(sides: int) -> int:
    """Roll one die with the supplied number of sides."""
    return randint(1, sides)


@dataclass
class Creature:
    name: str
    hp: int
    armor_class: int
    attack_bonus: int
    damage_die: int
    damage_bonus: int
    initiative_bonus: int = 0
    max_hp: int | None = None
    inventory: list[str] = field(default_factory=list)
    character_class: str = ""

    def __post_init__(self) -> None:
        if self.max_hp is None:
            self.max_hp = self.hp

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def heal(self, amount: int) -> int:
        """Restore HP up to the creature's original maximum and report the amount restored."""
        previous_hp = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - previous_hp


@dataclass(frozen=True)
class AttackResult:
    roll: int
    total: int
    hit: bool
    damage: int = 0


def roll_initiative(creature: Creature, roller: Roller = roll_die) -> int:
    return roller(20) + creature.initiative_bonus


def attack(attacker: Creature, defender: Creature, roller: Roller = roll_die) -> AttackResult:
    """Make one d20 attack; natural 20 hits and natural 1 misses."""
    roll = roller(20)
    total = roll + attacker.attack_bonus
    hit = roll == 20 or (roll != 1 and total >= defender.armor_class)
    if not hit:
        return AttackResult(roll, total, False)

    damage = max(1, roller(attacker.damage_die) + attacker.damage_bonus)
    defender.hp = max(0, defender.hp - damage)
    return AttackResult(roll, total, True, damage)


def make_hero() -> Creature:
    return Creature("Hero", hp=20, armor_class=14, attack_bonus=4, damage_die=8, damage_bonus=2, initiative_bonus=2)


def make_goblin() -> Creature:
    return Creature("Goblin", hp=12, armor_class=13, attack_bonus=4, damage_die=6, damage_bonus=2, initiative_bonus=2)
