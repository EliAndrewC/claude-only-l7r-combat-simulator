"""Tests for IkomaBardFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.ikoma_bard import IkomaBardFighter
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


def _make_ikoma_bard(
    name: str = "Ikoma Bard",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    bragging_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create an Ikoma Bard character."""
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
        school="Ikoma Bard",
        school_ring=RingName.WATER,
        school_knacks=["Discern Honor", "Oppose Knowledge", "Oppose Social"],
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
                name="Bragging", rank=bragging_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Oppose Knowledge", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Oppose Social", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
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
    bard_char: Character,
    opponent_char: Character,
    bard_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [bard_char.name, opponent_char.name],
        [bard_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    b_void = (
        bard_void if bard_void is not None
        else bard_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        bard_char.name, state,
        char=bard_char, weapon=KATANA, void_points=b_void,
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
    bragging_rank: int = 5,
    void_points: int | None = None,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> IkomaBardFighter:
    """Create an IkomaBardFighter with a full CombatState."""
    char = _make_ikoma_bard(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        bragging_rank=bragging_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, bard_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, IkomaBardFighter)
    return fighter


class TestIkomaBardInit:
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
        """Pool is 2 * bragging_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_free_raise_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, bragging_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0

    def test_sa_uses_starts_at_zero(self) -> None:
        """SA uses counter starts at 0."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter._sa_uses_this_round == 0

    def test_max_sa_per_round_1_before_5th_dan(self) -> None:
        """Max SA per round is 1 before 5th Dan."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter._max_sa_per_round == 1

    def test_max_sa_per_round_2_at_5th_dan(self) -> None:
        """Max SA per round is 2 at 5th Dan."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter._max_sa_per_round == 2


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

    def test_attack_extra_rolled_at_dan_5(self) -> None:
        """Higher dans still get +1."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.attack_extra_rolled() == 1

    def test_sa_attack_bonus_at_dan_2(self) -> None:
        """2nd Dan gives +5 free raise on attack."""
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 5
        assert "ikoma bard 2nd Dan" in note

    def test_sa_attack_bonus_at_dan_1(self) -> None:
        """No bonus before 2nd Dan."""
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 0
        assert note == ""

    def test_sa_attack_bonus_at_dan_5(self) -> None:
        """5th Dan still gets the +5 free raise."""
        fighter = _make_fighter(knack_rank=5)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 5


class TestOffensiveSA:
    """SA: Force opponent to parry."""

    def test_sa_fires_when_available(self) -> None:
        """sa_force_parry returns True when SA available and opponent has die."""
        fighter = _make_fighter(knack_rank=1)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [3, 5]
        result, note = fighter.sa_force_parry("Generic", 3)
        assert result is True
        assert "ikoma bard SA" in note
        assert fighter._sa_uses_this_round == 1

    def test_sa_fails_when_opponent_no_dice(self) -> None:
        """sa_force_parry returns False when opponent has no action dice."""
        fighter = _make_fighter(knack_rank=1)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = []
        result, note = fighter.sa_force_parry("Generic", 3)
        assert result is False
        assert note == ""

    def test_sa_fails_when_used_this_round(self) -> None:
        """sa_force_parry returns False when SA already used this round."""
        fighter = _make_fighter(knack_rank=1)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [3, 5]
        fighter._sa_uses_this_round = 1
        result, note = fighter.sa_force_parry("Generic", 3)
        assert result is False
        assert note == ""

    def test_5th_dan_can_use_twice(self) -> None:
        """At 5th Dan, can use SA twice per round."""
        fighter = _make_fighter(knack_rank=5)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [1, 3, 5]

        result1, _ = fighter.sa_force_parry("Generic", 3)
        assert result1 is True
        assert fighter._sa_uses_this_round == 1

        result2, _ = fighter.sa_force_parry("Generic", 5)
        assert result2 is True
        assert fighter._sa_uses_this_round == 2

    def test_5th_dan_blocked_after_two_uses(self) -> None:
        """At 5th Dan, SA is blocked after 2 uses."""
        fighter = _make_fighter(knack_rank=5)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [1, 3, 5]
        fighter._sa_uses_this_round = 2
        result, _ = fighter.sa_force_parry("Generic", 3)
        assert result is False


class TestDefensiveSA:
    """5th Dan: Cancel incoming attack with defensive SA."""

    def test_no_cancel_before_5th_dan(self) -> None:
        """try_defensive_sa returns '' at dan < 5."""
        fighter = _make_fighter(knack_rank=4, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        result = fighter.try_defensive_sa(40, 25, 4, 3, "Generic")
        assert result == ""

    def test_no_cancel_when_sa_used(self) -> None:
        """try_defensive_sa returns '' when SA already used."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        fighter._sa_uses_this_round = 2
        result = fighter.try_defensive_sa(40, 25, 4, 3, "Generic")
        assert result == ""

    def test_cancel_when_near_mortal(self) -> None:
        """try_defensive_sa cancels when attack would be near-mortal."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        # Big attack with extra dice — should project lethal damage
        result = fighter.try_defensive_sa(40, 25, 4, 3, "Generic")
        assert result != ""
        assert "ikoma bard 5th Dan" in result
        assert fighter._sa_uses_this_round == 1

    def test_no_cancel_when_survivable(self) -> None:
        """try_defensive_sa returns '' when damage is survivable."""
        # Healthy fighter — no need to cancel
        fighter = _make_fighter(knack_rank=5, earth=4, water=4)
        result = fighter.try_defensive_sa(25, 25, 4, 2, "Generic")
        assert result == ""

    def test_increments_sa_uses(self) -> None:
        """Defensive SA increments _sa_uses_this_round."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        assert fighter._sa_uses_this_round == 0
        fighter.try_defensive_sa(40, 25, 4, 3, "Generic")
        assert fighter._sa_uses_this_round == 1


class TestFourthDanDamage:
    """4th Dan: Minimum 10 rolled dice on unparried damage."""

    def test_min_10_when_unparried_no_extra_kept(self) -> None:
        """Returns max(10, current) when not parried and no extra kept."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_min_rolled(6, False, 0) == 10

    def test_no_change_when_already_above_10(self) -> None:
        """Returns current if already >= 10."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_min_rolled(12, False, 0) == 12

    def test_no_change_when_parried(self) -> None:
        """Returns current when parried."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_min_rolled(6, True, 0) == 6

    def test_no_change_when_extra_kept(self) -> None:
        """Returns current when extra_kept > 0."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_min_rolled(6, False, 1) == 6

    def test_no_change_before_4th_dan(self) -> None:
        """Returns current when dan < 4."""
        fighter = _make_fighter(knack_rank=3)
        assert fighter.damage_min_rolled(6, False, 0) == 6


class TestThirdDanFreeRaises:
    """3rd Dan: Free raise pool mechanics."""

    def test_spend_on_attack_miss(self) -> None:
        """Spend minimum raises to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 5
        assert fighter._free_raises == 9
        assert "1 free raise" in note

    def test_spend_on_attack_larger_deficit(self) -> None:
        """Spend multiple raises for larger deficit."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(13, 25, 3, "Generic")
        assert bonus == 15
        assert fighter._free_raises == 7
        assert "3 free raise" in note

    def test_no_spend_when_hit(self) -> None:
        """Don't spend if already hitting."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_no_spend_when_gap_too_large(self) -> None:
        """Don't spend if can't bridge gap with max per roll."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(0, 26, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_pool_exhaustion(self) -> None:
        """Pool decreases with each spend."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 5
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 0
        bonus, _ = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0

    def test_wc_bonus_pool_total(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_total_before_3rd_dan(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, bragging_rank=5)
        assert fighter.wc_bonus_pool_total() == 0

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=2, earth=3)
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
        fighter = _make_fighter(knack_rank=3, bragging_rank=5, earth=2)
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
        fighter = _make_fighter(knack_rank=3, bragging_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, bragging_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
        assert note == ""


class TestWoundCheck:
    """Wound check extra rolled die."""

    def test_wound_check_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on wound check."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


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


class TestOnRoundStart:
    """on_round_start resets per-round state."""

    def test_resets_sa_uses(self) -> None:
        """Resets _sa_uses_this_round to 0."""
        fighter = _make_fighter(knack_rank=1)
        fighter._sa_uses_this_round = 1
        fighter.on_round_start()
        assert fighter._sa_uses_this_round == 0

    def test_clears_stored_parry(self) -> None:
        """Clears _stored_parry_total on self."""
        fighter = _make_fighter(knack_rank=1)
        fighter._stored_parry_total = 30
        fighter.on_round_start()
        assert fighter._stored_parry_total == 0


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled (lines 84-88)."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Ikoma Bard does not spend void on attack."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_with_2nd_dan_bonus(self) -> None:
        """Non-crippled 2nd Dan uses known_bonus=5."""
        fighter = _make_fighter(knack_rank=2, void_points=5, fire=3, void=3)
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestDefensiveSAOpponentNone:
    """try_defensive_sa when opponent not found (line 146)."""

    def test_opponent_none_returns_empty(self) -> None:
        """When opponent is not in fighters, returns ''."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        # Use an attacker_name not in fighters
        result = fighter.try_defensive_sa(40, 25, 4, 3, "Nonexistent")
        assert result == ""


class TestDefensiveSANotNearMortal:
    """try_defensive_sa: survivable projected damage (line 168)."""

    def test_projected_damage_not_near_mortal(self) -> None:
        """When wc_deficit > 0 but existing_sw + projected_sw < 2*earth.

        High earth=5 -> mortal threshold = 10.
        Low water=1 -> expected WC is low.
        Moderate existing LW -> projected_lw > expected_wc -> wc_deficit > 0.
        But existing_sw(0) + projected_sw(small) < 2*5 = 10 -> not mortal.
        """
        fighter = _make_fighter(knack_rank=5, earth=5, water=1, air=1, bragging_rank=1)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 0
        wound_tracker.light_wounds = 40
        # attack_total=30, tn=25 -> extra_dice=(30-25)//5=1
        # damage_rolled = weapon_rolled(4) + attacker_fire(2) + extra_dice(1) = 7
        # weapon_kept = 2 (katana), expected_damage ~ estimate_roll(7, 2) ~ 17
        # projected_lw = 40 + 17 = 57
        # water=1, water_rolled=2 (5th dan), expected_wc ~ 8
        # pool_bonus (bragging=1, knack=5): 2 raises, usable=1, total=5
        # expected_wc = 8 + 5 = 13
        # wc_deficit = 57 - 13 = 44 > 0
        # projected_sw = 1 + 44//10 = 5
        # existing_sw(0) + 5 = 5 < 2*5=10 -> NOT near mortal -> line 168
        result = fighter.try_defensive_sa(30, 25, 4, 2, "Generic")
        assert result == ""


class TestPostWoundCheckDeficitLeZero:
    """post_wound_check: deficit <= 0 returns early (line 240)."""

    def test_deficit_le_zero_returns_early(self) -> None:
        """When wc_total >= light_wounds, no raises spent."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=25, attacker_name="Generic",
        )
        assert not new_passed
        assert new_total == 25
        assert note == ""
        assert fighter._free_raises == 10


class TestPostWoundCheckBestSpendZero:
    """post_wound_check: best_spend <= 0 returns early (line 264)."""

    def test_best_spend_zero_returns_early(self) -> None:
        """When spending raises cannot reduce SW, returns early."""
        fighter = _make_fighter(knack_rank=3, bragging_rank=1, earth=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 50
        wound_tracker.serious_wounds = 1
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=46, attacker_name="Generic",
            sw_before_wc=0,
        )
        assert note == ""
        assert fighter._free_raises == 2


class TestFactoryRegistration:
    """Ikoma Bard creates via fighter factory."""

    def test_creates_ikoma_bard_fighter(self) -> None:
        """create_fighter returns IkomaBardFighter for school='Ikoma Bard'."""
        char = _make_ikoma_bard()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, IkomaBardFighter)
