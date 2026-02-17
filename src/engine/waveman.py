"""Wave Man profession builder.

Builds non-samurai Wave Man characters from earned XP. Rings start at 1
(not 2), no school ring, attack/parry start at 0. Gains profession
abilities based on earned XP.
"""

from __future__ import annotations

from src.engine.xp_builder import (
    ComputedStats,
    advanced_skill_raise_cost,
    ring_raise_cost,
)
from src.models.character import (
    Character,
    ProfessionAbility,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)

# Short display names for each Wave Man ability (keyed by ability number).
WAVE_MAN_ABILITY_NAMES: dict[int, str] = {
    1: "free raise on miss",
    2: "raise parry TN",
    3: "weapon damage boost",
    4: "round up damage",
    5: "crippled reroll",
    6: "initiative boost",
    7: "wound check bonus",
    8: "damage reduction",
    9: "failed parry bonus",
    10: "raise wound TN",
}

# Order in which abilities are granted: first pass rank 1, second pass rank 2.
WAVE_MAN_ABILITY_ORDER: list[int] = [1, 4, 7, 5, 6, 10, 8, 9, 2, 3]

# Combat progression for Wave Man: starts from ring values of 1.
# Same parry-first philosophy as the samurai default progression.
WAVE_MAN_COMBAT_PROGRESSION: list[str] = [
    # Skills to 3 (parry prioritised, attack enables each raise)
    "parry",
    "attack", "parry",
    "attack", "parry",
    # Skills to 4 (before any ring reaches 4)
    "attack", "parry",
    # Rings first raise (1→2)
    "void", "water", "earth", "fire", "air",
    # Skills to 5 (before any ring reaches 5)
    "attack", "parry",
    # Rings second raise (2→3)
    "void", "water", "earth", "fire", "air",
    # Rings third raise (3→4)
    "void", "water", "earth", "fire", "air",
    # Rings fourth raise (4→5)
    "void", "water", "earth", "fire", "air",
    # Attack to 5 (catch up with parry)
    "attack",
]


def compute_abilities(earned_xp: int) -> list[ProfessionAbility]:
    """Compute profession abilities from earned XP.

    Count = 1 + earned_xp // 15. Walk ABILITY_ORDER once for rank 1,
    then again for rank 2.

    Args:
        earned_xp: XP earned beyond the base 150.

    Returns:
        List of ProfessionAbility objects.
    """
    count = 1 + earned_xp // 15
    abilities: dict[int, int] = {}  # number -> rank

    granted = 0
    # First pass: rank 1
    for num in WAVE_MAN_ABILITY_ORDER:
        if granted >= count:
            break
        abilities[num] = 1
        granted += 1

    # Second pass: rank 2
    for num in WAVE_MAN_ABILITY_ORDER:
        if granted >= count:
            break
        if num in abilities and abilities[num] == 1:
            abilities[num] = 2
            granted += 1

    return [
        ProfessionAbility(number=num, rank=rank)
        for num, rank in sorted(abilities.items())
    ]


def compute_waveman_stats_from_xp(
    earned_xp: int = 0,
    non_combat_pct: float = 0.20,
) -> ComputedStats:
    """Compute raw ring values and skill ranks for a Wave Man from XP.

    Rings start at 1 (not 2), no school ring. Uses
    ``WAVE_MAN_COMBAT_PROGRESSION`` for stat advancement.

    Args:
        earned_xp: XP earned beyond the base 150.
        non_combat_pct: Fraction of total XP lost to non-combat skills.

    Returns:
        A ``ComputedStats`` with ring_values, attack, and parry.
    """
    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))

    ring_values: dict[str, int] = {
        "air": 1, "fire": 1, "earth": 1, "water": 1, "void": 1,
    }

    attack = 0
    parry = 0
    budget = combat_xp

    for entry in WAVE_MAN_COMBAT_PROGRESSION:
        if entry in ring_values:
            current = ring_values[entry]
            max_val = 5
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

    return ComputedStats(ring_values=ring_values, attack=attack, parry=parry)


def build_waveman_from_xp(
    name: str = "Wave Man",
    earned_xp: int = 0,
    non_combat_pct: float = 0.20,
) -> Character:
    """Build a Wave Man character by spending XP.

    Rings start at 1 (not 2), no school ring, attack/parry start at 0.
    Uses WAVE_MAN_COMBAT_PROGRESSION for stat advancement.

    Args:
        name: Character name.
        earned_xp: XP earned beyond the base 150.
        non_combat_pct: Fraction of total XP lost to non-combat skills.

    Returns:
        A fully constructed Character with profession abilities.
    """
    stats = compute_waveman_stats_from_xp(
        earned_xp=earned_xp,
        non_combat_pct=non_combat_pct,
    )

    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))
    non_combat_xp = total_xp - combat_xp

    # Compute combat_spent from stats
    base_rings: dict[str, int] = {
        "air": 1, "fire": 1, "earth": 1, "water": 1, "void": 1,
    }
    ring_cost = sum(
        sum(ring_raise_cost(v) for v in range(base_rings[r] + 1, stats.ring_values[r] + 1))
        for r in stats.ring_values
    )
    skill_cost = sum(
        advanced_skill_raise_cost(v) for v in range(1, stats.attack + 1)
    ) + sum(
        advanced_skill_raise_cost(v) for v in range(1, stats.parry + 1)
    )
    combat_spent = ring_cost + skill_cost
    xp_spent = combat_spent + non_combat_xp

    rings = Rings(
        air=Ring(name=RingName.AIR, value=stats.ring_values["air"]),
        fire=Ring(name=RingName.FIRE, value=stats.ring_values["fire"]),
        earth=Ring(name=RingName.EARTH, value=stats.ring_values["earth"]),
        water=Ring(name=RingName.WATER, value=stats.ring_values["water"]),
        void=Ring(name=RingName.VOID, value=stats.ring_values["void"]),
    )

    skills = [
        Skill(name="Attack", rank=stats.attack, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=stats.parry, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
    ]

    abilities = compute_abilities(earned_xp)

    return Character(
        name=name,
        rings=rings,
        skills=skills,
        school_ring=None,
        xp_total=total_xp,
        xp_spent=xp_spent,
        profession_abilities=abilities,
    )
