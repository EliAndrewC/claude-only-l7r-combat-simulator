"""Tests for ShibaFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.shiba import ShibaFighter
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


def _make_shiba(
    name: str = "Shiba",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    counterattack_rank: int | None = None,
    double_attack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Shiba Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    ca_rank = (
        counterattack_rank if counterattack_rank is not None
        else knack_rank
    )
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Shiba Bushi",
        school_ring=RingName.AIR,
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
                name="Counterattack", rank=ca_rank,
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
    shiba_char: Character,
    opponent_char: Character,
    shiba_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [shiba_char.name, opponent_char.name],
        [shiba_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    s_void = (
        shiba_void if shiba_void is not None
        else shiba_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        shiba_char.name, state,
        char=shiba_char, weapon=KATANA, void_points=s_void,
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
    counterattack_rank: int | None = None,
    double_attack_rank: int | None = None,
    void_points: int | None = None,
    **ring_overrides: int,
) -> ShibaFighter:
    """Create a ShibaFighter with a full CombatState."""
    char = _make_shiba(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        counterattack_rank=counterattack_rank,
        double_attack_rank=double_attack_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, shiba_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, ShibaFighter)
    return fighter


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on double attack."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


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

    def test_bonus_description(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        desc = fighter.parry_bonus_description(5)
        assert "shiba 2nd Dan" in desc
        assert "+5" in desc


class TestWoundCheckExtraRolled:
    """1st-3rd Dan: +1 rolled, 4th+ Dan: +4 rolled (3 extra + 1 from 1st Dan)."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_third_dan(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        assert fighter.wound_check_extra_rolled() == 1

    def test_fourth_dan(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.wound_check_extra_rolled() == 4

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestWoundCheckExtraKept:
    """4th Dan: +1 extra kept die on wound check."""

    def test_fourth_dan(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.wound_check_extra_kept() == 1

    def test_third_dan_no_extra_kept(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        assert fighter.wound_check_extra_kept() == 0


class TestShouldConsumePhase:
    """Pre-5th Dan: never attack. 5th Dan: attack when TN reduction >= base TN."""

    def test_pre_5th_dan_never_attacks(self) -> None:
        fighter = _make_fighter(knack_rank=4, parry_rank=4)
        assert fighter.should_consume_phase_die(5) is False

    def test_5th_dan_no_reduction_no_attack(self) -> None:
        fighter = _make_fighter(knack_rank=5, parry_rank=4)
        fighter.parry_tn_reduction = 0
        assert fighter.should_consume_phase_die(5) is False

    def test_5th_dan_sufficient_reduction_attacks(self) -> None:
        fighter = _make_fighter(knack_rank=5, parry_rank=4)
        # Base TN for opponent with Parry 2: 5 + 5*2 = 15
        fighter.parry_tn_reduction = 15
        assert fighter.should_consume_phase_die(5) is True


class TestChooseAttack:
    """5th Dan uses double attack, lower dans use normal attack."""

    def test_5th_dan_double_attack(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert choice == "double_attack"
        assert void_spend == 0

    def test_pre_5th_dan_normal_attack(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert choice == "attack"
        assert void_spend == 0


class TestParryBehavior:
    """Shiba always predeclares, reactive parries, and interrupt parries."""

    def test_always_predeclares(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        assert fighter.should_predeclare_parry(25, 5) is True

    def test_always_reactive_parries(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        result = fighter.should_reactive_parry(
            attack_total=30, attack_tn=25,
            weapon_rolled=6, attacker_fire=3,
        )
        assert result is True

    def test_always_interrupt_parries(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_interrupt_parry(
            attack_total=30, attack_tn=25,
            weapon_rolled=6, attacker_fire=3,
        )
        assert result is True


class TestSelectParryDie:
    """Shiba selects lowest eligible die."""

    def test_selects_lowest(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        fighter.actions_remaining = [2, 5, 8]
        result = fighter.select_parry_die(5)
        assert result == 2

    def test_only_eligible(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        fighter.actions_remaining = [6, 8]
        result = fighter.select_parry_die(5)
        assert result is None

    def test_exact_phase(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        fighter.actions_remaining = [5, 8]
        result = fighter.select_parry_die(5)
        assert result == 5


class TestInterruptDice:
    """SA: interrupt for 1 die (lowest)."""

    def test_min_interrupt_dice(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.min_interrupt_dice() == 1

    def test_consume_interrupt_lowest(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        fighter.actions_remaining = [3, 7, 9]
        consumed, parry_die_value = fighter.consume_interrupt_parry_dice()
        assert consumed == [3]
        assert parry_die_value == 3
        assert fighter.actions_remaining == [7, 9]


class TestOnParryAttempt:
    """3rd Dan: parry damage. 5th Dan: TN reduction."""

    def test_5th_dan_stores_margin(self) -> None:
        fighter = _make_fighter(knack_rank=5, attack_rank=3)
        fighter.on_parry_attempt(True, 10, "Generic", 5)
        assert fighter.parry_tn_reduction == 10

    def test_5th_dan_margin_stacks(self) -> None:
        fighter = _make_fighter(knack_rank=5, attack_rank=3)
        fighter.on_parry_attempt(True, 10, "Generic", 5)
        fighter.on_parry_attempt(True, 5, "Generic", 7)
        assert fighter.parry_tn_reduction == 15

    def test_5th_dan_failed_parry_no_tn_reduction(self) -> None:
        fighter = _make_fighter(knack_rank=5, attack_rank=3)
        fighter.on_parry_attempt(False, -5, "Generic", 5)
        assert fighter.parry_tn_reduction == 0

    def test_3rd_dan_parry_damage_logged(self) -> None:
        """3rd Dan: parry (success or fail) deals chip damage."""
        from src.models.combat import ActionType

        fighter = _make_fighter(knack_rank=3, attack_rank=3, fire=3)
        fighter.actions_remaining = [3, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]

        fighter.on_parry_attempt(True, 5, "Generic", 3)

        log = fighter.state.log
        damage_actions = [
            a for a in log.actions
            if a.action_type == ActionType.DAMAGE
            and "parry damage" in (a.label or "")
        ]
        assert len(damage_actions) >= 1

    def test_3rd_dan_parry_damage_on_failed_parry(self) -> None:
        """3rd Dan: parry damage fires even on failed parry."""
        from src.models.combat import ActionType

        fighter = _make_fighter(knack_rank=3, attack_rank=3, fire=3)
        fighter.actions_remaining = [3, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]

        fighter.on_parry_attempt(False, -5, "Generic", 3)

        log = fighter.state.log
        damage_actions = [
            a for a in log.actions
            if a.action_type == ActionType.DAMAGE
            and "parry damage" in (a.label or "")
        ]
        assert len(damage_actions) >= 1

    def test_2nd_dan_no_parry_damage(self) -> None:
        """Below 3rd Dan: no parry damage."""
        fighter = _make_fighter(knack_rank=2, attack_rank=3, fire=3)
        fighter.on_parry_attempt(True, 5, "Generic", 3)
        log = fighter.state.log
        assert len(log.actions) == 0

    def test_5th_dan_both_damage_and_tn_reduction(self) -> None:
        """5th Dan: parry deals damage AND stores TN reduction."""
        from src.models.combat import ActionType

        fighter = _make_fighter(knack_rank=5, attack_rank=3, fire=3)
        fighter.actions_remaining = [3, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]

        fighter.on_parry_attempt(True, 10, "Generic", 3)

        # Should have damage action
        damage_actions = [
            a for a in fighter.state.log.actions
            if a.action_type == ActionType.DAMAGE
            and "parry damage" in (a.label or "")
        ]
        assert len(damage_actions) >= 1
        # Should have stored TN reduction
        assert fighter.parry_tn_reduction == 10


class TestParryTnReductionExtraDice:
    """5th Dan TN reduction should increase extra damage dice."""

    def test_extra_dice_use_reduced_tn(self) -> None:
        """Extra damage dice should be computed from the reduced TN,
        not the original TN.

        With parry_tn_reduction=20 and opponent Parry 2 (base TN 15),
        the effective TN for a normal attack is 15-20 = -5.
        A roll of 30 should yield (30 - (-5)) // 5 = 7 extra dice,
        not (30 - 15) // 5 = 3.
        """
        from unittest.mock import patch

        from src.engine.simulation import _resolve_attack
        from src.models.combat import ActionType

        shiba = _make_shiba(
            knack_rank=5, attack_rank=3, parry_rank=3,
            fire=3, air=4, earth=3, void=3,
        )
        generic = _make_generic(fire=3, earth=3, water=3)
        state = _make_state(shiba, generic)
        shiba_f = state.fighters["Shiba"]
        generic_f = state.fighters["Generic"]
        shiba_f.actions_remaining = [3, 5]
        generic_f.actions_remaining = []

        # Set up TN reduction and force attack
        shiba_f.parry_tn_reduction = 20

        # Mock roll_and_keep to return a fixed total so we can
        # predict exact extra dice.  Attack pool is (3+3+1)k3 = 7k3.
        # Return total=30 so extra dice = (30 - (15-20)) // 5 = 7
        # without the fix it would be (30 - 15) // 5 = 3
        fixed_dice = [10, 10, 10, 5, 3, 2, 1]
        fixed_kept = [10, 10, 10]
        with patch(
            "src.engine.simulation.roll_and_keep",
            return_value=(fixed_dice, fixed_kept, 30),
        ):
            _resolve_attack(state, shiba_f, generic_f, 3)

        # Find the damage action and check its dice pool
        damage_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.DAMAGE
            and a.actor == "Shiba"
            and "parry damage" not in (a.label or "")
        ]
        assert len(damage_actions) == 1
        pool = damage_actions[0].dice_pool
        # Katana is 4k2, + Fire 3 = base 4 rolled.
        # Extra dice = (30 - (-5)) // 5 = 7
        # Total rolled = 4 + 7 = 11, kept = 2 → "10k3" overflow
        # (weapon_rolled_boost returns 4, fire=3, so raw = 4+3+7=14k2
        #  → overflow to 10k6)
        # The key assertion: extra dice must be > 3 (the wrong value
        # from the unfixed base_tn).  With reduced TN of -5, extra=7.
        # rolled = weapon.rolled + fire + extra = 4 + 3 + 7 = 14
        # overflow: 14k2 → kept += (14-10) = 6, so 10k6
        assert "10k6" in pool


class TestFactoryCreatesShiba:
    """create_fighter returns ShibaFighter for Shiba Bushi."""

    def test_factory_returns_shiba_fighter(self) -> None:
        char = _make_shiba()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, ShibaFighter)


class TestSimulationIntegration:
    """Shiba can complete a full combat simulation."""

    def test_shiba_vs_generic_completes(self) -> None:
        """Shiba vs Generic finishes without errors."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        shiba = _make_shiba(knack_rank=3, fire=3, air=3, earth=3, void=3)
        generic = _make_generic(fire=3, earth=3, water=3)
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(shiba, generic, weapon, weapon)
        assert log.round_number >= 1

    def test_shiba_vs_shiba_completes(self) -> None:
        """Two Shiba fighters complete without infinite loop."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        shiba1 = _make_shiba(
            name="Shiba 1", knack_rank=3, fire=3, air=3, earth=3, void=3,
        )
        shiba2 = _make_shiba(
            name="Shiba 2", knack_rank=3, fire=3, air=3, earth=3, void=3,
        )
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(shiba1, shiba2, weapon, weapon)
        assert log.round_number >= 1

    def test_shiba_5th_dan_vs_generic(self) -> None:
        """5th Dan Shiba vs Generic finishes (tests TN reduction + DA)."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        shiba = _make_shiba(
            knack_rank=5, attack_rank=5, parry_rank=5,
            fire=4, air=5, earth=3, water=3, void=4,
        )
        generic = _make_generic(fire=3, earth=3, water=3)
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(shiba, generic, weapon, weapon)
        assert log.round_number >= 1

    def test_shiba_vs_mirumoto(self) -> None:
        """Shiba vs Mirumoto completes without errors."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        shiba = _make_shiba(knack_rank=3, fire=3, air=4, earth=3, void=3)
        mirumoto = Character(
            name="Mirumoto",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=3),
                fire=Ring(name=RingName.FIRE, value=3),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=3),
                void=Ring(name=RingName.VOID, value=3),
            ),
            school="Mirumoto Bushi",
            school_ring=RingName.VOID,
            school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(
                    name="Counterattack", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Double Attack", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(name="Iaijutsu", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(shiba, mirumoto, weapon, weapon)
        assert log.round_number >= 1

    def test_shiba_vs_hida(self) -> None:
        """Shiba vs Hida completes without errors."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        shiba = _make_shiba(knack_rank=3, fire=3, air=4, earth=3, void=3)
        hida = Character(
            name="Hida",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=3),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=3),
                void=Ring(name=RingName.VOID, value=3),
            ),
            school="Hida Bushi",
            school_ring=RingName.WATER,
            school_knacks=["Counterattack", "Iaijutsu", "Lunge"],
            skills=[
                Skill(
                    name="Attack", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Parry", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.AIR,
                ),
                Skill(
                    name="Counterattack", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(shiba, hida, weapon, weapon)
        assert log.round_number >= 1
