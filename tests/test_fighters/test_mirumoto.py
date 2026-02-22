"""Tests for MirumotoFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.mirumoto import MirumotoFighter
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.weapon import Weapon, WeaponType

KATANA = Weapon(name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2)


def _make_mirumoto(
    name: str = "Mirumoto",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Mirumoto Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    da_rank = double_attack_rank if double_attack_rank is not None else knack_rank
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Mirumoto Bushi",
        school_ring=RingName.VOID,
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
                name="Counterattack", rank=knack_rank,
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


def _make_generic(name: str = "Generic", **ring_overrides: int) -> Character:
    """Create a generic character (opponent)."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    return Character(
        name=name,
        rings=Rings(**kwargs),
        skills=[
            Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ],
    )


def _make_state(
    mirumoto_char: Character,
    opponent_char: Character,
    mirumoto_void: int | None = None,
    opponent_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [mirumoto_char.name, opponent_char.name],
        [mirumoto_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    m_void = mirumoto_void if mirumoto_void is not None else mirumoto_char.void_points_max
    o_void = opponent_void if opponent_void is not None else opponent_char.void_points_max
    state = CombatState(log=log)
    create_fighter(
        mirumoto_char.name, state,
        char=mirumoto_char, weapon=KATANA, void_points=m_void,
    )
    create_fighter(
        opponent_char.name, state,
        char=opponent_char, weapon=KATANA, void_points=o_void,
    )
    return state


def _make_fighter(
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    void_points: int | None = None,
    **ring_overrides: int,
) -> MirumotoFighter:
    """Create a MirumotoFighter with a full CombatState."""
    char = _make_mirumoto(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        double_attack_rank=double_attack_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, mirumoto_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, MirumotoFighter)
    return fighter


class TestOnRoundStart:
    """on_round_start: regenerate dan points each round."""

    def test_3rd_dan_regenerates_dan_points(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=4)
        fighter.on_round_start()
        assert fighter.dan_points == 8  # 2 * 4

    def test_1st_dan_resets_to_zero(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        fighter.dan_points = 5  # leftover
        fighter.on_round_start()
        assert fighter.dan_points == 0

    def test_5th_dan_regenerates(self) -> None:
        fighter = _make_fighter(knack_rank=5, attack_rank=5)
        fighter.on_round_start()
        assert fighter.dan_points == 10  # 2 * 5


class TestChooseAttack:
    """choose_attack: DA decision for Mirumoto."""

    def test_no_da_skill_returns_attack(self) -> None:
        fighter = _make_fighter(knack_rank=1, double_attack_rank=0)
        result = fighter.choose_attack("Generic", 5)
        assert result == ("attack", 0)

    def test_crippled_returns_attack(self) -> None:
        fighter = _make_fighter(knack_rank=3, fire=3, void=3)
        # Make fighter crippled
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.choose_attack("Generic", 5)
        assert result == ("attack", 0)


class TestAttackExtraRolled:
    """attack_extra_rolled: +1 die at 1st Dan."""

    def test_first_dan_gives_plus_one(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_fifth_dan_gives_plus_one(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan_gives_zero(self) -> None:
        # knack_rank=0 means dan=0
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestAttackVoidStrategy:
    """attack_void_strategy: void spending on normal attacks."""

    def test_crippled_returns_zero(self) -> None:
        fighter = _make_fighter(knack_rank=1, void_points=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_may_spend(self) -> None:
        fighter = _make_fighter(knack_rank=1, void_points=3, fire=3, void=3)
        # High TN relative to pool should trigger void spending
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestFifthDanVoidBonus:
    """fifth_dan_void_bonus: +10 per void at 5th Dan."""

    def test_5th_dan_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        assert fighter.fifth_dan_void_bonus(2) == 20

    def test_4th_dan_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.fifth_dan_void_bonus(2) == 0

    def test_zero_void_gives_zero(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        assert fighter.fifth_dan_void_bonus(0) == 0


class TestPostAttackRollBonus:
    """post_attack_roll_bonus: 3rd Dan dan point spending."""

    def test_3rd_dan_spends_points_on_miss(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.on_round_start()  # sets dan_points = 6
        assert fighter.dan_points == 6
        bonus, note = fighter.post_attack_roll_bonus(13, 15, 5, "Generic")
        assert bonus > 0
        assert "3rd dan" in note
        assert fighter.dan_points < 6

    def test_3rd_dan_no_spending_on_hit(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.on_round_start()
        bonus, note = fighter.post_attack_roll_bonus(20, 15, 5, "Generic")
        assert bonus == 0
        assert note == ""
        assert fighter.dan_points == 6  # unchanged

    def test_1st_dan_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.post_attack_roll_bonus(10, 15, 5, "Generic")
        assert bonus == 0

    def test_no_dan_points_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.dan_points = 0
        bonus, note = fighter.post_attack_roll_bonus(13, 15, 5, "Generic")
        assert bonus == 0


class TestParryExtraRolled:
    """parry_extra_rolled: +1 die at 1st Dan."""

    def test_first_dan_gives_plus_one(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.parry_extra_rolled() == 1

    def test_zero_dan_gives_zero(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.parry_extra_rolled() == 0


class TestParryBonus:
    """parry_bonus: +5 free raise at 2nd Dan."""

    def test_second_dan_gives_5(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        assert fighter.parry_bonus() == 5

    def test_first_dan_gives_zero(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.parry_bonus() == 0


class TestParryVoidStrategy:
    """parry_void_strategy: void spending on parry."""

    def test_crippled_returns_zero(self) -> None:
        fighter = _make_fighter(knack_rank=2, void_points=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.parry_void_strategy(4, 2, 20)
        assert result == 0


class TestPostParryRollBonus:
    """post_parry_roll_bonus: 3rd Dan dan point spending on parry."""

    def test_3rd_dan_spends_on_failed_parry(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.on_round_start()
        bonus, note = fighter.post_parry_roll_bonus(12, 15)
        assert bonus > 0
        assert "3rd dan" in note

    def test_3rd_dan_no_spending_on_success(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.on_round_start()
        bonus, note = fighter.post_parry_roll_bonus(20, 15)
        assert bonus == 0
        assert note == ""


class TestOnParryAttempt:
    """on_parry_attempt: SA gives +1 temp void."""

    def test_temp_void_increases_on_success(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.temp_void == 0
        fighter.on_parry_attempt(parry_succeeded=True, margin=5)
        assert fighter.temp_void == 1

    def test_temp_void_increases_on_failure(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        fighter.on_parry_attempt(parry_succeeded=False, margin=-3)
        assert fighter.temp_void == 1

    def test_temp_void_stacks(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        fighter.on_parry_attempt(parry_succeeded=True, margin=5)
        fighter.on_parry_attempt(parry_succeeded=False, margin=-2)
        assert fighter.temp_void == 2


class TestDamageParryReduction:
    """damage_parry_reduction: 4th Dan halves parry rank."""

    def test_4th_dan_halves(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_parry_reduction(4) == 2

    def test_4th_dan_rounds_down(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_parry_reduction(3) == 1

    def test_3rd_dan_full_reduction(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        assert fighter.damage_parry_reduction(4) == 4

    def test_1st_dan_full_reduction(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.damage_parry_reduction(3) == 3


class TestShouldReactiveParry:
    """should_reactive_parry: Mirumoto reactive parry decisions."""

    def test_returns_bool(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        result = fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=4, attacker_fire=2,
        )
        assert isinstance(result, bool)


class TestShouldInterruptParry:
    """should_interrupt_parry: Mirumoto interrupt parry decisions."""

    def test_returns_bool(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_interrupt_parry(
            attack_total=20, attack_tn=15,
            weapon_rolled=4, attacker_fire=3,
        )
        assert isinstance(result, bool)


class TestShouldPredeclareParry:
    """should_predeclare_parry: Mirumoto pre-declare decisions."""

    def test_returns_bool(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        result = fighter.should_predeclare_parry(attack_tn=15, phase=5)
        assert isinstance(result, bool)

    def test_no_parry_skill_returns_false(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=0)
        result = fighter.should_predeclare_parry(attack_tn=15, phase=5)
        assert result is False


class TestShouldUseDoubleAttackCrippled:
    """_should_use_double_attack returns False when crippled (line 30)."""

    def test_crippled_returns_false(self) -> None:
        """When crippled, _should_use_double_attack returns (False, 0)."""
        from src.engine.fighters.mirumoto import _should_use_double_attack
        result, void_spend = _should_use_double_attack(
            double_attack_rank=5,
            attack_skill=3,
            fire_ring=3,
            defender_parry=2,
            void_available=5,
            max_void_spend=2,
            dan=3,
            is_crippled=True,
        )
        assert result is False
        assert void_spend == 0


class TestPostParryEffectDescriptionNoVoid:
    """post_parry_effect_description when temp_void_delta <= 0 (line 261)."""

    def test_no_void_gained_returns_empty(self) -> None:
        """When temp_void_delta <= 0, returns ''."""
        fighter = _make_fighter(knack_rank=3)
        desc = fighter.post_parry_effect_description(
            temp_void_delta=0,
            actions_changed=False,
            bonus_stored=None,
        )
        assert desc == ""

    def test_negative_void_delta_returns_empty(self) -> None:
        """When temp_void_delta < 0, returns ''."""
        fighter = _make_fighter(knack_rank=3)
        desc = fighter.post_parry_effect_description(
            temp_void_delta=-1,
            actions_changed=False,
            bonus_stored=None,
        )
        assert desc == ""


class TestFactoryCreatesMirumoto:
    """create_fighter returns MirumotoFighter for Mirumoto Bushi."""

    def test_factory_returns_mirumoto_fighter(self) -> None:
        from src.engine.fighters import create_fighter

        char = _make_mirumoto()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, MirumotoFighter)
