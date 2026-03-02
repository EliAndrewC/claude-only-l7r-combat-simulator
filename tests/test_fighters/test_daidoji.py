"""Tests for DaidojiFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.daidoji import DaidojiFighter
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


def _make_daidoji(
    name: str = "Daidoji",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    counterattack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Daidoji Yojimbo character."""
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
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Daidoji Yojimbo",
        school_ring=RingName.WATER,
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
                name="Double Attack", rank=knack_rank,
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
    daidoji_char: Character,
    opponent_char: Character,
    daidoji_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [daidoji_char.name, opponent_char.name],
        [daidoji_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    d_void = (
        daidoji_void if daidoji_void is not None
        else daidoji_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        daidoji_char.name, state,
        char=daidoji_char, weapon=KATANA, void_points=d_void,
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
    void_points: int | None = None,
    **ring_overrides: int,
) -> DaidojiFighter:
    """Create a DaidojiFighter with a full CombatState."""
    char = _make_daidoji(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        counterattack_rank=counterattack_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, daidoji_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, DaidojiFighter)
    return fighter


class TestChooseAttack:
    """Daidoji prefers DA, else normal attack."""

    def test_da_preference(self) -> None:
        """When DA skill > 0, choose double_attack."""
        fighter = _make_fighter(knack_rank=1)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "double_attack"
        assert void_spend == 0

    def test_attack_default(self) -> None:
        """When no DA, choose normal attack."""
        char = Character(
            name="Daidoji",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Daidoji Yojimbo",
            school_ring=RingName.WATER,
            school_knacks=["Counterattack", "Iaijutsu"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(
                    name="Counterattack", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(name="Iaijutsu", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters["Daidoji"]
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_crippled_falls_back_to_attack(self) -> None:
        """When crippled, always normal attack."""
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
    """3rd Dan: Bonus from counterattack stored WC bonus."""

    def test_with_counterattack_wc_bonus(self) -> None:
        """Consumes stored counterattack WC bonus."""
        fighter = _make_fighter(knack_rank=3)
        fighter._counterattack_wc_bonus = 15
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 15
        assert "daidoji 3rd Dan" in note
        assert fighter._counterattack_wc_bonus == 0

    def test_no_bonus_when_empty(self) -> None:
        """No bonus when no counterattack WC bonus stored."""
        fighter = _make_fighter(knack_rank=3)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""


class TestCanInterrupt:
    """SA: Counterattack as interrupt for 1 die."""

    def test_true_with_ca_and_dice(self) -> None:
        """Can interrupt with CA skill and action dice."""
        fighter = _make_fighter(knack_rank=1, counterattack_rank=2)
        fighter.actions_remaining = [3, 5]
        assert fighter.can_interrupt() is True

    def test_false_without_ca(self) -> None:
        """Cannot interrupt without CA skill."""
        char = Character(
            name="Daidoji",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Daidoji Yojimbo",
            school_ring=RingName.WATER,
            school_knacks=["Double Attack", "Iaijutsu"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(
                    name="Double Attack", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(name="Iaijutsu", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters["Daidoji"]
        fighter.actions_remaining = [3, 5]
        assert fighter.can_interrupt() is False

    def test_false_without_dice(self) -> None:
        """Cannot interrupt without action dice."""
        fighter = _make_fighter(knack_rank=1, counterattack_rank=2)
        fighter.actions_remaining = []
        assert fighter.can_interrupt() is False


class TestResolvePreAttackCounterattack:
    """SA: Counterattack interrupt for 1 die, with 3rd Dan WC bonus."""

    def test_consumes_die(self) -> None:
        """Counterattack consumes cheapest action die."""
        fighter = _make_fighter(knack_rank=1, counterattack_rank=2)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is not None
        assert 3 not in fighter.actions_remaining

    def test_returns_margin_and_zero_penalty(self) -> None:
        """Counterattack returns (margin, 0) — no SA penalty on attacker."""
        fighter = _make_fighter(knack_rank=1, counterattack_rank=2)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is not None
        margin, sa_penalty = result
        assert sa_penalty == 0
        assert isinstance(margin, int)

    def test_sets_wc_bonus_at_3rd_dan(self) -> None:
        """3rd Dan stores counterattack WC bonus = attack_rank * 5."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3, counterattack_rank=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is not None
        assert fighter._counterattack_wc_bonus == 15  # 3 * 5

    def test_no_wc_bonus_before_3rd_dan(self) -> None:
        """No WC bonus stored before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, counterattack_rank=2)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is not None
        assert fighter._counterattack_wc_bonus == 0

    def test_no_counter_without_interrupt(self) -> None:
        """Cannot counterattack when can_interrupt is False."""
        fighter = _make_fighter(knack_rank=1, counterattack_rank=2)
        fighter.actions_remaining = []
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is None


class TestPostWoundCheck5thDan:
    """5th Dan: WC excess lowers opponent's TN."""

    def test_passed_wc_excess_reduces_opponent_tn(self) -> None:
        """After passing WC with excess, parry_tn_reduction increases."""
        fighter = _make_fighter(knack_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        initial = fighter.parry_tn_reduction

        fighter.post_wound_check(
            passed=True, wc_total=30, attacker_name="Generic",
        )
        assert fighter.parry_tn_reduction == initial + 10

    def test_no_reduction_on_failed_wc(self) -> None:
        """No TN reduction when WC fails."""
        fighter = _make_fighter(knack_rank=5)
        initial = fighter.parry_tn_reduction
        fighter.post_wound_check(
            passed=False, wc_total=10, attacker_name="Generic",
        )
        assert fighter.parry_tn_reduction == initial

    def test_no_reduction_before_5th_dan(self) -> None:
        """No TN reduction before 5th Dan."""
        fighter = _make_fighter(knack_rank=4, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        initial = fighter.parry_tn_reduction
        fighter.post_wound_check(
            passed=True, wc_total=30, attacker_name="Generic",
        )
        assert fighter.parry_tn_reduction == initial


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Daidoji does not spend void on attack."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_may_spend(self) -> None:
        """Non-crippled Daidoji may spend void on attack."""
        fighter = _make_fighter(knack_rank=1, void_points=5, fire=3, void=3)
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestFactoryRegistration:
    """Daidoji Yojimbo creates via fighter factory."""

    def test_creates_daidoji_fighter(self) -> None:
        """create_fighter returns DaidojiFighter for school='Daidoji Yojimbo'."""
        char = _make_daidoji()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, DaidojiFighter)
