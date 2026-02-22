"""Tests for IdeDiplomatFighter school-specific overrides."""

from __future__ import annotations

from unittest.mock import patch

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.ide_diplomat import IdeDiplomatFighter
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


def _make_ide_diplomat(
    name: str = "Ide Diplomat",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    tact_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create an Ide Diplomat character."""
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
        school="Ide Diplomat",
        school_ring=RingName.WATER,
        school_knacks=["Double Attack", "Feint", "Worldliness"],
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
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Double Attack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Feint", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
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


def _setup(
    knack_rank: int = 1,
    void_points: int = 5,
    tact_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> tuple[IdeDiplomatFighter, CombatState]:
    """Create an IdeDiplomatFighter wired to a CombatState."""
    char = _make_ide_diplomat(
        knack_rank=knack_rank,
        tact_rank=tact_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    log = create_combat_log(
        [char.name, opp.name],
        [char.rings.earth.value, opp.rings.earth.value],
    )
    state = CombatState(log=log)
    fighter = create_fighter(
        char.name, state, char=char, weapon=KATANA,
        void_points=void_points,
    )
    create_fighter(opp.name, state, char=opp, weapon=KATANA, void_points=3)
    assert isinstance(fighter, IdeDiplomatFighter)
    return fighter, state


# -- TestIdeDiplomatInit --

class TestIdeDiplomatInit:
    def test_tact_rank_from_skill(self) -> None:
        fighter, _ = _setup(tact_rank=5)
        assert fighter._tact_rank == 5

    def test_worldliness_void_from_rank(self) -> None:
        fighter, _ = _setup(worldliness_rank=3)
        assert fighter.worldliness_void == 3

    def test_sa_feint_tn_bonus_starts_at_zero(self) -> None:
        fighter, _ = _setup()
        assert fighter._sa_feint_tn_bonus == 0

    def test_4th_dan_extra_void(self) -> None:
        fighter, _ = _setup(knack_rank=4, void_points=5)
        # 4th Dan adds +1 void
        assert fighter.void_points == 6

    def test_no_extra_void_below_4th_dan(self) -> None:
        fighter, _ = _setup(knack_rank=3, void_points=5)
        assert fighter.void_points == 5


# -- TestAttackHooks --

class TestAttackHooks:
    def test_choose_attack_normal(self) -> None:
        """With DA available and SA inactive, should choose DA."""
        fighter, _ = _setup(knack_rank=2)
        fighter.actions_remaining = [3, 5]
        attack_type, void_spend = fighter.choose_attack("Generic", 3)
        assert attack_type == "double_attack"

    def test_choose_attack_feint_when_low_success(self) -> None:
        """With low success chance and SA inactive, should feint."""
        fighter, state = _setup(knack_rank=2, fire=1)
        fighter.actions_remaining = [3, 5]
        # With fire=1, atk=3, extra_rolled=1: rolled=5, kept=1
        # TN vs parry 2 = 15; estimate_roll(5,1) ~ 7.3 < 15*0.8=12
        attack_type, void_spend = fighter.choose_attack("Generic", 3)
        assert attack_type == "feint"

    def test_choose_attack_feint_skipped_when_sa_active(self) -> None:
        """When SA is already active, skip feint and use DA."""
        fighter, _ = _setup(knack_rank=2, fire=1)
        fighter._sa_feint_tn_bonus = 10
        fighter.actions_remaining = [3, 5]
        attack_type, void_spend = fighter.choose_attack("Generic", 3)
        assert attack_type == "double_attack"

    def test_choose_attack_normal_no_knacks(self) -> None:
        """Without knack ranks, should use normal attack."""
        char = _make_ide_diplomat(knack_rank=0)
        opp = _make_generic()
        log = create_combat_log(
            [char.name, opp.name],
            [char.rings.earth.value, opp.rings.earth.value],
        )
        state = CombatState(log=log)
        fighter = create_fighter(
            char.name, state, char=char, weapon=KATANA, void_points=5,
        )
        create_fighter(opp.name, state, char=opp, weapon=KATANA, void_points=3)
        fighter.actions_remaining = [3, 5]
        attack_type, _ = fighter.choose_attack("Generic", 3)
        assert attack_type == "attack"

    def test_attack_extra_rolled_dan1(self) -> None:
        fighter, _ = _setup(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_attack_extra_rolled_dan0(self) -> None:
        char = _make_ide_diplomat(knack_rank=0)
        opp = _make_generic()
        log = create_combat_log(
            [char.name, opp.name],
            [char.rings.earth.value, opp.rings.earth.value],
        )
        state = CombatState(log=log)
        fighter = create_fighter(
            char.name, state, char=char, weapon=KATANA, void_points=5,
        )
        assert fighter.attack_extra_rolled() == 0


# -- TestSAFeintTNReduction --

class TestSAFeintTNReduction:
    def test_on_feint_sets_bonus_when_met_tn(self) -> None:
        fighter, _ = _setup()
        fighter.on_feint_result(True, 3, "Generic", 0, feint_met_tn=True)
        assert fighter._sa_feint_tn_bonus == 10

    def test_on_feint_no_bonus_when_not_met_tn(self) -> None:
        fighter, _ = _setup()
        fighter.on_feint_result(False, 3, "Generic", 0, feint_met_tn=False)
        assert fighter._sa_feint_tn_bonus == 0

    def test_on_feint_sets_bonus_even_if_parried(self) -> None:
        """Feint met TN but was parried — SA still activates."""
        fighter, _ = _setup()
        # feint_landed=False (parried), but feint_met_tn=True
        fighter.on_feint_result(False, 3, "Generic", 0, feint_met_tn=True)
        assert fighter._sa_feint_tn_bonus == 10

    def test_consume_sa_tn_bonus_active(self) -> None:
        fighter, _ = _setup()
        fighter._sa_feint_tn_bonus = 10
        bonus, note = fighter.consume_sa_tn_bonus()
        assert bonus == 10
        assert "ide diplomat SA" in note
        assert fighter._sa_feint_tn_bonus == 0

    def test_consume_sa_tn_bonus_inactive(self) -> None:
        fighter, _ = _setup()
        bonus, note = fighter.consume_sa_tn_bonus()
        assert bonus == 0
        assert note == ""


# -- TestSecondDanWoundCheck --

class TestSecondDanWoundCheck:
    def test_wound_check_flat_bonus_dan2(self) -> None:
        fighter, _ = _setup(knack_rank=2)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5
        assert "2nd Dan" in note

    def test_wound_check_flat_bonus_dan1(self) -> None:
        fighter, _ = _setup(knack_rank=1)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""


# -- TestThirdDanPenalty --

class TestThirdDanPenalty:
    def test_defend_against_attack_penalizes_hit(self) -> None:
        fighter, _ = _setup(knack_rank=3, void_points=5)
        # Attack hits with small margin
        with patch("src.engine.fighters.ide_diplomat.roll_and_keep", return_value=([7], [7], 7)):
            penalty, note = fighter.defend_against_attack(20, 15, "Generic")
        assert penalty == 7
        assert "3rd Dan" in note

    def test_defend_against_attack_miss(self) -> None:
        fighter, _ = _setup(knack_rank=3, void_points=5)
        penalty, note = fighter.defend_against_attack(10, 15, "Generic")
        assert penalty == 0
        assert note == ""

    def test_defend_against_attack_no_void(self) -> None:
        fighter, _ = _setup(knack_rank=3, void_points=0)
        fighter.temp_void = 0
        fighter.worldliness_void = 0
        penalty, note = fighter.defend_against_attack(20, 15, "Generic")
        assert penalty == 0

    def test_defend_against_attack_below_dan3(self) -> None:
        fighter, _ = _setup(knack_rank=2, void_points=5)
        penalty, note = fighter.defend_against_attack(20, 15, "Generic")
        assert penalty == 0

    def test_defend_against_attack_large_margin_skipped(self) -> None:
        """When margin is large (>= expected_penalty * 1.5), skip spending."""
        fighter, _ = _setup(knack_rank=3, void_points=5, tact_rank=2)
        # tact_rank=2, estimate_roll(2,1) ~ 6.5, 1.5*6.5 ~ 9.75
        # margin = 30 - 15 = 15 >= 9.75, so should skip
        penalty, note = fighter.defend_against_attack(30, 15, "Generic")
        assert penalty == 0

    def test_penalize_opponent_wc_passed(self) -> None:
        fighter, _ = _setup(knack_rank=3, void_points=5)
        with patch("src.engine.fighters.ide_diplomat.roll_and_keep", return_value=([5], [5], 5)):
            penalty, note = fighter.penalize_opponent_wound_check(22, 20, "Generic")
        assert penalty == 5
        assert "wound check" in note

    def test_penalize_opponent_wc_failed(self) -> None:
        fighter, _ = _setup(knack_rank=3, void_points=5)
        penalty, note = fighter.penalize_opponent_wound_check(15, 20, "Generic")
        assert penalty == 0

    def test_penalize_opponent_wc_below_dan3(self) -> None:
        fighter, _ = _setup(knack_rank=2, void_points=5)
        penalty, note = fighter.penalize_opponent_wound_check(22, 20, "Generic")
        assert penalty == 0


# -- TestFifthDanVoidRegen --

class TestFifthDanVoidRegen:
    def test_spend_regular_void_gains_temp(self) -> None:
        # All knacks at 5 so dan=5
        fighter, _ = _setup(knack_rank=5, void_points=5)
        fighter.temp_void = 0
        from_temp, from_reg, from_wl = fighter.spend_void(1)
        assert from_reg == 1
        assert fighter.temp_void == 1  # gained 1 temp from 5th Dan

    def test_spend_worldliness_void_gains_temp(self) -> None:
        # All knacks at 5 so dan=5; void_points=0 so it falls through to WL
        fighter, _ = _setup(knack_rank=5, void_points=0)
        fighter.temp_void = 0
        # 4th Dan added +1 void, so void_points=1; drain it first
        fighter.void_points = 0
        from_temp, from_reg, from_wl = fighter.spend_void(1)
        assert from_wl == 1
        assert fighter.temp_void == 1  # gained 1 temp from 5th Dan

    def test_spend_temp_void_no_extra(self) -> None:
        fighter, _ = _setup(knack_rank=5, void_points=0)
        fighter.void_points = 0
        fighter.worldliness_void = 0
        fighter.temp_void = 3
        from_temp, from_reg, from_wl = fighter.spend_void(1)
        assert from_temp == 1
        assert fighter.temp_void == 2  # no gain since spent from temp

    def test_spend_void_below_5th_dan(self) -> None:
        fighter, _ = _setup(knack_rank=4, void_points=5)
        fighter.temp_void = 0
        fighter.spend_void(1)
        assert fighter.temp_void == 0  # no 5th Dan regen

    def test_on_void_spent_reports_gain(self) -> None:
        fighter, _ = _setup(knack_rank=5, void_points=5)
        fighter.temp_void = 0
        fighter.spend_void(1)
        note = fighter.on_void_spent(1, "attack")
        assert "5th Dan" in note
        assert "+1 temp void" in note

    def test_on_void_spent_no_gain(self) -> None:
        fighter, _ = _setup(knack_rank=5, void_points=0)
        fighter.void_points = 0
        fighter.worldliness_void = 0
        fighter.temp_void = 3
        fighter.spend_void(1)
        note = fighter.on_void_spent(1, "attack")
        assert note == ""


# -- TestWoundCheck --

class TestWoundCheck:
    def test_wound_check_extra_rolled_dan1(self) -> None:
        fighter, _ = _setup(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_dan0(self) -> None:
        char = _make_ide_diplomat(knack_rank=0)
        opp = _make_generic()
        log = create_combat_log(
            [char.name, opp.name],
            [char.rings.earth.value, opp.rings.earth.value],
        )
        state = CombatState(log=log)
        fighter = create_fighter(
            char.name, state, char=char, weapon=KATANA, void_points=5,
        )
        assert fighter.wound_check_extra_rolled() == 0


# -- TestChooseAttackDefenderNone --

class TestChooseAttackDefenderNone:
    """choose_attack when defender is not found in fighters (line 92)."""

    def test_defender_not_found_uses_default_tn(self) -> None:
        """When defender is not in state.fighters, TN defaults to 15."""
        fighter, state = _setup(knack_rank=2, fire=1)
        fighter.actions_remaining = [3, 5]
        # Remove defender from fighters dict to trigger line 92
        del state.fighters["Generic"]
        attack_type, _ = fighter.choose_attack("Generic", 3)
        assert attack_type in ("feint", "double_attack", "attack")


# -- TestAttackVoidStrategyCrippled --

class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled (lines 109-112)."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Ide Diplomat does not spend void on attack."""
        fighter, _ = _setup(knack_rank=3, void_points=5)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_delegates(self) -> None:
        """Non-crippled Ide Diplomat delegates to heuristic."""
        fighter, _ = _setup(knack_rank=3, void_points=5, fire=3, void=3)
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


# -- TestPenalizeWoundCheckEdgeCases --

class TestPenalizeWoundCheckEdgeCases:
    """penalize_opponent_wound_check edge cases (lines 185, 191)."""

    def test_no_penalty_when_low_void(self) -> None:
        """No penalty when total_void <= 1 (line 185)."""
        fighter, _ = _setup(knack_rank=3, void_points=1)
        fighter.temp_void = 0
        fighter.worldliness_void = 0
        penalty, note = fighter.penalize_opponent_wound_check(22, 20, "Generic")
        assert penalty == 0
        assert note == ""

    def test_no_penalty_when_large_margin(self) -> None:
        """No penalty when margin >= expected_penalty * 1.5 (line 191)."""
        fighter, _ = _setup(knack_rank=3, void_points=5, tact_rank=1)
        # tact_rank=1 -> estimate_roll(1,1) ~ 6.5, 1.5*6.5 ~ 9.75
        # margin = 35-20 = 15 >= 9.75 -> skip
        penalty, note = fighter.penalize_opponent_wound_check(35, 20, "Generic")
        assert penalty == 0
        assert note == ""


# -- TestFactoryRegistration --

class TestFactoryRegistration:
    def test_factory_returns_ide_diplomat_fighter(self) -> None:
        char = _make_ide_diplomat()
        opp = _make_generic()
        log = create_combat_log(
            [char.name, opp.name],
            [char.rings.earth.value, opp.rings.earth.value],
        )
        state = CombatState(log=log)
        fighter = create_fighter(
            char.name, state, char=char, weapon=KATANA, void_points=5,
        )
        assert isinstance(fighter, IdeDiplomatFighter)
