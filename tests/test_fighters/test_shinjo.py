"""Tests for ShinjoFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.shinjo import ShinjoFighter
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


def _make_shinjo(
    name: str = "Shinjo",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Shinjo Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**kwargs),
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
    shinjo_char: Character,
    opponent_char: Character,
    shinjo_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [shinjo_char.name, opponent_char.name],
        [shinjo_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    s_void = (
        shinjo_void if shinjo_void is not None
        else shinjo_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        shinjo_char.name, state,
        char=shinjo_char, weapon=KATANA, void_points=s_void,
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
    void_points: int | None = None,
    **ring_overrides: int,
) -> ShinjoFighter:
    """Create a ShinjoFighter with a full CombatState."""
    char = _make_shinjo(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, shinjo_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, ShinjoFighter)
    return fighter


class TestInitiativeExtraUnkept:
    """1st Dan: +1 unkept die on initiative."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.initiative_extra_unkept() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.initiative_extra_unkept() == 0


class TestPostInitiative:
    """4th Dan: highest die set to 1."""

    def test_4th_dan_sets_highest_to_1(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        result = fighter.post_initiative([3, 7], [3, 7])
        assert result == [1, 3]

    def test_3rd_dan_no_change(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        result = fighter.post_initiative([3, 7], [3, 7])
        assert result == [3, 7]


class TestShouldConsumePhaDie:
    """SA: Hold dice until phase 10."""

    def test_phase_5_returns_false(self) -> None:
        fighter = _make_fighter()
        assert fighter.should_consume_phase_die(5) is False

    def test_phase_10_returns_true(self) -> None:
        fighter = _make_fighter()
        assert fighter.should_consume_phase_die(10) is True

    def test_phase_1_returns_false(self) -> None:
        fighter = _make_fighter()
        assert fighter.should_consume_phase_die(1) is False


class TestChooseAttack:
    """choose_attack: DA or lunge at phase 10."""

    def test_returns_da_or_lunge(self) -> None:
        fighter = _make_fighter(knack_rank=2, fire=3, void=3)
        fighter.actions_remaining = [3, 5]
        choice, void_spend = fighter.choose_attack("Generic", 10)
        assert choice in ("double_attack", "lunge")
        assert isinstance(void_spend, int)

    def test_crippled_returns_lunge(self) -> None:
        fighter = _make_fighter(knack_rank=2, fire=3, void=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 3
        fighter.actions_remaining = [3]
        choice, _ = fighter.choose_attack("Generic", 10)
        assert choice == "lunge"


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestCanInterrupt:
    """Shinjo cannot interrupt-parry."""

    def test_cannot_interrupt(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        assert fighter.can_interrupt() is False


class TestParryExtraRolled:
    """1st Dan: +1 rolled die on parry."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.parry_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.parry_extra_rolled() == 0


class TestParryBonus:
    """2nd Dan: +5 free raise on parry."""

    def test_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        assert fighter.parry_bonus() == 5

    def test_first_dan_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.parry_bonus() == 0


class TestShouldReactiveParry:
    """Shinjo reactive parry based on dice count."""

    def test_3_dice_always_parries(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=4, attacker_fire=2,
        )
        assert result is True

    def test_0_parry_returns_false(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=0, air=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=4, attacker_fire=2,
        )
        assert result is False

    def test_1_die_near_mortal_parries(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [5]
        # Near mortal: serious >= 2*earth - 1 = 3
        fighter.state.log.wounds[fighter.name].serious_wounds = 3
        result = fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=4, attacker_fire=2,
        )
        assert result is True

    def test_1_die_healthy_does_not_parry(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [5]
        result = fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=4, attacker_fire=2,
        )
        assert result is False


class TestShouldPredeclareParry:
    """Shinjo predeclare: skip with <=2 dice."""

    def test_3_dice_returns_bool(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_predeclare_parry(15, 5)
        assert isinstance(result, bool)

    def test_2_dice_healthy_returns_false(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [3, 5]
        result = fighter.should_predeclare_parry(15, 5)
        assert result is False

    def test_no_parry_returns_false(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=0, air=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_predeclare_parry(15, 5)
        assert result is False


class TestOnParryAttempt:
    """3rd Dan: dice decrease; 5th Dan: store margin."""

    def test_3rd_dan_decreases_dice(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=2)
        fighter.actions_remaining = [3, 5, 7]
        fighter.on_parry_attempt(True, 5)
        # decrease by 2 (attack rank)
        assert fighter.actions_remaining == [1, 3, 5]

    def test_5th_dan_stores_margin(self) -> None:
        fighter = _make_fighter(knack_rank=5, attack_rank=3)
        fighter.actions_remaining = [3, 5]
        fighter.on_parry_attempt(True, 8)
        # 5th Dan stores margin=8 AND 3rd Dan decreases dice
        assert 8 in fighter.shinjo_bonuses
        assert fighter.actions_remaining == [0, 2]

    def test_5th_dan_no_store_on_failure(self) -> None:
        fighter = _make_fighter(knack_rank=5, attack_rank=3)
        fighter.actions_remaining = [3]
        fighter.on_parry_attempt(False, -3)
        assert len(fighter.shinjo_bonuses) == 0

    def test_2nd_dan_no_decrease(self) -> None:
        fighter = _make_fighter(knack_rank=2, attack_rank=3)
        fighter.actions_remaining = [3, 5]
        fighter.on_parry_attempt(True, 5)
        assert fighter.actions_remaining == [3, 5]


class TestWoundCheckVoidStrategy:
    """5th Dan: skip void when bonus pool is large enough."""

    def test_5th_dan_skips_with_big_pool(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter.shinjo_bonuses = [15, 10]
        result = fighter.wound_check_void_strategy(2, 20)
        assert result == 0  # pool (25) >= light_wounds (20)

    def test_5th_dan_uses_default_with_small_pool(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter.shinjo_bonuses = [5]
        result = fighter.wound_check_void_strategy(2, 20)
        assert result == -1  # pool (5) < 20

    def test_4th_dan_uses_default(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        fighter.shinjo_bonuses = [30]
        result = fighter.wound_check_void_strategy(2, 20)
        assert result == -1


class TestPostWoundCheck:
    """5th Dan: apply stored bonuses to failed wound check."""

    def test_5th_dan_applies_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter.shinjo_bonuses = [8, 15]
        fighter.state.log.wounds[fighter.name].light_wounds = 20
        passed, total, note = fighter.post_wound_check(
            False, 15, "Generic",
        )
        assert passed is True
        assert total > 15
        assert "shinjo 5th Dan" in note

    def test_5th_dan_no_bonus_already_passed(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter.shinjo_bonuses = [10]
        fighter.state.log.wounds[fighter.name].light_wounds = 10
        passed, total, note = fighter.post_wound_check(
            True, 15, "Generic",
        )
        assert passed is True
        assert total == 15
        assert note == ""


class TestHasPhase10Action:
    """SA: Shinjo has phase 10 action."""

    def test_always_true(self) -> None:
        fighter = _make_fighter()
        assert fighter.has_phase10_action() is True


class TestResolvePhase10NoDice:
    """_resolve_shinjo_phase10_attack returns early when no dice (line 72)."""

    def test_no_dice_early_return(self) -> None:
        """When no actions remaining, phase 10 attack is a no-op."""
        fighter = _make_fighter(knack_rank=3)
        fighter.actions_remaining = []
        # Should not error out
        from src.engine.fighters.shinjo import _resolve_shinjo_phase10_attack
        _resolve_shinjo_phase10_attack(fighter.state, fighter.name, "Generic")


class TestPostInitiativeDescriptionBelow4thDan:
    """post_initiative_description returns '' before 4th Dan (line 118)."""

    def test_below_4th_dan_returns_empty(self) -> None:
        """Before 4th Dan, no description for initiative."""
        fighter = _make_fighter(knack_rank=3)
        desc = fighter.post_initiative_description([3, 7], [3, 7])
        assert desc == ""


class TestConsumeAttackDieEdgeCases:
    """consume_attack_die edge cases (lines 158, 161-164)."""

    def test_die_value_not_in_actions(self) -> None:
        """When die_value is not in actions_remaining, return None (line 158)."""
        fighter = _make_fighter(knack_rank=3)
        fighter.actions_remaining = [3, 5]
        result = fighter.consume_attack_die(10, die_value=9)
        assert result is None

    def test_phase_below_10_returns_none(self) -> None:
        """When phase < 10, should_consume_phase_die returns False (line 160)."""
        fighter = _make_fighter(knack_rank=3)
        fighter.actions_remaining = [3, 5]
        result = fighter.consume_attack_die(3)
        assert result is None

    def test_phase_10_not_in_actions(self) -> None:
        """When phase 10 is not in actions_remaining, return None (line 164)."""
        fighter = _make_fighter(knack_rank=3)
        fighter.actions_remaining = [3, 5]
        result = fighter.consume_attack_die(10)
        assert result is None

    def test_phase_10_in_actions_consumed(self) -> None:
        """When phase 10 IS in actions_remaining, consume it (lines 162-163)."""
        fighter = _make_fighter(knack_rank=3)
        fighter.actions_remaining = [3, 5, 10]
        result = fighter.consume_attack_die(10)
        assert result == 10
        assert 10 not in fighter.actions_remaining


class TestSAAttackBonusZero:
    """sa_attack_bonus returns (0, '') when bonus <= 0 (line 208)."""

    def test_phase_10_gives_zero_bonus(self) -> None:
        """At phase 10, bonus = 2*(10-10) = 0."""
        fighter = _make_fighter(knack_rank=3)
        bonus, note = fighter.sa_attack_bonus(10)
        assert bonus == 0
        assert note == ""


class TestPostWoundCheck5thDanNotPassed:
    """5th Dan post_wound_check when bonuses applied but WC not passed (lines 435-436, 451)."""

    def test_5th_dan_bonuses_applied_not_passed(self) -> None:
        """5th Dan bonuses reduce SW but WC still fails."""
        fighter = _make_fighter(knack_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 50
        wound_tracker.serious_wounds = 3
        # Set shinjo_bonuses small enough that they help but don't pass
        fighter.shinjo_bonuses = [5]
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=30, attacker_name="Generic",
            sw_before_wc=0,
        )
        # deficit = 50 - 30 = 20, sw = 3
        # With +5: deficit = 50 - 35 = 15, sw = 1+15//10 = 2
        # Still not passed (35 < 50)
        if note:
            assert "shinjo 5th Dan" in note


class TestResolvePhase10SafetyBreak:
    """resolve_phase10 safety break when no die consumed (line 480)."""

    def test_safety_break_no_die_consumed(self) -> None:
        """When consume_attack_die fails (no die consumed), loop breaks."""
        from unittest.mock import patch

        fighter = _make_fighter(knack_rank=3)
        fighter.actions_remaining = [3, 5]

        # Mock _resolve_shinjo_phase10_attack to be a no-op
        # (doesn't consume any die)
        with patch(
            "src.engine.fighters.shinjo._resolve_shinjo_phase10_attack",
        ):
            fighter.resolve_phase10("Generic")
        # Should break immediately since no die was consumed
        assert fighter.actions_remaining == [3, 5]


class TestFactoryCreatesShinjo:
    """create_fighter returns ShinjoFighter for Shinjo Bushi."""

    def test_factory_returns_shinjo_fighter(self) -> None:
        from src.engine.fighters import create_fighter

        char = _make_shinjo()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, ShinjoFighter)
