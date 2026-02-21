"""Courtier school builder.

Builds Courtier characters from earned XP. School ring is Air
(starts at 3, max 6), other rings start at 2. School knacks
(Discern Honor, Oppose Social, Worldliness) start at rank 1 for free.
Tact is hardcoded at rank 5 (cost absorbed by non-combat %).
Fourth Dan grants a free Air +1 when all knacks reach 4.
"""

from __future__ import annotations

from src.engine.character_builders.xp_builder import (
    ComputedStats,
    advanced_skill_raise_cost,
    ring_raise_cost,
)
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)

COURTIER_KNACK_NAMES: list[str] = [
    "discern_honor", "oppose_social", "worldliness",
]

# Each entry raises that stat by 1. Knack entries raise the named knack.
# Ring priority: Air > Void > Water > Earth > Fire
COURTIER_COMBAT_PROGRESSION: list[str] = [
    "parry",
    "attack", "parry",
    "discern_honor", "oppose_social", "worldliness",  # 1->2
    "attack", "parry",
    "discern_honor", "oppose_social", "worldliness",  # 2->3
    "air", "void", "water", "earth", "fire",
    "attack", "parry",
    "discern_honor", "oppose_social", "worldliness",  # 3->4
    "air", "void", "water", "earth", "fire",
    "attack", "parry",
    "discern_honor", "oppose_social", "worldliness",  # 4->5
    "air", "void", "water", "earth", "fire",
    "attack",
]


def compute_courtier_stats_from_xp(
    earned_xp: int = 0,
    non_combat_pct: float = 0.20,
) -> ComputedStats:
    """Compute ring values, skill ranks, and knack ranks for a Courtier.

    School ring = Air (starts at 3, max 6); other rings start at 2, max 5.
    School knacks start at 1. Fourth Dan grants a free Air +1.
    Tact is hardcoded at rank 5 (cost absorbed by non-combat %).

    Args:
        earned_xp: XP earned beyond the base 150.
        non_combat_pct: Fraction of total XP lost to non-combat skills.

    Returns:
        A ComputedStats with ring_values, attack, parry, and knack_ranks.
    """
    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))

    ring_values: dict[str, int] = {
        "air": 3, "fire": 2, "earth": 2, "water": 2, "void": 2,
    }

    attack = 0
    parry = 0
    knack_ranks: dict[str, int] = {k: 1 for k in COURTIER_KNACK_NAMES}
    budget = combat_xp

    # Track 4th Dan air boost
    air_boosted = False
    air_cost_discount = 0

    def _check_4th_dan() -> None:
        nonlocal air_boosted, air_cost_discount
        if air_boosted:
            return
        if all(knack_ranks[k] >= 4 for k in COURTIER_KNACK_NAMES):
            ring_values["air"] = min(ring_values["air"] + 1, 6)
            air_boosted = True
            air_cost_discount = 5

    for entry in COURTIER_COMBAT_PROGRESSION:
        if entry in ring_values:
            current = ring_values[entry]
            max_val = 6 if entry == "air" else 5
            if current >= max_val:
                continue
            cost = ring_raise_cost(current + 1)
            if entry == "air" and air_cost_discount > 0:
                cost = max(0, cost - air_cost_discount)
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

        elif entry in knack_ranks:
            current_rank = knack_ranks[entry]
            if current_rank >= 5:
                continue
            cost = advanced_skill_raise_cost(current_rank + 1)
            if cost > budget:
                continue
            knack_ranks[entry] = current_rank + 1
            budget -= cost

        _check_4th_dan()

    return ComputedStats(
        ring_values=ring_values,
        attack=attack,
        parry=parry,
        knack_ranks=knack_ranks,
    )


