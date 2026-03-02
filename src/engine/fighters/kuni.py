"""KuniWitchHunterFighter: Kuni Witch Hunter school-specific overrides.

The Kuni Witch Hunter is a bushi school focused on hunting Tainted enemies.
Against non-Tainted opponents (the default assumption), combat abilities are:

SA: +1k1 on wound checks (from the (X+1)k(X+1) formula with X=0 Taint).
1st Dan: +1 rolled die on damage and wound check rolls.
2nd Dan: Free raise on interrogation rolls (no combat effect).
3rd Dan: 2*investigation free raises per adventure (max investigation per roll).
         Applies to: attack and wound checks (combat-relevant).
4th Dan: Earth +1 (builder). Extra action die that cannot attack non-Tainted
         targets (parry-only against non-Tainted opponents).
5th Dan: After taking light wounds and resolving wound check, may reflect
         that damage back to the attacker and take half yourself.
"""

from __future__ import annotations

import math

from src.engine.dice import roll_die
from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    should_spend_void_on_combat_roll,
)


class KuniWitchHunterFighter(Fighter):
    """Kuni Witch Hunter fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        investigation_skill = self.char.get_skill("Investigation")
        investigation_rank = investigation_skill.rank if investigation_skill else 0
        self._free_raises = 2 * investigation_rank if self.dan >= 3 else 0
        self._max_per_roll = investigation_rank if self.dan >= 3 else 0
        self._parry_only_active = False

    # -- Initiative hooks ---------------------------------------------------

    def post_initiative(
        self, rolled_dice: list[int], kept_dice: list[int],
    ) -> list[int]:
        """4th Dan: Add an extra action die (parry-only vs non-Tainted)."""
        if self.dan >= 4:
            extra_die = roll_die(explode=False)
            new_actions = sorted(kept_dice + [extra_die])
            self._parry_only_active = True
            return new_actions
        self._parry_only_active = False
        return kept_dice

    def post_initiative_description(
        self, old_actions: list[int], new_actions: list[int],
    ) -> str:
        """Describe the extra parry-only die."""
        if self.dan >= 4 and len(new_actions) > len(old_actions):
            added = [d for d in new_actions if d not in old_actions]
            if not added:
                # Duplicate value — find the extra by length
                added = [new_actions[-1]]
            return (
                f" (kuni 4th Dan: +1 parry-only die,"
                f" phase {added[0]})"
            )
        return ""

    def on_round_start(self) -> None:
        """Reset per-round state."""
        self._parry_only_active = False

    # -- Attack hooks -------------------------------------------------------

    def consume_attack_die(
        self, phase: int, die_value: int | None = None,
    ) -> int | None:
        """4th Dan: Skip attack with the lowest die (parry-only)."""
        if (
            self._parry_only_active
            and die_value is None
            and phase in self.actions_remaining
        ):
            lowest = min(self.actions_remaining)
            if phase == lowest:
                self.actions_remaining.remove(phase)
                self._parry_only_active = False
                return None
        return super().consume_attack_die(phase, die_value)

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Kuni has iaijutsu but no bonuses — always normal attack."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """No extra dice on attack (1st Dan is damage/WC only)."""
        return 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Standard void strategy with no known bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=0,
        )

    # -- Damage hooks -------------------------------------------------------

    def weapon_rolled_boost(self) -> int:
        """1st Dan: +1 rolled die on damage."""
        return 1 if self.dan >= 1 else 0

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """SA: +1 rolled die on wound checks. 1st Dan: +1 more."""
        return 1 + (1 if self.dan >= 1 else 0)

    def wound_check_extra_kept(self) -> int:
        """SA: +1 kept die on wound checks (from +1k1)."""
        return 1

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
            f" (kuni 3rd Dan: {raises_needed} free raise(s)"
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
            f" (kuni 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- 5th Dan damage reflection ------------------------------------------

    def reflect_damage_after_wc(
        self, damage_taken: int, attacker_name: str,
    ) -> tuple[int, int, str]:
        """5th Dan: Reflect damage to attacker, take half extra yourself.

        Only reflects when the extra self-damage is survivable and the
        reflected damage is meaningful.
        """
        if self.dan < 5 or damage_taken <= 0:
            return 0, 0, ""

        wound_info = self.state.log.wounds[self.name]
        self_extra = damage_taken // 2

        # Check if we can survive the extra self-damage
        projected_lw = wound_info.light_wounds + self_extra
        water = self.char.rings.water.value
        # SA gives +1k1 on wound checks, 1st Dan gives +1 rolled
        water_rolled = water + 2  # SA + 1st Dan (always have both at 5th Dan)
        water_kept = water + 1  # SA +1 kept
        expected_wc = estimate_roll(water_rolled, water_kept)
        pool_bonus = self.wc_bonus_pool_total()
        expected_wc += pool_bonus

        existing_sw = wound_info.serious_wounds
        if projected_lw > expected_wc:
            wc_deficit = projected_lw - expected_wc
            projected_sw = 1 + int(wc_deficit) // 10
            if existing_sw + projected_sw >= wound_info.mortal_wound_threshold:
                return 0, 0, ""  # Would die from extra damage

        note = (
            f" (kuni 5th Dan: reflects {damage_taken} LW"
            f" to {attacker_name}, takes {self_extra} LW self)"
        )
        return damage_taken, self_extra, note

    # -- Parry decisions (tank hits strategy) --------------------------------

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Never pre-declare parry — rely on wound check resilience."""
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
        # 1st Dan: +1 damage die (opponent doesn't have this, but
        # this is the attacker's damage, not ours)
        opponent = self.state.fighters[self.opponent_name]
        weapon_kept = opponent.weapon.kept
        expected_damage = estimate_roll(damage_rolled, weapon_kept)

        wound_info = self.state.log.wounds[self.name]
        projected_lw = wound_info.light_wounds + expected_damage

        water = self.char.rings.water.value
        # SA: +1k1, 1st Dan: +1 rolled
        water_rolled = water + self.wound_check_extra_rolled()
        water_kept = water + self.wound_check_extra_kept()
        expected_wc = estimate_roll(water_rolled, water_kept)

        pool_bonus = self.wc_bonus_pool_total()
        expected_wc += pool_bonus

        wc_deficit = projected_lw - expected_wc
        if wc_deficit <= 0:
            return False
        projected_sw = 1 + int(wc_deficit) // 10

        existing_sw = wound_info.serious_wounds
        return existing_sw + projected_sw >= wound_info.mortal_wound_threshold
