"""Tests for HirumaFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.hiruma import HirumaFighter
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


def _make_hiruma(
    name: str = "Hiruma",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    **ring_overrides: int,
) -> Character:
    """Create a Hiruma Scout character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Hiruma Scout",
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
                name="Double Attack", rank=knack_rank,
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
    hiruma_char: Character,
    opponent_char: Character,
    hiruma_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [hiruma_char.name, opponent_char.name],
        [hiruma_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    h_void = (
        hiruma_void if hiruma_void is not None
        else hiruma_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        hiruma_char.name, state,
        char=hiruma_char, weapon=KATANA, void_points=h_void,
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
) -> HirumaFighter:
    """Create a HirumaFighter with a full CombatState."""
    char = _make_hiruma(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, hiruma_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, HirumaFighter)
    return fighter


class TestInitiativeExtraUnkept:
    """1st Dan: +1 rolled die on initiative."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.initiative_extra_unkept() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.initiative_extra_unkept() == 0


class TestPostInitiative4thDan:
    """4th Dan: Lower all initiative dice by 2 (min 1)."""

    def test_dice_lowered_by_2(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        result = fighter.post_initiative([5, 7, 3], [5, 7, 3])
        assert result == [3, 5, 1]

    def test_min_value_is_1(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        result = fighter.post_initiative([1, 2, 3], [1, 2, 3])
        assert result == [1, 1, 1]

    def test_no_change_before_4th_dan(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        dice = [5, 7, 3]
        result = fighter.post_initiative(dice, dice)
        assert result == dice


class TestChooseAttack:
    """Hiruma prefers DA, else normal attack."""

    def test_da_preference(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "double_attack"
        assert void_spend == 0

    def test_attack_default(self) -> None:
        """When no DA, choose normal attack."""
        char = Character(
            name="Hiruma",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Hiruma Scout",
            school_ring=RingName.WATER,
            school_knacks=["Iaijutsu", "Lunge"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(name="Iaijutsu", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Lunge", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters["Hiruma"]
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attacks."""

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
    """2nd Dan: Free raise on parry (+5)."""

    def test_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        bonus = fighter.parry_bonus()
        assert bonus == 5
        note = fighter.parry_bonus_description(bonus)
        assert "hiruma 2nd Dan" in note

    def test_below_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        bonus = fighter.parry_bonus()
        assert bonus == 0


class TestOnParryAttempt3rdDan:
    """3rd Dan: Store 2*atk_rank as attack and damage bonus."""

    def test_stores_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=4)
        fighter.on_parry_attempt(
            parry_succeeded=True, margin=5,
            attacker_name="Generic", phase=3,
        )
        assert fighter._parry_attack_bonus == 8  # 2 * 4
        assert fighter._parry_damage_bonus == 8

    def test_stores_on_failure_too(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.on_parry_attempt(
            parry_succeeded=False, margin=-5,
            attacker_name="Generic", phase=3,
        )
        assert fighter._parry_attack_bonus == 6  # 2 * 3
        assert fighter._parry_damage_bonus == 6

    def test_no_store_before_3rd_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2, attack_rank=4)
        fighter.on_parry_attempt(
            parry_succeeded=True, margin=5,
            attacker_name="Generic", phase=3,
        )
        assert fighter._parry_attack_bonus == 0
        assert fighter._parry_damage_bonus == 0


class TestSAAttackBonus:
    """3rd Dan: Consume stored parry attack bonus."""

    def test_consumes_stored_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._parry_attack_bonus = 10
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 10
        assert "hiruma 3rd Dan" in note
        assert fighter._parry_attack_bonus == 0

    def test_zero_when_empty(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 0
        assert note == ""


class TestSADamageFlatBonus:
    """3rd Dan: Consume stored parry damage bonus."""

    def test_consumes_stored_damage_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._parry_damage_bonus = 8
        bonus, note = fighter.sa_damage_flat_bonus()
        assert bonus == 8
        assert "hiruma 3rd Dan" in note
        assert fighter._parry_damage_bonus == 0

    def test_zero_when_empty(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        bonus, note = fighter.sa_damage_flat_bonus()
        assert bonus == 0
        assert note == ""


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestDamageReduction5thDan:
    """5th Dan: 10 damage reduction with charges."""

    def test_reduces_damage_with_charges(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter._damage_reduction_charges = 2
        new_total, note = fighter.damage_reduction(25, False)
        assert new_total == 15
        assert "hiruma 5th Dan" in note
        assert fighter._damage_reduction_charges == 1

    def test_second_charge_also_works(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter._damage_reduction_charges = 2
        fighter.damage_reduction(25, False)
        new_total, note = fighter.damage_reduction(20, False)
        assert new_total == 10
        assert fighter._damage_reduction_charges == 0

    def test_no_reduction_without_charges(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter._damage_reduction_charges = 0
        new_total, note = fighter.damage_reduction(25, False)
        assert new_total == 25
        assert note == ""

    def test_charges_set_on_parry(self) -> None:
        """5th Dan parry attempt sets 2 charges."""
        fighter = _make_fighter(knack_rank=5, attack_rank=3)
        fighter.on_parry_attempt(
            parry_succeeded=True, margin=5,
            attacker_name="Generic", phase=3,
        )
        assert fighter._damage_reduction_charges == 2

    def test_reduction_capped_at_damage(self) -> None:
        """Cannot reduce below 0."""
        fighter = _make_fighter(knack_rank=5)
        fighter._damage_reduction_charges = 1
        new_total, note = fighter.damage_reduction(5, False)
        assert new_total == 0
        assert "hiruma 5th Dan" in note


class TestChooseAttackCrippled:
    """choose_attack returns 'attack' when crippled."""

    def test_crippled_returns_attack(self) -> None:
        """Crippled Hiruma falls back to normal attack."""
        fighter = _make_fighter(knack_rank=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Hiruma does not spend void on attack."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_uses_parry_bonus(self) -> None:
        """Non-crippled Hiruma factors in parry attack bonus."""
        fighter = _make_fighter(knack_rank=3, void_points=5, fire=3, void=3)
        fighter._parry_attack_bonus = 10
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestFactoryRegistration:
    """Hiruma Scout creates via fighter factory."""

    def test_creates_hiruma_fighter(self) -> None:
        """create_fighter returns HirumaFighter for school='Hiruma Scout'."""
        char = _make_hiruma()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, HirumaFighter)
