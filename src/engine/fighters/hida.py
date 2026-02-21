"""HidaFighter: Hida Bushi school-specific overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState

from src.engine.combat import make_wound_check
from src.engine.dice import roll_and_keep, roll_die
from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    format_pool_with_overflow,
    should_convert_light_to_serious,
    should_spend_void_on_wound_check,
    void_spent_label,
)
from src.models.character import Character
from src.models.combat import ActionType, CombatAction
from src.models.weapon import Weapon


def _resolve_hida_counterattack(
    state: "CombatState",
    hida_name: str,
    target_name: str,
    phase: int,
    consumed_die: int,
) -> int:
    """Resolve a Hida counterattack against the target.

    Returns the margin (total - TN) if the counterattack hits, else 0.
    """
    log = state.log
    hida_ctx = state.fighters[hida_name]
    target_ctx = state.fighters[target_name]
    hida_char: Character = hida_ctx.char
    target_char: Character = target_ctx.char
    weapon: Weapon = hida_ctx.weapon

    dan = hida_char.dan

    # Counterattack skill
    ca_skill = hida_char.get_skill("Counterattack")
    ca_rank = ca_skill.rank if ca_skill else 0

    # Target's parry rank
    def_parry_skill = target_char.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # TN = 5 + 5 * target's parry rank
    tn = 5 + 5 * def_parry_rank

    # Roll: counterattack_rank + fire_ring + (1 if dan >= 1)
    fire_ring = hida_char.rings.fire.value
    rolled = ca_rank + fire_ring + (1 if dan >= 1 else 0)
    kept = fire_ring

    # Explode: True unless crippled AND dan < 3
    is_crippled = log.wounds[hida_name].is_crippled
    explode = not is_crippled or dan >= 3

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=explode)

    # 3rd Dan rerolls: count = 2 * ca_rank (halved round up if crippled)
    reroll_note = ""
    if dan >= 3 and ca_rank > 0:
        reroll_count = 2 * ca_rank
        if is_crippled:
            reroll_count = (reroll_count + 1) // 2  # round up

        # Find dice <= 6, pick lowest N
        eligible = [(i, d) for i, d in enumerate(all_dice) if d <= 6]
        eligible.sort(key=lambda x: x[1])
        to_reroll = eligible[:reroll_count]

        if to_reroll:
            old_values = sorted([d for _, d in to_reroll], reverse=True)
            # Reroll with explode (3rd Dan overrides crippled no-explode)
            for idx, _old in to_reroll:
                all_dice[idx] = roll_die(explode=True)
            new_values = sorted(
                [all_dice[idx] for idx, _ in to_reroll], reverse=True,
            )

            # Re-sort, re-keep, recalc
            old_total = total
            all_dice = sorted(all_dice, reverse=True)
            kept_dice = all_dice[:kept]
            total = sum(kept_dice)

            diff = total - old_total
            reroll_note = (
                f" (hida 3rd Dan: rerolled"
                f" {old_values} → {new_values},"
                f" added {'+' if diff >= 0 else ''}{diff})"
            )

    # 2nd Dan: free raise (+5 to total)
    bonus_note = ""
    if dan >= 2:
        total += 5
        bonus_note = " (hida 2nd Dan: free raise +5)"

    success = total >= tn

    ca_action = CombatAction(
        phase=phase,
        actor=hida_name,
        action_type=ActionType.COUNTERATTACK,
        target=target_name,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=tn,
        success=success,
        description=(
            f"{hida_name} counterattacks: "
            f"{format_pool_with_overflow(rolled, kept)}"
            f" vs TN {tn}{reroll_note}{bonus_note}"
        ),
        dice_pool=format_pool_with_overflow(rolled, kept),
        label=f"SA counterattack (consuming phase {consumed_die} die)",
    )
    ca_action.status_after = state.snapshot_status()
    log.add_action(ca_action)

    if not success:
        return 0

    margin = total - tn

    # Roll damage: weapon + fire + raises
    extra_dice = max(0, margin // 5)
    damage_rolled = weapon.rolled + fire_ring + extra_dice
    damage_kept = weapon.kept

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(
        damage_rolled, damage_kept, explode=True,
    )

    damage_action = CombatAction(
        phase=phase,
        actor=hida_name,
        action_type=ActionType.DAMAGE,
        target=target_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=f"{hida_name} counterattack deals {dmg_total} damage",
        dice_pool=format_pool_with_overflow(damage_rolled, damage_kept),
    )

    # Apply damage as light wounds
    wound_tracker = log.wounds[target_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = state.snapshot_status()
    log.add_action(damage_action)

    # --- Wound check for target ---
    water_value = target_char.rings.water.value

    # Compute wound check bonuses via Fighter hooks
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
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn

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

    return margin


class HidaFighter(Fighter):
    """Hida Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on attack, counterattack, wound check.
      2nd Dan: Free raise on counterattack (+5 flat).
      3rd Dan: Reroll 2X dice on counterattack or X on other attacks
               (X = counterattack rank). Reroll lowest dice <= 6.
               When crippled: halve reroll count (round up), but dice
               still explode.
      4th Dan: Water +1 / XP discount (builder). May take 2 SW instead
               of wound check, resetting LW to 0.
      5th Dan: Counterattack margin adds to wound check. May counterattack
               AFTER seeing damage.

    School Ability (SA): Counterattack as interrupt for 1 die (normal: 2).
    Penalty: attacker gets +5 on their attack roll.
    """

    _in_counterattack: bool = False
    _counterattack_margin: int = 0

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Hida always uses lunge — no DA knack."""
        return "lunge", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    def post_attack_reroll(
        self, all_dice: list[int], kept_count: int,
    ) -> tuple[list[int], list[int], int, str]:
        """3rd Dan: reroll X dice <= 6 on attacks (X = counterattack rank).

        When crippled: halve reroll count (round up), but dice still explode.
        """
        if self.dan < 3:
            kept_dice = sorted(all_dice, reverse=True)[:kept_count]
            return all_dice, kept_dice, sum(kept_dice), ""

        ca_skill = self.char.get_skill("Counterattack")
        ca_rank = ca_skill.rank if ca_skill else 0
        if ca_rank <= 0:
            kept_dice = sorted(all_dice, reverse=True)[:kept_count]
            return all_dice, kept_dice, sum(kept_dice), ""

        is_crippled = self.state.log.wounds[self.name].is_crippled
        reroll_count = ca_rank
        if is_crippled:
            reroll_count = (reroll_count + 1) // 2  # round up

        # Find dice <= 6, pick lowest N
        eligible = [(i, d) for i, d in enumerate(all_dice) if d <= 6]
        eligible.sort(key=lambda x: x[1])
        to_reroll = eligible[:reroll_count]

        if not to_reroll:
            kept_dice = sorted(all_dice, reverse=True)[:kept_count]
            return all_dice, kept_dice, sum(kept_dice), ""

        old_kept = sorted(all_dice, reverse=True)[:kept_count]
        old_total = sum(old_kept)
        old_values = sorted([d for _, d in to_reroll], reverse=True)

        # Reroll with explode (3rd Dan overrides crippled no-explode)
        for idx, _old in to_reroll:
            all_dice[idx] = roll_die(explode=True)
        new_values = sorted(
            [all_dice[idx] for idx, _ in to_reroll], reverse=True,
        )

        # Re-sort, re-keep, recalc
        all_dice = sorted(all_dice, reverse=True)
        kept_dice = all_dice[:kept_count]
        total = sum(kept_dice)

        diff = total - old_total
        note = (
            f" (hida 3rd Dan: rerolled"
            f" {old_values} → {new_values},"
            f" added {'+' if diff >= 0 else ''}{diff})"
        )
        return all_dice, kept_dice, total, note

    # -- Parry hooks (save dice for counterattack) --------------------------

    def should_predeclare_parry(
        self, attack_tn: int, phase: int,
    ) -> bool:
        """Hida never pre-declares parries (save dice for counterattack)."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Hida never parries — counterattack is the defense."""
        return False

    def should_interrupt_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Hida never interrupt-parries — counterattack is the defense."""
        return False

    # -- Counterattack hooks -----------------------------------------------

    def _consume_cheapest_die(self) -> int | None:
        """Consume the cheapest action die for counterattack."""
        if not self.actions_remaining:
            return None
        cheapest = min(self.actions_remaining)
        self.actions_remaining.remove(cheapest)
        return cheapest

    def resolve_pre_attack_counterattack(
        self, attacker_name: str, phase: int,
    ) -> tuple[int, int] | None:
        """Counterattack before opponent's attack roll.

        Returns (margin, sa_penalty=5) if counterattack fires.
        At 5th Dan, the margin is also stored for wound check bonus.
        """
        # Recursion prevention
        if self._in_counterattack:
            return None

        # Check for attacker already in counter-lunge or counterattack
        attacker_f = self.state.fighters.get(attacker_name)
        if attacker_f and getattr(attacker_f, '_in_counter_lunge', False):
            return None
        if attacker_f and getattr(attacker_f, '_in_counterattack', False):
            return None

        # Need dice to counterattack
        if not self.actions_remaining:
            return None

        # Don't counter if mortally wounded
        if self.state.log.wounds[self.name].is_mortally_wounded:
            return None
        if self.state.log.wounds[attacker_name].is_mortally_wounded:
            return None

        consumed = self._consume_cheapest_die()
        if consumed is None:
            return None

        self._in_counterattack = True
        try:
            margin = _resolve_hida_counterattack(
                self.state, self.name, attacker_name, phase, consumed,
            )
        finally:
            self._in_counterattack = False

        # 5th Dan: store margin for wound check bonus
        if self.dan >= 5 and margin > 0:
            self._counterattack_margin = margin

        return margin, 5

    def resolve_post_damage_counterattack(
        self, attacker_name: str, phase: int, damage_total: int,
    ) -> int:
        """5th Dan: counterattack after seeing damage, store margin.

        Returns counterattack margin if fired, else 0.
        """
        if self.dan < 5:
            return 0

        # Recursion prevention
        if self._in_counterattack:
            return 0

        # Check for attacker already in counter-lunge or counterattack
        attacker_f = self.state.fighters.get(attacker_name)
        if attacker_f and getattr(attacker_f, '_in_counter_lunge', False):
            return 0
        if attacker_f and getattr(attacker_f, '_in_counterattack', False):
            return 0

        # Need dice
        if not self.actions_remaining:
            return 0

        # Don't counter if mortally wounded
        if self.state.log.wounds[self.name].is_mortally_wounded:
            return 0
        if self.state.log.wounds[attacker_name].is_mortally_wounded:
            return 0

        consumed = self._consume_cheapest_die()
        if consumed is None:
            return 0

        self._in_counterattack = True
        try:
            margin = _resolve_hida_counterattack(
                self.state, self.name, attacker_name, phase, consumed,
            )
        finally:
            self._in_counterattack = False

        # Store margin for wound check flat bonus
        if margin > 0:
            self._counterattack_margin = margin

        return margin

    # -- Wound check hooks -------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """5th Dan: counterattack margin adds to wound check."""
        if self.dan >= 5 and self._counterattack_margin > 0:
            margin = self._counterattack_margin
            self._counterattack_margin = 0  # Consume after use
            return margin, f" (hida 5th Dan: +{margin} from counterattack)"
        return 0, ""

    def should_replace_wound_check(
        self, light_wounds: int,
    ) -> tuple[bool, int, str]:
        """4th Dan: take 2 SW instead of wound check when expecting 3+ SW.

        Estimates the wound check total (with max void spend) and only
        replaces when the expected serious wounds >= 3.
        """
        if self.dan < 4:
            return False, 0, ""

        water = self.char.rings.water.value
        max_void = min(self.total_void, self.char.rings.lowest())
        kept = water + max_void

        # ~6.5 average per kept die (exploding d10 keep-highest)
        expected_total = int(kept * 6.5)

        # 5th Dan wound check bonus from counterattack margin
        if self.dan >= 5:
            expected_total += self._counterattack_margin

        # Expected SW = 1 + (LW - expected_total) / 10  (when failing)
        expected_sw = 1 + max(0, (light_wounds - expected_total)) // 10
        if expected_sw >= 3:
            return True, 2, (
                " (hida 4th Dan: taking 2 SW instead of"
                " wound check, LW reset to 0)"
            )
        return False, 0, ""
