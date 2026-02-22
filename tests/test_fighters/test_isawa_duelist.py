"""Tests for IsawaDuelistFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.isawa_duelist import IsawaDuelistFighter
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


def _make_isawa(
    name: str = "Isawa",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    **ring_overrides: int,
) -> Character:
    """Create an Isawa Duelist character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Isawa Duelist",
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
    isawa_char: Character,
    opponent_char: Character,
    isawa_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [isawa_char.name, opponent_char.name],
        [isawa_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    i_void = (
        isawa_void if isawa_void is not None
        else isawa_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        isawa_char.name, state,
        char=isawa_char, weapon=KATANA, void_points=i_void,
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
) -> IsawaDuelistFighter:
    """Create an IsawaDuelistFighter with a full CombatState."""
    char = _make_isawa(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, isawa_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, IsawaDuelistFighter)
    return fighter


class TestDamageRingValue:
    """SA: Use Water instead of Fire for damage."""

    def test_returns_water_ring(self) -> None:
        fighter = _make_fighter(knack_rank=1, water=4, fire=2)
        assert fighter.damage_ring_value() == 4

    def test_different_values(self) -> None:
        fighter = _make_fighter(knack_rank=1, water=3, fire=5)
        assert fighter.damage_ring_value() == 3


class TestChooseAttack:
    """Isawa Duelist prefers DA, then lunge, then attack."""

    def test_da_preference(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "double_attack"
        assert void_spend == 0

    def test_lunge_fallback(self) -> None:
        """When no DA but lunge available, choose lunge."""
        char = Character(
            name="Isawa",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Isawa Duelist",
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
        fighter = state.fighters["Isawa"]
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "lunge"
        assert void_spend == 0

    def test_attack_default(self) -> None:
        """When no DA or lunge, choose normal attack."""
        char = Character(
            name="Isawa",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Isawa Duelist",
            school_ring=RingName.WATER,
            school_knacks=["Iaijutsu"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(name="Iaijutsu", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters["Isawa"]
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_crippled_falls_back_to_attack(self) -> None:
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


class TestLungeExtraRolled:
    """1st Dan: +1 rolled die on lunge."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.lunge_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.lunge_extra_rolled() == 0


class TestSAAttackBonus3rdDan:
    """3rd Dan: +3*atk_rank bonus, sets TN penalty pending."""

    def test_3rd_dan_gives_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=4)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 12  # 3 * 4
        assert "isawa 3rd Dan" in note
        assert fighter._tn_penalty_pending is True

    def test_no_bonus_before_3rd_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2, attack_rank=4)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 0
        assert note == ""
        assert fighter._tn_penalty_pending is False


class TestDefenderTnPenalty:
    """3rd Dan: -5 TN self-debuff, consumed on read."""

    def test_returns_5_when_pending(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._tn_penalty_pending = True
        penalty, note = fighter.defender_tn_penalty()
        assert penalty == 5
        assert "isawa 3rd Dan" in note

    def test_returns_0_when_not_pending(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._tn_penalty_pending = False
        penalty, note = fighter.defender_tn_penalty()
        assert penalty == 0
        assert note == ""

    def test_consumed_on_read(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._tn_penalty_pending = True
        fighter.defender_tn_penalty()
        assert fighter._tn_penalty_pending is False
        # Second read should return 0
        penalty, note = fighter.defender_tn_penalty()
        assert penalty == 0


class TestOnAttackParried:
    """3rd Dan: If attack parried, clear TN penalty."""

    def test_clears_pending_penalty(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._tn_penalty_pending = True
        fighter.on_attack_parried(parry_succeeded=True)
        assert fighter._tn_penalty_pending is False

    def test_clears_on_failed_parry_too(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        fighter._tn_penalty_pending = True
        fighter.on_attack_parried(parry_succeeded=False)
        assert fighter._tn_penalty_pending is False


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestWoundCheckFlatBonus2ndDan:
    """2nd Dan: +5 on wound checks. 5th Dan: includes WC pool."""

    def test_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5
        assert "isawa 2nd Dan" in note

    def test_below_second_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""

    def test_5th_dan_with_wc_pool(self) -> None:
        """5th Dan includes stored WC bonus pool."""
        fighter = _make_fighter(knack_rank=5)
        fighter._wc_bonus_pool = 10
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 15  # 5 from 2nd Dan + 10 from pool
        assert "isawa 2nd Dan" in note
        assert "isawa 5th Dan" in note
        assert fighter._wc_bonus_pool == 0  # consumed

    def test_5th_dan_without_pool(self) -> None:
        """5th Dan with empty pool only gets 2nd Dan bonus."""
        fighter = _make_fighter(knack_rank=5)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5
        assert "isawa 2nd Dan" in note


class TestPostWoundCheck5thDan:
    """5th Dan: Store WC excess in pool."""

    def test_stores_excess(self) -> None:
        fighter = _make_fighter(knack_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        fighter.post_wound_check(
            passed=True, wc_total=35, attacker_name="Generic",
        )
        assert fighter._wc_bonus_pool == 15  # 35 - 20

    def test_no_store_on_failure(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter.post_wound_check(
            passed=False, wc_total=10, attacker_name="Generic",
        )
        assert fighter._wc_bonus_pool == 0

    def test_no_store_before_5th_dan(self) -> None:
        fighter = _make_fighter(knack_rank=4, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        fighter.post_wound_check(
            passed=True, wc_total=35, attacker_name="Generic",
        )
        assert fighter._wc_bonus_pool == 0

    def test_accumulates(self) -> None:
        """Pool accumulates across multiple wound checks."""
        fighter = _make_fighter(knack_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        fighter.post_wound_check(passed=True, wc_total=30, attacker_name="Generic")
        fighter.post_wound_check(passed=True, wc_total=25, attacker_name="Generic")
        assert fighter._wc_bonus_pool == 15  # 10 + 5


class TestFactoryRegistration:
    """Isawa Duelist creates via fighter factory."""

    def test_creates_isawa_duelist_fighter(self) -> None:
        """create_fighter returns IsawaDuelistFighter for school='Isawa Duelist'."""
        char = _make_isawa()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, IsawaDuelistFighter)
