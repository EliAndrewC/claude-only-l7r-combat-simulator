"""ShibaFighter: Shiba Bushi school-specific overrides."""

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
    should_spend_void_on_wound_check,
    void_spent_label,
)
from src.models.character import Character
from src.models.combat import ActionType, CombatAction


def _resolve_shiba_parry_damage(
    state: "CombatState",
    shiba_name: str,
    target_name: str,
    phase: int,
) -> None:
    """Resolve Shiba 3rd Dan parry damage against the attacker.

    Damage pool: (2 * attack_rank)k1, exploding d10s.
    No Fire bonus, no raises bonus.
    """
    log = state.log
    shiba_ctx = state.fighters[shiba_name]
    target_ctx = state.fighters[target_name]
    shiba_char: Character = shiba_ctx.char
    target_char: Character = target_ctx.char

    atk_skill = shiba_char.get_skill("Attack")
    atk_rank = atk_skill.rank if atk_skill else 0

    dmg_rolled = 2 * atk_rank
    dmg_kept = 1

    if dmg_rolled <= 0:
        return

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(
        dmg_rolled, dmg_kept, explode=True,
    )

    damage_action = CombatAction(
        phase=phase,
        actor=shiba_name,
        action_type=ActionType.DAMAGE,
        target=target_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=(
            f"{shiba_name} parry deals {dmg_total} damage"
            f" ({format_pool_with_overflow(dmg_rolled, dmg_kept)})"
        ),
        dice_pool=format_pool_with_overflow(dmg_rolled, dmg_kept),
        label="parry damage (shiba 3rd Dan)",
    )

    # Apply damage as light wounds
    wound_tracker = log.wounds[target_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = state.snapshot_status()
    log.add_action(damage_action)

    # --- Wound check for target ---
    water_value = target_char.rings.water.value

    # Wound check extra rolled via Fighter hook
    wc_extra_rolled = target_ctx.wound_check_extra_rolled()

    # Void strategy
    wc_void_strategy = target_ctx.wound_check_void_strategy(
        water_value, wound_tracker.light_wounds,
    )
    max_spend = target_char.rings.lowest()
    if wc_void_strategy == 0:
        void_spend = 0
    else:
        void_spend = should_spend_void_on_wound_check(
            water_value, wound_tracker.light_wounds, target_ctx.total_void,
            max_spend=max_spend, extra_rolled=wc_extra_rolled,
        )
    wc_from_temp, wc_from_reg = target_ctx.spend_void(void_spend)
    wc_void_label = void_spent_label(wc_from_temp, wc_from_reg)

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


class ShibaFighter(Fighter):
    """Shiba Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on double attack, parry, and wound check.
      2nd Dan: Free raise on parry (+5 flat).
      3rd Dan: Parries (success or fail) deal (2X)k1 damage
               (X = attack rank). No Fire bonus, no raises bonus.
      4th Dan: Air +1 / XP discount (builder). +3k1 on wound checks
               (3 extra rolled, 1 extra kept).
      5th Dan: After successful parry, opponent's TN lowered by parry
               margin. Stacks across parries. Consumed when Shiba attacks.

    School Ability (SA): Interrupt parry for 1 die (lowest).
    """

    # -- Attack hooks -------------------------------------------------------

    def should_consume_phase_die(self, phase: int) -> bool:
        """Pre-5th Dan: never attack. 5th Dan: attack when ready."""
        if self.dan < 5:
            return False
        # 5th Dan: attack when accumulated TN reduction >= base TN
        opp_name = self.opponent_name
        opp_ctx = self.state.fighters[opp_name]
        def_parry_skill = opp_ctx.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        base_tn = 5 + 5 * def_parry_rank
        return self.parry_tn_reduction >= base_tn

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """5th Dan: double attack. Otherwise normal attack."""
        if self.dan >= 5:
            return "double_attack", 0
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    # -- Parry hooks (as defender) ------------------------------------------

    def should_predeclare_parry(
        self, attack_tn: int, phase: int,
    ) -> bool:
        """Shiba always pre-declares parry."""
        return True

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Shiba always reactive parries."""
        return True

    def should_interrupt_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Shiba always interrupt parries."""
        return True

    def select_parry_die(self, phase: int) -> int | None:
        """Shiba: spend lowest eligible die <= phase (save high dice)."""
        eligible = [d for d in self.actions_remaining if d <= phase]
        return min(eligible) if eligible else None

    def min_interrupt_dice(self) -> int:
        """SA: interrupt for 1 die."""
        return 1

    def consume_interrupt_parry_dice(self) -> tuple[list[int], int]:
        """SA: consume 1 lowest die for interrupt parry."""
        if not self.actions_remaining:
            return [], 0
        lowest = min(self.actions_remaining)
        self.actions_remaining.remove(lowest)
        return [lowest], lowest

    def parry_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on parry."""
        return 1 if self.dan >= 1 else 0

    def parry_bonus(self) -> int:
        """2nd Dan: +5 free-raise bonus on parry."""
        return 5 if self.dan >= 2 else 0

    def parry_bonus_description(self, bonus: int) -> str:
        """2nd Dan: shiba-specific parry bonus description."""
        return f" (shiba 2nd Dan: free raise +{bonus})"

    def on_parry_attempt(
        self, parry_succeeded: bool, margin: int,
        attacker_name: str = "", phase: int = 0,
    ) -> None:
        """3rd Dan: parry damage. 5th Dan: accumulate TN reduction."""
        # 3rd Dan: parry damage (fires on success or failure)
        if self.dan >= 3 and attacker_name:
            _resolve_shiba_parry_damage(
                self.state, self.name, attacker_name, phase,
            )

        # 5th Dan: store parry margin as TN reduction
        if self.dan >= 5 and parry_succeeded and margin > 0:
            self.parry_tn_reduction += margin

    # -- Wound check hooks (as defender) ------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die. 4th Dan: +3k1 (3 extra rolled + 1 extra kept)."""
        if self.dan >= 4:
            return 4  # 3 extra + 1 from 1st Dan
        if self.dan >= 1:
            return 1
        return 0

    def wound_check_extra_kept(self) -> int:
        """4th Dan: +1 extra kept die on wound check."""
        return 1 if self.dan >= 4 else 0
