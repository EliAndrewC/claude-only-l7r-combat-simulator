"""Tests for KitsukiFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.kitsuki import KitsukiFighter
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


def _make_kitsuki(
    name: str = "Kitsuki",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    investigation_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    """Create a Kitsuki Magistrate character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Kitsuki Magistrate",
        school_ring=RingName.WATER,
        school_knacks=["Interrogation", "Investigation", "Lore"],
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
                name="Interrogation", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Investigation", rank=investigation_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Lore", rank=knack_rank,
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


def _make_state(
    kitsuki_char: Character,
    opponent_char: Character,
    kitsuki_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [kitsuki_char.name, opponent_char.name],
        [kitsuki_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    k_void = (
        kitsuki_void if kitsuki_void is not None
        else kitsuki_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        kitsuki_char.name, state,
        char=kitsuki_char, weapon=KATANA, void_points=k_void,
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
    investigation_rank: int = 5,
    void_points: int | None = None,
    **ring_overrides: int,
) -> KitsukiFighter:
    """Create a KitsukiFighter with a full CombatState."""
    char = _make_kitsuki(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        investigation_rank=investigation_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, kitsuki_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, KitsukiFighter)
    return fighter


class TestChooseAttack:
    """Kitsuki always uses normal attack."""

    def test_returns_attack(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """No extra rolled die on attacks (1st Dan is WC only)."""

    def test_returns_0(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 0

    def test_returns_0_at_5th_dan(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        assert fighter.attack_extra_rolled() == 0


class TestSAAttackBonus:
    """SA: +2*Water to all attack rolls."""

    def test_returns_2x_water(self) -> None:
        fighter = _make_fighter(knack_rank=1, water=3)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 6  # 2 * 3
        assert "kitsuki SA" in note

    def test_scales_with_water(self) -> None:
        fighter = _make_fighter(knack_rank=1, water=5)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 10  # 2 * 5


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestPostAttackRollBonus3rdDan:
    """3rd Dan: Spend free raises to bridge attack deficit."""

    def test_spend_on_attack_miss(self) -> None:
        """Spend minimum raises to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 5
        assert fighter._free_raises == 9
        assert "1 free raise" in note

    def test_spend_on_attack_larger_deficit(self) -> None:
        """Spend multiple raises for larger deficit."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(13, 25, 3, "Generic")
        assert bonus == 15
        assert fighter._free_raises == 7
        assert "3 free raise" in note

    def test_no_spend_when_hit(self) -> None:
        """Don't spend if already hitting."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_no_spend_when_gap_too_large(self) -> None:
        """Don't spend if can't bridge gap with max per roll."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(0, 26, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_pool_exhaustion(self) -> None:
        """Pool decreases with each spend."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 5
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 0
        bonus, _ = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, investigation_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0


class TestWCBonusPoolTotal3rdDan:
    """3rd Dan: Free raise pool for WC."""

    def test_returns_usable_times_5(self) -> None:
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_returns_0_before_3rd_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2, investigation_rank=5)
        assert fighter.wc_bonus_pool_total() == 0

    def test_decreases_after_spending(self) -> None:
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        fighter._free_raises = 3
        # min(3, 5) * 5 = 15
        assert fighter.wc_bonus_pool_total() == 15


class TestPostWoundCheck3rdDan:
    """3rd Dan: Spend raises to reduce SW on failed WC."""

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC.

        investigation_rank=3 at 3rd Dan → _free_raises=6, _max_per_roll=3.
        LW=45, wc_total=24, deficit=21, current_sw=3.
        spend=1: new_deficit=16, new_sw=2.
        spend=2: new_deficit=11, new_sw=2 (no further improvement).
        spend=3: new_deficit=6, new_sw=1 (improvement).
        Best: spend 3 raises (+15) → new_total=39, SW=1.
        """
        fighter = _make_fighter(knack_rank=3, investigation_rank=3, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45

        wound_tracker.serious_wounds = 3
        sw_before = 0
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert not new_passed
        assert new_total == 39
        assert "3 free raise" in note
        assert wound_tracker.serious_wounds == 1

    def test_spend_to_pass_when_mortal(self) -> None:
        """Spend to pass if taking SW would be mortal."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5, earth=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 25

        wound_tracker.serious_wounds = 4
        sw_before = 3
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert new_passed
        assert note != ""

    def test_no_spend_when_passed(self) -> None:
        """Don't spend on already-passed wound check."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, investigation_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
        assert note == ""


class TestApply5thDanDebuff:
    """5th Dan: Reduce opponent's Air, Fire, Water by 1."""

    def test_reduces_rings(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        opp = fighter.state.fighters["Generic"]
        old_air = opp.char.rings.air.value
        old_fire = opp.char.rings.fire.value
        old_water = opp.char.rings.water.value

        note = fighter.apply_5th_dan_debuff("Generic")
        assert opp.char.rings.air.value == old_air - 1
        assert opp.char.rings.fire.value == old_fire - 1
        assert opp.char.rings.water.value == old_water - 1
        assert "kitsuki 5th Dan" in note

    def test_no_debuff_before_5th_dan(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        opp = fighter.state.fighters["Generic"]
        old_air = opp.char.rings.air.value
        note = fighter.apply_5th_dan_debuff("Generic")
        assert opp.char.rings.air.value == old_air
        assert note == ""

    def test_only_applied_once(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        opp = fighter.state.fighters["Generic"]
        fighter.apply_5th_dan_debuff("Generic")
        air_after_first = opp.char.rings.air.value
        note = fighter.apply_5th_dan_debuff("Generic")
        assert opp.char.rings.air.value == air_after_first
        assert note == ""

    def test_rings_dont_go_below_1(self) -> None:
        """Rings at value 1 should not be reduced further."""
        fighter = _make_fighter(knack_rank=5)
        opp = fighter.state.fighters["Generic"]
        opp.char.rings.air.value = 1
        fighter.apply_5th_dan_debuff("Generic")
        assert opp.char.rings.air.value == 1


class TestFreeRaisePoolInit:
    """3rd Dan: Free raise pool initialization."""

    def test_pool_at_3rd_dan(self) -> None:
        """Pool is 2 * investigation_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, investigation_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0


class TestFactoryRegistration:
    """Kitsuki Magistrate creates via fighter factory."""

    def test_creates_kitsuki_fighter(self) -> None:
        """create_fighter returns KitsukiFighter for school='Kitsuki Magistrate'."""
        char = _make_kitsuki()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, KitsukiFighter)
