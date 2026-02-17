"""XP-based character builder.

Converts total XP (150 base + earned) into combat stats following a
configurable progression order. A percentage of XP is allocated to
non-combat skills and the rest is spent raising rings and combat skills.
"""

from __future__ import annotations

from typing import Optional

from src.models.character import Character, Ring, RingName, Rings, Skill, SkillType


def ring_raise_cost(new_value: int) -> int:
    """Cost to raise a ring to *new_value*: 5 × new_value."""
    return 5 * new_value


def advanced_skill_raise_cost(new_rank: int) -> int:
    """Cost to raise an advanced skill to *new_rank*.

    Ranks 1-2 cost 4 XP each.  Ranks 3+ cost 2 × new_rank.
    """
    if new_rank <= 2:
        return 4
    return 2 * new_rank


# Each entry raises that stat by 1. Covers all rings to 5 and skills to 5.
DEFAULT_COMBAT_PROGRESSION: list[str] = [
    # Cycle 1
    "void", "water", "earth", "fire", "attack", "parry",
    # Cycle 2
    "void", "water", "attack", "parry",
    # Cycle 3
    "air", "earth", "attack", "parry",
    # Cycle 4
    "fire", "void", "water", "attack", "parry",
    # Cycle 5
    "air", "earth", "fire", "attack", "parry",
    # Cycle 6
    "void", "water", "air",
    # Cycle 7
    "earth", "fire",
]

_RING_NAMES: dict[str, RingName] = {
    "air": RingName.AIR,
    "fire": RingName.FIRE,
    "earth": RingName.EARTH,
    "water": RingName.WATER,
    "void": RingName.VOID,
}


def build_character_from_xp(
    name: str = "Fighter",
    earned_xp: int = 0,
    school_ring: Optional[RingName] = None,
    non_combat_pct: float = 0.20,
    progression: Optional[list[str]] = None,
) -> Character:
    """Build a character by spending XP along a progression order.

    Args:
        name: Character name.
        earned_xp: XP earned beyond the base 150.
        school_ring: The school's focus ring (starts at 3, max 6).
        non_combat_pct: Fraction of total XP lost to non-combat skills.
        progression: Ordered list of stats to raise. Defaults to
            ``DEFAULT_COMBAT_PROGRESSION``.

    Returns:
        A fully constructed ``Character``.
    """
    if progression is None:
        progression = DEFAULT_COMBAT_PROGRESSION

    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))
    non_combat_xp = total_xp - combat_xp

    # --- Initialise stats ---
    ring_values: dict[str, int] = {
        "air": 2, "fire": 2, "earth": 2, "water": 2, "void": 2,
    }
    if school_ring is not None:
        ring_values[school_ring.value.lower()] = 3

    attack = 0
    parry = 0
    budget = combat_xp

    # --- Walk the progression ---
    for entry in progression:
        if entry in ring_values:
            current = ring_values[entry]
            max_val = 6 if (school_ring and entry == school_ring.value.lower()) else 5
            if current >= max_val:
                continue
            cost = ring_raise_cost(current + 1)
            if cost > budget:
                continue
            ring_values[entry] = current + 1
            budget -= cost

        elif entry == "attack":
            if attack >= 5:
                continue
            cost = advanced_skill_raise_cost(attack + 1)
            if cost > budget:
                continue
            attack += 1
            budget -= cost

        elif entry == "parry":
            if parry >= 5:
                continue
            if parry + 1 > attack + 1:
                continue
            cost = advanced_skill_raise_cost(parry + 1)
            if cost > budget:
                continue
            parry += 1
            budget -= cost

    # --- Build Character ---
    combat_spent = combat_xp - budget
    xp_spent = combat_spent + non_combat_xp

    rings = Rings(
        air=Ring(name=RingName.AIR, value=ring_values["air"]),
        fire=Ring(name=RingName.FIRE, value=ring_values["fire"]),
        earth=Ring(name=RingName.EARTH, value=ring_values["earth"]),
        water=Ring(name=RingName.WATER, value=ring_values["water"]),
        void=Ring(name=RingName.VOID, value=ring_values["void"]),
    )

    skills = [
        Skill(name="Attack", rank=attack, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=parry, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
    ]

    return Character(
        name=name,
        rings=rings,
        skills=skills,
        school_ring=school_ring,
        xp_total=total_xp,
        xp_spent=xp_spent,
    )
