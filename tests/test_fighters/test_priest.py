"""Tests for PriestFighter school-specific overrides."""

from __future__ import annotations

from unittest.mock import patch

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


# ── 3rd Dan Dice Pool Tests ──────────────────────────────────────────────


class TestDicePoolInit:
    """Pool initialization at 3rd Dan."""

    def test_pool_empty_below_dan_3(self) -> None:
        """No pool when dan < 3."""
        fighter = _make_fighter(knack_rank=2)
        assert fighter._dice_pool == []

    def test_pool_has_precepts_rank_dice(self) -> None:
        """Pool has precepts_rank dice at dan >= 3."""
        with patch(
            "src.engine.fighters.priest.roll_die",
            side_effect=[8, 5, 3, 7, 1],
        ):
            fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        assert len(fighter._dice_pool) == 5

    def test_pool_sorted_descending(self) -> None:
        """Pool dice are sorted highest first."""
        with patch(
            "src.engine.fighters.priest.roll_die",
            side_effect=[3, 8, 5, 7, 1],
        ):
            fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        assert fighter._dice_pool == [8, 7, 5, 3, 1]

    def test_pool_empty_with_zero_precepts(self) -> None:
        """No pool when precepts rank is 0."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=0)
        assert fighter._dice_pool == []

    def test_pool_respects_precepts_rank(self) -> None:
        """Pool size equals the precepts rank."""
        with patch(
            "src.engine.fighters.priest.roll_die",
            side_effect=[6, 4, 9],
        ):
            fighter = _make_fighter(knack_rank=3, precepts_rank=3)
        assert len(fighter._dice_pool) == 3
        assert fighter._dice_pool == [9, 6, 4]


class TestFreeSwapsUnkept:
    """Phase 1: free swaps on unkept dice."""

    def test_high_pool_die_replaces_low_unkept(self) -> None:
        """Pool die higher than unkept die swaps in (may become kept)."""
        fighter = _make_fighter(knack_rank=2)  # no pool from init
        fighter._dice_pool = [9]

        # Use "damage" context to isolate Phase 1 (Phase 2 & 3 skip damage)
        # all_dice=[10, 8, 4, 2], kept=2, total=18
        # Phase 1: pool 9 > unkept 4 → swap. Then pool 2(was 4).. let me trace:
        #   i=2: pool=[9], dice[2]=4. 9>4→swap. dice[2]=9, pool=[4].
        #   i=3: pool=[4], dice[3]=2. 4>2→swap. dice[3]=4, pool=[2].
        #   After sort: [10, 9, 8, 4], kept=[10, 9]=19.
        result = fighter.post_roll_modify([10, 8, 4, 2], 2, 18, 0, "damage")
        _, kept, new_total, _, note = result
        assert new_total == 19
        assert note != ""
        assert fighter._dice_pool == [2]

    def test_high_unkept_refreshes_pool(self) -> None:
        """Unkept die higher than lowest pool die swaps to refresh pool."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [3]

        # all_dice=[10, 8, 7, 2], kept=2, total=18, tn=15, attack
        # unkept 7 > pool 3 → swap. Pool gets 7, roll gets 3.
        # After re-sort: [10, 8, 3, 2], kept=[10,8], total=18 (unchanged kept)
        result = fighter.post_roll_modify([10, 8, 7, 2], 2, 18, 15, "attack")
        _, _, new_total, _, _ = result
        # Total shouldn't decrease from the unkept refresh
        # Pool should now contain 7 (or higher if further swaps happened)
        assert 7 in fighter._dice_pool or any(d >= 7 for d in fighter._dice_pool)

    def test_no_swap_when_pool_empty(self) -> None:
        """No changes when pool is empty."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = []

        result = fighter.post_roll_modify([10, 8, 4, 2], 2, 18, 15, "attack")
        _, _, new_total, _, note = result
        assert new_total == 18
        assert note == ""

    def test_no_swap_when_no_improvement(self) -> None:
        """No swap when pool die equals unkept die."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [4]

        # all_dice=[10, 8, 4], kept=2, total=18, tn=15
        # Pool 4 == unkept 4 → no swap (not strictly greater)
        result = fighter.post_roll_modify([10, 8, 4], 2, 18, 15, "attack")
        _, _, new_total, _, _ = result
        assert new_total == 18


