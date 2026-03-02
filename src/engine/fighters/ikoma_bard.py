"""IkomaBardFighter: Ikoma Bard school-specific overrides.

The Ikoma Bard is a non-bushi school. Most abilities are social, but the SA
and several Dan techniques affect combat:

SA: Once per round before attacking, force opponent to parry with next action
    die (no free raise). Usable if opponent has >=1 action die.
1st Dan: +1 rolled die on attack, bragging, and wound check rolls.
2nd Dan: Free raise on attack rolls (+5 flat).
3rd Dan: 2*bragging free raises per adventure (max bragging per roll).
         Applies to: bragging, culture, heraldry, intimidation, attack, wound
         checks.
4th Dan: Non-Void ring +1 (Water, handled by builder). When making damage
         for an unparried attack with no extra kept dice, always roll 10 dice.
5th Dan: Use SA or oppose knack an extra time per round. Can use SA
         defensively: after opponent's attack roll, cancel the attack and use
         their attack roll as their parry roll.

The Ikoma Bard has no combat knacks -- only normal attacks.
"""

from __future__ import annotations

import math

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    should_spend_void_on_combat_roll,
)


class IkomaBardFighter(Fighter):
    """Ikoma Bard fighter with school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on attack and wound checks.
      2nd Dan: Free raise on attack rolls (+5 flat).
      3rd Dan: 2*bragging free raises per adventure, max bragging per roll.
      4th Dan: Water +1 (builder); 10 dice on unparried damage with no extra kept.
      5th Dan: Double SA uses per round; defensive SA cancel.

    School Ability (SA): Force opponent to parry (no free raise).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        bragging_skill = self.char.get_skill("Bragging")
        bragging_rank = bragging_skill.rank if bragging_skill else 0
        self._free_raises = 2 * bragging_rank if self.dan >= 3 else 0
        self._max_per_roll = bragging_rank if self.dan >= 3 else 0
        self._sa_uses_this_round = 0
        self._max_sa_per_round = 2 if self.dan >= 5 else 1

    # -- Round hooks ------------------------------------------------------------

    def on_round_start(self) -> None:
        """Reset per-round SA uses and clear stored parry on both fighters."""
        self._sa_uses_this_round = 0
        self._stored_parry_total = 0
        # Also clear stored parry on opponent (in case they have one)
        opponent_name = self.opponent_name
        opponent = self.state.fighters.get(opponent_name)
        if opponent is not None:
            opponent._stored_parry_total = 0

    # -- Attack hooks -----------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Ikoma Bard has no combat knacks -- always normal attack."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Spend void on attack with known 2nd Dan bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        known_bonus = 5 if self.dan >= 2 else 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=known_bonus,
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """2nd Dan: Free raise on attack rolls (+5 flat)."""
        if self.dan >= 2:
            return 5, " (ikoma bard 2nd Dan: free raise +5)"
        return 0, ""

    # -- Offensive SA (force parry) ---------------------------------------------

    def sa_force_parry(self, defender_name: str, phase: int) -> tuple[bool, str]:
        """SA: Force opponent to parry with next action die (no free raise).

        Returns (True, note) if SA fires; (False, "") otherwise.
        """
        if self._sa_uses_this_round >= self._max_sa_per_round:
            return False, ""

        opponent = self.state.fighters.get(defender_name)
        if opponent is None or not opponent.actions_remaining:
            return False, ""

        self._sa_uses_this_round += 1
        note = (
            f" (ikoma bard SA: forces {defender_name} to parry,"
            f" SA use {self._sa_uses_this_round}/{self._max_sa_per_round})"
        )
        return True, note

    # -- 5th Dan defensive SA ---------------------------------------------------

    def try_defensive_sa(
        self, attack_total: int, tn: int,
        weapon_rolled: int, attacker_fire: int,
        attacker_name: str,
    ) -> str:
        """5th Dan: Cancel incoming attack, store attack roll as forced parry.

        Returns cancel note if canceling (empty = don't cancel).
        """
        if self.dan < 5:
            return ""
        if self._sa_uses_this_round >= self._max_sa_per_round:
            return ""

        # Only use defensively when the hit would be near-mortal
        # (same threshold as should_reactive_parry)
        extra_dice = max(0, (attack_total - tn) // 5)
        damage_rolled = weapon_rolled + attacker_fire + extra_dice
        opponent = self.state.fighters.get(attacker_name)
        if opponent is None:
            return ""
        weapon_kept = opponent.weapon.kept
        expected_damage = estimate_roll(damage_rolled, weapon_kept)

        wound_info = self.state.log.wounds[self.name]
        projected_lw = wound_info.light_wounds + expected_damage

        water = self.char.rings.water.value
        water_rolled = water + (1 if self.dan >= 1 else 0)  # 1st Dan
        expected_wc = estimate_roll(water_rolled, water)

        pool_bonus = self.wc_bonus_pool_total()
        expected_wc += pool_bonus

        wc_deficit = projected_lw - expected_wc
        if wc_deficit <= 0:
            return ""
        projected_sw = 1 + int(wc_deficit) // 10

        existing_sw = wound_info.serious_wounds
        if existing_sw + projected_sw < wound_info.mortal_wound_threshold:
            return ""

        # Fire the defensive SA
        self._sa_uses_this_round += 1
        return (
            f" (ikoma bard 5th Dan: {self.name} cancels attack,"
            f" uses {attacker_name}'s roll as parry;"
            f" SA use {self._sa_uses_this_round}/{self._max_sa_per_round})"
        )

    # -- 4th Dan damage ---------------------------------------------------------

    def damage_min_rolled(
        self, current_rolled: int, parry_attempted: bool, extra_kept: int,
    ) -> int:
        """4th Dan: 10 dice on unparried damage with no extra kept."""
        if self.dan >= 4 and not parry_attempted and extra_kept == 0:
            return max(10, current_rolled)
        return current_rolled

    # -- 3rd Dan free raise pool ------------------------------------------------

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
            f" (ikoma bard 3rd Dan: {raises_needed} free raise(s)"
            f" +{bonus}, {self._free_raises} remaining)"
        )
        return bonus, note

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

        current_sw = 1 + deficit // 10
        would_die = (sw_before_wc + current_sw >= wound_tracker.mortal_wound_threshold)

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
            f" (ikoma bard 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- Wound check hooks ------------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    # -- Parry decisions (tank hits strategy) -----------------------------------

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Ikoma Bard never pre-declares parry — keep dice for attacks."""
        return False

    def can_interrupt(self) -> bool:
        """Ikoma Bard cannot interrupt-parry — 2-die cost never worth it."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Only parry when taking the hit unmitigated would be near-fatal.

        Same approach as Courtier/Merchant: the Ikoma Bard's wound-check
        toolkit (1st Dan extra die, 3rd Dan free raises) means they can
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
        water_rolled = water + (1 if self.dan >= 1 else 0)  # 1st Dan
        expected_wc = estimate_roll(water_rolled, water)

        pool_bonus = self.wc_bonus_pool_total()
        expected_wc += pool_bonus

        wc_deficit = projected_lw - expected_wc
        if wc_deficit <= 0:
            return False
        projected_sw = 1 + int(wc_deficit) // 10

        existing_sw = wound_info.serious_wounds
        return existing_sw + projected_sw >= wound_info.mortal_wound_threshold
