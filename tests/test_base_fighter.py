"""Tests for base Fighter class (default / Wave Man behavior)."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.base import Fighter
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


def _make_generic(
    name: str = "Generic",
    parry_rank: int = 2,
    **ring_overrides: int,
) -> Character:
    """Create a generic (Wave Man) character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
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
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
        ],
    )


def _make_state(
    char1: Character,
    char2: Character,
    void1: int | None = None,
    void2: int | None = None,
) -> CombatState:
    """Build a CombatState with two characters."""
    log = create_combat_log(
        [char1.name, char2.name],
        [char1.rings.earth.value, char2.rings.earth.value],
    )
    v1 = void1 if void1 is not None else char1.void_points_max
    v2 = void2 if void2 is not None else char2.void_points_max
    state = CombatState(log=log)
    create_fighter(
        char1.name, state,
        char=char1, weapon=KATANA, void_points=v1,
    )
    create_fighter(
        char2.name, state,
        char=char2, weapon=KATANA, void_points=v2,
    )
    return state


def _make_fighter(
    name: str = "Generic",
    parry_rank: int = 2,
    void_points: int | None = None,
    **ring_overrides: int,
) -> Fighter:
    """Create a base Fighter with a full CombatState."""
    char = _make_generic(
        name=name, parry_rank=parry_rank, **ring_overrides,
    )
    opp = _make_generic(name="Opponent")
    state = _make_state(char, opp, void1=void_points)
    return state.fighters[name]


class TestConsumeAttackDieWithValue:
    """consume_attack_die with specific die_value parameter."""

    def test_consumes_specified_die(self) -> None:
        """When die_value is in actions_remaining, consume it."""
        fighter = _make_fighter()
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.consume_attack_die(3, die_value=5)
        assert result == 5
        assert 5 not in fighter.actions_remaining
        assert fighter.actions_remaining == [3, 7]

    def test_returns_none_when_die_value_not_present(self) -> None:
        """When die_value is NOT in actions_remaining, return None."""
        fighter = _make_fighter()
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.consume_attack_die(3, die_value=9)
        assert result is None
        assert fighter.actions_remaining == [3, 5, 7]


class TestNearMissDaDescription:
    """near_miss_da_description returns empty string (base class)."""

    def test_returns_empty(self) -> None:
        fighter = _make_fighter()
        assert fighter.near_miss_da_description() == ""


class TestSelectParryDieNone:
    """select_parry_die returns None when phase not in actions."""

    def test_returns_phase_when_present(self) -> None:
        fighter = _make_fighter()
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.select_parry_die(5)
        assert result == 5

    def test_returns_none_when_phase_not_present(self) -> None:
        fighter = _make_fighter()
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.select_parry_die(4)
        assert result is None


class TestShouldPredeclareParryZeroRank:
    """should_predeclare_parry returns False when parry_rank <= 0."""

    def test_zero_parry_rank_returns_false(self) -> None:
        fighter = _make_fighter(parry_rank=0)
        result = fighter.should_predeclare_parry(15, 5)
        assert result is False


class TestParryBonusDescription:
    """parry_bonus_description returns generic format string."""

    def test_generic_format(self) -> None:
        fighter = _make_fighter()
        desc = fighter.parry_bonus_description(5)
        assert desc == " (free raise +5)"

    def test_generic_format_other_value(self) -> None:
        fighter = _make_fighter()
        desc = fighter.parry_bonus_description(10)
        assert desc == " (free raise +10)"
