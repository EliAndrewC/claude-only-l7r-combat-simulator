"""DaidojiFighter: Daidoji Yojimbo school-specific overrides.

SA: Counterattack as interrupt for 1 action die; opponent gets free raise on WC
    from counterattack damage if Daidoji hits.
1st Dan: +1 rolled die on attack, counterattack, and wound checks.
2nd Dan: Free raise on counterattack rolls (+5 flat).
3rd Dan: When counterattacking, Daidoji's WC from original attack gets
         attack_rank * 5 bonus.
4th Dan: Water +1 (builder). May take damage for adjacent ally (no-op 1v1).
5th Dan: After WC, lower opponent's TN by WC excess for next attack.
"""

from __future__ import annotations

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


def _resolve_daidoji_counterattack(
    state: "CombatState",
    daidoji_name: str,
    target_name: str,
    phase: int,
    consumed_die: int,
) -> int:
    """Resolve a Daidoji counterattack against the target.

    Returns the margin (total - TN) if the counterattack hits, else 0.
    SA: opponent gets free raise (+5) on wound check if Daidoji hits.
    """
    log = state.log
    daidoji_ctx = state.fighters[daidoji_name]
    target_ctx = state.fighters[target_name]
    daidoji_char: Character = daidoji_ctx.char
    target_char: Character = target_ctx.char
    weapon: Weapon = daidoji_ctx.weapon

    dan = daidoji_char.dan

    # Counterattack skill
    ca_skill = daidoji_char.get_skill("Counterattack")
    ca_rank = ca_skill.rank if ca_skill else 0

    # Target's parry rank
    def_parry_skill = target_char.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # TN = 5 + 5 * target's parry rank
    tn = 5 + 5 * def_parry_rank

    # Roll: counterattack_rank + fire_ring + (1 if dan >= 1)
    fire_ring = daidoji_char.rings.fire.value
    rolled = ca_rank + fire_ring + (1 if dan >= 1 else 0)
    kept = fire_ring

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=True)

    # 2nd Dan: free raise (+5 to total)
    bonus_note = ""
    if dan >= 2:
        total += 5
        bonus_note = " (daidoji 2nd Dan: free raise +5)"

    success = total >= tn

    ca_action = CombatAction(
        phase=phase,
        actor=daidoji_name,
        action_type=ActionType.COUNTERATTACK,
        target=target_name,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=tn,
        success=success,
        description=(
            f"{daidoji_name} counterattacks: "
            f"{format_pool_with_overflow(rolled, kept)}"
            f" vs TN {tn}{bonus_note}"
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
        actor=daidoji_name,
        action_type=ActionType.DAMAGE,
        target=target_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=f"{daidoji_name} counterattack deals {dmg_total} damage",
        dice_pool=format_pool_with_overflow(damage_rolled, damage_kept),
    )

    # Apply damage as light wounds
    wound_tracker = log.wounds[target_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = state.snapshot_status()
    log.add_action(damage_action)

    # --- Wound check for target ---
    # SA: opponent gets free raise (+5) on wound check
    sa_wc_bonus = 5
    sa_wc_note = " (daidoji SA: opponent free raise +5)"

    water_value = target_char.rings.water.value
    wc_extra_rolled = target_ctx.wound_check_extra_rolled()

    max_spend = target_char.rings.lowest()
    void_spend = should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, target_ctx.total_void,
        max_spend=max_spend, extra_rolled=wc_extra_rolled,
        tn_bonus=sa_wc_bonus,
    )
    wc_from_temp, wc_from_reg, wc_from_wl = target_ctx.spend_void(void_spend)
    wc_void_label = void_spent_label(wc_from_temp, wc_from_reg, wc_from_wl)

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=wc_extra_rolled,
    )

    # Apply SA WC bonus
    wc_total += sa_wc_bonus

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
            f"(rolled {wc_total}){void_note}{sa_wc_note}{wc_flat_note}"
            f"{convert_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    if not passed:
        wound_tracker.light_wounds = 0

    wc_action.status_after = state.snapshot_status()

    return margin


class DaidojiFighter(Fighter):
    """Daidoji Yojimbo fighter with school technique overrides."""

    _in_counterattack: bool = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._counterattack_wc_bonus: int = 0
        self._in_counterattack = False

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Daidoji prefers DA when available, else normal attack."""
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "attack", 0
        if da_rank > 0:
            return "double_attack", 0
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack and counterattack."""
        return 1 if self.dan >= 1 else 0

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

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """3rd Dan: Bonus from counterattack stored WC bonus."""
        if self._counterattack_wc_bonus > 0:
            bonus = self._counterattack_wc_bonus
            self._counterattack_wc_bonus = 0
            note = f" (daidoji 3rd Dan: +{bonus} from counterattack)"
            return bonus, note
        return 0, ""

    # -- 5th Dan: WC excess → TN reduction on opponent ----------------------

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """5th Dan: After WC, lower opponent's TN by WC excess."""
        if self.dan >= 5 and passed:
            wound_tracker = self.state.log.wounds[self.name]
            tn = wound_tracker.light_wounds
            excess = wc_total - tn
            if excess > 0:
                # Store as parry_tn_reduction (lowers opponent's TN for next attack)
                self.parry_tn_reduction += excess
        return passed, wc_total, ""

    # -- SA: Counterattack as interrupt for 1 die ---------------------------

    def can_interrupt(self) -> bool:
        """Daidoji can counterattack as interrupt."""
        ca_skill = self.char.get_skill("Counterattack")
        ca_rank = ca_skill.rank if ca_skill else 0
        return ca_rank > 0 and len(self.actions_remaining) >= 1

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
        """SA: Counterattack interrupt for 1 die.

        Returns (margin, sa_penalty=0) if counterattack fires, else None.
        """
        if self._in_counterattack:
            return None
        if not self.can_interrupt():
            return None

        # Don't counter if mortally wounded
        if self.state.log.wounds[self.name].is_mortally_wounded:
            return None
        if self.state.log.wounds[attacker_name].is_mortally_wounded:
            return None

        # Check for attacker already in counterattack
        attacker_f = self.state.fighters.get(attacker_name)
        if attacker_f and getattr(attacker_f, '_in_counterattack', False):
            return None

        consumed = self._consume_cheapest_die()
        if consumed is None:
            return None

        # Store 3rd Dan WC bonus
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            self._counterattack_wc_bonus = atk_rank * 5

        self._in_counterattack = True
        try:
            margin = _resolve_daidoji_counterattack(
                self.state, self.name, attacker_name, phase, consumed,
            )
        finally:
            self._in_counterattack = False

        # No SA penalty on attacker's subsequent attack (unlike Hida)
        return margin, 0