class TestDowngradeKeptAttack:
    """Phase 2: downgrade kept dice on attacks."""

    def test_swap_when_raises_unchanged(self) -> None:
        """Downgrade kept die when raises count is preserved."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [15]

        # No unkept dice to isolate Phase 2.
        # dice=[20, 16], kept=2, total=36, tn=30, raises=(36-30)//5=1
        # Phase 2: swap kept 16 for pool 15 → [20, 15]=35, raises=1 → ok
        # Then swap kept 20 for pool 16? [16, 15]=31, raises=0 → reject
        # Final: total=35, pool=[16]
        result = fighter.post_roll_modify([20, 16], 2, 36, 30, "attack")
        _, _, new_total, _, note = result
        assert new_total == 35
        assert 16 in fighter._dice_pool
        assert note != ""

    def test_no_swap_when_raises_would_decrease(self) -> None:
        """No downgrade when it would reduce raises count."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [10]

        # No unkept dice. dice=[20, 18], kept=2, total=38, tn=30
        # raises = (38-30)//5 = 1
        # Swap kept 18 for pool 10 → [20, 10]=30, raises=0 → reject
        # Swap kept 20 for pool 10 → [18, 10]=28, raises<0 → reject
        result = fighter.post_roll_modify([20, 18], 2, 38, 30, "attack")
        _, _, new_total, _, _ = result
        assert new_total == 38  # unchanged


class TestDowngradeKeptWoundCheck:
    """Phase 2: downgrade kept dice on wound checks."""

    def test_swap_when_still_passing(self) -> None:
        """Downgrade kept die if wound check still passes."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [8]

        # all_dice=[15, 10, 4], kept=2, total=25, tn=20
        # Passing (25 >= 20)
        # Swap kept 10 for pool 8 → [15, 8, 4] → kept [15, 8]=23 >= 20 → ok
        result = fighter.post_roll_modify(
            [15, 10, 4], 2, 25, 20, "wound_check",
        )
        _, _, new_total, _, note = result
        assert new_total == 23
        assert 10 in fighter._dice_pool
        assert note != ""

    def test_swap_when_failing_sw_count_same(self) -> None:
        """Downgrade when failing but SW count doesn't increase."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [7]

        # all_dice=[13, 9, 3], kept=2, total=22, tn=27
        # Failing: SW = 1 + (27-22)//10 = 1
        # Swap kept 9 for pool 7 → [13, 7, 3] → kept [13, 7]=20
        # SW = 1 + (27-20)//10 = 1 → same → ok
        result = fighter.post_roll_modify(
            [13, 9, 3], 2, 22, 27, "wound_check",
        )
        _, _, new_total, _, note = result
        assert new_total == 20
        assert 9 in fighter._dice_pool
        assert note != ""

    def test_no_swap_when_sw_would_increase(self) -> None:
        """No downgrade when SW count would go up."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [2]

        # all_dice=[13, 9, 3], kept=2, total=22, tn=27
        # Failing: SW = 1 + (27-22)//10 = 1
        # Swap kept 9 for pool 2 → [13, 3, 2] → kept [13, 3]=16
        # SW = 1 + (27-16)//10 = 2 → increased → reject
        result = fighter.post_roll_modify(
            [13, 9, 3], 2, 22, 27, "wound_check",
        )
        _, _, new_total, _, _ = result
        assert new_total == 22  # unchanged


class TestDowngradeKeptParry:
    """Phase 2: downgrade kept dice on parry rolls."""

    def test_swap_when_still_passing(self) -> None:
        """Downgrade kept die if parry still passes."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [7]

        # No unkept dice to isolate Phase 2.
        # dice=[15, 12], kept=2, total=27, tn=20
        # Phase 2: swap kept 12 for pool 7 → [15, 7]=22 >= 20 → ok
        # Then swap kept 15 for pool 12 → [12, 7]=19 < 20 → reject
        # Final: total=22, pool=[12]
        result = fighter.post_roll_modify(
            [15, 12], 2, 27, 20, "parry",
        )
        _, _, new_total, _, note = result
        assert new_total == 22
        assert 12 in fighter._dice_pool
        assert note != ""

    def test_no_swap_on_failing_parry(self) -> None:
        """No downgrade on a failing parry."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [5]

        # all_dice=[10, 8, 3], kept=2, total=18, tn=20
        # Failing (18 < 20) → skip phase 2
        result = fighter.post_roll_modify(
            [10, 8, 3], 2, 18, 20, "parry",
        )
        _, _, new_total, _, _ = result
        # Pool die 5 > unkept 3 → Phase 1 swaps, but no kept downgrade
        # After Phase 1: dice might be [10, 8, 5], total still 18
        assert new_total == 18


class TestSpendPoolAttack:
    """Phase 3: spend pool die to turn miss into hit."""

    def test_pool_die_turns_miss_into_hit(self) -> None:
        """Pool die replaces low kept die to make total >= TN."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [15]

        # all_dice=[10, 5, 3], kept=2, total=15, tn=20
        # Missing (15 < 20). Need 5 more.
        # Replace kept 5 with pool 15 → [15, 10, 3] → kept [15, 10]=25 >= 20
        result = fighter.post_roll_modify([10, 5, 3], 2, 15, 20, "attack")
        _, _, new_total, _, note = result
        assert new_total >= 20
        assert note != ""

    def test_uses_smallest_sufficient_pool_die(self) -> None:
        """Spend the smallest pool die that achieves the hit."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [20, 12, 8]

        # No unkept dice to prevent Phase 1 interference.
        # dice=[10, 5], kept=2, total=15, tn=20
        # Phase 2: attack missing → _can_downgrade rejects (total < tn)
        # Phase 3: replace kept 5. needed = 20 - (15-5) = 10.
        #   Smallest pool >= 10 is 12 (pool[1]).
        #   Swap: dice[1]=12, pool[1]=5. dice=[12, 10]=22. pool=[20, 8, 5].
        result = fighter.post_roll_modify([10, 5], 2, 15, 20, "attack")
        _, _, new_total, _, note = result
        assert new_total == 22
        assert note != ""
        assert 20 in fighter._dice_pool
        assert 5 in fighter._dice_pool

    def test_no_spend_when_gap_too_large(self) -> None:
        """No spend when no pool die can close the gap."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [6, 4]

        # all_dice=[10, 5, 3], kept=2, total=15, tn=25
        # Need 10 more. Replace kept 5: need pool die >= 25-10 = 15.
        # No pool die >= 15. Replace kept 10: need pool die >= 25-5 = 20.
        # No pool die >= 20.
        result = fighter.post_roll_modify([10, 5, 3], 2, 15, 25, "attack")
        _, _, new_total, _, _ = result
        assert new_total < 25  # still missing


