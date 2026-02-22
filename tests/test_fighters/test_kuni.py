"""Tests for KuniWitchHunterFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.kuni import KuniWitchHunterFighter
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


def _make_kuni(
    name: str = "Kuni Witch Hunter",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    investigation_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    """Create a Kuni Witch Hunter character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Kuni Witch Hunter",
        school_ring=RingName.EARTH,
        school_knacks=["Detect Taint", "Iaijutsu", "Presence"],
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
                name="Investigation", rank=investigation_rank,
                skill_type=SkillType.BASIC, ring=RingName.EARTH,
            ),
            Skill(
                name="Detect Taint", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.EARTH,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Presence", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.EARTH,
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
    kuni_char: Character,
    opponent_char: Character,
    kuni_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [kuni_char.name, opponent_char.name],
        [kuni_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    k_void = (
        kuni_void if kuni_void is not None
        else kuni_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        kuni_char.name, state,
        char=kuni_char, weapon=KATANA, void_points=k_void,
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
) -> KuniWitchHunterFighter:
    """Create a KuniWitchHunterFighter with a full CombatState."""
    char = _make_kuni(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        investigation_rank=investigation_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, kuni_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, KuniWitchHunterFighter)
    return fighter


class TestKuniInit:
    """Initialization and state tracking."""

    def test_free_raise_pool_at_3rd_dan(self) -> None:
        """Pool is 2 * investigation_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_free_raise_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, investigation_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0

    def test_parry_only_starts_inactive(self) -> None:
        """_parry_only_active starts False."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter._parry_only_active is False


class TestAttackHooks:
    """Attack-related hooks."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_attack_extra_rolled_always_zero(self) -> None:
        """No extra dice on attack (1st Dan is damage/WC only)."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan)
            assert fighter.attack_extra_rolled() == 0


class TestDamageHooks:
    """Damage-related hooks."""

    def test_weapon_rolled_boost_at_dan_1(self) -> None:
        """1st Dan: +1 rolled die on damage."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.weapon_rolled_boost() == 1

    def test_weapon_rolled_boost_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.weapon_rolled_boost() == 0

    def test_weapon_rolled_boost_at_dan_5(self) -> None:
        """Higher dans still get +1."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.weapon_rolled_boost() == 1


class TestWoundCheck:
    """Wound check extra dice."""

    def test_wound_check_extra_rolled_at_dan_0(self) -> None:
        """SA gives +1 rolled die even at dan 0."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_at_dan_1(self) -> None:
        """SA +1 and 1st Dan +1 = +2."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 2

    def test_wound_check_extra_kept(self) -> None:
        """SA gives +1 kept die on wound checks."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_kept() == 1


class TestFourthDanInitiative:
    """4th Dan: Extra parry-only action die."""

    def test_post_initiative_adds_die(self) -> None:
        """4th Dan adds an extra die to actions."""
        fighter = _make_fighter(knack_rank=4)
        old_actions = [3, 7]
        new_actions = fighter.post_initiative(
            rolled_dice=[1, 3, 5, 7, 9], kept_dice=old_actions,
        )
        assert len(new_actions) == 3
        assert fighter._parry_only_active is True

    def test_post_initiative_no_extra_before_4th_dan(self) -> None:
        """No extra die before 4th Dan."""
        fighter = _make_fighter(knack_rank=3)
        old_actions = [3, 7]
        new_actions = fighter.post_initiative(
            rolled_dice=[1, 3, 5, 7, 9], kept_dice=old_actions,
        )
        assert len(new_actions) == 2
        assert fighter._parry_only_active is False

    def test_post_initiative_description(self) -> None:
        """Description mentions parry-only die."""
        fighter = _make_fighter(knack_rank=4)
        old_actions = [3, 7]
        new_actions = fighter.post_initiative(
            rolled_dice=[1, 3, 5, 7, 9], kept_dice=old_actions,
        )
        desc = fighter.post_initiative_description(old_actions, new_actions)
        assert "parry-only" in desc

    def test_consume_attack_die_skips_lowest(self) -> None:
        """Parry-only die causes lowest die attack to be skipped."""
        fighter = _make_fighter(knack_rank=4)
        fighter._parry_only_active = True
        fighter.actions_remaining = [2, 5, 8]
        # Phase 2 is the lowest — should be skipped
        result = fighter.consume_attack_die(phase=2)
        assert result is None
        assert 2 not in fighter.actions_remaining
        assert fighter._parry_only_active is False

    def test_consume_attack_die_normal_for_higher_phase(self) -> None:
        """Non-lowest phase attacks normally even when parry-only active."""
        fighter = _make_fighter(knack_rank=4)
        fighter._parry_only_active = True
        fighter.actions_remaining = [2, 5, 8]
        # Phase 5 is NOT the lowest — should attack normally
        result = fighter.consume_attack_die(phase=5)
        assert result == 5
        assert 5 not in fighter.actions_remaining

    def test_on_round_start_resets_parry_only(self) -> None:
        """on_round_start resets _parry_only_active."""
        fighter = _make_fighter(knack_rank=4)
        fighter._parry_only_active = True
        fighter.on_round_start()
        assert fighter._parry_only_active is False


class TestThirdDanFreeRaises:
    """3rd Dan: Free raise pool mechanics."""

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

    def test_wc_bonus_pool_total(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_total_before_3rd_dan(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, investigation_rank=5)
        assert fighter.wc_bonus_pool_total() == 0

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC."""
        fighter = _make_fighter(knack_rank=3, investigation_rank=2, earth=3)
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


class TestFifthDanReflection:
    """5th Dan: Damage reflection."""

    def test_no_reflect_before_5th_dan(self) -> None:
        """No reflection at dan < 5."""
        fighter = _make_fighter(knack_rank=4, earth=3, water=3)
        reflected, self_extra, note = fighter.reflect_damage_after_wc(
            damage_taken=20, attacker_name="Generic",
        )
        assert reflected == 0
        assert self_extra == 0
        assert note == ""

    def test_no_reflect_zero_damage(self) -> None:
        """No reflection on 0 damage."""
        fighter = _make_fighter(knack_rank=5, earth=3, water=3)
        reflected, self_extra, note = fighter.reflect_damage_after_wc(
            damage_taken=0, attacker_name="Generic",
        )
        assert reflected == 0
        assert self_extra == 0
        assert note == ""

    def test_reflects_when_survivable(self) -> None:
        """Reflects full damage when extra self-damage is survivable."""
        fighter = _make_fighter(knack_rank=5, earth=4, water=4)
        reflected, self_extra, note = fighter.reflect_damage_after_wc(
            damage_taken=10, attacker_name="Generic",
        )
        assert reflected == 10
        assert self_extra == 5
        assert "reflects 10 LW" in note

    def test_no_reflect_when_would_die(self) -> None:
        """No reflection when extra self-damage would kill."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2, investigation_rank=0)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 50
        reflected, self_extra, note = fighter.reflect_damage_after_wc(
            damage_taken=40, attacker_name="Generic",
        )
        assert reflected == 0
        assert self_extra == 0
        assert note == ""


class TestParryDecisions:
    """Parry decisions — tank hits strategy."""

    def test_never_predeclares(self) -> None:
        """should_predeclare_parry returns False at all dans."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan, air=4)
            assert fighter.should_predeclare_parry(25, 3) is False

    def test_cannot_interrupt(self) -> None:
        """can_interrupt returns False."""
        fighter = _make_fighter(knack_rank=3, air=3)
        assert fighter.can_interrupt() is False

    def test_no_parry_on_normal_hit(self) -> None:
        """Moderate attack — does not parry."""
        fighter = _make_fighter(knack_rank=3, air=3, earth=3, water=3)
        assert fighter.should_reactive_parry(
            attack_total=25, attack_tn=25,
            weapon_rolled=4, attacker_fire=2,
        ) is False

    def test_parries_when_near_mortal(self) -> None:
        """Near mortal wound — parries."""
        fighter = _make_fighter(knack_rank=3, air=3, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        assert fighter.should_reactive_parry(
            attack_total=40, attack_tn=25,
            weapon_rolled=4, attacker_fire=3,
        ) is True


class TestFactoryRegistration:
    """Kuni Witch Hunter creates via fighter factory."""

    def test_creates_kuni_fighter(self) -> None:
        """create_fighter returns KuniWitchHunterFighter for school='Kuni Witch Hunter'."""
        char = _make_kuni()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, KuniWitchHunterFighter)
