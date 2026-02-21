"""Tests for CourtierFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.courtier import CourtierFighter
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


def _make_courtier(
    name: str = "Courtier",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    tact_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    """Create a Courtier character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Courtier",
        school_ring=RingName.AIR,
        school_knacks=["Discern Honor", "Oppose Social", "Worldliness"],
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
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Oppose Social", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Worldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
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
    courtier_char: Character,
    opponent_char: Character,
    courtier_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [courtier_char.name, opponent_char.name],
        [courtier_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    c_void = (
        courtier_void if courtier_void is not None
        else courtier_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        courtier_char.name, state,
        char=courtier_char, weapon=KATANA, void_points=c_void,
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
    tact_rank: int = 5,
    void_points: int | None = None,
    **ring_overrides: int,
) -> CourtierFighter:
    """Create a CourtierFighter with a full CombatState."""
    char = _make_courtier(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        tact_rank=tact_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, courtier_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, CourtierFighter)
    return fighter


class TestChooseAttack:
    """Courtier always uses normal attack."""

    def test_always_attack(self) -> None:
        """choose_attack returns 'attack' at any dan."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_zero_dan_attack(self) -> None:
        """Even at dan 0 the Courtier attacks normally."""
        fighter = _make_fighter(knack_rank=0)
        choice, _ = fighter.choose_attack("Generic", 5)
        assert choice == "attack"


class TestSAAttackBonus:
    """SA: Add Air to attack rolls; 5th Dan doubles."""

    def test_sa_bonus_at_dan_0(self) -> None:
        """SA applies at any dan level."""
        fighter = _make_fighter(knack_rank=0, air=3)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 3
        assert "courtier SA" in note

    def test_sa_bonus_at_first_dan(self) -> None:
        """Air is added to attacks at 1st Dan."""
        fighter = _make_fighter(knack_rank=1, air=3)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 3
        assert "courtier SA" in note

    def test_sa_bonus_at_fourth_dan(self) -> None:
        """Still single Air at 4th Dan."""
        fighter = _make_fighter(knack_rank=4, air=4)
        bonus, _ = fighter.sa_attack_bonus(3)
        assert bonus == 4

    def test_sa_bonus_at_fifth_dan(self) -> None:
        """5th Dan doubles the Air bonus."""
        fighter = _make_fighter(knack_rank=5, air=4)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 8
        assert "5th Dan" in note

    def test_sa_bonus_default_air(self) -> None:
        """Air 2 (default) produces +2."""
        fighter = _make_fighter(knack_rank=1)
        bonus, _ = fighter.sa_attack_bonus(3)
        assert bonus == 2


class TestSADamageFlatBonus:
    """SA: Add Air to damage total."""

    def test_damage_flat_bonus(self) -> None:
        """Air is added to damage as flat bonus."""
        fighter = _make_fighter(knack_rank=1, air=3)
        bonus, note = fighter.sa_damage_flat_bonus()
        assert bonus == 3
        assert "courtier SA" in note
        assert "damage" in note

    def test_damage_flat_bonus_default(self) -> None:
        """Default Air 2 adds +2 to damage."""
        fighter = _make_fighter(knack_rank=0)
        bonus, _ = fighter.sa_damage_flat_bonus()
        assert bonus == 2


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan_extra_rolled(self) -> None:
        """1st Dan grants +1 rolled die."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan_no_extra(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0

    def test_fifth_dan_extra_rolled(self) -> None:
        """Higher dans still get +1."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.wound_check_extra_rolled() == 1


class TestFreeRaisePool:
    """3rd Dan: Free raise pool mechanics."""

    def test_pool_init_size(self) -> None:
        """Pool is 2 * tact_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_pool_init_lower_tact(self) -> None:
        """Pool scales with tact rank."""
        fighter = _make_fighter(knack_rank=3, tact_rank=3)
        assert fighter._free_raises == 6
        assert fighter._max_per_roll == 3

    def test_no_pool_before_third_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, tact_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0

    def test_spend_on_attack_miss(self) -> None:
        """Spend minimum raises to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        # Miss by 3 -> need 1 raise (+5 bridges it)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 5
        assert fighter._free_raises == 9
        assert "1 free raise" in note

    def test_spend_on_attack_larger_deficit(self) -> None:
        """Spend multiple raises for larger deficit."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        # Miss by 12 -> need 3 raises
        bonus, note = fighter.post_attack_roll_bonus(13, 25, 3, "Generic")
        assert bonus == 15
        assert fighter._free_raises == 7
        assert "3 free raise" in note

    def test_no_spend_when_hit(self) -> None:
        """Don't spend if already hitting."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_no_spend_when_gap_too_large(self) -> None:
        """Don't spend if can't bridge gap with max per roll."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        # Miss by 26 -> need 6 raises but max is 5
        bonus, note = fighter.post_attack_roll_bonus(0, 26, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_pool_exhaustion(self) -> None:
        """Pool decreases with each spend."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        # Spend 5 raises each time (miss by 25)
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 5
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 0
        # Now empty
        bonus, _ = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0

    def test_wc_bonus_pool_total(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_total_low_remaining(self) -> None:
        """When fewer raises remain than max per roll, uses remaining."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        fighter._free_raises = 2
        # min(2, 5) * 5 = 10
        assert fighter.wc_bonus_pool_total() == 10

    def test_wc_bonus_pool_total_before_3rd_dan(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, tact_rank=5)
        assert fighter.wc_bonus_pool_total() == 0


class TestFreeRaiseWoundCheck:
    """3rd Dan: Free raises on wound check."""

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC (plan example)."""
        # Use tact=2 so max_per_roll=2 to match plan example
        fighter = _make_fighter(knack_rank=3, tact_rank=2, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45

        # Fail WC: deficit=21, current_sw=3
        # After WC engine sets sw, we call post_wound_check
        wound_tracker.serious_wounds = 3  # engine added 3 SW
        sw_before = 0
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        # With max 2 raises: spend 1 → deficit=16, sw=2; spend 2 → deficit=11, sw=2
        # Minimum spend for best sw: 1 raise
        assert not new_passed
        assert new_total == 29
        assert "1 free raise" in note
        assert wound_tracker.serious_wounds == 2

    def test_spend_optimal_raises_for_best_sw(self) -> None:
        """Spend enough raises to achieve best possible SW reduction."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45

        # deficit=21, with max 5 raises:
        # spend 3 → deficit=6, sw=1 (best without passing)
        wound_tracker.serious_wounds = 3
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
            sw_before_wc=0,
        )
        assert not new_passed
        assert new_total == 39  # 24 + 15
        assert "3 free raise" in note
        assert wound_tracker.serious_wounds == 1

    def test_no_spend_to_pass_when_not_dying(self) -> None:
        """Don't spend to pass if not near mortal wound."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45

        # Deficit=5, current_sw=1, not dying (0+1 < 6)
        wound_tracker.serious_wounds = 1
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=40, attacker_name="Generic",
            sw_before_wc=0,
        )
        # Should not spend to pass (1 SW is acceptable)
        assert not new_passed
        assert note == ""

    def test_spend_to_pass_when_mortal(self) -> None:
        """Spend to pass if taking SW would be mortal."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5, earth=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 25

        # existing_sw=3, current_sw=1, total would be 4 >= 2*2=4 -> mortal
        wound_tracker.serious_wounds = 4  # engine added 1
        sw_before = 3
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        # deficit=5, spend 1 raise to pass
        assert new_passed
        assert note != ""

    def test_no_spend_when_passed(self) -> None:
        """Don't spend on already-passed wound check."""
        fighter = _make_fighter(knack_rank=3, tact_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, tact_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
        assert note == ""


class TestFourthDanTempVoid:
    """4th Dan: First hit per target grants temp void."""

    def test_first_hit_grants_void(self) -> None:
        """First hit on a target grants +1 temp void."""
        fighter = _make_fighter(knack_rank=4, void_points=2)
        initial_temp = fighter.temp_void
        note = fighter.post_damage_effect("Generic")
        assert fighter.temp_void == initial_temp + 1
        assert "temp void" in note
        assert "Generic" in note

    def test_second_hit_same_target_no_void(self) -> None:
        """Second hit on same target does not grant void."""
        fighter = _make_fighter(knack_rank=4, void_points=2)
        fighter.post_damage_effect("Generic")
        initial_temp = fighter.temp_void
        note = fighter.post_damage_effect("Generic")
        assert fighter.temp_void == initial_temp
        assert note == ""

    def test_different_target_grants_void(self) -> None:
        """Different target still grants void."""
        fighter = _make_fighter(knack_rank=4, void_points=2)
        fighter.post_damage_effect("Generic")
        initial_temp = fighter.temp_void
        fighter._targets_hit.discard("Other")
        note = fighter.post_damage_effect("Other")
        assert fighter.temp_void == initial_temp + 1
        assert "Other" in note

    def test_no_void_before_4th_dan(self) -> None:
        """No temp void before 4th Dan."""
        fighter = _make_fighter(knack_rank=3, void_points=2)
        initial_temp = fighter.temp_void
        note = fighter.post_damage_effect("Generic")
        assert fighter.temp_void == initial_temp
        assert note == ""


class TestFifthDanContested:
    """5th Dan: Air added to parry and wound checks."""

    def test_parry_bonus_at_5th_dan(self) -> None:
        """5th Dan adds Air to parry."""
        fighter = _make_fighter(knack_rank=5, air=4)
        assert fighter.parry_bonus() == 4

    def test_parry_bonus_before_5th(self) -> None:
        """No parry bonus before 5th Dan."""
        fighter = _make_fighter(knack_rank=4, air=4)
        assert fighter.parry_bonus() == 0

    def test_parry_bonus_description(self) -> None:
        """Parry bonus description mentions courtier 5th Dan."""
        fighter = _make_fighter(knack_rank=5, air=4)
        desc = fighter.parry_bonus_description(4)
        assert "courtier 5th Dan" in desc

    def test_wound_check_flat_bonus_at_5th(self) -> None:
        """5th Dan adds Air to wound check."""
        fighter = _make_fighter(knack_rank=5, air=4)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 4
        assert "5th Dan" in note

    def test_wound_check_flat_bonus_before_5th(self) -> None:
        """No WC flat bonus before 5th Dan."""
        fighter = _make_fighter(knack_rank=4, air=4)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""


class TestParryReluctance:
    """Courtier almost never parries — attrition playstyle."""

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
        """Moderate attack with no extra dice — does not parry."""
        # attack_total == attack_tn → 0 extra dice, healthy courtier
        fighter = _make_fighter(knack_rank=3, air=3, earth=3, water=3)
        assert fighter.should_reactive_parry(
            attack_total=25, attack_tn=25,
            weapon_rolled=4, attacker_fire=2,
        ) is False

    def test_no_parry_with_extra_dice_when_healthy(self) -> None:
        """Attack with extra dice but far from mortal — does not parry."""
        # attack_total 35 vs tn 25 → 2 extra dice, but 0 SW and earth=3
        fighter = _make_fighter(knack_rank=3, air=3, earth=3, water=3)
        assert fighter.should_reactive_parry(
            attack_total=35, attack_tn=25,
            weapon_rolled=4, attacker_fire=2,
        ) is False

    def test_parries_when_near_mortal(self) -> None:
        """Near mortal wound AND significant incoming damage — parries."""
        # earth=2, mortal at 4 SW. Give 3 existing SW + lots of LW.
        # Big hit with extra dice should project enough damage to push over.
        fighter = _make_fighter(knack_rank=3, air=3, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        # attack_total 40 vs tn 25 → 3 extra dice → big damage
        assert fighter.should_reactive_parry(
            attack_total=40, attack_tn=25,
            weapon_rolled=4, attacker_fire=3,
        ) is True

    def test_no_parry_when_healthy_despite_big_hit(self) -> None:
        """Even a large hit doesn't trigger parry if SW safely below mortal."""
        # earth=4, mortal at 8 SW. With 0 SW, huge buffer.
        fighter = _make_fighter(knack_rank=3, air=3, earth=4, water=4)
        assert fighter.should_reactive_parry(
            attack_total=40, attack_tn=25,
            weapon_rolled=4, attacker_fire=3,
        ) is False


class TestWorldlinessVoidPool:
    """Worldliness knack provides a separate void point pool."""

    def test_worldliness_void_initialized_to_knack_rank(self) -> None:
        """worldliness_void equals the Worldliness skill rank."""
        for rank in range(6):
            fighter = _make_fighter(knack_rank=rank)
            assert fighter.worldliness_void == rank

    def test_total_void_includes_worldliness(self) -> None:
        """total_void sums regular + temp + worldliness."""
        fighter = _make_fighter(knack_rank=3, void_points=2)
        fighter.temp_void = 1
        # regular=2, temp=1, worldliness=3
        assert fighter.total_void == 6

    def test_spend_order_temp_regular_worldliness(self) -> None:
        """Spending drains temp first, then regular, then worldliness."""
        fighter = _make_fighter(knack_rank=2, void_points=1)
        fighter.temp_void = 1
        # Available: temp=1, regular=1, worldliness=2 → total=4
        assert fighter.total_void == 4

        from_temp, from_reg, from_wl = fighter.spend_void(4)
        assert from_temp == 1
        assert from_reg == 1
        assert from_wl == 2
        assert fighter.temp_void == 0
        assert fighter.void_points == 0
        assert fighter.worldliness_void == 0

    def test_spend_worldliness_partial(self) -> None:
        """Only worldliness is consumed when temp and regular are empty."""
        fighter = _make_fighter(knack_rank=3, void_points=0)
        fighter.temp_void = 0
        # worldliness=3 only
        from_temp, from_reg, from_wl = fighter.spend_void(2)
        assert from_temp == 0
        assert from_reg == 0
        assert from_wl == 2
        assert fighter.worldliness_void == 1

    def test_worldliness_not_touched_when_others_suffice(self) -> None:
        """Worldliness pool is preserved when temp+regular cover the cost."""
        fighter = _make_fighter(knack_rank=3, void_points=2)
        fighter.temp_void = 1
        from_temp, from_reg, from_wl = fighter.spend_void(2)
        assert from_wl == 0
        assert fighter.worldliness_void == 3

    def test_non_courtier_has_zero_worldliness(self) -> None:
        """Non-courtier fighters have worldliness_void == 0."""
        char = _make_generic()
        opp = _make_courtier()
        state = _make_state(opp, char)
        fighter = state.fighters[char.name]
        assert not isinstance(fighter, CourtierFighter)
        assert fighter.worldliness_void == 0


class TestFactoryRegistration:
    """Courtier creates via fighter factory."""

    def test_creates_courtier_fighter(self) -> None:
        """create_fighter returns CourtierFighter for school='Courtier'."""
        char = _make_courtier()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, CourtierFighter)
