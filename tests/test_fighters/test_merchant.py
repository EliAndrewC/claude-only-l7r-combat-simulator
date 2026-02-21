"""Tests for MerchantFighter school-specific overrides."""

from __future__ import annotations

from unittest.mock import patch

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.merchant import MerchantFighter
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


def _make_merchant(
    name: str = "Merchant",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    sincerity_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    """Create a Merchant character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Merchant",
        school_ring=RingName.WATER,
        school_knacks=["Discern Honor", "Oppose Knowledge", "Worldliness"],
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
                name="Sincerity", rank=sincerity_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Oppose Knowledge", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Worldliness", rank=knack_rank,
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
    merchant_char: Character,
    opponent_char: Character,
    merchant_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [merchant_char.name, opponent_char.name],
        [merchant_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    m_void = (
        merchant_void if merchant_void is not None
        else merchant_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        merchant_char.name, state,
        char=merchant_char, weapon=KATANA, void_points=m_void,
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
    sincerity_rank: int = 5,
    void_points: int | None = None,
    **ring_overrides: int,
) -> MerchantFighter:
    """Create a MerchantFighter with a full CombatState."""
    char = _make_merchant(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        sincerity_rank=sincerity_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, merchant_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, MerchantFighter)
    return fighter


class TestMerchantInit:
    """Initialization and pool setup."""

    def test_worldliness_void_initialized(self) -> None:
        """worldliness_void equals the Worldliness skill rank."""
        for rank in range(6):
            fighter = _make_fighter(knack_rank=rank)
            assert fighter.worldliness_void == rank

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

    def test_sincerity_rank_affects_pool(self) -> None:
        """Pool scales with sincerity rank."""
        fighter = _make_fighter(knack_rank=3, sincerity_rank=3)
        assert fighter._free_raises == 6
        assert fighter._max_per_roll == 3


class TestMerchantSA:
    """SA: Merchant never pre-spends void (post-roll instead)."""

    def test_attack_void_strategy_returns_zero(self) -> None:
        """attack_void_strategy always returns 0."""
        fighter = _make_fighter(knack_rank=5, void_points=5)
        assert fighter.attack_void_strategy(5, 2, 25) == 0

    def test_parry_void_strategy_returns_zero(self) -> None:
        """parry_void_strategy always returns 0."""
        fighter = _make_fighter(knack_rank=5, void_points=5)
        assert fighter.parry_void_strategy(5, 2, 25) == 0

    def test_wound_check_void_strategy_returns_zero(self) -> None:
        """wound_check_void_strategy always returns 0 (not -1)."""
        fighter = _make_fighter(knack_rank=5, void_points=5)
        assert fighter.wound_check_void_strategy(3, 30) == 0


class TestPostRollModify:
    """SA post-roll void spending mechanics."""

    def test_spend_one_void_adds_die_when_under_10(self) -> None:
        """Spending 1 void post-roll adds a die to pool when rolled < 10."""
        fighter = _make_fighter(knack_rank=1, void_points=3, water=3)
        # 5 dice rolled, keeping 3, total=20, TN=30
        # Should spend void to add dice
        all_dice = [8, 7, 5, 3, 2]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 3, 20, 30, "wound_check", explode=True,
            )
        assert void_spent > 0
        assert len(result_dice) > len(all_dice)
        assert "merchant SA" in note

    def test_spend_void_when_rolled_eq_10_keeps_more(self) -> None:
        """When rolled == 10, spending void just keeps more (no new die)."""
        fighter = _make_fighter(knack_rank=1, void_points=3, water=3)
        # 10 dice rolled, keeping 3, total=24, TN=30
        all_dice = [9, 8, 7, 6, 5, 4, 3, 2, 1, 1]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 3, 24, 30, "wound_check", explode=True,
            )
        # Dice pool stays at 10 — no new die rolled
        assert len(result_dice) == 10
        assert void_spent > 0

    def test_spend_void_when_kept_eq_10_adds_flat_bonus(self) -> None:
        """When kept == 10, spending void adds flat +2 bonus."""
        fighter = _make_fighter(knack_rank=1, void_points=3, water=3)
        # 10 dice, keeping 10, total=50, TN=55
        all_dice = [9, 8, 7, 6, 5, 4, 3, 2, 1, 5]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 10, 50, 55, "wound_check", explode=True,
            )
        assert void_spent > 0
        assert total >= 52  # At least +2 from flat bonus
        assert len(result_dice) == 10  # Pool unchanged

    def test_respects_per_action_void_cap(self) -> None:
        """Only spends up to lowest ring per action."""
        # lowest ring = 2 (all rings at 2), so max 2 void per action
        fighter = _make_fighter(knack_rank=1, void_points=5)
        all_dice = [5, 3, 2]
        with patch("src.engine.fighters.merchant.roll_die", return_value=6):
            _, _, _, void_spent, _ = fighter.post_roll_modify(
                all_dice, 2, 8, 100, "wound_check", explode=True,
            )
        assert void_spent <= 2  # Capped at lowest ring (2)

    def test_reserves_1_vp_for_wound_check_on_attack(self) -> None:
        """When context is 'attack', reserves 1 VP for wound check."""
        # knack_rank=0 so no worldliness void; only 2 regular void
        fighter = _make_fighter(knack_rank=0, void_points=2, water=3)
        all_dice = [5, 3]
        with patch("src.engine.fighters.merchant.roll_die", return_value=6):
            _, _, _, void_spent, _ = fighter.post_roll_modify(
                all_dice, 2, 8, 100, "attack", explode=True,
            )
        # Should reserve 1 VP, so only 1 spent from 2 available
        assert void_spent <= 1

    def test_reserves_1_vp_for_wound_check_on_parry(self) -> None:
        """When context is 'parry', reserves 1 VP for wound check."""
        # knack_rank=0 so no worldliness void; only 2 regular void
        fighter = _make_fighter(knack_rank=0, void_points=2, water=3)
        all_dice = [5, 3]
        with patch("src.engine.fighters.merchant.roll_die", return_value=6):
            _, _, _, void_spent, _ = fighter.post_roll_modify(
                all_dice, 2, 8, 100, "parry", explode=True,
            )
        assert void_spent <= 1

    def test_no_spend_when_already_passing(self) -> None:
        """Don't spend void when already meeting TN."""
        fighter = _make_fighter(knack_rank=1, void_points=5, water=3)
        all_dice = [10, 8, 7]
        _, _, _, void_spent, note = fighter.post_roll_modify(
            all_dice, 3, 25, 20, "attack", explode=True,
        )
        assert void_spent == 0
        assert note == ""

    def test_no_spend_when_tn_zero(self) -> None:
        """Don't spend void when TN is 0."""
        fighter = _make_fighter(knack_rank=1, void_points=5, water=3)
        _, _, _, void_spent, note = fighter.post_roll_modify(
            [5, 3], 2, 8, 0, "attack", explode=True,
        )
        assert void_spent == 0
        assert note == ""


class TestFifthDanReroll:
    """5th Dan selective dice reroll."""

    @staticmethod
    def _deplete_void(fighter: MerchantFighter) -> None:
        """Drain all void pools so phase 1 (SA void) is skipped."""
        fighter.void_points = 0
        fighter.temp_void = 0
        fighter.worldliness_void = 0

    def test_single_low_die_rerolled(self) -> None:
        """A single die <= 5 is always valid for reroll (threshold=0)."""
        fighter = _make_fighter(knack_rank=5, void_points=0, water=3)
        self._deplete_void(fighter)
        all_dice = [1]
        with patch("src.engine.fighters.merchant.roll_die", return_value=8):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 1, 1, 10, "wound_check", explode=True,
            )
        assert "5th Dan reroll" in note
        assert "[1] →" in note
        assert "[8]" in note
        assert total == 8

    def test_two_dice_rerolled_when_sum_gte_threshold(self) -> None:
        """Two dice rerolled when sum >= 5*(2-1)=5."""
        fighter = _make_fighter(knack_rank=5, void_points=0, water=3)
        self._deplete_void(fighter)
        all_dice = [3, 3]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 2, 6, 15, "wound_check", explode=True,
            )
        assert "5th Dan reroll" in note
        assert "[3, 3] →" in note
        assert "[9, 9]" in note
        assert "+12" in note
        assert total == 18  # Both dice replaced with 9

    def test_no_reroll_when_all_dice_above_6(self) -> None:
        """Does not reroll when all dice > 6."""
        fighter = _make_fighter(knack_rank=5, void_points=0, water=3)
        self._deplete_void(fighter)
        all_dice = [9, 8, 7]
        _, _, _, void_spent, note = fighter.post_roll_modify(
            all_dice, 3, 24, 30, "wound_check", explode=True,
        )
        assert "5th Dan reroll" not in note

    def test_rerolls_all_sixes_and_below(self) -> None:
        """Rerolls all dice <= 6, leaves 7+ untouched."""
        fighter = _make_fighter(knack_rank=5, void_points=0, water=3)
        self._deplete_void(fighter)
        # [9, 6, 5, 3] keeping 2 — rerolls 6, 5, 3 (all <= 6)
        all_dice = [9, 6, 5, 3]
        with patch("src.engine.fighters.merchant.roll_die", return_value=8):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 2, 15, 20, "wound_check", explode=True,
            )
        assert "5th Dan reroll" in note
        assert "[6, 5, 3] →" in note
        # 9 stays, three 8s from reroll; top 2 = 9 + 8 = 17
        assert total == 17

    def test_drops_lowest_when_threshold_violated(self) -> None:
        """Drops lowest candidates when sum < 5*(X-1) threshold."""
        fighter = _make_fighter(knack_rank=5, void_points=0, water=3)
        self._deplete_void(fighter)
        # [1, 1, 1] — sum=3, threshold for 3 dice = 10, so must drop
        # Drop first 1: [1, 1] sum=2, threshold=5, still fails
        # Drop another: [1] sum=1, threshold=0, passes — reroll 1 die
        all_dice = [1, 1, 1]
        with patch("src.engine.fighters.merchant.roll_die", return_value=8):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 2, 2, 10, "wound_check", explode=True,
            )
        assert "5th Dan reroll" in note
        assert "[1] →" in note

    def test_reroll_fires_on_passing_roll(self) -> None:
        """Reroll fires even when total already >= TN (raises matter)."""
        fighter = _make_fighter(knack_rank=5, void_points=0, water=3)
        self._deplete_void(fighter)
        # total=12 already beats TN=10, but die [2] can be improved
        all_dice = [10, 2]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            _, _, total, _, note = fighter.post_roll_modify(
                all_dice, 2, 12, 10, "attack", explode=True,
            )
        assert "5th Dan reroll" in note
        assert total == 19  # 10 + 9

    def test_reroll_fires_on_damage(self) -> None:
        """Reroll fires on damage context (no void spent, just reroll)."""
        fighter = _make_fighter(knack_rank=5, void_points=5, water=3)
        # Damage roll with low dice — should reroll without spending void
        all_dice = [8, 3, 1]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            result_dice, kept, total, void_spent, note = fighter.post_roll_modify(
                all_dice, 2, 11, 0, "damage", explode=True,
            )
        assert "5th Dan reroll" in note
        assert "→" in note
        assert void_spent == 0  # No void spent on damage

    def test_damage_skips_void_spending(self) -> None:
        """Damage context never spends void, even when available."""
        fighter = _make_fighter(knack_rank=3, void_points=5, water=3)
        all_dice = [3, 2]
        with patch("src.engine.fighters.merchant.roll_die", return_value=9):
            _, _, _, void_spent, note = fighter.post_roll_modify(
                all_dice, 2, 5, 0, "damage", explode=True,
            )
        assert void_spent == 0
        assert "merchant SA" not in note

    def test_no_reroll_before_5th_dan(self) -> None:
        """No reroll before 5th Dan."""
        fighter = _make_fighter(knack_rank=4, void_points=0, water=3)
        self._deplete_void(fighter)
        all_dice = [1]
        with patch("src.engine.fighters.merchant.roll_die", return_value=8):
            _, _, _, void_spent, note = fighter.post_roll_modify(
                all_dice, 1, 1, 10, "wound_check", explode=True,
            )
        assert "5th Dan" not in note


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


class TestParryDecisions:
    """Merchant parry strategy — identical to Courtier approach."""

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


class TestFactoryRegistration:
    """Merchant creates via fighter factory."""

    def test_creates_merchant_fighter(self) -> None:
        """create_fighter returns MerchantFighter for school='Merchant'."""
        char = _make_merchant()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, MerchantFighter)
