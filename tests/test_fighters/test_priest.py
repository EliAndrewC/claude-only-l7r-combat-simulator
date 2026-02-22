"""Tests for PriestFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.priest import PriestFighter
from src.models.character import (
    Character,
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


def _make_priest(
    name: str = "Priest",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Priest character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    wl_rank = worldliness_rank if worldliness_rank is not None else knack_rank
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Priest",
        school_ring=RingName.WATER,
        school_knacks=["Conviction", "Otherworldliness", "Pontificate"],
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
                name="Precepts", rank=precepts_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Conviction", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.EARTH,
            ),
            Skill(
                name="Otherworldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.VOID,
            ),
            Skill(
                name="Pontificate", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Worldliness", rank=wl_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
        ],
    )


def _make_generic(name: str = "Generic", **kw: int) -> Character:
    """Create a generic character (opponent)."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = kw.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
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


def _make_state(
    priest_char: Character,
    opponent_char: Character,
    priest_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [priest_char.name, opponent_char.name],
        [priest_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    p_void = (
        priest_void if priest_void is not None
        else priest_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        priest_char.name, state,
        char=priest_char, weapon=KATANA, void_points=p_void,
    )
    create_fighter(
        opponent_char.name, state,
        char=opponent_char, weapon=KATANA,
        void_points=opponent_char.void_points_max,
    )
    return state


def _make_fighter(
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    void_points: int | None = None,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> PriestFighter:
    """Create a PriestFighter with a full CombatState."""
    char = _make_priest(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        precepts_rank=precepts_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, priest_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, PriestFighter)
    return fighter


class TestChooseAttack:
    """choose_attack always returns ('attack', 0)."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """No extra rolled die on attacks."""

    def test_attack_extra_rolled_is_zero(self) -> None:
        """No extra rolled die on attacks at any dan."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan)
            assert fighter.attack_extra_rolled() == 0


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_wound_check_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on wound check."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0

    def test_wound_check_extra_rolled_at_dan_5(self) -> None:
        """Higher dans still get +1."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.wound_check_extra_rolled() == 1


class TestWorldlinessVoid:
    """Worldliness void pool initialization."""

    def test_worldliness_void_initialized(self) -> None:
        """worldliness_void equals the Worldliness skill rank."""
        for rank in range(6):
            fighter = _make_fighter(knack_rank=rank)
            assert fighter.worldliness_void == rank

    def test_worldliness_void_custom_rank(self) -> None:
        """worldliness_void can differ from knack_rank."""
        fighter = _make_fighter(knack_rank=3, worldliness_rank=5)
        assert fighter.worldliness_void == 5


class TestFactoryRegistration:
    """Priest creates via fighter factory."""

    def test_creates_priest_fighter(self) -> None:
        """create_fighter returns PriestFighter for school='Priest'."""
        char = _make_priest()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, PriestFighter)