def build_courtier_from_xp(
    name: str = "Courtier",
    earned_xp: int = 0,
    non_combat_pct: float = 0.20,
) -> Character:
    """Build a Courtier character by spending XP.

    Args:
        name: Character name.
        earned_xp: XP earned beyond the base 150.
        non_combat_pct: Fraction of total XP lost to non-combat skills.

    Returns:
        A fully constructed Character.
    """
    stats = compute_courtier_stats_from_xp(
        earned_xp=earned_xp,
        non_combat_pct=non_combat_pct,
    )

    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))
    non_combat_xp = total_xp - combat_xp

    base_rings: dict[str, int] = {
        "air": 3, "fire": 2, "earth": 2, "water": 2, "void": 2,
    }

    # Recompute cost by replaying the progression (most accurate)
    ring_cost = 0
    knack_cost = 0
    _rv: dict[str, int] = {k: v for k, v in base_rings.items()}
    _atk = 0
    _par = 0
    _kr: dict[str, int] = {k: 1 for k in COURTIER_KNACK_NAMES}
    _budget = combat_xp
    _fb = False
    _fd = 0

    for entry in COURTIER_COMBAT_PROGRESSION:
        if entry in _rv:
            current = _rv[entry]
            max_val = 6 if entry == "air" else 5
            if current >= max_val:
                continue
            cost = ring_raise_cost(current + 1)
            if entry == "air" and _fd > 0:
                cost = max(0, cost - _fd)
            if cost > _budget:
                continue
            _rv[entry] = current + 1
            _budget -= cost
            ring_cost += cost

        elif entry == "attack":
            if _atk >= 5:
                continue
            cost = advanced_skill_raise_cost(_atk + 1)
            if cost > _budget:
                continue
            _atk += 1
            _budget -= cost

        elif entry == "parry":
            if _par >= 5:
                continue
            if _par + 1 > _atk + 1:
                continue
            cost = advanced_skill_raise_cost(_par + 1)
            if cost > _budget:
                continue
            _par += 1
            _budget -= cost

        elif entry in _kr:
            cr = _kr[entry]
            if cr >= 5:
                continue
            cost = advanced_skill_raise_cost(cr + 1)
            if cost > _budget:
                continue
            _kr[entry] = cr + 1
            _budget -= cost
            knack_cost += cost

        if not _fb and all(_kr[k] >= 4 for k in COURTIER_KNACK_NAMES):
            _rv["air"] = min(_rv["air"] + 1, 6)
            _fb = True
            _fd = 5

    skill_cost = sum(
        advanced_skill_raise_cost(v) for v in range(1, stats.attack + 1)
    ) + sum(
        advanced_skill_raise_cost(v) for v in range(1, stats.parry + 1)
    )
    combat_spent = ring_cost + skill_cost + knack_cost
    xp_spent = combat_spent + non_combat_xp

    rings = Rings(
        air=Ring(name=RingName.AIR, value=stats.ring_values["air"]),
        fire=Ring(name=RingName.FIRE, value=stats.ring_values["fire"]),
        earth=Ring(name=RingName.EARTH, value=stats.ring_values["earth"]),
        water=Ring(name=RingName.WATER, value=stats.ring_values["water"]),
        void=Ring(name=RingName.VOID, value=stats.ring_values["void"]),
    )

    knack_display_names: dict[str, str] = {
        "discern_honor": "Discern Honor",
        "oppose_social": "Oppose Social",
        "worldliness": "Worldliness",
    }

    skills: list[Skill] = [
        Skill(name="Attack", rank=stats.attack, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=stats.parry, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        Skill(name="Tact", rank=5, skill_type=SkillType.BASIC, ring=RingName.AIR),
    ]
    for knack_key, display_name in knack_display_names.items():
        skills.append(
            Skill(
                name=display_name,
                rank=stats.knack_ranks[knack_key],
                skill_type=SkillType.BASIC,
                ring=RingName.AIR,
            )
        )

    return Character(
        name=name,
        rings=rings,
        skills=skills,
        school="Courtier",
        school_ring=RingName.AIR,
        school_knacks=["Discern Honor", "Oppose Social", "Worldliness"],
        xp_total=total_xp,
        xp_spent=xp_spent,
    )
