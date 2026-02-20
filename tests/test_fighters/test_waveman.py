"""Tests for WaveManFighter profession ability overrides."""

from __future__ import annotations

from unittest.mock import patch

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.generic import GenericFighter
from src.engine.fighters.waveman import WaveManFighter
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
SMALL_WEAPON = Weapon(
    name="Tanto", weapon_type=WeaponType.KATANA, rolled=2, kept=1,
)


def _make_waveman(
    name: str = "WM",
    abilities: list[tuple[int, int]] | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Wave Man character with specific abilities."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    pa = [ProfessionAbility(number=n, rank=r) for n, r in (abilities or [])]
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
        profession_abilities=pa,
    )


def _make_generic(name: str = "Opp", **kw: int) -> Character:
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
    wm_char: Character,
    opp_char: Character,
    wm_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [wm_char.name, opp_char.name],
        [wm_char.rings.earth.value, opp_char.rings.earth.value],
    )
    state = CombatState(log=log)
    create_fighter(
        wm_char.name, state,
        char=wm_char, weapon=KATANA,
        void_points=wm_void if wm_void is not None else wm_char.void_points_max,
    )
    create_fighter(
        opp_char.name, state,
        char=opp_char, weapon=KATANA,
        void_points=opp_char.void_points_max,
    )
    return state


def _make_fighter(
    abilities: list[tuple[int, int]] | None = None,
    weapon: Weapon | None = None,
    void_points: int | None = None,
    **ring_overrides: int,
) -> WaveManFighter:
    """Create a WaveManFighter with a full CombatState.

    If abilities is empty/None, returns a GenericFighter (which inherits
    no-op defaults from base Fighter — fine for rank-0 tests).
    """
    char = _make_waveman(abilities=abilities, **ring_overrides)
    opp = _make_generic()
    state = _make_state(char, opp, wm_void=void_points)
    return state.fighters[char.name]  # type: ignore[return-value]


# -- Factory dispatch --------------------------------------------------


class TestFactoryDispatch:
    """Verify create_fighter returns the correct subclass."""

    def test_waveman_with_abilities(self) -> None:
        """Character with profession_abilities gets WaveManFighter."""
        char = _make_waveman(abilities=[(1, 1)])
        opp = _make_generic()
        state = _make_state(char, opp)
        assert isinstance(state.fighters["WM"], WaveManFighter)

    def test_generic_without_abilities(self) -> None:
        """Character without profession_abilities gets GenericFighter."""
        char = _make_generic(name="G")
        log = create_combat_log(["G", "G2"], [2, 2])
        state = CombatState(log=log)
        create_fighter("G", state, char=char, weapon=KATANA)
        assert isinstance(state.fighters["G"], GenericFighter)


# -- Ability 1: Free raise on miss ------------------------------------


class TestPostAttackMissBonus:
    """Ability 1: add 5*rank on miss, parry auto-succeeds."""

    def test_rank0_no_bonus(self) -> None:
        f = _make_fighter(abilities=[])
        bonus, parry_auto, note = f.post_attack_miss_bonus(10, 15)
        assert bonus == 0
        assert parry_auto is False

    def test_rank1_miss_boosted(self) -> None:
        f = _make_fighter(abilities=[(1, 1)])
        bonus, parry_auto, note = f.post_attack_miss_bonus(12, 15)
        assert bonus == 5
        assert parry_auto is True
        assert "wave man" in note

    def test_rank2_miss_boosted(self) -> None:
        f = _make_fighter(abilities=[(1, 2)])
        bonus, parry_auto, note = f.post_attack_miss_bonus(6, 15)
        assert bonus == 10
        assert parry_auto is True

    def test_miss_not_enough_even_with_bonus(self) -> None:
        f = _make_fighter(abilities=[(1, 1)])
        bonus, parry_auto, note = f.post_attack_miss_bonus(5, 15)
        assert bonus == 0
        assert parry_auto is False


# -- Ability 2: Raise parry TN ----------------------------------------


