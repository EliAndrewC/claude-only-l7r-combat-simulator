"""MerchantFighter: Merchant school-specific overrides.

The Merchant is a non-bushi school. Most abilities are social, but the SA
and several Dan techniques affect combat:

SA: Spend void points AFTER seeing the roll. Each void adds +1k1,
    applied iteratively with overflow rules.
1st Dan: +1 rolled die on wound checks.
2nd Dan: Free raise on interrogation (not combat-relevant).
3rd Dan: Pool of 2*sincerity free raises per adventure (max sincerity per roll).
4th Dan: Water +1 (handled by builder). No combat technique.
5th Dan: Selective dice reroll — pick dice whose sum >= 5*(X-1) where
         X = number of dice rerolled. Once per roll. Can spend void
         before/after reroll.

The Merchant has no combat knacks -- only normal attacks.
"""

from __future__ import annotations

import math

from src.engine.dice import roll_die
from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import estimate_roll


class MerchantFighter(Fighter):
    """Merchant fighter with school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on wound checks.
      2nd Dan: Free raise on interrogation (not combat-relevant).
      3rd Dan: 2*sincerity free raises per adventure, max sincerity per roll.
      4th Dan: Water +1 (builder); no combat technique.
      5th Dan: Selective dice reroll (once per roll).

    School Ability (SA): Spend void AFTER seeing the roll. Each void adds
    +1k1, applied iteratively with overflow rules.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        sincerity_skill = self.char.get_skill("Sincerity")
        sincerity_rank = sincerity_skill.rank if sincerity_skill else 0
        self._free_raises = 2 * sincerity_rank if self.dan >= 3 else 0
        self._max_per_roll = sincerity_rank if self.dan >= 3 else 0
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Merchant has no combat knacks -- always normal attack."""
        return "attack", 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Merchant never pre-spends void (SA is post-roll)."""
        return 0

    # -- Post-roll modify (SA + 5th Dan) ------------------------------------

    def post_roll_modify(
        self,
        all_dice: list[int],
        kept_count: int,
        total: int,
        tn: int,
        context: str,
        explode: bool = True,
    ) -> tuple[list[int], list[int], int, int, str]:
        """Merchant SA: spend void post-roll, then 5th Dan reroll, then more void.

        Returns (all_dice, kept_dice, new_total, void_spent, note).
        """
        # Damage rolls have no TN — only 5th Dan reroll applies
        skip_void = context == "damage"

        if tn <= 0 and self.dan < 5:
            kept_dice = sorted(all_dice, reverse=True)[:kept_count]
            return all_dice, kept_dice, total, 0, ""

        all_dice = list(all_dice)
        flat_bonus = 0
        void_spent = 0
        note_parts: list[str] = []

        # Phase 1: spend void post-roll until total >= TN or out of void
        if not skip_void:
            max_void_per_action = self.char.rings.lowest()
            reserve = 1 if context in ("attack", "parry") else 0

            phase1_spent = _spend_void_post_roll(
                self, all_dice, kept_count, flat_bonus, total, tn,
                max_void_per_action, reserve, explode,
            )
            void_spent += phase1_spent.void_spent
            all_dice = phase1_spent.all_dice
            kept_count = phase1_spent.kept_count
            flat_bonus = phase1_spent.flat_bonus
            total = phase1_spent.total

            if phase1_spent.void_spent > 0:
                note_parts.append(
                    f"merchant SA: {phase1_spent.void_spent} void post-roll"
                )

        # Phase 2: 5th Dan selective reroll (always attempt — higher totals
        # mean more raises on attacks and bigger margins on parry/WC/damage)
        if self.dan >= 5:
            reroll_result = _fifth_dan_reroll(
                all_dice, kept_count, flat_bonus, explode,
            )
            if reroll_result is not None:
                all_dice = reroll_result.all_dice
                total = reroll_result.total
                diff = reroll_result.diff
                note_parts.append(
                    f"5th Dan reroll:"
                    f" {reroll_result.old_values} → {reroll_result.new_values},"
                    f" {'+' if diff >= 0 else ''}{diff}"
                )

        # Phase 3: spend more void post-reroll if needed
        if not skip_void:
            remaining_cap = max_void_per_action - void_spent
            if remaining_cap > 0 and total < tn:
                phase3_spent = _spend_void_post_roll(
                    self, all_dice, kept_count, flat_bonus, total, tn,
                    remaining_cap, reserve, explode,
                )
                void_spent += phase3_spent.void_spent
                all_dice = phase3_spent.all_dice
                kept_count = phase3_spent.kept_count
                flat_bonus = phase3_spent.flat_bonus
                total = phase3_spent.total

                if phase3_spent.void_spent > 0:
                    note_parts.append(
                        f"+{phase3_spent.void_spent} void post-reroll"
                    )

        kept_dice = sorted(all_dice, reverse=True)[:kept_count]
        if not note_parts:
            return all_dice, kept_dice, total, 0, ""

        note = " (" + ", ".join(note_parts) + ")"
        return all_dice, kept_dice, total, void_spent, note

    # -- Post-attack roll bonus (3rd Dan free raises on miss) ---------------

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str,
    ) -> tuple[int, str]:
        """3rd Dan: Spend free raises to bridge attack deficit."""
        if self.dan < 3 or self._free_raises <= 0:
            return 0, ""

        deficit = tn - attack_total
        if deficit <= 0:
            return 0, ""

        raises_needed = math.ceil(deficit / 5)
        usable = min(self._max_per_roll, self._free_raises)
        if raises_needed > usable:
            return 0, ""

        self._free_raises -= raises_needed
        bonus = raises_needed * 5
        note = (
            f" (merchant 3rd Dan: {raises_needed} free raise(s)"
            f" +{bonus}, {self._free_raises} remaining)"
        )
        return bonus, note

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wc_bonus_pool_total(self) -> int:
        """3rd Dan: Remaining free raise pool affects conversion threshold."""
        if self.dan >= 3:
            usable = min(self._free_raises, self._max_per_roll)
            return usable * 5
        return 0

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: Spend free raises to reduce serious wounds on failed WC.

        Strategy:
        - NEVER spend to pass unless taking 1 more SW would be mortal.
        - Only spend to reduce the number of serious wounds taken.
        - Spend the minimum raises needed for the best SW reduction.
        """
        if self.dan < 3 or self._free_raises <= 0 or passed:
            return passed, wc_total, ""

        wound_tracker = self.state.log.wounds[self.name]
        base_tn = wound_tracker.light_wounds
        deficit = base_tn - wc_total

        if deficit <= 0:
            return passed, wc_total, ""

        earth = wound_tracker.earth_ring
        current_sw = 1 + deficit // 10
        would_die = (sw_before_wc + current_sw >= 2 * earth)

        usable = min(self._max_per_roll, self._free_raises)
        best_sw = current_sw
        best_spend = 0

        for spend in range(1, usable + 1):
            new_deficit = deficit - spend * 5
            if new_deficit <= 0:
                if would_die:
                    if spend < best_spend or best_sw > 0:
                        best_sw = 0
                        best_spend = spend
                break
            new_sw = 1 + new_deficit // 10
            if new_sw < best_sw:
                best_sw = new_sw
                best_spend = spend

        if best_spend <= 0 or best_sw >= current_sw:
            return passed, wc_total, ""

        self._free_raises -= best_spend
        bonus = best_spend * 5
        new_total = wc_total + bonus
        new_deficit = base_tn - new_total

        sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
        if new_deficit <= 0:
            new_sw_count = 0
            new_passed = True
        else:
            new_sw_count = 1 + new_deficit // 10
            new_passed = False
        wound_tracker.serious_wounds += (new_sw_count - sw_added_by_wc)

        note = (
            f" (merchant 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- Parry hooks --------------------------------------------------------

    def parry_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Merchant never pre-spends void on parry (SA is post-roll)."""
        return 0

    def wound_check_void_strategy(self, water_ring: int, light_wounds: int) -> int:
        """Merchant never pre-spends void on wound check (SA is post-roll)."""
        return 0

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Merchant never pre-declares parry — keep dice for attacks."""
        return False

    def can_interrupt(self) -> bool:
        """Merchant cannot interrupt-parry — 2-die cost never worth it."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Only parry when taking the hit unmitigated would be near-fatal.

        Same logic as Courtier: the Merchant's wound-check toolkit (1st Dan
        extra die, 3rd Dan free raises, SA post-roll void) means they can
        absorb most hits. Only parry when projected damage would push them
        to mortal wound territory.
        """
        extra_dice = max(0, (attack_total - attack_tn) // 5)
        damage_rolled = weapon_rolled + attacker_fire + extra_dice
        opponent = self.state.fighters[self.opponent_name]
        weapon_kept = opponent.weapon.kept
        expected_damage = estimate_roll(damage_rolled, weapon_kept)

        wound_info = self.state.log.wounds[self.name]
        projected_lw = wound_info.light_wounds + expected_damage

        water = self.char.rings.water.value
        water_rolled = water + (1 if self.dan >= 1 else 0)
        expected_wc = estimate_roll(water_rolled, water)

        pool_bonus = self.wc_bonus_pool_total()
        expected_wc += pool_bonus

        wc_deficit = projected_lw - expected_wc
        if wc_deficit <= 0:
            return False
        projected_sw = 1 + int(wc_deficit) // 10

        earth = wound_info.earth_ring
        existing_sw = wound_info.serious_wounds
        return existing_sw + projected_sw >= 2 * earth


# -- Internal helpers -------------------------------------------------------


class _VoidSpendResult:
    """Result of post-roll void spending."""

    __slots__ = ("all_dice", "kept_count", "flat_bonus", "total", "void_spent")

    def __init__(
        self,
        all_dice: list[int],
        kept_count: int,
        flat_bonus: int,
        total: int,
        void_spent: int,
    ) -> None:
        self.all_dice = all_dice
        self.kept_count = kept_count
        self.flat_bonus = flat_bonus
        self.total = total
        self.void_spent = void_spent


def _spend_void_post_roll(
    fighter: MerchantFighter,
    all_dice: list[int],
    kept_count: int,
    flat_bonus: int,
    total: int,
    tn: int,
    max_spend: int,
    reserve: int,
    explode: bool,
) -> _VoidSpendResult:
    """Spend void points post-roll, one at a time, until total >= TN or capped.

    For each void spent:
    1. If len(all_dice) < 10: roll 1 new die, add to pool, kept_count += 1
    2. Elif kept_count < 10: kept_count += 1 (keep more, no new die)
    3. Else: flat_bonus += 2 (overflow)
    """
    all_dice = list(all_dice)
    void_spent = 0

    while total < tn:
        available = fighter.total_void
        if available <= reserve:
            break
        if void_spent >= max_spend:
            break

        fighter.spend_void(1)
        void_spent += 1

        if len(all_dice) < 10:
            new_die = roll_die(explode=explode)
            all_dice.append(new_die)
            kept_count += 1
        elif kept_count < 10:
            kept_count += 1
        else:
            flat_bonus += 2

        all_dice.sort(reverse=True)
        kept_dice = all_dice[:kept_count]
        total = sum(kept_dice) + flat_bonus

    return _VoidSpendResult(all_dice, kept_count, flat_bonus, total, void_spent)


class _RerollResult:
    """Result of 5th Dan selective reroll."""

    __slots__ = ("all_dice", "total", "count", "old_values", "new_values", "diff")

    def __init__(
        self,
        all_dice: list[int],
        total: int,
        count: int,
        old_values: list[int],
        new_values: list[int],
        diff: int,
    ) -> None:
        self.all_dice = all_dice
        self.total = total
        self.count = count
        self.old_values = old_values
        self.new_values = new_values
        self.diff = diff


def _fifth_dan_reroll(
    all_dice: list[int],
    kept_count: int,
    flat_bonus: int,
    explode: bool,
) -> _RerollResult | None:
    """5th Dan selective reroll: reroll all dice <= 6, subject to threshold.

    Reroll every die valued 6 or below. The constraint is that the sum of
    dice being rerolled must be >= 5*(X-1) where X is the number of dice
    rerolled. If the full set of candidates violates the threshold, drop
    the lowest-valued candidates until the constraint is satisfied.
    """
    n = len(all_dice)
    if n == 0:
        return None

    # Current total from kept dice
    sorted_dice = sorted(all_dice, reverse=True)
    current_kept = sorted_dice[:kept_count]
    current_total = sum(current_kept) + flat_bonus

    # Candidates: all dice <= 6, sorted ascending (drop lowest first)
    candidates = [(i, d) for i, d in enumerate(all_dice) if d <= 6]
    candidates.sort(key=lambda x: x[1])

    if not candidates:
        return None

    # Drop lowest candidates until threshold is met
    while candidates:
        count = len(candidates)
        subset_sum = sum(d for _, d in candidates)
        threshold = 5 * (count - 1)
        if subset_sum >= threshold:
            break
        # Drop the lowest-valued candidate
        candidates.pop(0)

    if not candidates:
        return None

    reroll_indices = {i for i, _ in candidates}
    old_values = sorted([d for _, d in candidates], reverse=True)

    # Actually reroll the selected dice
    new_dice: list[int] = []
    rerolled_values: list[int] = []
    reroll_count = 0
    for i in range(n):
        if i in reroll_indices:
            new_val = roll_die(explode=explode)
            new_dice.append(new_val)
            rerolled_values.append(new_val)
            reroll_count += 1
        else:
            new_dice.append(all_dice[i])

    new_values = sorted(rerolled_values, reverse=True)
    new_dice.sort(reverse=True)
    new_kept = new_dice[:kept_count]
    new_total = sum(new_kept) + flat_bonus
    diff = new_total - current_total

    return _RerollResult(new_dice, new_total, reroll_count, old_values, new_values, diff)
