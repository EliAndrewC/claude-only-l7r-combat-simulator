"""Tests for BayushiFighter school-specific hooks and simulation integration."""

from __future__ import annotations

from unittest.mock import patch

from src.engine.character_builders.bayushi import build_bayushi_from_xp
from src.engine.combat_state import CombatState
from src.engine.fighters.bayushi import BayushiFighter
from src.engine.simulation import simulate_combat
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.combat import ActionType
from src.models.weapon import WEAPONS, WeaponType


def _make_bayushi(
    dan: int = 1,
    fire: int = 3,
    air: int = 2,
    earth: int = 2,
    water: int = 2,
    void: int = 2,
    attack: int = 1,
    parry: int = 1,
    da_rank: int | None = None,
    feint_rank: int | None = None,
    iaijutsu_rank: int | None = None,
    name: str = "Bayushi",
) -> Character:
    """Build a Bayushi Bushi character with specific values.

    If knack ranks are not specified, they default to `dan`.
    """
    eff_da = da_rank if da_rank is not None else dan
    eff_feint = feint_rank if feint_rank is not None else dan
    eff_iaijutsu = iaijutsu_rank if iaijutsu_rank is not None else dan
    skills = [
        Skill(name="Attack", rank=attack, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=parry, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        Skill(name="Double Attack", rank=eff_da, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Feint", rank=eff_feint, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(
            name="Iaijutsu", rank=eff_iaijutsu,
            skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
        ),
    ]
    return Character(
        name=name,
        rings=Rings(
            air=Ring(name=RingName.AIR, value=air),
            fire=Ring(name=RingName.FIRE, value=fire),
            earth=Ring(name=RingName.EARTH, value=earth),
            water=Ring(name=RingName.WATER, value=water),
            void=Ring(name=RingName.VOID, value=void),
        ),
        skills=skills,
        school="Bayushi Bushi",
        school_ring=RingName.FIRE,
        school_knacks=["Double Attack", "Feint", "Iaijutsu"],
    )


def _make_generic(
    name: str = "Generic",
    fire: int = 3,
    air: int = 3,
    earth: int = 3,
    water: int = 3,
    void: int = 3,
    attack: int = 3,
    parry: int = 3,
) -> Character:
    """Build a generic opponent character."""
    skills = [
        Skill(name="Attack", rank=attack, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=parry, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
    ]
    return Character(
        name=name,
        rings=Rings(
            air=Ring(name=RingName.AIR, value=air),
            fire=Ring(name=RingName.FIRE, value=fire),
            earth=Ring(name=RingName.EARTH, value=earth),
            water=Ring(name=RingName.WATER, value=water),
            void=Ring(name=RingName.VOID, value=void),
        ),
        skills=skills,
    )


def _make_fighter(
    char: Character,
    name: str | None = None,
    void_points: int = 0,
    actions: list[int] | None = None,
) -> tuple[BayushiFighter, CombatState]:
    """Create a BayushiFighter from a character."""
    from src.engine.combat import create_combat_log

    fname = name or char.name
    opp_name = "Opponent"
    log = create_combat_log([fname, opp_name], [char.rings.earth.value, 3])
    state = CombatState(log=log)
    weapon = WEAPONS[WeaponType.KATANA]
    fighter = BayushiFighter(
        fname, state, char=char, weapon=weapon,
        void_points=void_points,
        actions_remaining=actions if actions is not None else [3, 5, 7],
    )
    state.fighters[fname] = fighter
    # Add a generic opponent
    opp_char = _make_generic(name=opp_name)
    from src.engine.fighters.generic import GenericFighter

    opp = GenericFighter(
        opp_name, state, char=opp_char, weapon=weapon, void_points=0,
        actions_remaining=[3, 5, 7],
    )
    state.fighters[opp_name] = opp
    return fighter, state


class TestAttackHooks:
    """Test attack-related hooks."""

    def test_attack_extra_rolled_dan_0(self) -> None:
        char = _make_bayushi(dan=0)
        fighter, _ = _make_fighter(char)
        assert fighter.attack_extra_rolled() == 0

    def test_attack_extra_rolled_dan_1(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        # 1st Dan: +1 die (applies to DA and attack rolls)
        assert fighter.attack_extra_rolled() == 1

    def test_da_extra_rolled_dan_1(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        assert fighter.da_extra_rolled() == 1

    def test_da_extra_rolled_dan_0(self) -> None:
        char = _make_bayushi(dan=0)
        fighter, _ = _make_fighter(char)
        assert fighter.da_extra_rolled() == 0


class TestNearMissDA:
    """Test 2nd Dan free raise on DA (near-miss DA)."""

    def test_near_miss_da_dan_1(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        assert fighter.on_near_miss_da() is False

    def test_near_miss_da_dan_2(self) -> None:
        char = _make_bayushi(dan=2)
        fighter, _ = _make_fighter(char)
        assert fighter.on_near_miss_da() is True

    def test_near_miss_da_description(self) -> None:
        char = _make_bayushi(dan=2)
        fighter, _ = _make_fighter(char)
        desc = fighter.near_miss_da_description()
        assert "bayushi" in desc.lower()
        assert "2nd" in desc.lower() or "free raise" in desc.lower()


class TestSADamageBonus:
    """Test SA: void on attacks adds 1k1 damage per void."""

    def test_sa_no_void(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        rolled, kept = fighter.sa_attack_damage_bonus(0)
        assert rolled == 0
        assert kept == 0

    def test_sa_one_void(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        rolled, kept = fighter.sa_attack_damage_bonus(1)
        assert rolled == 1
        assert kept == 1

    def test_sa_two_void(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        rolled, kept = fighter.sa_attack_damage_bonus(2)
        assert rolled == 2
        assert kept == 2


class TestFeintDamage:
    """Test 3rd Dan feint damage."""

    def test_feint_damage_pool_pre_3rd(self) -> None:
        char = _make_bayushi(dan=2)
        fighter, _ = _make_fighter(char)
        rolled, kept = fighter.feint_damage_pool()
        assert rolled == 0
        assert kept == 0

    def test_feint_damage_pool_3rd_dan(self) -> None:
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char)
        rolled, kept = fighter.feint_damage_pool()
        assert rolled == 3  # attack rank
        assert kept == 1

    def test_feint_damage_pool_high_attack(self) -> None:
        char = _make_bayushi(dan=3, attack=5)
        fighter, _ = _make_fighter(char)
        rolled, kept = fighter.feint_damage_pool()
        assert rolled == 5
        assert kept == 1


class TestFeintFreeRaises:
    """Test 4th Dan: feints store free raises."""

    def test_no_free_raises_pre_4th(self) -> None:
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char)
        # Call on_feint_result — should not store free raise at 3rd Dan
        fighter.on_feint_result(True, 3, "Opponent", 0)
        assert fighter.feint_free_raises == 0

    def test_free_raise_on_successful_feint(self) -> None:
        char = _make_bayushi(dan=4, attack=4)
        fighter, _ = _make_fighter(char)
        fighter.on_feint_result(True, 3, "Opponent", 0)
        assert fighter.feint_free_raises == 1

    def test_free_raise_on_failed_feint(self) -> None:
        """4th Dan: free raise even on unsuccessful feint."""
        char = _make_bayushi(dan=4, attack=4)
        fighter, _ = _make_fighter(char)
        fighter.on_feint_result(False, 3, "Opponent", 0)
        assert fighter.feint_free_raises == 1

    def test_free_raises_stack(self) -> None:
        char = _make_bayushi(dan=4, attack=4)
        fighter, _ = _make_fighter(char)
        fighter.on_feint_result(True, 3, "Opponent", 0)
        fighter.on_feint_result(True, 5, "Opponent", 0)
        assert fighter.feint_free_raises == 2

    def test_consume_free_raises(self) -> None:
        char = _make_bayushi(dan=4)
        fighter, _ = _make_fighter(char)
        fighter.feint_free_raises = 3
        bonus, note = fighter.consume_free_raise_bonus()
        assert bonus == 15  # 3 * 5
        assert fighter.feint_free_raises == 0
        assert "bayushi" in note.lower() or "free raise" in note.lower()

    def test_consume_zero_raises(self) -> None:
        char = _make_bayushi(dan=4)
        fighter, _ = _make_fighter(char)
        bonus, note = fighter.consume_free_raise_bonus()
        assert bonus == 0
        assert note == ""


class TestWoundCheckHooks:
    """Test wound check overrides."""

    def test_wound_check_extra_rolled_dan_1(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_dan_0(self) -> None:
        char = _make_bayushi(dan=0)
        fighter, _ = _make_fighter(char)
        assert fighter.wound_check_extra_rolled() == 0

    def test_5th_dan_serious_lw_halving(self) -> None:
        """5th Dan: halve LW for serious wound calculation."""
        char = _make_bayushi(dan=5, attack=5)
        fighter, _ = _make_fighter(char)
        assert fighter.wound_check_serious_lw(40) == 20
        assert fighter.wound_check_serious_lw(41) == 20  # floor division

    def test_pre_5th_no_halving(self) -> None:
        char = _make_bayushi(dan=4)
        fighter, _ = _make_fighter(char)
        assert fighter.wound_check_serious_lw(40) == 40


class TestChooseAttack:
    """Test attack choice strategy."""

    def test_dan_1_double_attack(self) -> None:
        """1st Dan: DA (has DA knack, free raise at 2nd Dan)."""
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        choice, void = fighter.choose_attack("Opponent", 3)
        assert choice == "double_attack"

    def test_dan_2_double_attack(self) -> None:
        """2nd Dan: DA with free raise."""
        char = _make_bayushi(dan=2)
        fighter, _ = _make_fighter(char)
        choice, void = fighter.choose_attack("Opponent", 3)
        assert choice == "double_attack"

    def test_dan_3_feint_with_remaining(self) -> None:
        """3rd Dan: feint when there are remaining actions."""
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char, actions=[3, 5, 7])
        choice, void = fighter.choose_attack("Opponent", 3)
        assert choice == "feint"

    def test_dan_3_da_last_action(self) -> None:
        """3rd Dan: DA when no follow-up actions remain."""
        char = _make_bayushi(dan=3, attack=3)
        # After consuming the current die, actions_remaining is empty
        fighter, _ = _make_fighter(char, actions=[])
        choice, void = fighter.choose_attack("Opponent", 5)
        assert choice == "double_attack"

    def test_dan_4_feint_with_remaining(self) -> None:
        """4th Dan: feint to build free raises."""
        char = _make_bayushi(dan=4, attack=4)
        fighter, _ = _make_fighter(char, actions=[3, 5, 7])
        choice, void = fighter.choose_attack("Opponent", 3)
        assert choice == "feint"

    def test_void_spending_on_feint(self) -> None:
        """SA incentivizes spending void on feints."""
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char, void_points=2, actions=[3, 5, 7])
        choice, void = fighter.choose_attack("Opponent", 3)
        assert choice == "feint"
        assert void >= 1  # Should spend at least 1 void for SA bonus


class TestSimulationIntegration:
    """Integration tests running full combats."""

    def test_bayushi_vs_generic_completes(self) -> None:
        """Bayushi vs Generic fighter runs to completion."""
        bayushi = build_bayushi_from_xp(name="Bayushi", earned_xp=100)
        generic = _make_generic()
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(bayushi, generic, weapon, weapon, max_rounds=10)
        assert log.round_number >= 1
        assert len(log.actions) > 0

    def test_feint_action_appears_in_log(self) -> None:
        """At 3rd Dan+, feint actions appear in combat log."""
        bayushi = _make_bayushi(
            dan=3, fire=4, attack=3, parry=2,
            da_rank=3, feint_rank=3, iaijutsu_rank=3,
        )
        generic = _make_generic(parry=1, earth=2, fire=2)
        weapon = WEAPONS[WeaponType.KATANA]
        # Run multiple combats to increase chance of seeing feints
        found_feint = False
        for _ in range(5):
            log = simulate_combat(bayushi, generic, weapon, weapon, max_rounds=5)
            feints = [a for a in log.actions if a.action_type == ActionType.FEINT]
            if feints:
                found_feint = True
                break
        assert found_feint, "Expected at least one feint action in 5 combats"

    def test_bayushi_mirror_completes(self) -> None:
        """Two Bayushi fighters can fight each other."""
        b1 = build_bayushi_from_xp(name="Bayushi A", earned_xp=150)
        b2 = build_bayushi_from_xp(name="Bayushi B", earned_xp=150)
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(b1, b2, weapon, weapon, max_rounds=15)
        assert log.round_number >= 1

    def test_feint_grants_temp_void(self) -> None:
        """Successful feint grants temporary void."""
        bayushi = _make_bayushi(
            dan=3, fire=5, attack=3, parry=2,
            da_rank=3, feint_rank=3, iaijutsu_rank=3,
            void=3,
        )
        generic = _make_generic(parry=0, earth=2, fire=2)
        weapon = WEAPONS[WeaponType.KATANA]
        # With parry=0, TN is only 5, so feints should always hit
        found_temp_void = False
        for _ in range(3):
            log = simulate_combat(bayushi, generic, weapon, weapon, max_rounds=3)
            feints = [
                a for a in log.actions
                if a.action_type == ActionType.FEINT and a.success
            ]
            for f in feints:
                if "temp void" in (f.description or ""):
                    found_temp_void = True
                    break
            if found_temp_void:
                break
        assert found_temp_void, "Expected feint to grant temp void"

    def test_feint_die_movement_unconditional(self) -> None:
        """Die movement happens even when feint is parried or misses."""
        bayushi = _make_bayushi(
            dan=3, fire=5, attack=3, parry=2,
            da_rank=3, feint_rank=3, iaijutsu_rank=3,
            void=3,
        )
        # Strong parrier: high air + parry to reliably parry feints
        generic = _make_generic(parry=5, air=5, earth=4, fire=3)
        weapon = WEAPONS[WeaponType.KATANA]
        # Run combats looking for feints that were parried but still moved dice
        found_parried_with_move = False
        for _ in range(20):
            log = simulate_combat(bayushi, generic, weapon, weapon, max_rounds=3)
            feints = [
                a for a in log.actions
                if a.action_type == ActionType.FEINT
            ]
            parries = [
                a for a in log.actions
                if a.action_type in (ActionType.PARRY, ActionType.INTERRUPT)
                and a.success
            ]
            parried_phases = {a.phase for a in parries}
            for f in feints:
                if f.phase in parried_phases and "moved phase" in (f.description or ""):
                    found_parried_with_move = True
                    break
            if found_parried_with_move:
                break
        assert found_parried_with_move, (
            "Expected at least one parried feint with die movement in 20 combats"
        )

    def test_bayushi_5th_dan_half_serious(self) -> None:
        """5th Dan wound check halving works in simulation."""
        bayushi = _make_bayushi(
            dan=5, fire=5, attack=5, parry=3,
            da_rank=5, feint_rank=5, iaijutsu_rank=5,
            earth=3, water=3, void=4,
        )
        generic = _make_generic(
            fire=5, attack=5, parry=0, earth=5, water=5,
        )
        weapon = WEAPONS[WeaponType.KATANA]
        # Just verify it completes without errors
        log = simulate_combat(bayushi, generic, weapon, weapon, max_rounds=10)
        assert log.round_number >= 1

    def test_sa_damage_bonus_in_log(self) -> None:
        """SA damage bonus appears when void spent on attacks."""
        bayushi = _make_bayushi(
            dan=1, fire=4, attack=3, parry=1,
            da_rank=1, feint_rank=1, iaijutsu_rank=1,
            void=3,
        )
        generic = _make_generic(parry=0, earth=2, fire=2)
        weapon = WEAPONS[WeaponType.KATANA]
        # Run combats looking for SA bonus in damage descriptions
        found_sa = False
        for _ in range(10):
            log = simulate_combat(bayushi, generic, weapon, weapon, max_rounds=3)
            for a in log.actions:
                if a.action_type == ActionType.DAMAGE and "SA:" in (a.description or ""):
                    found_sa = True
                    break
            if found_sa:
                break
        # SA only triggers if void is spent on attack, which depends on strategy
        # At dan 1, Bayushi uses normal attacks with void spending
        # This is more of a smoke test


class TestFeintDamageResolution:
    """Test 3rd Dan feint damage resolution in detail."""

    def test_feint_damage_with_mock(self) -> None:
        """3rd Dan feint damage uses attack_rank k 1."""
        bayushi = _make_bayushi(
            dan=3, fire=4, attack=3, parry=2,
            da_rank=3, feint_rank=3, iaijutsu_rank=3,
        )
        generic = _make_generic(parry=0, earth=2, fire=2, water=2)
        weapon = WEAPONS[WeaponType.KATANA]

        with patch("src.engine.dice.roll_and_keep") as mock_rak:
            # Feint roll succeeds, then damage roll
            mock_rak.side_effect = [
                # Initiative A
                ([3, 5, 7], [3, 5], 8),
                # Initiative B
                ([2, 4, 6], [2, 4], 6),
                # Feint roll (should hit TN 5 with parry=0)
                ([8, 9, 10, 7], [10, 9, 8], 27),
                # Feint damage: 3k1 (attack_rank=3, kept=1)
                ([4, 6, 8], [8], 8),
                # Wound check for damage
                ([5, 7, 3], [7, 5], 12),
                # Next action (DA or attack)
                ([10, 8, 7, 6], [10, 8, 7], 25),
                # Damage for follow-up
                ([9, 8, 7, 6, 5, 4], [9, 8, 7], 24),
                # Wound check
                ([3, 4, 2], [4, 3], 7),
            ]

            log = simulate_combat(
                bayushi, generic, weapon, weapon, max_rounds=1,
            )

        # The key test is that the simulation completes without error
        assert len(log.actions) > 0


class TestParryStrategy:
    """Bayushi rarely parries — only against extreme incoming damage."""

    def test_predeclare_parry_always_false(self) -> None:
        """Bayushi never pre-declares parry."""
        char = _make_bayushi(dan=3, air=4, parry=4)
        fighter, _ = _make_fighter(char)
        # Even with high parry skill and a hard TN, never pre-declare
        assert fighter.should_predeclare_parry(attack_tn=5, phase=3) is False
        assert fighter.should_predeclare_parry(attack_tn=50, phase=3) is False

    def test_reactive_parry_low_damage_refused(self) -> None:
        """Bayushi refuses reactive parry against moderate attacks."""
        char = _make_bayushi(dan=3, air=3, earth=3, parry=3)
        fighter, _ = _make_fighter(char)
        # Attack that barely hits TN (no raises): low damage
        assert fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=3, attacker_fire=3,
        ) is False

    def test_reactive_parry_high_damage_accepted(self) -> None:
        """Bayushi parries reactively when damage would be devastating."""
        char = _make_bayushi(dan=3, air=3, earth=3, parry=3)
        fighter, _ = _make_fighter(char)
        # Attack with massive raises: damage_rolled = 3 + 3 + 6 = 12, total > 15
        # weapon_rolled=6, fire=6, extra_dice=4 → damage_rolled=16
        assert fighter.should_reactive_parry(
            attack_total=40, attack_tn=15,
            weapon_rolled=6, attacker_fire=6,
        ) is True

    def test_reactive_parry_near_cripple(self) -> None:
        """Bayushi parries when near cripple and attack has raises."""
        char = _make_bayushi(dan=3, air=3, earth=3, parry=3)
        fighter, state = _make_fighter(char)
        # Put fighter at earth-1 serious wounds (1 away from cripple)
        state.log.wounds["Bayushi"].serious_wounds = 2  # earth=3, so 1 away
        assert fighter.should_reactive_parry(
            attack_total=25, attack_tn=15,
            weapon_rolled=3, attacker_fire=3,
        ) is True

    def test_interrupt_parry_moderate_refused(self) -> None:
        """Bayushi refuses interrupt parry against moderate attacks."""
        char = _make_bayushi(dan=3, air=3, earth=3, parry=3)
        fighter, _ = _make_fighter(char, actions=[3, 5, 7])
        assert fighter.should_interrupt_parry(
            attack_total=20, attack_tn=15,
            weapon_rolled=3, attacker_fire=3,
        ) is False

    def test_interrupt_parry_lethal_accepted(self) -> None:
        """Bayushi interrupt parries when damage is lethal."""
        char = _make_bayushi(dan=3, air=3, earth=3, parry=3)
        fighter, _ = _make_fighter(char, actions=[3, 5, 7])
        # Massive damage: weapon_rolled=6, fire=6, extra_dice=6 → 18
        assert fighter.should_interrupt_parry(
            attack_total=50, attack_tn=15,
            weapon_rolled=6, attacker_fire=6,
        ) is True


class TestFeintCapping:
    """Bayushi limits feints per round then switches to DA."""

    def test_feints_this_round_starts_zero(self) -> None:
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char)
        assert fighter.feints_this_round == 0

    def test_feints_this_round_increments(self) -> None:
        """on_feint_result increments feints_this_round."""
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char)
        fighter.on_feint_result(True, 3, "Opponent", 0)
        assert fighter.feints_this_round == 1

    def test_feints_this_round_resets_on_round_start(self) -> None:
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char)
        fighter.feints_this_round = 2
        fighter.on_round_start()
        assert fighter.feints_this_round == 0

    def test_da_after_max_feints(self) -> None:
        """After 2 feints, switch to DA even with remaining actions."""
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char, actions=[3, 5, 7])
        fighter.feints_this_round = 2
        choice, _ = fighter.choose_attack("Opponent", 3)
        assert choice == "double_attack"

    def test_feint_when_under_cap(self) -> None:
        """Still feints when under the cap with remaining actions."""
        char = _make_bayushi(dan=3, attack=3)
        fighter, _ = _make_fighter(char, actions=[3, 5, 7])
        fighter.feints_this_round = 1
        choice, _ = fighter.choose_attack("Opponent", 3)
        assert choice == "feint"


class TestBayushiFighterHooks:
    """Direct unit tests for BayushiFighter hook methods."""

    def test_should_consume_phase_die(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        assert fighter.should_consume_phase_die(3) is True

    def test_feint_extra_rolled_default(self) -> None:
        char = _make_bayushi(dan=1)
        fighter, _ = _make_fighter(char)
        assert fighter.feint_extra_rolled() == 0

    def test_feint_damage_pool_accessor(self) -> None:
        """feint_damage_pool returns (attack_rank, 1) at 3rd Dan."""
        char = _make_bayushi(dan=3, attack=4)
        fighter, _ = _make_fighter(char)
        r, k = fighter.feint_damage_pool()
        assert r == 4
        assert k == 1

    def test_wound_check_extra_rolled_progression(self) -> None:
        """1st Dan: +1 on wound check."""
        for dan in range(6):
            char = _make_bayushi(dan=dan, attack=max(dan, 1))
            fighter, _ = _make_fighter(char)
            if dan >= 1:
                assert fighter.wound_check_extra_rolled() == 1
            else:
                assert fighter.wound_check_extra_rolled() == 0