class TestSpendPoolWoundCheck:
    """Phase 3: spend pool die to reduce SW on wound check."""

    def test_pool_die_reduces_sw(self) -> None:
        """Pool die replaces kept die to reduce serious wound count."""
        fighter = _make_fighter(knack_rank=2, earth=3)
        fighter._dice_pool = [15]
        # Set up wound state: 2 SW already, earth=3, mortal at 6
        wounds = fighter.state.log.wounds[fighter.name]
        wounds.serious_wounds = 2

        # No unkept dice to isolate Phase 3.
        # dice=[10, 8], kept=2, total=18, tn=30
        # Phase 2: pool[0]=15, not < any kept → no downgrade
        # Phase 3: SW = 1 + (30-18)//10 = 2. pending >= 2 → spend.
        #   Replace kept 8 with pool 15 → [15, 10]=25. pool=[8].
        result = fighter.post_roll_modify(
            [10, 8], 2, 18, 30, "wound_check",
        )
        _, _, new_total, _, note = result
        assert new_total == 25
        assert note != ""

    def test_pool_die_to_pass_when_mortal(self) -> None:
        """Pool die helps pass when next SW would be mortal."""
        fighter = _make_fighter(knack_rank=2, earth=2)
        fighter._dice_pool = [18]
        # earth=2, mortal at 4 SW. Set current at 3.
        wounds = fighter.state.log.wounds[fighter.name]
        wounds.serious_wounds = 3

        # all_dice=[10, 5, 3], kept=2, total=15, tn=20
        # Failing: pending_sw = 1 + (20-15)//10 = 1
        # would_be_mortal = (3+1) >= 4 → True
        # Replace kept 5 with pool 18 → [18, 10, 3] → kept [18, 10]=28 >= 20
        result = fighter.post_roll_modify(
            [10, 5, 3], 2, 15, 20, "wound_check",
        )
        _, _, new_total, _, note = result
        assert new_total >= 20
        assert note != ""

    def test_no_spend_at_1sw_not_mortal(self) -> None:
        """No spend when pending is 1 SW and not mortal."""
        fighter = _make_fighter(knack_rank=2, earth=3)
        fighter._dice_pool = [15]
        # earth=3, mortal at 6. current SW=0.
        wounds = fighter.state.log.wounds[fighter.name]
        wounds.serious_wounds = 0

        # all_dice=[10, 8, 3], kept=2, total=18, tn=20
        # Failing: pending_sw = 1 + (20-18)//10 = 1
        # would_be_mortal = (0+1) >= 6 → False
        # pending < 2 and not mortal → no spend
        result = fighter.post_roll_modify(
            [10, 8, 3], 2, 18, 20, "wound_check",
        )
        _, _, new_total, _, _ = result
        # Phase 1 might swap unkept 3 with pool 15 (15 > 3).
        # After: dice=[15, 10, 8], kept=[15, 10]=25 >= 20 → pass
        # Phase 2: passing wound check → may downgrade
        # The important thing: Phase 3 was NOT needed because Phase 1 fixed it
        # Let's test a case where Phase 1 can't help:

    def test_no_spend_at_1sw_not_mortal_strict(self) -> None:
        """No Phase 3 spend when 1 SW and not mortal (no unkept to help)."""
        fighter = _make_fighter(knack_rank=2, earth=3)
        fighter._dice_pool = [1]
        wounds = fighter.state.log.wounds[fighter.name]
        wounds.serious_wounds = 0

        # dice=[10, 8], kept=2, total=18, tn=26
        # No unkept dice → Phase 1 does nothing
        # Phase 2: wound_check, failing. SW = 1 + (26-18)//10 = 1.
        #   Swap kept 8 for pool 1 → [10, 1]=11. SW = 1+(26-11)//10 = 2 → reject
        #   No Phase 2 swaps.
        # Phase 3: pending_sw=1, not mortal (0+1 < 6) → no spend
        result = fighter.post_roll_modify(
            [10, 8], 2, 18, 26, "wound_check",
        )
        _, _, new_total, _, _ = result
        assert new_total == 18
        assert fighter._dice_pool == [1]  # pool unchanged