class TestAttackerParryTnBonus:
    """Ability 2: flat bonus to parry TN."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        assert f.attacker_parry_tn_bonus() == 0

    def test_rank1(self) -> None:
        f = _make_fighter(abilities=[(2, 1)])
        assert f.attacker_parry_tn_bonus() == 5

    def test_rank2(self) -> None:
        f = _make_fighter(abilities=[(2, 2)])
        assert f.attacker_parry_tn_bonus() == 10


# -- Ability 3: Weapon damage boost ------------------------------------


class TestWeaponRolledBoost:
    """Ability 3: boost weapon rolled dice if weapon < 4k2."""

    def test_rank0_no_boost(self) -> None:
        f = _make_fighter(abilities=[])
        assert f.weapon_rolled_boost(2, 1) == 2

    def test_rank1_small_weapon(self) -> None:
        f = _make_fighter(abilities=[(3, 1)])
        assert f.weapon_rolled_boost(2, 1) == 3

    def test_rank2_small_weapon(self) -> None:
        f = _make_fighter(abilities=[(3, 2)])
        assert f.weapon_rolled_boost(2, 1) == 4

    def test_rank2_caps_at_4(self) -> None:
        f = _make_fighter(abilities=[(3, 2)])
        # 2 + 2 = 4, capped at 4
        assert f.weapon_rolled_boost(2, 1) == 4

    def test_already_4k2_no_boost(self) -> None:
        """Weapon already at 4k2: no boost applied."""
        f = _make_fighter(abilities=[(3, 1)])
        assert f.weapon_rolled_boost(4, 2) == 4

    def test_4k1_gets_boost(self) -> None:
        """4k1 weapon should get boosted (kept < 2)."""
        f = _make_fighter(abilities=[(3, 1)])
        assert f.weapon_rolled_boost(4, 1) == 4

    def test_3k2_gets_boost(self) -> None:
        """3k2 weapon should get boosted (rolled < 4)."""
        f = _make_fighter(abilities=[(3, 1)])
        assert f.weapon_rolled_boost(3, 2) == 4


# -- Ability 4: Damage rounding ----------------------------------------


class TestDamageRounding:
    """Ability 4: round up damage."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        total, note = f.damage_rounding(13)
        assert total == 13
        assert note == ""

    def test_rank1_rounds_up(self) -> None:
        f = _make_fighter(abilities=[(4, 1)])
        total, note = f.damage_rounding(13)
        assert total == 15
        assert "wave man" in note

    def test_rank1_divisible_by_5(self) -> None:
        f = _make_fighter(abilities=[(4, 1)])
        total, _ = f.damage_rounding(15)
        assert total == 18

    def test_rank2_rounds_twice(self) -> None:
        f = _make_fighter(abilities=[(4, 2)])
        # 13 → 15 (round up to 5), then 15 → 18 (+3 for divisible)
        total, _ = f.damage_rounding(13)
        assert total == 18


# -- Ability 5: Crippled reroll ----------------------------------------


class TestCrippledReroll:
    """Ability 5: free crippled reroll of 10s."""

    def test_rank0_no_reroll(self) -> None:
        f = _make_fighter(abilities=[])
        all_d, kept, total, note = f.crippled_reroll([10, 7, 3], 2)
        assert all_d == [10, 7, 3]
        assert kept == [10, 7]
        assert total == 17
        assert note == ""

    def test_rank1_rerolls_one_ten(self) -> None:
        f = _make_fighter(abilities=[(5, 1)])
        with patch("src.engine.fighters.waveman.reroll_tens") as mock:
            mock.return_value = ([15, 7, 3], [15, 7], 22)
            all_d, kept, total, note = f.crippled_reroll([10, 7, 3], 2)
            mock.assert_called_once()
            args, kwargs = mock.call_args
            assert kwargs.get("max_reroll") == 1 or args[2] == 1
            assert total == 22
            assert "crippled reroll" in note

    def test_rank2_rerolls_two_tens(self) -> None:
        f = _make_fighter(abilities=[(5, 2)])
        with patch("src.engine.fighters.waveman.reroll_tens") as mock:
            mock.return_value = ([15, 12, 3], [15, 12], 27)
            all_d, kept, total, note = f.crippled_reroll([10, 10, 3], 2)
            args, kwargs = mock.call_args
            assert kwargs.get("max_reroll") == 2 or args[2] == 2
            assert "tens" in note

    def test_no_tens_no_reroll(self) -> None:
        f = _make_fighter(abilities=[(5, 1)])
        all_d, kept, total, note = f.crippled_reroll([9, 7, 3], 2)
        assert note == ""
        assert total == 16


