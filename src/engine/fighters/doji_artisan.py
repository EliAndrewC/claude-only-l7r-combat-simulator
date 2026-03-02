"""DojiArtisanFighter: Doji Artisan school-specific overrides.

SA: Spend void to counterattack as interrupt for 1 die; void gives +1k1.
    Counterattack bonus = attacker's roll / 5.
1st Dan: +1 rolled die on counterattack, manipulation, and wound checks.
2nd Dan: Free raise on manipulation (non-combat, no-op).
3rd Dan: 2X free raises (X = culture skill), for counterattack and WC.
4th Dan: Water +1 (builder). When attacking a target who hasn't attacked you
         this round, bonus = current phase.
5th Dan: On any TN or contested roll, bonus = (TN - 10) / 5 (min 0).
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
    format_pool_with_overflow,
    should_convert_light_to_serious,
    should_spend_void_on_combat_roll,
    should_spend_void_on_wound_check,
    void_spent_label,
)
from src.models.character import Character
from src.models.combat import ActionType, CombatAction
from src.models.weapon import Weapon


def _resolve_doji_artisan_counterattack(
    state: "CombatState",
    doji_name: str,
    target_name: str,
    phase: int,
    consumed_die: int,
    attacker_roll: int,
) -> int:
    """Resolve a Doji Artisan SA counterattack against the target.

    SA: Spend void for +1k1 on counterattack. Bonus = attacker's roll / 5.
    Returns the margin (total - TN) if hit, else 0.
    """
    log = state.log
    doji_ctx = state.fighters[doji_name]
    target_ctx = state.fighters[target_name]
    doji_char: Character = doji_ctx.char
    target_char: Character = target_ctx.char
    weapon: Weapon = doji_ctx.weapon

    dan = doji_char.dan

    # Counterattack skill
    ca_skill = doji_char.get_skill("Counterattack")
    ca_rank = ca_skill.rank if ca_skill else 0

    # Target's parry rank
    def_parry_skill = target_char.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # TN = 5 + 5 * target's parry rank
    tn = 5 + 5 * def_parry_rank

    # Roll: CA + Fire + void(+1k1) + 1st Dan(+1 rolled)
    fire_ring = doji_char.rings.fire.value
    first_dan_extra = 1 if dan >= 1 else 0
    # SA void gives +1k1
    rolled = ca_rank + fire_ring + 1 + first_dan_extra
    kept = fire_ring + 1

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=True)

    # SA bonus: attacker's roll / 5
    atk_bonus = attacker_roll // 5
    bonus_notes: list[str] = []
    if atk_bonus > 0:
        total += atk_bonus
        bonus_notes.append(f"SA: +{atk_bonus} (attacker roll {attacker_roll}/5)")

    # 3rd Dan: free raises on counterattack
    if dan >= 3 and doji_ctx._free_raises > 0:
        deficit = tn - total
        if deficit > 0:
            raises_needed = math.ceil(deficit / 5)
            usable = min(doji_ctx._max_per_roll, doji_ctx._free_raises)
            if raises_needed <= usable:
                doji_ctx._free_raises -= raises_needed
                raise_bonus = raises_needed * 5
                total += raise_bonus
                bonus_notes.append(
                    f"3rd Dan: {raises_needed} free raise(s) +{raise_bonus},"
                    f" {doji_ctx._free_raises} remaining"
                )

    # 5th Dan: +(TN - 10) / 5 bonus
    if dan >= 5 and tn > 10:
        fifth_bonus = (tn - 10) // 5
        if fifth_bonus > 0:
            total += fifth_bonus
            bonus_notes.append(f"5th Dan: +{fifth_bonus}")

    success = total >= tn
    bonus_note = f" ({'; '.join(bonus_notes)})" if bonus_notes else ""

    ca_action = CombatAction(
        phase=phase,
        actor=doji_name,
        action_type=ActionType.COUNTERATTACK,
        target=target_name,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=tn,
        success=success,
        description=(
            f"{doji_name} counterattacks: "
            f"{format_pool_with_overflow(rolled, kept)}"
            f" vs TN {tn}{bonus_note}"
        ),
        dice_pool=format_pool_with_overflow(rolled, kept),
        label=f"SA counterattack (void + phase {consumed_die} die)",
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
        actor=doji_name,
        action_type=ActionType.DAMAGE,
        target=target_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=f"{doji_name} counterattack deals {dmg_total} damage",
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
            mortal_wound_threshold=wound_tracker.mortal_wound_threshold,
        )
        if should_convert:
            wound_tracker.serious_wounds += 1
            wound_tracker.light_wounds = 0
            convert_note = " — converted light wounds to 1 serious wound"
        else:
            convert_note = (
                f" — keeping {wound_tracker.light_wounds} light wounds"
            )

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


class DojiArtisanFighter(Fighter):
    """Doji Artisan fighter with school technique overrides."""

    _in_counterattack: bool = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        culture_skill = self.char.get_skill("Culture")
        culture_rank = culture_skill.rank if culture_skill else 0
        self._free_raises = 2 * culture_rank if self.dan >= 3 else 0
        self._max_per_roll = culture_rank if self.dan >= 3 else 0
        self._opponent_attacked_this_round = False
        self._in_counterattack = False

    # -- Round hooks --------------------------------------------------------

    def on_round_start(self) -> None:
        """Reset per-round tracking."""
        self._opponent_attacked_this_round = False

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Doji Artisan uses normal attacks (CA is defensive/interrupt)."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """No extra die on normal attacks (1st Dan is CA/manipulation/WC)."""
        return 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Standard void spending."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """4th Dan: +phase bonus when target hasn't attacked this round.
        5th Dan: +(TN - 10) / 5 bonus.
        """
        bonus = 0
        notes: list[str] = []

        if self.dan >= 4 and not self._opponent_attacked_this_round:
            bonus += phase
            notes.append(f"doji 4th Dan: +{phase} (phase bonus)")

        note = f" ({'; '.join(notes)})" if notes else ""
        return bonus, note

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str,
    ) -> tuple[int, str]:
        """5th Dan: +(TN - 10) / 5 bonus on attack. 3rd Dan: free raises."""
        total_bonus = 0
        notes: list[str] = []

        if self.dan >= 5 and tn > 10:
            fifth_bonus = (tn - 10) // 5
            if fifth_bonus > 0:
                total_bonus += fifth_bonus
                notes.append(f"doji 5th Dan: +{fifth_bonus}")

        # 3rd Dan: free raises to bridge deficit
        if self.dan >= 3 and self._free_raises > 0:
            deficit = tn - (attack_total + total_bonus)
            if deficit > 0:
                raises_needed = math.ceil(deficit / 5)
                usable = min(self._max_per_roll, self._free_raises)
                if raises_needed <= usable:
                    self._free_raises -= raises_needed
                    raise_bonus = raises_needed * 5
                    total_bonus += raise_bonus
                    notes.append(
                        f"doji 3rd Dan: {raises_needed} free raise(s)"
                        f" +{raise_bonus}, {self._free_raises} remaining"
                    )

        note = f" ({'; '.join(notes)})" if notes else ""
        return total_bonus, note

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wc_bonus_pool_total(self) -> int:
        """3rd Dan: Remaining free raise pool for WC."""
        if self.dan >= 3:
            usable = min(self._free_raises, self._max_per_roll)
            return usable * 5
        return 0

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: Spend free raises on failed WC. Track opponent attacked."""
        self._opponent_attacked_this_round = True

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
            f" (doji 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- SA: Counterattack as interrupt ------------------------------------

    def resolve_post_attack_interrupt(
        self, attacker_name: str, phase: int,
        attack_total: int = 0,
    ) -> None:
        """SA: Counterattack interrupt — spend void + 1 die. Void gives +1k1.

        Bonus = attacker's roll / 5. Fires after opponent attacks.
        """
        if self._in_counterattack:
            return

        # Need void and dice
        if self.total_void < 1:
            return
        if not self.actions_remaining:
            return

        # Need counterattack skill
        ca_skill = self.char.get_skill("Counterattack")
        ca_rank = ca_skill.rank if ca_skill else 0
        if ca_rank <= 0:
            return

        # Don't counter if mortally wounded
        if self.state.log.wounds[self.name].is_mortally_wounded:
            return
        if self.state.log.wounds[attacker_name].is_mortally_wounded:
            return

        # Check for attacker already in counterattack
        attacker_f = self.state.fighters.get(attacker_name)
        if attacker_f and getattr(attacker_f, '_in_counterattack', False):
            return

        # Consume cheapest die + 1 void
        cheapest = min(self.actions_remaining)
        self.actions_remaining.remove(cheapest)
        self.spend_void(1)

        self._in_counterattack = True
        try:
            _resolve_doji_artisan_counterattack(
                self.state, self.name, attacker_name, phase,
                cheapest, attack_total,
            )
        finally:
            self._in_counterattack = False
