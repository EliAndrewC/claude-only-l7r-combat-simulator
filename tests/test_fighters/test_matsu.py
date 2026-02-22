"""Tests for MatsuFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.matsu import MatsuFighter
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


def _make_matsu(
    name: str = "Matsu",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Matsu Bushi character."""
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
    lng_rank = (
        lunge_rank if lunge_rank is not None else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Matsu Bushi",
        school_ring=RingName.FIRE,
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
                name="Lunge", rank=lng_rank,
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
    matsu_char: Character,
    opponent_char: Character,
    matsu_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [matsu_char.name, opponent_char.name],
        [matsu_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    m_void = (
        matsu_void if matsu_void is not None
        else matsu_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        matsu_char.name, state,
        char=matsu_char, weapon=KATANA, void_points=m_void,
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
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    void_points: int | None = None,
    **ring_overrides: int,
) -> MatsuFighter:
    """Create a MatsuFighter with a full CombatState."""
    char = _make_matsu(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        double_attack_rank=double_attack_rank,
        lunge_rank=lunge_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, matsu_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, MatsuFighter)
    return fighter


class TestInitiativeExtraUnkept:
    """SA: always rolls 10 dice for initiative."""

    def test_void_2_gets_7_extra(self) -> None:
        fighter = _make_fighter(void=2)
        assert fighter.initiative_extra_unkept() == 7

    def test_void_4_gets_5_extra(self) -> None:
        fighter = _make_fighter(void=4)
        assert fighter.initiative_extra_unkept() == 5

    def test_void_1_gets_8_extra(self) -> None:
        fighter = _make_fighter(void=1, air=1, fire=1, earth=1, water=1)
        assert fighter.initiative_extra_unkept() == 8


class TestChooseAttack:
    """choose_attack: always Lunge or DA, never normal."""

    def test_crippled_always_lunges(self) -> None:
        fighter = _make_fighter(knack_rank=3, fire=3, void=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 3
        result = fighter.choose_attack("Generic", 5)
        assert result[0] == "lunge"

    def test_returns_lunge_or_da(self) -> None:
        fighter = _make_fighter(knack_rank=2, fire=3, void=3)
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert choice in ("lunge", "double_attack")
        assert isinstance(void_spend, int)


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestOnNearMissDa:
    """4th Dan: near-miss DA still hits."""

    def test_4th_dan_true(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.on_near_miss_da() is True

    def test_3rd_dan_false(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        assert fighter.on_near_miss_da() is False

    def test_5th_dan_true(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        assert fighter.on_near_miss_da() is True


class TestOnVoidSpent:
    """3rd Dan: void spending generates wound-check bonus."""

    def test_3rd_dan_generates_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=4)
        assert len(fighter.matsu_bonuses) == 0
        fighter.on_void_spent(2, "attack")
        assert len(fighter.matsu_bonuses) == 2
        assert all(b == 12 for b in fighter.matsu_bonuses)  # 3*4

    def test_1st_dan_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=1, attack_rank=4)
        fighter.on_void_spent(1, "attack")
        assert len(fighter.matsu_bonuses) == 0

    def test_zero_amount_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.on_void_spent(0, "attack")
        assert len(fighter.matsu_bonuses) == 0


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound check."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestWoundCheckVoidStrategy:
    """3rd Dan: skip void when stored bonuses can help."""

    def test_3rd_dan_skips_with_good_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter.matsu_bonuses = [10]
        # bonus (10) >= light_wounds (20) * 0.3 (6) → skip
        result = fighter.wound_check_void_strategy(2, 20)
        assert result == 0

    def test_3rd_dan_uses_default_without_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        result = fighter.wound_check_void_strategy(2, 20)
        assert result == -1  # default logic

    def test_1st_dan_uses_default(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        fighter.matsu_bonuses = [10]
        result = fighter.wound_check_void_strategy(2, 20)
        assert result == -1


class TestPostWoundCheck:
    """3rd Dan: apply stored bonus to failed wound check."""

    def test_3rd_dan_applies_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter.matsu_bonuses = [8, 12]
        # Set light wounds so effective_tn = 20
        fighter.state.log.wounds[fighter.name].light_wounds = 20
        passed, total, note = fighter.post_wound_check(
            False, 15, "Generic",
        )
        # 15 + 8 >= 20 → passes with bonus[0] = 8 (first match)
        assert passed is True
        assert total == 23
        assert "matsu 3rd Dan" in note
        assert len(fighter.matsu_bonuses) == 1
        assert fighter.matsu_bonuses[0] == 12  # remaining

    def test_3rd_dan_no_match_returns_unchanged(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter.matsu_bonuses = [3]
        fighter.state.log.wounds[fighter.name].light_wounds = 20
        passed, total, note = fighter.post_wound_check(
            False, 10, "Generic",
        )
        # 10 + 3 < 20 → no bonus applied
        assert passed is False
        assert total == 10
        assert note == ""

    def test_already_passed_returns_unchanged(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter.matsu_bonuses = [20]
        fighter.state.log.wounds[fighter.name].light_wounds = 10
        passed, total, note = fighter.post_wound_check(
            True, 15, "Generic",
        )
        assert passed is True
        assert total == 15
        assert note == ""


class TestOnWoundCheckFailed:
    """5th Dan: light wounds reset to 15."""

    def test_5th_dan_returns_15(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        reset_value, note = fighter.on_wound_check_failed("Generic")
        assert reset_value == 15
        assert "matsu 5th Dan" in note

    def test_4th_dan_returns_0(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        reset_value, note = fighter.on_wound_check_failed("Generic")
        assert reset_value == 0
        assert note == ""


class TestMatsuAttackChoiceFunction:
    """Tests for _matsu_attack_choice helper covering edge cases."""

    def test_lunge_with_void_spend_when_no_da(self) -> None:
        """When no DA, lunge with void spend if expected < base_tn."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # Low lunge_rank + low fire = low expected, high parry = high TN
        # Forces the deficit path to spend void on lunge
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=1,
            double_attack_rank=0,
            attack_skill=3,
            fire_ring=1,
            defender_parry=5,
            void_available=5,
            max_void_spend=3,
            dan=1,
            is_crippled=False,
        )
        assert choice == "lunge"
        assert void_spend > 0

    def test_lunge_no_void_when_expected_meets_tn(self) -> None:
        """When no DA and expected >= base_tn, lunge without void."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # High lunge + fire vs low parry → expected >= base_tn
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=5,
            double_attack_rank=0,
            attack_skill=3,
            fire_ring=5,
            defender_parry=1,
            void_available=5,
            max_void_spend=3,
            dan=1,
            is_crippled=False,
        )
        assert choice == "lunge"
        assert void_spend == 0

    def test_4th_dan_da_with_deficit(self) -> None:
        """4th Dan: DA with deficit when effective_da_tn is reachable."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # At 4th Dan, effective_da_tn = base_tn = 5+5*3 = 20
        # da_rolled = 1+1+1 = 3, da_kept = 1
        # da_expected = estimate_roll(3, 1) = 7.5 < 20
        # usable_void = min(5, 1) = 1 (dan >= 3)
        # max_void_boost = 1*5.5 = 5.5
        # da_expected + max_void_boost = 13 >= 20*0.6 = 12 → viable with deficit
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=1,
            double_attack_rank=1,
            attack_skill=3,
            fire_ring=1,
            defender_parry=3,
            void_available=5,
            max_void_spend=1,
            dan=4,
            is_crippled=False,
        )
        assert choice == "double_attack"
        assert void_spend > 0

    def test_pre_4th_dan_da_with_deficit(self) -> None:
        """Pre-4th Dan: DA with deficit when da_tn is reachable."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # dan=2, fire=3, da_rank=3, defender_parry=1
        # da_rolled = 3+3+1 = 7, da_kept = 3
        # da_expected = estimate_roll(7, 3) = 22.5
        # da_tn = 10+20 = 30
        # usable_void = min(5-1, 3) = 3 (dan < 3)
        # max_void_boost = 3*5.5 = 16.5
        # 22.5 + 16.5 = 39 >= 30*0.85 = 25.5 → viable
        # 22.5 < 30 → deficit path
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=3,
            double_attack_rank=3,
            attack_skill=3,
            fire_ring=3,
            defender_parry=1,
            void_available=5,
            max_void_spend=3,
            dan=2,
            is_crippled=False,
        )
        assert choice == "double_attack"
        assert void_spend > 0

    def test_da_not_viable_lunge_with_void(self) -> None:
        """When DA is not viable (pre-4th Dan, high TN), fall back to lunge."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # DA rank exists but TN is too high for DA to be viable
        # da_expected + max_void_boost < da_tn * 0.85
        # Lunge expected < base_tn, usable_void > 0 → lunge with void
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=1,
            double_attack_rank=1,
            attack_skill=2,
            fire_ring=2,
            defender_parry=6,
            void_available=5,
            max_void_spend=2,
            dan=2,
            is_crippled=False,
        )
        assert choice == "lunge"
        assert void_spend > 0

    def test_4th_dan_da_no_void_when_expected_meets_tn(self) -> None:
        """4th Dan: DA with no void when da_expected >= effective_da_tn."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # da_expected = estimate_roll(7, 3) = 22.5
        # effective_da_tn = 5+5*1 = 10
        # 22.5 >= 10 → return "double_attack", 0
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=3,
            double_attack_rank=3,
            attack_skill=3,
            fire_ring=3,
            defender_parry=1,
            void_available=5,
            max_void_spend=3,
            dan=4,
            is_crippled=False,
        )
        assert choice == "double_attack"
        assert void_spend == 0

    def test_pre_4th_dan_da_no_void_when_expected_meets_tn(self) -> None:
        """Pre-4th Dan: DA with no void when da_expected >= da_tn."""
        from src.engine.fighters.matsu import _matsu_attack_choice

        # da_expected = estimate_roll(11, 5) ~= 40.9
        # da_tn = 5+5*0+20 = 25
        # 40.9 >= 25 → return "double_attack", 0
        choice, void_spend = _matsu_attack_choice(
            lunge_rank=5,
            double_attack_rank=5,
            attack_skill=5,
            fire_ring=5,
            defender_parry=0,
            void_available=5,
            max_void_spend=5,
            dan=2,
            is_crippled=False,
        )
        assert choice == "double_attack"
        assert void_spend == 0


class TestNearMissDaDescription:
    """near_miss_da_description returns description string."""

    def test_description_content(self) -> None:
        """near_miss_da_description includes matsu 4th Dan info."""
        fighter = _make_fighter(knack_rank=4)
        desc = fighter.near_miss_da_description()
        assert "matsu 4th Dan" in desc


class TestFactoryCreatesMatsu:
    """create_fighter returns MatsuFighter for Matsu Bushi."""

    def test_factory_returns_matsu_fighter(self) -> None:
        from src.engine.fighters import create_fighter

        char = _make_matsu()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, MatsuFighter)
