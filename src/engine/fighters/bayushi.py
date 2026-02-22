"""BayushiFighter: Bayushi Bushi school-specific overrides."""

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


def _resolve_bayushi_feint_damage(
    state: "CombatState",
    bayushi_name: str,
    target_name: str,
    phase: int,
    void_spent_on_feint: int,
) -> None:
    """Resolve Bayushi 3rd Dan feint damage against the target.

    Damage pool: (attack_rank)k1, exploding d10s.
    No Fire bonus, no raises bonus.
    SA bonus: +1k1 per void spent on the feint roll.
    """
    log = state.log
    bayushi_ctx = state.fighters[bayushi_name]
    target_ctx = state.fighters[target_name]
    bayushi_char: Character = bayushi_ctx.char
    target_char: Character = target_ctx.char

    atk_skill = bayushi_char.get_skill("Attack")
    atk_rank = atk_skill.rank if atk_skill else 0

    dmg_rolled = atk_rank
    dmg_kept = 1

    # SA bonus: +1k1 per void spent on the feint roll
    sa_extra_rolled, sa_extra_kept = bayushi_ctx.sa_attack_damage_bonus(
        void_spent_on_feint,
    )
    dmg_rolled += sa_extra_rolled
    dmg_kept += sa_extra_kept

    if dmg_rolled <= 0:
        return

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(
        dmg_rolled, dmg_kept, explode=True,
    )

    sa_note = ""
    if sa_extra_rolled > 0:
        sa_note = f" (SA: +{sa_extra_rolled}k{sa_extra_kept} from void)"

    damage_action = CombatAction(
        phase=phase,
        actor=bayushi_name,
        action_type=ActionType.DAMAGE,
        target=target_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=(
            f"{bayushi_name} feint deals {dmg_total} damage"
            f" ({format_pool_with_overflow(dmg_rolled, dmg_kept)})"
            f"{sa_note}"
        ),
        dice_pool=format_pool_with_overflow(dmg_rolled, dmg_kept),
        label="feint damage (bayushi 3rd Dan)",
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


class BayushiFighter(Fighter):
    """Bayushi Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on DA, iaijutsu, and wound check.
      2nd Dan: Free raise on DA (+20 TN forgiven = near-miss DA).
      3rd Dan: Feints deal Xk1 damage (X = attack rank).
               No Fire bonus, no raises bonus. SA may increase.
      4th Dan: Fire +1 / XP discount (builder). After any feint,
               apply a free raise to any future attack this combat.
      5th Dan: Failed wound check uses half LW for serious calculation.

    School Ability (SA): When spending void on attack rolls, add 1k1
                         to damage per void spent.

    Strategy: Offense-first. Feint 1-2 times to build damage/raises,
              then DA. Parry only against extremely dangerous attacks.
    """

    _MAX_FEINTS_PER_ROUND = 2

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.feints_this_round: int = 0

    def on_round_start(self) -> None:
        """Reset per-round feint counter."""
        self.feints_this_round = 0

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Choose attack type: feint to build resources, then DA/attack."""
        feint_skill = self.char.get_skill("Feint")
        feint_rank = feint_skill.rank if feint_skill else 0
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0

        # Remaining actions after the current die is consumed
        remaining = len(self.actions_remaining)

        void_spend = min(1, self.total_void) if self.total_void > 0 else 0

        can_feint = (
            self.dan >= 3
            and feint_rank > 0
            and remaining > 0
            and self.feints_this_round < self._MAX_FEINTS_PER_ROUND
        )

        if can_feint:
            return "feint", void_spend

        if self.dan >= 2 and da_rank > 0:
            # 2nd Dan+: DA with near-miss free raise
            return "double_attack", void_spend

        if self.dan >= 1 and da_rank > 0:
            return "double_attack", void_spend

        return "attack", void_spend

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on DA (also applied to attack rolls)."""
        return 1 if self.dan >= 1 else 0

    def da_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on DA (informational accessor)."""
        return 1 if self.dan >= 1 else 0

    def on_near_miss_da(self) -> bool:
        """2nd Dan: free raise on DA (near-miss DA still hits)."""
        return self.dan >= 2

    def near_miss_da_description(self) -> str:
        """2nd Dan: near-miss DA description."""
        return " (bayushi 2nd Dan: free raise DA, base damage only)"

    # -- SA hooks -----------------------------------------------------------

    def sa_attack_damage_bonus(self, void_spent: int) -> tuple[int, int]:
        """SA: +1k1 damage per void spent on attack rolls."""
        if void_spent > 0:
            return void_spent, void_spent
        return 0, 0

    def attack_void_strategy(
        self, rolled: int, kept: int, tn: int,
    ) -> int:
        """Spend void on normal attacks for SA damage bonus."""
        if self.total_void > 0:
            return 1
        return 0

    # -- Feint hooks --------------------------------------------------------

    def feint_damage_pool(self) -> tuple[int, int]:
        """3rd Dan: feint damage = attack_rank k 1."""
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            return atk_rank, 1
        return 0, 0

    def on_feint_result(
        self, feint_landed: bool, phase: int,
        defender_name: str = "", void_spent: int = 0,
        *, feint_met_tn: bool = False,
    ) -> None:
        """3rd Dan: feint damage. 4th Dan: store free raise. Track count."""
        self.feints_this_round += 1

        # 3rd Dan: deal feint damage if landed
        if self.dan >= 3 and feint_landed and defender_name:
            _resolve_bayushi_feint_damage(
                self.state, self.name, defender_name, phase, void_spent,
            )

        # 4th Dan: store free raise regardless of outcome
        if self.dan >= 4:
            self.feint_free_raises += 1

    def consume_free_raise_bonus(self) -> tuple[int, str]:
        """Consume accumulated free raises from feints."""
        if self.feint_free_raises > 0:
            bonus = 5 * self.feint_free_raises
            count = self.feint_free_raises
            self.feint_free_raises = 0
            return bonus, (
                f" (bayushi 4th Dan: {count} free raise(s) +{bonus})"
            )
        return 0, ""

    # -- Parry hooks (offense-first: only parry extreme threats) -------------

    def should_predeclare_parry(
        self, attack_tn: int, phase: int,
    ) -> bool:
        """Bayushi never pre-declares parry — offense first."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Parry reactively only against extremely high damage."""
        parry_skill = self.char.get_skill("Parry")
        parry_rank = parry_skill.rank if parry_skill else 0
        if parry_rank <= 0:
            return False

        extra_dice = max(0, (attack_total - attack_tn) // 5)
        damage_rolled = weapon_rolled + attacker_fire + extra_dice

        wound_info = self.state.log.wounds[self.name]
        wounds_to_cripple = wound_info.earth_ring - wound_info.serious_wounds

        # Only parry if near cripple with raises, or massive damage pool
        if wounds_to_cripple <= 1 and extra_dice >= 2:
            return True
        return damage_rolled > 15

    def should_interrupt_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Interrupt parry only against lethal damage (costs 2 dice)."""
        parry_skill = self.char.get_skill("Parry")
        parry_rank = parry_skill.rank if parry_skill else 0
        if parry_rank <= 0 or len(self.actions_remaining) < 2:
            return False

        extra_dice = max(0, (attack_total - attack_tn) // 5)
        damage_rolled = weapon_rolled + attacker_fire + extra_dice

        wound_info = self.state.log.wounds[self.name]
        wounds_to_cripple = wound_info.earth_ring - wound_info.serious_wounds

        # Only interrupt if about to die, or damage pool is massive
        if wounds_to_cripple <= 0:
            return True
        return damage_rolled > 18

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound check."""
        return 1 if self.dan >= 1 else 0

    def wound_check_serious_lw(self, light_wounds: int) -> int:
        """5th Dan: halve LW for serious wound calculation on failed WC."""
        if self.dan >= 5:
            return light_wounds // 2
        return light_wounds

    def wound_check_lw_severity_divisor(self) -> int:
        """5th Dan: tolerate ~2x LW before converting (halved serious on failure)."""
        return 2 if self.dan >= 5 else 1
