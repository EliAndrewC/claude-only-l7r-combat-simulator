"""Tests for ShosuroActorFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.shosuro import ShosuroActorFighter
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


def _make_shosuro(
    name: str = "Shosuro Actor",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    acting_rank: int = 5,
    sincerity_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    """Create a Shosuro Actor character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Shosuro Actor",
        school_ring=RingName.AIR,
        school_knacks=["Athletics", "Discern Honor", "Pontificate"],
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
                name="Acting", rank=acting_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Sincerity", rank=sincerity_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Athletics", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Pontificate", rank=knack_rank,
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
    shosuro_char: Character,
    opponent_char: Character,
    shosuro_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [shosuro_char.name, opponent_char.name],
        [shosuro_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    s_void = (
        shosuro_void if shosuro_void is not None
        else shosuro_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        shosuro_char.name, state,
        char=shosuro_char, weapon=KATANA, void_points=s_void,
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
    acting_rank: int = 5,
    sincerity_rank: int = 5,
    void_points: int | None = None,
    **ring_overrides: int,
) -> ShosuroActorFighter:
    """Create a ShosuroActorFighter with a full CombatState."""
    char = _make_shosuro(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        acting_rank=acting_rank,
        sincerity_rank=sincerity_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, shosuro_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, ShosuroActorFighter)
    return fighter


class TestShosuroInit:
    """Initialization and state tracking."""

    def test_acting_rank_stored(self) -> None:
        """Acting rank is stored from skill."""
        fighter = _make_fighter(acting_rank=3)
        assert fighter._acting_rank == 3

    def test_free_raise_pool_at_3rd_dan(self) -> None:
        """Pool is 2 * sincerity_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_free_raise_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, sincerity_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0


class TestAttackHooks:
    """Attack-related hooks."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_attack_extra_rolled_sa_only(self) -> None:
        """SA: acting dice on attack (no 1st Dan bonus yet)."""
        fighter = _make_fighter(knack_rank=0, acting_rank=3)
        assert fighter.attack_extra_rolled() == 3

    def test_attack_extra_rolled_sa_plus_1st_dan(self) -> None:
        """SA + 1st Dan: acting + 1 on attack."""
        fighter = _make_fighter(knack_rank=1, acting_rank=3)
        assert fighter.attack_extra_rolled() == 4

    def test_attack_extra_rolled_at_dan_5(self) -> None:
        """Higher dans still get acting + 1."""
        fighter = _make_fighter(knack_rank=5, acting_rank=5)
        assert fighter.attack_extra_rolled() == 6


class TestParryExtraRolled:
    """Parry extra dice from SA."""

    def test_parry_extra_rolled_sa(self) -> None:
        """SA: acting dice on parry."""
        fighter = _make_fighter(acting_rank=4)
        assert fighter.parry_extra_rolled() == 4

    def test_parry_extra_rolled_zero_acting(self) -> None:
        """No extra parry dice with 0 acting."""
        fighter = _make_fighter(acting_rank=0)
        assert fighter.parry_extra_rolled() == 0


class TestWoundCheck:
    """Wound check extra dice."""

    def test_wound_check_extra_rolled_sa_only(self) -> None:
        """SA: acting dice on wound check (no 1st Dan)."""
        fighter = _make_fighter(knack_rank=0, acting_rank=3)
        assert fighter.wound_check_extra_rolled() == 3

    def test_wound_check_extra_rolled_sa_plus_1st_dan(self) -> None:
        """SA + 1st Dan: acting + 1 on wound check."""
        fighter = _make_fighter(knack_rank=1, acting_rank=3)
        assert fighter.wound_check_extra_rolled() == 4

    def test_wound_check_extra_rolled_at_dan_5(self) -> None:
        """Higher dans still get acting + 1."""
        fighter = _make_fighter(knack_rank=5, acting_rank=5)
        assert fighter.wound_check_extra_rolled() == 6


class TestFifthDanPostRollModify:
    """5th Dan: Add lowest 3 dice to result."""

    def test_adds_lowest_3(self) -> None:
        """Adds sum of lowest 3 dice to total."""
        fighter = _make_fighter(knack_rank=5)
        all_dice = [10, 8, 6, 4, 2, 1]
        kept_count = 3
        total = 24  # 10 + 8 + 6
        result = fighter.post_roll_modify(
            all_dice, kept_count, total, 25, "attack", explode=True,
        )
        # lowest 3 are [1, 2, 4] → bonus = 7
        _, _, new_total, _, note = result
        assert new_total == 31
        assert "shosuro 5th Dan" in note
        assert "+7" in note

    def test_no_modify_before_5th_dan(self) -> None:
        """No modification at dan < 5."""
        fighter = _make_fighter(knack_rank=4, acting_rank=5)
        all_dice = [10, 8, 6, 4, 2, 1]
        kept_count = 3
        total = 24
        result = fighter.post_roll_modify(
            all_dice, kept_count, total, 25, "attack", explode=True,
        )
        _, _, new_total, _, note = result
        assert new_total == 24
        assert note == ""

    def test_no_modify_on_damage(self) -> None:
        """No modification on damage rolls."""
        fighter = _make_fighter(knack_rank=5)
        all_dice = [10, 8, 6, 4, 2, 1]
        kept_count = 3
        total = 24
        result = fighter.post_roll_modify(
            all_dice, kept_count, total, 25, "damage", explode=True,
        )
        _, _, new_total, _, note = result
        assert new_total == 24
        assert note == ""

    def test_applies_to_parry(self) -> None:
        """5th Dan applies to parry context."""
        fighter = _make_fighter(knack_rank=5)
        all_dice = [10, 8, 6, 4, 2]
        kept_count = 2
        total = 18  # 10 + 8
        result = fighter.post_roll_modify(
            all_dice, kept_count, total, 20, "parry", explode=True,
        )
        # lowest 3 are [2, 4, 6] → bonus = 12
        _, _, new_total, _, note = result
        assert new_total == 30
        assert "shosuro 5th Dan" in note

    def test_applies_to_wound_check(self) -> None:
        """5th Dan applies to wound_check context."""
        fighter = _make_fighter(knack_rank=5)
        all_dice = [10, 8, 6, 4, 2]
        kept_count = 2
        total = 18
        result = fighter.post_roll_modify(
            all_dice, kept_count, total, 20, "wound_check", explode=True,
        )
        _, _, new_total, _, note = result
        assert new_total == 30
        assert "shosuro 5th Dan" in note

    def test_not_enough_dice(self) -> None:
        """No modification if fewer than 3 dice."""
        fighter = _make_fighter(knack_rank=5)
        all_dice = [10, 8]
        kept_count = 2
        total = 18
        result = fighter.post_roll_modify(
            all_dice, kept_count, total, 20, "attack", explode=True,
        )
        _, _, new_total, _, note = result
        assert new_total == 18
        assert note == ""


class TestThirdDanFreeRaises:
    """3rd Dan: Free raise pool mechanics."""

    def test_spend_on_attack_miss(self) -> None:
        """Spend minimum raises to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 5
        assert fighter._free_raises == 9
        assert "1 free raise" in note

    def test_spend_on_attack_larger_deficit(self) -> None:
        """Spend multiple raises for larger deficit."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(13, 25, 3, "Generic")
        assert bonus == 15
        assert fighter._free_raises == 7
        assert "3 free raise" in note

    def test_no_spend_when_hit(self) -> None:
        """Don't spend if already hitting."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_no_spend_when_gap_too_large(self) -> None:
        """Don't spend if can't bridge gap with max per roll."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(0, 26, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_pool_exhaustion(self) -> None:
        """Pool decreases with each spend."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 5
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 0
        bonus, _ = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0

    def test_wc_bonus_pool_total(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_total_before_3rd_dan(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, sincerity_rank=5)
        assert fighter.wc_bonus_pool_total() == 0

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=2, earth=3)
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
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5, earth=2)
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
        fighter = _make_fighter(knack_rank=3, sincerity_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, sincerity_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
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


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled (lines 52-55)."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Shosuro does not spend void on attack."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_delegates(self) -> None:
        """Non-crippled Shosuro delegates to standard heuristic."""
        fighter = _make_fighter(knack_rank=3, void_points=5, fire=3, void=3)
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestPostRollModifyFewDice:
    """post_roll_modify 5th Dan with fewer than 3 dice returns early (line 87-89)."""

    def test_fewer_than_3_dice_returns_early(self) -> None:
        """When len(all_dice) < 3, returns early without adding bonus."""
        fighter = _make_fighter(knack_rank=5, acting_rank=2)
        all_dice = [8, 9]
        result = fighter.post_roll_modify(
            all_dice, 1, 17, 15, "attack", explode=True,
        )
        # Returns early because len(all_dice) < 3
        assert result[2] == 17  # total unchanged


class TestPostWoundCheckDeficitLeZero:
    """post_wound_check: deficit <= 0 returns early (line 149)."""

    def test_deficit_le_zero_returns_early(self) -> None:
        """When wc_total >= light_wounds, no raises spent."""
        fighter = _make_fighter(knack_rank=3, acting_rank=5, sincerity_rank=5, earth=3)
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
    """post_wound_check: best_spend <= 0 returns early (line 173)."""

    def test_best_spend_zero_returns_early(self) -> None:
        """When spending raises cannot reduce SW, returns early."""
        fighter = _make_fighter(
            knack_rank=3, acting_rank=1, sincerity_rank=1, earth=5,
        )
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
    """Shosuro Actor creates via fighter factory."""

    def test_creates_shosuro_fighter(self) -> None:
        """create_fighter returns ShosuroActorFighter for school='Shosuro Actor'."""
        char = _make_shosuro()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, ShosuroActorFighter)