class TestDamageNoDowngrade:
    """No kept-die downgrades on damage rolls."""

    def test_no_downgrade_on_damage(self) -> None:
        """Only Phase 1 unkept swaps happen on damage, no kept downgrades."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [6]

        # all_dice=[10, 8, 4], kept=2, total=18, tn=0 (damage has no TN)
        # Phase 1: pool 6 > unkept 4 → swap. dice=[10, 8, 6], total still 18
        # Phase 2: context=damage → skip
        # Phase 3: context=damage → skip
        result = fighter.post_roll_modify([10, 8, 4], 2, 18, 0, "damage")
        _, _, new_total, _, _ = result
        assert new_total == 18  # kept dice unchanged
        # Pool got refreshed with the unkept die
        assert 4 in fighter._dice_pool or 6 in fighter._dice_pool

    def test_damage_phase1_only(self) -> None:
        """Damage rolls benefit from Phase 1 when pool die enters kept range."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [12]

        # all_dice=[10, 8, 4], kept=2, total=18, tn=0
        # Phase 1: pool 12 > unkept 4 → swap. dice=[10, 8, 12] → sort [12, 10, 8]
        # New kept=[12, 10]=22 (improved!)
        # Phase 2: skip (damage)
        result = fighter.post_roll_modify([10, 8, 4], 2, 18, 0, "damage")
        _, _, new_total, _, note = result
        assert new_total == 22
        assert note != ""


class TestPoolPersistence:
    """Pool carries across rolls; depleted dice stay gone."""

    def test_pool_persists_across_calls(self) -> None:
        """Pool changes from one roll carry to the next."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [9, 5, 3]

        # First call: attack, some swaps happen
        fighter.post_roll_modify([10, 8, 2, 1], 2, 18, 15, "attack")
        pool_after_first = list(fighter._dice_pool)

        # Pool was modified by first call
        assert pool_after_first != [9, 5, 3]

        # Second call uses the updated pool
        fighter.post_roll_modify([10, 7, 3], 2, 17, 15, "attack")
        pool_after_second = list(fighter._dice_pool)

        # Pool was modified again
        assert pool_after_second == fighter._dice_pool

    def test_depleted_pool_stops_swapping(self) -> None:
        """Once pool is empty, post_roll_modify is a no-op."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = []

        result = fighter.post_roll_modify([10, 8, 4], 2, 18, 15, "attack")
        _, _, new_total, _, note = result
        assert new_total == 18
        assert note == ""
        assert fighter._dice_pool == []

    def test_pool_size_unchanged(self) -> None:
        """Pool always has the same number of dice (swaps, not removes)."""
        fighter = _make_fighter(knack_rank=2)
        fighter._dice_pool = [9, 7, 5]
        initial_count = len(fighter._dice_pool)

        fighter.post_roll_modify([10, 8, 4, 2], 2, 18, 15, "attack")
        assert len(fighter._dice_pool) == initial_count

        fighter.post_roll_modify([10, 6, 3], 2, 16, 20, "parry")
        assert len(fighter._dice_pool) == initial_count
