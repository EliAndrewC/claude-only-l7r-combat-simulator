"""Skill check engine for L7R.

Handles TN rolls, open rolls, contested rolls, and void point spending.
"""

from __future__ import annotations

from src.engine.dice import roll_and_keep
from src.models.character import Character, RingName, SkillType


def skill_roll(
    character: Character,
    skill_name: str,
    ring: RingName,
    void_spend: int = 0,
) -> tuple[list[int], list[int], int]:
    """Perform a skill roll: (skill + ring)k(ring + void_spend).

    Rules:
    - Skill at 0: no exploding 10s.
    - Advanced skill at 0: subtract 10 from result.
    - Max void spend per roll = character's lowest ring.

    Args:
        character: The character making the roll.
        skill_name: Name of the skill being used.
        ring: Which ring to use for the roll.
        void_spend: Number of void points to spend (adds kept dice).

    Returns:
        Tuple of (all_dice, kept_dice, total).

    Raises:
        ValueError: If void_spend exceeds maximum.
    """
    max_void = character.rings.lowest()
    if void_spend > max_void:
        raise ValueError(f"Cannot spend {void_spend} void points (max {max_void})")

    skill = character.get_skill(skill_name)
    skill_rank = skill.rank if skill else 0
    skill_type = skill.skill_type if skill else SkillType.BASIC

    ring_value = character.rings.get(ring).value
    rolled = skill_rank + ring_value
    kept = ring_value + void_spend

    explode = skill_rank > 0

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=explode)

    if skill_rank == 0 and skill_type == SkillType.ADVANCED:
        total = max(0, total - 10)

    return all_dice, kept_dice, total


def tn_check(
    character: Character,
    skill_name: str,
    ring: RingName,
    tn: int,
    void_spend: int = 0,
) -> tuple[bool, int]:
    """Make a skill roll against a target number.

    Args:
        character: The character making the check.
        skill_name: Name of the skill.
        ring: Which ring to use.
        tn: Target number to meet or exceed.
        void_spend: Void points to spend.

    Returns:
        Tuple of (success, total).
    """
    _, _, total = skill_roll(character, skill_name, ring, void_spend)
    return total >= tn, total


def contested_roll(
    char_a: Character,
    skill_a: str,
    ring_a: RingName,
    char_b: Character,
    skill_b: str,
    ring_b: RingName,
    void_a: int = 0,
    void_b: int = 0,
) -> tuple[str, int, int]:
    """Resolve a contested roll between two characters.

    Args:
        char_a: First character.
        skill_a: First character's skill.
        ring_a: First character's ring.
        char_b: Second character.
        skill_b: Second character's skill.
        ring_b: Second character's ring.
        void_a: Void points spent by first character.
        void_b: Void points spent by second character.

    Returns:
        Tuple of (winner_name, total_a, total_b).
    """
    _, _, total_a = skill_roll(char_a, skill_a, ring_a, void_a)
    _, _, total_b = skill_roll(char_b, skill_b, ring_b, void_b)

    if total_a >= total_b:
        return char_a.name, total_a, total_b
    return char_b.name, total_a, total_b
