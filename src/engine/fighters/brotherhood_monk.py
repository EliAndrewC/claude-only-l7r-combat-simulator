"""BrotherhoodMonkFighter: Brotherhood of Shinsei Monk school overrides.

The Brotherhood Monk is a hybrid martial/spiritual school that fights unarmed.

SA: Keep one extra die for damage rolls from unarmed attacks (+1 kept die).
1st Dan: +1 rolled die on attack, damage, and wound check rolls.
2nd Dan: Free raise on all attack rolls (+5 flat).
3rd Dan: 2X free raises per adventure (X = precepts rank), applicable to
         attack rolls and wound checks. Max X per roll.
4th Dan: Water +1 (builder). Failed parry attempts do not lower rolled
         damage dice.
5th Dan: Once per round after attacked but before damage, spend action die
         to counterattack. If monk roll >= attacker's roll, cancel the attack.
         Monk's attack continues normally (hit/miss + damage).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState

from src.engine.combat import make_wound_check
from src.engine.dice import roll_and_keep
from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    format_pool_with_overflow,
    should_convert_light_to_serious,
    should_spend_void_on_combat_roll,
    should_spend_void_on_wound_check,
    void_spent_label,
)
from src.models.character import Character
from src.models.combat import ActionType, CombatAction
from src.models.weapon import Weapon, WeaponType


def _resolve_monk_counterattack(
    state: "CombatState",
    monk_name: str,
    target_name: str,
    phase: int,
    consumed_die: int,
    attacker_attack_total: int,
) -> tuple[bool, int]:
    """Resolve a Brotherhood Monk 5th Dan counterattack.

    Returns (attack_canceled, margin_if_hit).
    """
    log = state.log
    monk_ctx = state.fighters[monk_name]
    target_ctx = state.fighters[target_name]
    monk_char: Character = monk_ctx.char
    target_char: Character = target_ctx.char

    dan = monk_char.dan

    # Attack skill
    atk_skill = monk_char.get_skill("Attack")
    atk_rank = atk_skill.rank if atk_skill else 0

    # Target's parry rank
    def_parry_skill = target_char.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # TN = 5 + 5 * target's parry rank
    hit_tn = 5 + 5 * def_parry_rank

    # Roll: attack_rank + fire_ring + (1 if dan >= 1)
    fire_ring = monk_char.rings.fire.value
    rolled = atk_rank + fire_ring + (1 if dan >= 1 else 0)
    kept = fire_ring

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=True)

    # 2nd Dan: free raise (+5 to total)
    bonus_note = ""
    if dan >= 2:
        total += 5
        bonus_note = " (monk 2nd Dan: free raise +5)"

    # 3rd Dan: spend free raises to bridge deficit vs attacker's roll
    # (for cancellation check)
    cancel_raise_note = ""
    if dan >= 3 and monk_ctx._free_raises > 0:
        cancel_deficit = attacker_attack_total - total
        if cancel_deficit > 0:
            raises_needed = math.ceil(cancel_deficit / 5)
            usable = min(monk_ctx._max_per_roll, monk_ctx._free_raises)
            if raises_needed <= usable:
                monk_ctx._free_raises -= raises_needed
                cancel_bonus = raises_needed * 5
                total += cancel_bonus
                cancel_raise_note = (
                    f" (monk 3rd Dan: {raises_needed} free raise(s)"
                    f" +{cancel_bonus} for cancel,"
                    f" {monk_ctx._free_raises} remaining)"
                )

    # Cancellation check: total >= attacker's attack total
    attack_canceled = total >= attacker_attack_total

    # Hit check vs target TN (for damage)
    hit_success = total >= hit_tn

    ca_action = CombatAction(
        phase=phase,
        actor=monk_name,
        action_type=ActionType.COUNTERATTACK,
        target=target_name,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=hit_tn,
        success=hit_success,
        description=(
            f"{monk_name} counterattacks: "
            f"{format_pool_with_overflow(rolled, kept)}"
            f" vs TN {hit_tn}{bonus_note}{cancel_raise_note}"
            f" — {'cancels' if attack_canceled else 'does not cancel'}"
            f" incoming attack (rolled {total} vs {attacker_attack_total})"
        ),
        dice_pool=format_pool_with_overflow(rolled, kept),
        label=f"5th Dan counterattack (consuming phase {consumed_die} die)",
    )
    ca_action.status_after = state.snapshot_status()
    log.add_action(ca_action)

    if not hit_success:
        return attack_canceled, 0

    margin = total - hit_tn

    # Roll damage: weapon + 1st Dan boost + fire + raises extra dice
    weapon: Weapon = monk_ctx.weapon
    extra_dice = max(0, margin // 5)
    base_weapon_rolled = monk_ctx.weapon_rolled_boost(weapon.rolled, weapon.kept)
    damage_rolled = base_weapon_rolled + fire_ring + extra_dice
    # SA: +1 kept die for unarmed
    sa_extra_rolled, sa_extra_kept = monk_ctx.sa_attack_damage_bonus(0)
    damage_kept = weapon.kept + sa_extra_kept

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(
        damage_rolled, damage_kept, explode=True,
    )

    if dmg_total <= 0:
        return attack_canceled, margin

    damage_action = CombatAction(
        phase=phase,
        actor=monk_name,
        action_type=ActionType.DAMAGE,
        target=target_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=f"{monk_name} counterattack deals {dmg_total} damage",
        dice_pool=format_pool_with_overflow(damage_rolled, damage_kept),
    )

    # Apply damage as light wounds
    wound_tracker = log.wounds[target_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = state.snapshot_status()
    log.add_action(damage_action)

    # --- Wound check for target ---
    water_value = target_char.rings.water.value

    wc_extra_rolled = target_ctx.wound_check_extra_rolled()

    max_spend = target_char.rings.lowest()
    void_spend = should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, target_ctx.total_void,
        max_spend=max_spend, extra_rolled=wc_extra_rolled,
    )
    wc_from_temp, wc_from_reg, wc_from_wl = target_ctx.spend_void(void_spend)
    wc_void_label = void_spent_label(wc_from_temp, wc_from_reg, wc_from_wl)

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=wc_extra_rolled,
    )

    # Wound check flat bonus via Fighter hook
    wc_flat_bonus, wc_flat_note = target_ctx.wound_check_flat_bonus()
    if wc_flat_bonus > 0:
        wc_total += wc_flat_bonus
        effective_tn = wound_tracker.light_wounds
        passed = wc_total >= effective_tn

    void_note = f" ({wc_void_label})" if wc_void_label else ""
    wc_tn = wound_tracker.light_wounds

    # Wound check success choice
    convert_note = ""
    if passed:
        should_convert = should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            lw_severity_divisor=target_ctx.wound_check_lw_severity_divisor(),
        )
        if should_convert:
            wound_tracker.serious_wounds += 1
            wound_tracker.light_wounds = 0
            convert_note = " — converted light wounds to 1 serious wound"
        else:
            convert_note = f" — keeping {wound_tracker.light_wounds} light wounds"

    wc_rolled = water_value + 1 + wc_extra_rolled + void_spend
    wc_kept = water_value + void_spend
    wc_action = CombatAction(
        phase=phase,
        actor=target_name,
        action_type=ActionType.WOUND_CHECK,
        dice_rolled=wc_all_dice,
        dice_kept=wc_kept_dice,
        total=wc_total,
        tn=wc_tn,
        success=passed,
        description=(
            f"{target_name} wound check: {'passed' if passed else 'failed'} "
            f"(rolled {wc_total}){void_note}{wc_flat_note}"
            f"{convert_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    if not passed:
        wound_tracker.light_wounds = 0

    wc_action.status_after = state.snapshot_status()

    return attack_canceled, margin


class BrotherhoodMonkFighter(Fighter):
    """Brotherhood of Shinsei Monk fighter with school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on attack, damage, and wound checks.
      2nd Dan: Free raise on attack rolls (+5 flat).
      3rd Dan: 2*precepts free raises per adventure, max precepts per roll.
      4th Dan: Water +1 (builder); failed parry does not reduce damage dice.
      5th Dan: Pre-damage counterattack that can cancel incoming attack.

    School Ability (SA): +1 kept die on unarmed damage.
    """

    _in_counterattack: bool = False
    _counterattack_used_this_round: bool = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        precepts_skill = self.char.get_skill("Precepts")
        precepts_rank = precepts_skill.rank if precepts_skill else 0
        self._free_raises = 2 * precepts_rank if self.dan >= 3 else 0
        self._max_per_roll = precepts_rank if self.dan >= 3 else 0
        self._counterattack_used_this_round = False
        self._in_counterattack = False
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Round hooks ------------------------------------------------------------

    def on_round_start(self) -> None:
        """Reset per-round counterattack usage."""
        self._counterattack_used_this_round = False

    # -- Attack hooks -----------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Brotherhood Monk has no combat knacks — always normal attack."""
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
            return 5, " (monk 2nd Dan: free raise +5)"
        return 0, ""

    # -- SA: +1 kept die on unarmed damage --------------------------------------

    def sa_attack_damage_bonus(self, void_spent: int) -> tuple[int, int]:
        """SA: +1 kept die on unarmed damage."""
        if self.weapon.weapon_type == WeaponType.UNARMED:
            return 0, 1
        return 0, 0

    # -- 1st Dan: +1 rolled die on damage ---------------------------------------

    def weapon_rolled_boost(self, weapon_rolled: int, weapon_kept: int) -> int:
        """1st Dan: +1 rolled die on damage."""
        if self.dan >= 1:
            return weapon_rolled + 1
        return weapon_rolled

    # -- 1st Dan: +1 rolled die on wound check ----------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

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
            f" (monk 3rd Dan: {raises_needed} free raise(s)"
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
            f" (monk 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- 4th Dan: Failed parry does not reduce damage dice ----------------------

    def damage_parry_reduction(self, defender_parry_rank: int) -> int:
        """4th Dan: Failed parry does not reduce damage dice."""
        if self.dan >= 4:
            return 0
        return defender_parry_rank

    # -- 5th Dan: Pre-damage counterattack --------------------------------------

    def _consume_cheapest_die(self) -> int | None:
        """Consume the cheapest action die for counterattack."""
        if not self.actions_remaining:
            return None
        cheapest = min(self.actions_remaining)
        self.actions_remaining.remove(cheapest)
        return cheapest

    def try_cancel_before_damage(
        self,
        attack_total: int,
        tn: int,
        attacker_name: str,
        phase: int,
    ) -> tuple[bool, str]:
        """5th Dan: Counterattack before damage; may cancel incoming attack."""
        if self.dan < 5:
            return False, ""
        if self._counterattack_used_this_round:
            return False, ""
        if self._in_counterattack:
            return False, ""
        if not self.actions_remaining:
            return False, ""

        # Don't counter if mortally wounded
        if self.state.log.wounds[self.name].is_mortally_wounded:
            return False, ""
        if self.state.log.wounds[attacker_name].is_mortally_wounded:
            return False, ""

        # Heuristic: only fire when projected damage is near-mortal
        attacker_f = self.state.fighters.get(attacker_name)
        if attacker_f is None:
            return False, ""

        extra_dice = max(0, (attack_total - tn) // 5)
        weapon_rolled = attacker_f.weapon_rolled_boost(
            attacker_f.weapon.rolled, attacker_f.weapon.kept,
        )
        damage_rolled = weapon_rolled + attacker_f.char.rings.fire.value + extra_dice
        weapon_kept = attacker_f.weapon.kept
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
            return False, ""
        projected_sw = 1 + int(wc_deficit) // 10

        earth = wound_info.earth_ring
        existing_sw = wound_info.serious_wounds
        if existing_sw + projected_sw < 2 * earth:
            return False, ""

        # Fire the counterattack
        consumed = self._consume_cheapest_die()
        if consumed is None:
            return False, ""

        self._counterattack_used_this_round = True
        self._in_counterattack = True
        try:
            canceled, _margin = _resolve_monk_counterattack(
                self.state, self.name, attacker_name, phase,
                consumed, attack_total,
            )
        finally:
            self._in_counterattack = False

        if canceled:
            note = (
                f" (monk 5th Dan: {self.name} counterattack cancels attack,"
                f" consumed phase {consumed} die)"
            )
            return True, note

        note = (
            f" (monk 5th Dan: {self.name} counterattack does not cancel,"
            f" consumed phase {consumed} die)"
        )
        return False, note
