"""Mirumoto Bushi school builder.

Builds Mirumoto Bushi characters from earned XP. School ring is Void
(starts at 3, max 6), other rings start at 2. School knacks
(Counterattack, Double Attack, Iaijutsu) start at rank 1 for free.
Fourth Dan grants a free Void +1 when all knacks reach 4.
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

MIRUMOTO_KNACK_NAMES: list[str] = ["counterattack", "double_attack", "iaijutsu"]

# Each entry raises that stat by 1. Knack entries raise the named knack.
# Ring priority: Void > Air > Water > Earth > Fire
MIRUMOTO_COMBAT_PROGRESSION: list[str] = [
    # Skills/knacks to 3 (before non-Void rings reach 3)
    "parry",
    "attack", "parry",
    "counterattack", "double_attack", "iaijutsu",  # 1→2
    "attack", "parry",
    "counterattack", "double_attack", "iaijutsu",  # 2→3

    # Rings first raise (Void 3→4, Air 2→3, Water 2→3, Earth 2→3, Fire 2→3)
    "void", "air", "water", "earth", "fire",

    # Skills/knacks to 4 (before non-Void rings reach 4)
    "attack", "parry",
    "counterattack", "double_attack", "iaijutsu",  # 3→4

    # Rings second raise (Void 4→5, Air 3→4, etc.)
    "void", "air", "water", "earth", "fire",

    # Skills/knacks to 5 (before non-Void rings reach 5)
    "attack", "parry",
    "counterattack", "double_attack", "iaijutsu",  # 4→5

    # Rings third raise (Void 5→6, Air 4→5, etc.)
    "void", "air", "water", "earth", "fire",

    # Attack catch up
    "attack",
]


def compute_mirumoto_stats_from_xp(
    earned_xp: int = 0,
    non_combat_pct: float = 0.20,
) -> ComputedStats:
    """Compute ring values, skill ranks, and knack ranks for a Mirumoto Bushi.

    School ring = Void (starts at 3, max 6); other rings start at 2, max 5.
    School knacks start at 1. Fourth Dan grants a free Void +1.

    Args:
        earned_xp: XP earned beyond the base 150.
        non_combat_pct: Fraction of total XP lost to non-combat skills.

    Returns:
        A ComputedStats with ring_values, attack, parry, and knack_ranks.
    """
    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))

    ring_values: dict[str, int] = {
        "air": 2, "fire": 2, "earth": 2, "water": 2, "void": 3,
    }

    attack = 0
    parry = 0
    knack_ranks: dict[str, int] = {k: 1 for k in MIRUMOTO_KNACK_NAMES}
    budget = combat_xp

    # Track 4th Dan void boost
    void_boosted = False
    void_cost_discount = 0

    def _check_4th_dan() -> None:
        nonlocal void_boosted, void_cost_discount
        if void_boosted:
            return
        if all(knack_ranks[k] >= 4 for k in MIRUMOTO_KNACK_NAMES):
            ring_values["void"] = min(ring_values["void"] + 1, 6)
            void_boosted = True
            void_cost_discount = 5

    for entry in MIRUMOTO_COMBAT_PROGRESSION:
        if entry in ring_values:
            current = ring_values[entry]
            max_val = 6 if entry == "void" else 5
            if current >= max_val:
                continue
            cost = ring_raise_cost(current + 1)
            if entry == "void" and void_cost_discount > 0:
                cost = max(0, cost - void_cost_discount)
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


def build_mirumoto_from_xp(
    name: str = "Mirumoto",
    earned_xp: int = 0,
    non_combat_pct: float = 0.20,
) -> Character:
    """Build a Mirumoto Bushi character by spending XP.

    Args:
        name: Character name.
        earned_xp: XP earned beyond the base 150.
        non_combat_pct: Fraction of total XP lost to non-combat skills.

    Returns:
        A fully constructed Character.
    """
    stats = compute_mirumoto_stats_from_xp(
        earned_xp=earned_xp,
        non_combat_pct=non_combat_pct,
    )

    total_xp = 150 + earned_xp
    combat_xp = int(total_xp * (1 - non_combat_pct))
    non_combat_xp = total_xp - combat_xp

    # Compute combat_spent from stats
    base_rings: dict[str, int] = {
        "air": 2, "fire": 2, "earth": 2, "water": 2, "void": 3,
    }

    # Account for 4th Dan void boost: if all knacks >= 4, one Void raise was free
    all_knacks_4 = all(stats.knack_ranks[k] >= 4 for k in MIRUMOTO_KNACK_NAMES)
    void_boost_raises = 1 if all_knacks_4 else 0

    ring_cost = 0
    for r in stats.ring_values:
        for v in range(base_rings[r] + 1, stats.ring_values[r] + 1):
            ring_cost += ring_raise_cost(v)
    # Subtract the cost of the free Void raise (4th Dan boost)
    if void_boost_raises > 0 and stats.ring_values["void"] > base_rings["void"]:
        # The free raise was applied, so discount the cost of the highest Void raise paid
        # Actually: the boost added +1 for free, and then future raises got -5 discount
        # Simpler: subtract 1 raise worth from paid Void raises
        # The free raise value = one raise above what Void was before boosting
        # We need to figure out paid vs free. Let's just subtract one full raise cost.
        # The free raise went from X to X+1 for free. But we don't know X easily.
        # Instead, subtract the discount: each Void raise after boost cost 5 less.
        # Count Void raises after the boost in the progression.
        # Simpler approach: recompute cost by replaying.
        pass

    # Recompute cost by replaying the progression (most accurate)
    ring_cost = 0
    knack_cost = 0
    _rv: dict[str, int] = {k: v for k, v in base_rings.items()}
    _atk = 0
    _par = 0
    _kr: dict[str, int] = {k: 1 for k in MIRUMOTO_KNACK_NAMES}
    _budget = combat_xp
    _vb = False
    _vd = 0

    for entry in MIRUMOTO_COMBAT_PROGRESSION:
        if entry in _rv:
            current = _rv[entry]
            max_val = 6 if entry == "void" else 5
            if current >= max_val:
                continue
            cost = ring_raise_cost(current + 1)
            if entry == "void" and _vd > 0:
                cost = max(0, cost - _vd)
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

        if not _vb and all(_kr[k] >= 4 for k in MIRUMOTO_KNACK_NAMES):
            _rv["void"] = min(_rv["void"] + 1, 6)
            _vb = True
            _vd = 5

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
        "counterattack": "Counterattack",
        "double_attack": "Double Attack",
        "iaijutsu": "Iaijutsu",
    }

    skills = [
        Skill(name="Attack", rank=stats.attack, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=stats.parry, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
    ]
    for knack_key, display_name in knack_display_names.items():
        skills.append(
            Skill(
                name=display_name,
                rank=stats.knack_ranks[knack_key],
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            )
        )

    return Character(
        name=name,
        rings=rings,
        skills=skills,
        school="Mirumoto Bushi",
        school_ring=RingName.VOID,
        school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
        xp_total=total_xp,
        xp_spent=xp_spent,
    )
