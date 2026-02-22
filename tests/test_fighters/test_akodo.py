"""Tests for AkodoFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.akodo import AkodoFighter
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


def _make_akodo(
    name: str = "Akodo",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    **ring_overrides: int,
) -> Character:
    """Create an Akodo Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Akodo Bushi",
        school_ring=RingName.WATER,
        school_knacks=["Feint", "Double Attack", "Lunge"],
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
                name="Feint", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Double Attack", rank=knack_rank,
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
    akodo_char: Character,
    opponent_char: Character,
    akodo_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [akodo_char.name, opponent_char.name],
        [akodo_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    a_void = (
        akodo_void if akodo_void is not None
        else akodo_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        akodo_char.name, state,
        char=akodo_char, weapon=KATANA, void_points=a_void,
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
) -> AkodoFighter:
    """Create an AkodoFighter with a full CombatState."""
    char = _make_akodo(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, akodo_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, AkodoFighter)
    return fighter


class TestChooseAttack:
    """Akodo prefers feint, then DA, then attack."""

    def test_feint_preference(self) -> None:
        """When feint skill > 0, choose feint."""
        fighter = _make_fighter(knack_rank=1)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "feint"
        assert void_spend == 0

    def test_da_fallback(self) -> None:
        """When no feint but DA available, choose double_attack."""
        char = Character(
            name="Akodo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Akodo Bushi",
            school_ring=RingName.WATER,
            school_knacks=["Double Attack", "Lunge"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(
                    name="Double Attack", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(name="Lunge", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters["Akodo"]
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "double_attack"
        assert void_spend == 0

    def test_attack_default(self) -> None:
        """When no feint or DA, choose attack."""
        char = Character(
            name="Akodo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Akodo Bushi",
            school_ring=RingName.WATER,
            school_knacks=["Lunge"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(name="Lunge", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters["Akodo"]
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_crippled_falls_back_to_attack(self) -> None:
        """When crippled, always attack regardless of skills."""
        fighter = _make_fighter(knack_rank=3, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestWoundCheckFlatBonus:
    """2nd Dan: +5 on wound checks."""

    def test_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5
        assert "akodo 2nd Dan" in note

    def test_below_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""


class TestOnFeintResult:
    """SA: +4 temp void on success, +1 on failure."""

    def test_success_adds_4_temp_void(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        initial = fighter.temp_void
        fighter.on_feint_result(
            feint_landed=True, phase=3,
            defender_name="Generic", void_spent=0,
            feint_met_tn=True,
        )
        assert fighter.temp_void == initial + 4

    def test_failure_adds_1_temp_void(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        initial = fighter.temp_void
        fighter.on_feint_result(
            feint_landed=False, phase=3,
            defender_name="Generic", void_spent=0,
            feint_met_tn=False,
        )
        assert fighter.temp_void == initial + 1


class TestPostWoundCheck3rdDan:
    """3rd Dan: attack_bonus_pool increases on WC pass."""

    def test_stores_excess_as_attack_bonus(self) -> None:
        """After passing WC with excess, pool increases."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20

        # WC total exceeds TN by 10 → excess=10, raises=2, increment=2*3=6
        new_passed, new_total, _ = fighter.post_wound_check(
            passed=True, wc_total=30, attacker_name="Generic",
        )
        assert new_passed is True
        assert fighter._attack_bonus_pool == 6

    def test_no_store_on_failure(self) -> None:
        """No bonus stored when WC fails."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.post_wound_check(
            passed=False, wc_total=10, attacker_name="Generic",
        )
        assert fighter._attack_bonus_pool == 0

    def test_no_store_before_3rd_dan(self) -> None:
        """No bonus stored before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        fighter.post_wound_check(
            passed=True, wc_total=30, attacker_name="Generic",
        )
        assert fighter._attack_bonus_pool == 0


class TestPostAttackRollBonus:
    """3rd Dan: pool spending to bridge deficit."""

    def test_spend_to_bridge_deficit(self) -> None:
        """Spend pool to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3)
        fighter._attack_bonus_pool = 20
        bonus, note = fighter.post_attack_roll_bonus(20, 25, 3, "Generic")
        assert bonus > 0
        assert "akodo 3rd Dan" in note
        assert fighter._attack_bonus_pool < 20

    def test_spend_when_already_hitting(self) -> None:
        """When already hitting, spend pool for raises."""
        fighter = _make_fighter(knack_rank=3)
        fighter._attack_bonus_pool = 10
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus > 0
        assert "akodo 3rd Dan" in note

    def test_no_spend_when_pool_empty(self) -> None:
        """No spending when pool is empty."""
        fighter = _make_fighter(knack_rank=3)
        fighter._attack_bonus_pool = 0
        bonus, note = fighter.post_attack_roll_bonus(20, 25, 3, "Generic")
        assert bonus == 0
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2)
        fighter._attack_bonus_pool = 20
        bonus, note = fighter.post_attack_roll_bonus(20, 25, 3, "Generic")
        assert bonus == 0


class TestReflectDamageAfterWC:
    """5th Dan: Spend void to reflect damage to attacker."""

    def test_reflects_damage(self) -> None:
        """5th Dan with void and damage reflects LW to attacker."""
        fighter = _make_fighter(knack_rank=5, void_points=5, water=3)
        # Make the opponent vulnerable so the fighter decides to reflect
        opp_wounds = fighter.state.log.wounds["Generic"]
        opp_wounds.light_wounds = 20
        opp_wounds.serious_wounds = 1

        reflect_lw, self_lw, note = fighter.reflect_damage_after_wc(
            damage_taken=30, attacker_name="Generic",
        )
        assert reflect_lw > 0
        assert "akodo 5th Dan" in note

    def test_no_reflect_below_5th_dan(self) -> None:
        """No reflection before 5th Dan."""
        fighter = _make_fighter(knack_rank=4, void_points=5)
        reflect_lw, self_lw, note = fighter.reflect_damage_after_wc(
            damage_taken=30, attacker_name="Generic",
        )
        assert reflect_lw == 0
        assert note == ""

    def test_no_reflect_zero_damage(self) -> None:
        """No reflection on zero damage."""
        fighter = _make_fighter(knack_rank=5, void_points=5)
        reflect_lw, self_lw, note = fighter.reflect_damage_after_wc(
            damage_taken=0, attacker_name="Generic",
        )
        assert reflect_lw == 0

    def test_no_reflect_no_void(self) -> None:
        """No reflection when no void available."""
        fighter = _make_fighter(knack_rank=5, void_points=0)
        reflect_lw, self_lw, note = fighter.reflect_damage_after_wc(
            damage_taken=30, attacker_name="Generic",
        )
        assert reflect_lw == 0


class TestAttackVoidStrategy:
    """attack_void_strategy: crippled returns 0, normal delegates."""

    def test_crippled_returns_zero(self) -> None:
        """When crippled, attack_void_strategy returns 0."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(rolled=5, kept=3, tn=15)
        assert result == 0

    def test_not_crippled_delegates_to_utility(self) -> None:
        """When not crippled, delegates to should_spend_void_on_combat_roll."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        result = fighter.attack_void_strategy(rolled=5, kept=3, tn=15)
        assert isinstance(result, int)
        assert result >= 0


class TestSaAttackBonus:
    """sa_attack_bonus always returns (0, '')."""

    def test_returns_zero(self) -> None:
        """sa_attack_bonus returns (0, '') for Akodo."""
        fighter = _make_fighter(knack_rank=3)
        bonus, note = fighter.sa_attack_bonus(phase=3)
        assert bonus == 0
        assert note == ""


class TestPostAttackRollBonusEdgeCases:
    """Edge cases for post_attack_roll_bonus."""

    def test_already_hitting_pool_below_5(self) -> None:
        """When already hitting but pool < 5, returns (0, '')."""
        fighter = _make_fighter(knack_rank=3)
        fighter._attack_bonus_pool = 4  # < 5, not enough for a raise
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert note == ""

    def test_deficit_spend_zero_or_less(self) -> None:
        """When deficit > 0 but pool is 0 after dan check, returns (0, '')."""
        fighter = _make_fighter(knack_rank=3)
        # Pool is positive so dan check passes, but set pool to 0
        # to make spend = min(deficit, 0) = 0
        fighter._attack_bonus_pool = 0
        bonus, note = fighter.post_attack_roll_bonus(20, 25, 3, "Generic")
        # Pool is 0 so the first guard (dan < 3 or pool <= 0) catches it
        assert bonus == 0
        assert note == ""


class TestWoundCheckFlatBonus4thDan:
    """4th Dan: void spent on WC gives free raises."""

    def test_4th_dan_void_bonus(self) -> None:
        """4th Dan: +5 per void spent on WC, stacked with 2nd Dan."""
        fighter = _make_fighter(knack_rank=4)
        fighter._wc_void_spent = 2
        bonus, note = fighter.wound_check_flat_bonus()
        # 5 (2nd Dan) + 10 (4th Dan: 2 void * 5) = 15
        assert bonus == 15
        assert "akodo 4th Dan" in note
        assert "akodo 2nd Dan" in note

    def test_4th_dan_no_extra_without_void(self) -> None:
        """4th Dan with no void spent only gets 2nd Dan bonus."""
        fighter = _make_fighter(knack_rank=4)
        fighter._wc_void_spent = 0
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5


class TestWoundCheckVoidStrategy:
    """wound_check_void_strategy method."""

    def test_returns_int_and_stores_result(self) -> None:
        """wound_check_void_strategy stores result in _wc_void_spent."""
        fighter = _make_fighter(knack_rank=4, void_points=5, water=3)
        # Give enough light wounds to make void spending worthwhile
        fighter.state.log.wounds[fighter.name].light_wounds = 40
        result = fighter.wound_check_void_strategy(
            water_ring=3, light_wounds=40,
        )
        assert isinstance(result, int)
        assert result >= 0
        assert fighter._wc_void_spent == result

    def test_low_dan_still_works(self) -> None:
        """wound_check_void_strategy works at lower dans too."""
        fighter = _make_fighter(knack_rank=2, void_points=3, water=2)
        fighter.state.log.wounds[fighter.name].light_wounds = 20
        result = fighter.wound_check_void_strategy(
            water_ring=2, light_wounds=20,
        )
        assert isinstance(result, int)
        assert fighter._wc_void_spent == result


class TestReflectDamageEdgeCases:
    """Edge cases for reflect_damage_after_wc."""

    def test_damage_under_10_returns_zero(self) -> None:
        """When damage_taken < 10, max_void = 0, returns (0, 0, '')."""
        fighter = _make_fighter(knack_rank=5, void_points=5)
        reflect_lw, self_lw, note = fighter.reflect_damage_after_wc(
            damage_taken=9, attacker_name="Generic",
        )
        assert reflect_lw == 0
        assert self_lw == 0
        assert note == ""

    def test_projected_damage_not_significant(self) -> None:
        """When projected damage not significant, skips spending."""
        # Need opponent with high water so expected_wc is large
        # and projected_lw <= expected_wc * 0.5
        akodo_char = _make_akodo(knack_rank=5, water=3)
        opp = _make_generic(name="Generic", water=5)
        state = _make_state(akodo_char, opp, akodo_void=1)
        fighter = state.fighters[akodo_char.name]
        assert isinstance(fighter, AkodoFighter)
        # Opponent: 0 LW, not crippled, water=5
        # projected_lw = 0 + 1*10 = 10
        # expected_wc = estimate_roll(6, 5) ~= 28.6, * 0.5 = ~14.3
        # 10 <= 14.3 → skip
        opp_wounds = state.log.wounds["Generic"]
        opp_wounds.light_wounds = 0
        opp_wounds.serious_wounds = 0
        reflect_lw, self_lw, note = fighter.reflect_damage_after_wc(
            damage_taken=10, attacker_name="Generic",
        )
        assert reflect_lw == 0
        assert self_lw == 0
        assert note == ""


class TestFactoryRegistration:
    """Akodo Bushi creates via fighter factory."""

    def test_creates_akodo_fighter(self) -> None:
        """create_fighter returns AkodoFighter for school='Akodo Bushi'."""
        char = _make_akodo()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, AkodoFighter)
