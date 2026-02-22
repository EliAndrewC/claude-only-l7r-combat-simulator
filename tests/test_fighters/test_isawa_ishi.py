"""Tests for IsawaIshiFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.isawa_ishi import IsawaIshiFighter
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


def _make_isawa_ishi(
    name: str = "Isawa Ishi",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create an Isawa Ishi character."""
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
        school="Isawa Ishi",
        school_ring=RingName.VOID,
        school_knacks=["Absorb Void", "Kharmic Spin", "Otherworldliness"],
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
                name="Absorb Void", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.VOID,
            ),
            Skill(
                name="Kharmic Spin", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.VOID,
            ),
            Skill(
                name="Otherworldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.VOID,
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
    ishi_char: Character,
    opponent_char: Character,
    ishi_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [ishi_char.name, opponent_char.name],
        [ishi_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    i_void = (
        ishi_void if ishi_void is not None
        else ishi_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        ishi_char.name, state,
        char=ishi_char, weapon=KATANA, void_points=i_void,
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
) -> IsawaIshiFighter:
    """Create an IsawaIshiFighter with a full CombatState."""
    char = _make_isawa_ishi(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        precepts_rank=precepts_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, ishi_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, IsawaIshiFighter)
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
    """No extra rolled die on wound checks."""

    def test_wound_check_extra_rolled_is_zero(self) -> None:
        """No extra rolled die on wound checks at any dan."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan)
            assert fighter.wound_check_extra_rolled() == 0


class TestIshiMaxVoid:
    """SA: Max void = highest ring + dan."""

    def test_ishi_max_void_default_rings(self) -> None:
        """Max void = highest ring (2) + dan (1) = 3."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter._ishi_max_void == 3

    def test_ishi_max_void_with_high_ring(self) -> None:
        """Max void uses highest ring value."""
        fighter = _make_fighter(knack_rank=2, fire=4)
        # highest ring = 4, dan = 2
        assert fighter._ishi_max_void == 6

    def test_ishi_max_void_increases_with_dan(self) -> None:
        """Max void increases with dan."""
        fighter_d1 = _make_fighter(knack_rank=1)
        fighter_d3 = _make_fighter(knack_rank=3)
        assert fighter_d3._ishi_max_void > fighter_d1._ishi_max_void


class TestMaxVoidPerRoll:
    """SA: Max void per roll = lowest ring - 1."""

    def test_max_void_per_roll_default(self) -> None:
        """Max void per roll = lowest ring (2) - 1 = 1."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter._max_void_per_roll == 1

    def test_max_void_per_roll_with_high_lowest(self) -> None:
        """Max void per roll when all rings are 3."""
        fighter = _make_fighter(
            knack_rank=1, air=3, fire=3, earth=3, water=3, void=3,
        )
        assert fighter._max_void_per_roll == 2

    def test_max_void_per_roll_min_zero(self) -> None:
        """Max void per roll can't go below 0."""
        # Default rings are all 2, so lowest=2, result=1
        # With ring=1, result=0
        fighter = _make_fighter(knack_rank=1, air=1)
        assert fighter._max_void_per_roll == 0


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
    """Isawa Ishi creates via fighter factory."""

    def test_creates_isawa_ishi_fighter(self) -> None:
        """create_fighter returns IsawaIshiFighter for school='Isawa Ishi'."""
        char = _make_isawa_ishi()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, IsawaIshiFighter)