# -- Ability 6: Initiative boost ---------------------------------------


class TestInitiativeExtraUnkept:
    """Ability 6: extra unkept dice on initiative."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        assert f.initiative_extra_unkept() == 0

    def test_rank1(self) -> None:
        f = _make_fighter(abilities=[(6, 1)])
        assert f.initiative_extra_unkept() == 1

    def test_rank2(self) -> None:
        f = _make_fighter(abilities=[(6, 2)])
        assert f.initiative_extra_unkept() == 2


# -- Ability 7: Wound check bonus --------------------------------------


class TestWoundCheckExtraRolled:
    """Ability 7: extra rolled dice on wound check."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        assert f.wound_check_extra_rolled() == 0

    def test_rank1(self) -> None:
        f = _make_fighter(abilities=[(7, 1)])
        assert f.wound_check_extra_rolled() == 2

    def test_rank2(self) -> None:
        f = _make_fighter(abilities=[(7, 2)])
        assert f.wound_check_extra_rolled() == 4


# -- Ability 8: Damage reduction ---------------------------------------


class TestDamageReduction:
    """Ability 8: reduce incoming damage when attacker had extra dice."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        total, note = f.damage_reduction(20, True)
        assert total == 20
        assert note == ""

    def test_rank1_with_extra_dice(self) -> None:
        f = _make_fighter(abilities=[(8, 1)])
        total, note = f.damage_reduction(20, True)
        assert total == 15
        assert "wave man" in note

    def test_rank2_with_extra_dice(self) -> None:
        f = _make_fighter(abilities=[(8, 2)])
        total, note = f.damage_reduction(20, True)
        assert total == 10

    def test_no_extra_dice_no_reduction(self) -> None:
        f = _make_fighter(abilities=[(8, 1)])
        total, note = f.damage_reduction(20, False)
        assert total == 20
        assert note == ""

    def test_reduction_floors_at_zero(self) -> None:
        f = _make_fighter(abilities=[(8, 2)])
        total, note = f.damage_reduction(3, True)
        assert total == 0


# -- Ability 9: Failed parry bonus -------------------------------------


class TestFailedParryDiceRecovery:
    """Ability 9: recover some extra dice after failed parry."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        assert f.failed_parry_dice_recovery(3, 2) == 0

    def test_rank1_recovers_up_to_2(self) -> None:
        f = _make_fighter(abilities=[(9, 1)])
        assert f.failed_parry_dice_recovery(3, 2) == 2

    def test_rank1_limited_by_removed(self) -> None:
        f = _make_fighter(abilities=[(9, 1)])
        # Only 1 die was removed (min(3, 1) = 1), recovery capped at 1
        assert f.failed_parry_dice_recovery(3, 1) == 1

    def test_rank2_recovers_up_to_4(self) -> None:
        f = _make_fighter(abilities=[(9, 2)])
        assert f.failed_parry_dice_recovery(5, 4) == 4


# -- Ability 10: Raise wound TN ----------------------------------------


class TestWoundCheckTnBonus:
    """Ability 10: flat bonus to wound check TN."""

    def test_rank0(self) -> None:
        f = _make_fighter(abilities=[])
        assert f.wound_check_tn_bonus() == 0

    def test_rank1(self) -> None:
        f = _make_fighter(abilities=[(10, 1)])
        assert f.wound_check_tn_bonus() == 5

    def test_rank2(self) -> None:
        f = _make_fighter(abilities=[(10, 2)])
        assert f.wound_check_tn_bonus() == 10
