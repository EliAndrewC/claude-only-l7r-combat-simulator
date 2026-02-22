"""ShosuroActorFighter: Shosuro Actor school-specific overrides.

The Shosuro Actor is a non-bushi school with strong dice pool bonuses
across all roll types.

SA: Roll extra dice equal to Acting rank on attack, parry, and wound checks.
1st Dan: +1 rolled die on attack and wound check rolls.
2nd Dan: Free raise on sincerity rolls (no combat effect).
3rd Dan: 2*sincerity free raises per adventure (max sincerity per roll).
         Applies to: attack and wound checks (combat-relevant).
4th Dan: Air +1 (builder). Stipend bonus (no combat effect).
5th Dan: After any TN or contested roll, add lowest 3 dice to the result.
"""

from __future__ import annotations

import math

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    should_spend_void_on_combat_roll,
)


class ShosuroActorFighter(Fighter):
    """Shosuro Actor fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        acting_skill = self.char.get_skill("Acting")
        self._acting_rank = acting_skill.rank if acting_skill else 0
        sincerity_skill = self.char.get_skill("Sincerity")
        sincerity_rank = sincerity_skill.rank if sincerity_skill else 0
        self._free_raises = 2 * sincerity_rank if self.dan >= 3 else 0
        self._max_per_roll = sincerity_rank if self.dan >= 3 else 0

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """No combat knacks — always normal attack."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """SA: +acting dice on attack. 1st Dan: +1 more."""
        return self._acting_rank + (1 if self.dan >= 1 else 0)

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Standard void strategy with no known flat bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=0,
        )

    # -- Parry hooks --------------------------------------------------------

    def parry_extra_rolled(self) -> int:
        """SA: +acting dice on parry rolls."""
        return self._acting_rank

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """SA: +acting dice on wound checks. 1st Dan: +1 more."""
        return self._acting_rank + (1 if self.dan >= 1 else 0)

    # -- 5th Dan: add lowest 3 dice to result -------------------------------

    def post_roll_modify(
        self, all_dice: list[int], kept_count: int, total: int,
        tn: int, context: str, *, explode: bool,
    ) -> tuple[list[int], list[int], int, int, str]:
        """5th Dan: Add lowest 3 dice to the result on TN/contested rolls.

        Applies to attack, parry, and wound_check (not damage).
        """
        if self.dan < 5 or context == "damage":
            return all_dice, all_dice[:kept_count], total, 0, ""

        if len(all_dice) < 3:
            # Not enough dice to add lowest 3
            return all_dice, all_dice[:kept_count], total, 0, ""

        sorted_dice = sorted(all_dice)
        lowest_3 = sorted_dice[:3]
        bonus = sum(lowest_3)
        if bonus <= 0:
            return all_dice, all_dice[:kept_count], total, 0, ""

        new_total = total + bonus
        # Recalculate kept_dice from sorted descending
        sorted_desc = sorted(all_dice, reverse=True)
        kept_dice = sorted_desc[:kept_count]
        note = (
            f" (shosuro 5th Dan: +{bonus}"
            f" from lowest 3 dice {lowest_3})"
        )
        return all_dice, kept_dice, new_total, 0, note

    # -- 3rd Dan free raise pool --------------------------------------------

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
            f" (shosuro 3rd Dan: {raises_needed} free raise(s)"
            f" +{bonus}, {self._free_raises} remaining)"
        )
        return bonus, note

    def wc_bonus_pool_total(self) -> int:
        """3rd Dan: Remaining free raise pool for wound check threshold."""
        if self.dan >= 3:
            usable = min(self._free_raises, self._max_per_roll)
            return usable * 5
        return 0

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: Spend free raises to reduce SW on failed wound check."""
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
            f" (shosuro 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- Parry decisions (tank hits strategy) --------------------------------

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Never pre-declare parry — keep dice for attacks."""
        return False

    def can_interrupt(self) -> bool:
        """Cannot interrupt-parry."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Only parry when projected damage would be near-fatal."""
        extra_dice = max(0, (attack_total - attack_tn) // 5)
        damage_rolled = weapon_rolled + attacker_fire + extra_dice
        opponent = self.state.fighters[self.opponent_name]
        weapon_kept = opponent.weapon.kept
        expected_damage = estimate_roll(damage_rolled, weapon_kept)

        wound_info = self.state.log.wounds[self.name]
        projected_lw = wound_info.light_wounds + expected_damage

        water = self.char.rings.water.value
        water_rolled = water + self.wound_check_extra_rolled()
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
