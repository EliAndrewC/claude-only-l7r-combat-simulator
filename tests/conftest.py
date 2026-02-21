"""Shared test fixtures and helpers for the combat simulation tests."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.models.character import (
    Character,
    ProfessionAbility,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.weapon import Weapon, WeaponType

KATANA = Weapon(
    name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2,
)


def _rings(**overrides: int) -> dict[str, Ring]:
    """Build ring kwargs from optional overrides (default 2)."""
    return {
        rn: Ring(name=RingName(rn.capitalize()), value=overrides.get(rn, 2))
        for rn in ["air", "fire", "earth", "water", "void"]
    }


def make_character(name: str, **ring_overrides: int) -> Character:
    """Create a generic character with Attack 3, Parry 2."""
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
        ],
    )


def make_waveman(
    name: str,
    abilities: list[tuple[int, int]] | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Wave Man character with specific abilities."""
    pa = [
        ProfessionAbility(number=n, rank=r)
        for n, r in (abilities or [])
    ]
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
        ],
        profession_abilities=pa,
    )


def make_mirumoto(
    name: str = "Mirumoto",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Mirumoto Bushi character."""
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Mirumoto Bushi",
        school_ring=RingName.VOID,
        school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Counterattack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Double Attack", rank=da_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def make_matsu(
    name: str = "Matsu",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Matsu Bushi character."""
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    lng_rank = (
        lunge_rank if lunge_rank is not None else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Matsu Bushi",
        school_ring=RingName.FIRE,
        school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Double Attack", rank=da_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Lunge", rank=lng_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def make_kakita(
    name: str = "Kakita",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Kakita Duelist character."""
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    lng_rank = (
        lunge_rank if lunge_rank is not None else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Kakita Duelist",
        school_ring=RingName.FIRE,
        school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Double Attack", rank=da_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Lunge", rank=lng_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def make_shinjo(
    name: str = "Shinjo",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Shinjo Bushi character."""
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Shinjo Bushi",
        school_ring=RingName.WATER,
        school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Double Attack", rank=da_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Lunge", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def make_courtier(
    name: str = "Courtier",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    tact_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    """Create a Courtier school character."""
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Courtier",
        school_ring=RingName.AIR,
        school_knacks=["Discern Honor", "Oppose Social", "Worldliness"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Tact", rank=tact_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Oppose Social", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Worldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
        ],
    )


def make_combat_state(
    char_a: Character,
    char_b: Character,
    void_a: int | None = None,
    void_b: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters as Fighter instances."""
    log = create_combat_log(
        [char_a.name, char_b.name],
        [char_a.rings.earth.value, char_b.rings.earth.value],
    )
    state = CombatState(log=log)
    create_fighter(
        char_a.name, state,
        char=char_a, weapon=KATANA,
        void_points=(
            void_a if void_a is not None
            else char_a.void_points_max
        ),
    )
    create_fighter(
        char_b.name, state,
        char=char_b, weapon=KATANA,
        void_points=(
            void_b if void_b is not None
            else char_b.void_points_max
        ),
    )
    return state
