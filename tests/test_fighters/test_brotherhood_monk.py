"""Tests for BrotherhoodMonkFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.brotherhood_monk import BrotherhoodMonkFighter
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.weapon import Weapon, WeaponType

UNARMED = Weapon(
    name="Unarmed", weapon_type=WeaponType.UNARMED, rolled=0, kept=2,
)
KATANA = Weapon(
    name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2,
)


def _make_monk(
    name: str = "Brotherhood Monk",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Brotherhood Monk character."""
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
        school="Brotherhood Monk",
        school_ring=RingName.WATER,
        school_knacks=["Conviction", "Otherworldliness", "Worldliness"],
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
                name="Precepts", rank=precepts_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Conviction", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.EARTH,
            ),
            Skill(
                name="Otherworldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.VOID,
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


def _make_state(
    monk_char: Character,
    opponent_char: Character,
    monk_void: int | None = None,
    monk_weapon: Weapon = UNARMED,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [monk_char.name, opponent_char.name],
        [monk_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    m_void = (
        monk_void if monk_void is not None
        else monk_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        monk_char.name, state,
        char=monk_char, weapon=monk_weapon, void_points=m_void,
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
    precepts_rank: int = 5,
    void_points: int | None = None,
    worldliness_rank: int | None = None,
    monk_weapon: Weapon = UNARMED,
    **ring_overrides: int,
) -> BrotherhoodMonkFighter:
    """Create a BrotherhoodMonkFighter with a full CombatState."""
    char = _make_monk(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        precepts_rank=precepts_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, monk_void=void_points, monk_weapon=monk_weapon)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, BrotherhoodMonkFighter)
    return fighter


class TestBrotherhoodMonkInit:
    """Initialization and state tracking."""

    def test_worldliness_void_initialized(self) -> None:
        """worldliness_void equals the Worldliness skill rank."""
        for rank in range(6):
            fighter = _make_fighter(knack_rank=rank)
            assert fighter.worldliness_void == rank

    def test_worldliness_void_custom_rank(self) -> None:
        """worldliness_void can differ from knack_rank."""
        fighter = _make_fighter(knack_rank=3, worldliness_rank=5)
        assert fighter.worldliness_void == 5

    def test_free_raise_pool_at_3rd_dan(self) -> None:
        """Pool is 2 * precepts_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_free_raise_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, precepts_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0

    def test_counterattack_used_starts_false(self) -> None:
        """_counterattack_used_this_round starts False."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter._counterattack_used_this_round is False


class TestAttackHooks:
    """Attack-related hooks."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_attack_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on attack."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_attack_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0

    def test_sa_attack_bonus_at_dan_2(self) -> None:
        """2nd Dan gives +5 free raise on attack."""
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 5
        assert "monk 2nd Dan" in note

    def test_sa_attack_bonus_at_dan_1(self) -> None:
        """No bonus before 2nd Dan."""
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 0
        assert note == ""


class TestSADamageBonus:
    """SA: +1 kept die on unarmed damage."""

    def test_unarmed_gives_extra_kept(self) -> None:
        """sa_attack_damage_bonus returns (0, 1) with UNARMED weapon."""
        fighter = _make_fighter(knack_rank=1, monk_weapon=UNARMED)
        extra_rolled, extra_kept = fighter.sa_attack_damage_bonus(0)
        assert extra_rolled == 0
        assert extra_kept == 1

    def test_katana_gives_no_extra(self) -> None:
        """sa_attack_damage_bonus returns (0, 0) with KATANA weapon."""
        fighter = _make_fighter(knack_rank=1, monk_weapon=KATANA)
        extra_rolled, extra_kept = fighter.sa_attack_damage_bonus(0)
        assert extra_rolled == 0
        assert extra_kept == 0


class TestFirstDanDamage:
    """1st Dan: +1 rolled die on damage."""

    def test_weapon_rolled_boost_at_dan_1(self) -> None:
        """weapon_rolled_boost returns weapon_rolled + 1 at dan >= 1."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.weapon_rolled_boost(0, 2) == 1
        assert fighter.weapon_rolled_boost(4, 2) == 5

    def test_weapon_rolled_boost_at_dan_0(self) -> None:
        """weapon_rolled_boost returns weapon_rolled at dan 0."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.weapon_rolled_boost(0, 2) == 0
        assert fighter.weapon_rolled_boost(4, 2) == 4


class TestFirstDanWoundCheck:
    """1st Dan: +1 rolled die on wound checks."""

    def test_wound_check_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on wound check."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestThirdDanFreeRaises:
    """3rd Dan: Free raise pool mechanics."""

    def test_spend_on_attack_miss(self) -> None:
        """Spend minimum raises to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 5
        assert fighter._free_raises == 9
        assert "1 free raise" in note

    def test_spend_on_attack_larger_deficit(self) -> None:
        """Spend multiple raises for larger deficit."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(13, 25, 3, "Generic")
        assert bonus == 15
        assert fighter._free_raises == 7
        assert "3 free raise" in note

    def test_no_spend_when_hit(self) -> None:
        """Don't spend if already hitting."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_no_spend_when_gap_too_large(self) -> None:
        """Don't spend if can't bridge gap with max per roll."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(0, 26, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_pool_exhaustion(self) -> None:
        """Pool decreases with each spend."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 5
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 0
        bonus, _ = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0

    def test_wc_bonus_pool_total(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_total_before_3rd_dan(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, precepts_rank=5)
        assert fighter.wc_bonus_pool_total() == 0

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=2, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45

        wound_tracker.serious_wounds = 3
        sw_before = 0
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert not new_passed
        assert new_total == 29
        assert "1 free raise" in note
        assert wound_tracker.serious_wounds == 2

    def test_spend_to_pass_when_mortal(self) -> None:
        """Spend to pass if taking SW would be mortal."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5, earth=2)
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
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, precepts_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
        assert note == ""


class TestFourthDanParryReduction:
    """4th Dan: Failed parry does not reduce damage dice."""

    def test_no_reduction_at_dan_4(self) -> None:
        """damage_parry_reduction returns 0 at dan >= 4."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_parry_reduction(3) == 0

    def test_reduction_before_dan_4(self) -> None:
        """damage_parry_reduction returns defender_parry_rank at dan < 4."""
        fighter = _make_fighter(knack_rank=3)
        assert fighter.damage_parry_reduction(3) == 3

    def test_no_reduction_at_dan_5(self) -> None:
        """damage_parry_reduction returns 0 at dan 5."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.damage_parry_reduction(5) == 0


class TestFifthDanCounterattack:
    """5th Dan: Pre-damage counterattack."""

    def test_no_cancel_before_5th_dan(self) -> None:
        """try_cancel_before_damage returns (False, '') at dan < 5."""
        fighter = _make_fighter(knack_rank=4, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_no_cancel_when_already_used(self) -> None:
        """try_cancel_before_damage returns (False, '') when already used this round."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        fighter._counterattack_used_this_round = True
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_no_cancel_when_no_action_dice(self) -> None:
        """try_cancel_before_damage returns (False, '') when no action dice."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = []
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_no_cancel_when_survivable(self) -> None:
        """try_cancel_before_damage returns (False, '') when damage is survivable."""
        fighter = _make_fighter(knack_rank=5, earth=4, water=4)
        fighter.actions_remaining = [3, 5]
        result, note = fighter.try_cancel_before_damage(25, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_counterattack_fires_when_near_mortal(self) -> None:
        """Counterattack fires when projected damage is near-mortal."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2, fire=2)
        fighter.actions_remaining = [3, 5, 7]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30

        # Big attack that should project lethal damage
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        # Regardless of whether it cancels, the counterattack should fire
        assert note != ""
        assert "monk 5th Dan" in note
        assert fighter._counterattack_used_this_round is True
        # Cheapest die (3) should be consumed
        assert 3 not in fighter.actions_remaining

    def test_no_cancel_when_mortally_wounded(self) -> None:
        """No counterattack when monk is mortally wounded."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 4  # 2*earth = mortally wounded
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""


class TestOnRoundStart:
    """on_round_start resets per-round state."""

    def test_resets_counterattack_used(self) -> None:
        """Resets _counterattack_used_this_round to False."""
        fighter = _make_fighter(knack_rank=5)
        fighter._counterattack_used_this_round = True
        fighter.on_round_start()
        assert fighter._counterattack_used_this_round is False


class TestFactoryRegistration:
    """Brotherhood Monk creates via fighter factory."""

    def test_creates_brotherhood_monk_fighter(self) -> None:
        """create_fighter returns BrotherhoodMonkFighter for school='Brotherhood Monk'."""
        char = _make_monk()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, BrotherhoodMonkFighter)
