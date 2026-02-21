"""Base Fighter class with default (generic / Wave Man) behavior.

School subclasses override only the methods that differ.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState
    from src.models.character import Character
    from src.models.weapon import Weapon


class Fighter:
    """Base fighter wrapping a Character + CombatState reference.

    Provides default (generic / Wave Man) implementations for all hook
    methods.  School subclasses override only what differs.

    Owns mutable per-fighter state (void, actions, bonuses).
    """

    def __init__(
        self,
        name: str,
        state: CombatState,
        char: Character | None = None,
        weapon: Weapon | None = None,
        void_points: int = 0,
        temp_void: int = 0,
        dan_points: int = 0,
        actions_remaining: list[int] | None = None,
        matsu_bonuses: list[int] | None = None,
        shinjo_bonuses: list[int] | None = None,
        lunge_target_bonus: int = 0,
    ) -> None:
        self._name = name
        self._state = state

        # Mutable per-fighter state
        self._char = char
        self._weapon = weapon
        self.void_points = void_points
        self.temp_void = temp_void
        self.dan_points = dan_points
        self.actions_remaining = actions_remaining if actions_remaining is not None else []
        self.matsu_bonuses = matsu_bonuses if matsu_bonuses is not None else []
        self.shinjo_bonuses = shinjo_bonuses if shinjo_bonuses is not None else []
        self.lunge_target_bonus = lunge_target_bonus
        self.parry_tn_reduction = 0
        self.feint_free_raises = 0

    # -- Convenience accessors ------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CombatState:
        return self._state

    @property
    def char(self) -> Character:
        return self._char  # type: ignore[return-value]

    @property
    def weapon(self) -> Weapon:
        return self._weapon  # type: ignore[return-value]

    @property
    def total_void(self) -> int:
        """Total available void = regular + temp."""
        return self.void_points + self.temp_void

    def spend_void(self, amount: int) -> tuple[int, int]:
        """Spend void points, consuming temp void first.

        Returns:
            Tuple of (from_temp, from_regular).
        """
        from_temp = min(amount, self.temp_void)
        if from_temp > 0:
            self.temp_void -= from_temp
        remainder = amount - from_temp
        from_regular = 0
        if remainder > 0:
            from_regular = min(remainder, self.void_points)
            self.void_points -= from_regular
        return from_temp, from_regular

    @property
    def dan(self) -> int:
        return self.char.dan

    @property
    def opponent_name(self) -> str:
        return self._state.get_opponent(self._name)

    # -- Initiative hooks -----------------------------------------------

    def initiative_extra_unkept(self) -> int:
        """Extra unkept dice on initiative (default 0)."""
        return 0

    def post_initiative(
        self, rolled_dice: list[int], kept_dice: list[int],
    ) -> list[int]:
        """Transform initiative dice after rolling (default: no-op).

        Args:
            rolled_dice: All dice from the initiative roll.
            kept_dice: The sorted kept initiative dice.

        Returns:
            The (possibly modified) action dice list.
        """
        return kept_dice

    def post_initiative_description(
        self, old_actions: list[int], new_actions: list[int],
    ) -> str:
        """Description for post-initiative dice changes (default: empty)."""
        return ""

    def on_round_start(self) -> None:
        """Called at the beginning of each round (default: no-op)."""

    # -- Attack hooks ---------------------------------------------------

    def should_consume_phase_die(self, phase: int) -> bool:
        """Whether to consume and attack with the phase die (default True)."""
        return True

    def consume_attack_die(
        self, phase: int, die_value: int | None = None,
    ) -> int | None:
        """Consume an action die for attacking.

        Returns the consumed die value, or None to skip the attack.
        """
        if die_value is not None:
            if die_value in self.actions_remaining:
                self.actions_remaining.remove(die_value)
                return die_value
            return None
        if not self.should_consume_phase_die(phase):
            return None
        if phase in self.actions_remaining:
            self.actions_remaining.remove(phase)
            return phase
        return None

    def choose_attack(
        self, defender_name: str, phase: int
    ) -> tuple[str, int]:
        """Choose attack type and void spend.

        Returns:
            Tuple of ("attack" | "lunge" | "double_attack", void_to_spend).
        """
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """Extra rolled dice on attack (default 0)."""
        return 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Decide void to spend on normal attack (default 0)."""
        return 0

    def fifth_dan_void_bonus(self, void_spent: int) -> int:
        """Flat bonus per void spent on attack/parry (default 0)."""
        return 0

    def fifth_dan_void_description(self, bonus: int) -> str:
        """Description for 5th Dan void bonus (default: empty)."""
        return ""

    def near_miss_da_description(self) -> str:
        """Description for near-miss DA hit (default: empty)."""
        return ""

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """SA bonus applied to attack roll (default: none)."""
        return 0, ""

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str
    ) -> tuple[int, str]:
        """Post-roll bonus to attack total.

        Returns:
            Tuple of (bonus_amount, description_note).
        """
        return 0, ""

    def post_attack_reroll(
        self, all_dice: list[int], kept_count: int,
    ) -> tuple[list[int], list[int], int, str]:
        """School-technique reroll after attack roll (default: no-op).

        Returns (all_dice, kept_dice, total, note).
        """
        kept_dice = sorted(all_dice, reverse=True)[:kept_count]
        return all_dice, kept_dice, sum(kept_dice), ""

    # -- Feint hooks ----------------------------------------------------

    def feint_extra_rolled(self) -> int:
        """Extra rolled dice on feint attacks (default 0)."""
        return 0

    def on_feint_result(
        self, feint_landed: bool, phase: int,
        defender_name: str = "", void_spent: int = 0,
    ) -> None:
        """Called after every feint attempt (default: no-op)."""

    def consume_free_raise_bonus(self) -> tuple[int, str]:
        """Consume accumulated free raises. Returns (bonus, description_note)."""
        return 0, ""

    # -- SA damage hooks ------------------------------------------------

    def sa_attack_damage_bonus(self, void_spent: int) -> tuple[int, int]:
        """Extra (rolled, kept) damage dice from SA when void spent on attack.

        Default: no bonus.
        """
        return 0, 0

    # -- Wound check overrides ------------------------------------------

    def wound_check_serious_lw(self, light_wounds: int) -> int:
        """Effective LW for serious wound calc on failed WC.

        Default: returns light_wounds unchanged.
        """
        return light_wounds

    def wound_check_lw_severity_divisor(self) -> int:
        """Divisor for LW severity when deciding to convert on a passed WC.

        Fighters whose failed wound checks use reduced LW (e.g. Bayushi 5th
        Dan halves LW) can tolerate proportionally more light wounds before
        voluntarily converting.  Default: 1 (no adjustment).
        """
        return 1

    # -- Parry hooks (as defender) --------------------------------------

    def has_action_in_phase(self, phase: int) -> bool:
        """Whether the fighter has an action die in this phase."""
        return phase in self.actions_remaining

    def select_parry_die(self, phase: int) -> int | None:
        """Select which die to spend for a parry in this phase.

        Returns the die value to remove from actions_remaining, or None.
        """
        if phase in self.actions_remaining:
            return phase
        return None

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Whether to pre-declare a parry (default: generic heuristic)."""
        from src.engine.simulation_utils import (
            should_predeclare_parry,
        )

        parry_skill = self.char.get_skill("Parry")
        parry_rank = parry_skill.rank if parry_skill else 0
        if parry_rank <= 0:
            return False
        is_crippled = self.state.log.wounds[self.name].is_crippled
        return should_predeclare_parry(
            parry_rank, self.char.rings.air.value,
            attack_tn, is_crippled,
        )

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Whether to parry with 1 die (default: generic heuristic)."""
        from src.engine.simulation_utils import (
            should_reactive_parry,
        )

        parry_skill = self.char.get_skill("Parry")
        parry_rank = parry_skill.rank if parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
        return should_reactive_parry(
            parry_rank, self.char.rings.air.value,
            attack_total, attack_tn,
            weapon_rolled, attacker_fire,
            wound_info.serious_wounds, wound_info.earth_ring,
            wound_info.is_crippled,
        )

    def can_interrupt(self) -> bool:
        """Whether the fighter can interrupt-parry (default True)."""
        return True

    def should_interrupt_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Whether to spend 2 dice for interrupt parry (default: generic heuristic)."""
        from src.engine.simulation_utils import (
            should_interrupt_parry,
        )

        parry_skill = self.char.get_skill("Parry")
        parry_rank = parry_skill.rank if parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
        return should_interrupt_parry(
            parry_rank, self.char.rings.air.value,
            attack_total, attack_tn,
            weapon_rolled, attacker_fire,
            len(self.actions_remaining),
            wound_info.serious_wounds, wound_info.earth_ring,
        )

    def parry_extra_rolled(self) -> int:
        """Extra rolled dice on parry (default 0)."""
        return 0

    def parry_bonus(self) -> int:
        """Flat bonus to parry total from school techniques (default 0)."""
        return 0

    def parry_bonus_description(self, bonus: int) -> str:
        """Description for school parry bonus (default: generic)."""
        return f" (free raise +{bonus})"

    def sa_parry_bonus(
        self, phase: int, parry_die_value: int,
    ) -> tuple[int, str]:
        """SA bonus applied to parry roll (default: none)."""
        return 0, ""

    def can_phase_shift_parry(
        self, phase: int,
    ) -> tuple[bool, int, int]:
        """Whether this fighter can phase-shift parry.

        Returns:
            Tuple of (can_shift, shift_cost, shift_die).
        """
        return False, 0, 0

    def parry_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Decide void to spend on parry (default 0)."""
        return 0

    def post_parry_roll_bonus(self, parry_total: int, parry_tn: int) -> tuple[int, str]:
        """Post-roll bonus to parry total.

        Returns:
            Tuple of (bonus_amount, description_note).
        """
        return 0, ""

    def on_parry_attempt(
        self, parry_succeeded: bool, margin: int,
        attacker_name: str = "", phase: int = 0,
    ) -> None:
        """Called after every parry attempt (default: no-op)."""

    def post_parry_effect_description(
        self,
        temp_void_delta: int,
        actions_changed: bool,
        bonus_stored: int | None,
    ) -> str:
        """Description of post-parry side effects (default: empty)."""
        return ""

    # -- Post-attack hooks (Wave Man abilities) -------------------------

    def post_attack_miss_bonus(self, attack_total: int, tn: int) -> tuple[int, bool, str]:
        """Bonus after attack misses. Returns (bonus, parry_auto_succeeds, note)."""
        return 0, False, ""

    def attacker_parry_tn_bonus(self) -> int:
        """Flat bonus to parry TN applied by ATTACKER."""
        return 0

    def weapon_rolled_boost(self, weapon_rolled: int, weapon_kept: int) -> int:
        """Boosted weapon rolled dice count. Returns new rolled value."""
        return weapon_rolled

    def damage_rounding(self, damage_total: int) -> tuple[int, str]:
        """Post-damage rounding. Returns (new_total, note)."""
        return damage_total, ""

    def crippled_reroll(
        self, all_dice: list[int], kept_count: int,
    ) -> tuple[list[int], list[int], int, str]:
        """Free crippled reroll. Returns (all_dice, kept_dice, total, note)."""
        kept_dice = sorted(all_dice, reverse=True)[:kept_count]
        return all_dice, kept_dice, sum(kept_dice), ""

    def damage_reduction(self, damage_total: int, had_extra_dice: bool) -> tuple[int, str]:
        """Reduce incoming damage (called on DEFENDER). Returns (new_total, note)."""
        return damage_total, ""

    def failed_parry_dice_recovery(self, all_extra_dice: int, parry_reduction: int) -> int:
        """Extra dice recovered after opponent's failed parry (called on ATTACKER)."""
        return 0

    def wound_check_tn_bonus(self) -> int:
        """Flat bonus to wound check TN (called on ATTACKER)."""
        return 0

    # -- Damage hooks ---------------------------------------------------

    def lunge_extra_rolled(self) -> int:
        """Extra rolled dice on lunge attacks (default 0)."""
        return 0

    def lunge_damage_survives_parry(self) -> bool:
        """Whether lunge bonus die is immune to parry reduction (default False)."""
        return False

    def damage_parry_reduction(self, defender_parry_rank: int) -> int:
        """How much of defender's parry rank reduces extra dice (default: full)."""
        return defender_parry_rank

    def on_near_miss_da(self) -> bool:
        """Whether a near-miss DA still hits (default False)."""
        return False

    def should_trade_damage_for_wound(
        self, damage_rolled: int, *, is_double_attack: bool = False,
    ) -> tuple[bool, int, str]:
        """Whether to trade damage dice for an automatic serious wound.

        Args:
            damage_rolled: Total rolled damage dice count.
            is_double_attack: True if this is a double attack (which
                already inflicts an automatic serious wound).

        Returns:
            Tuple of (should_trade, dice_to_remove, description_note).
        """
        return False, 0, ""

    def post_damage_effect(self, defender_name: str) -> str:
        """Effect applied after dealing damage (default: no-op).

        Returns description note.
        """
        return ""

    def resolve_post_attack_interrupt(
        self, attacker_name: str, phase: int,
    ) -> None:
        """Reactive action after being attacked (default: no-op)."""

    # -- Counterattack hooks -------------------------------------------

    def resolve_pre_attack_counterattack(
        self, attacker_name: str, phase: int,
    ) -> tuple[int, int] | None:
        """Pre-attack counterattack (resolves before opponent's attack roll).

        Returns:
            Tuple of (margin, sa_penalty) if counterattack fires, else None.
        """
        return None

    def resolve_post_damage_counterattack(
        self, attacker_name: str, phase: int, damage_total: int,
    ) -> int:
        """Post-damage counterattack (5th Dan: after seeing damage).

        Returns:
            Counterattack margin if fired, else 0.
        """
        return 0

    def should_replace_wound_check(
        self, light_wounds: int,
    ) -> tuple[bool, int, str]:
        """Whether to replace wound check with automatic serious wounds.

        Returns:
            Tuple of (should_replace, auto_sw_count, description_note).
        """
        return False, 0, ""

    # -- Wound check hooks (as defender) --------------------------------

    def wound_check_extra_rolled(self) -> int:
        """Extra rolled dice on wound check (default 0)."""
        return 0

    def wound_check_extra_kept(self) -> int:
        """Extra kept dice on wound check (default 0)."""
        return 0

    def min_interrupt_dice(self) -> int:
        """Minimum dice needed for interrupt parry (default 2)."""
        return 2

    def consume_interrupt_parry_dice(self) -> tuple[list[int], int]:
        """Consume dice for interrupt parry. Returns (consumed, parry_die_value).

        Default: consume 2 highest dice, parry_die_value=0.
        """
        remaining = sorted(self.actions_remaining, reverse=True)
        consumed = remaining[:2]
        for die in consumed:
            self.actions_remaining.remove(die)
        return consumed, 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """Flat bonus added to wound check total (default 0).

        Returns:
            Tuple of (bonus_amount, description_note).
        """
        return 0, ""

    def wound_check_void_strategy(self, water_ring: int, light_wounds: int) -> int:
        """Decide void to spend on wound check (default: use standard heuristic)."""
        return -1  # -1 signals "use default logic"

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """Post-wound-check processing (apply stored bonuses, etc.).

        Returns:
            Tuple of (new_passed, new_wc_total, description_note).
        """
        return passed, wc_total, ""

    def wc_bonus_pool_total(self) -> int:
        """Total wound-check bonus pool available (default: 0)."""
        return 0

    def on_wound_check_failed(self, attacker_name: str) -> tuple[int, str]:
        """Light wound reset value on failed wound check (default 0).

        Returns:
            Tuple of (reset_value, description_note).
        """
        return 0, ""

    def on_void_spent(self, amount: int, context: str) -> str:
        """Called whenever void is spent. Returns description note."""
        return ""

    def set_pending_die(self, value: int) -> None:
        """Set a pending die value for the next consume_attack_die call (no-op by default)."""

    # -- Special phase hooks --------------------------------------------

    def has_phase0_action(self) -> bool:
        """Whether this fighter has a phase 0 special action (default False)."""
        return False

    def resolve_phase0(self, defender_name: str) -> None:
        """Execute phase 0 action (default: no-op)."""

    def has_phase10_action(self) -> bool:
        """Whether this fighter has a phase 10+ special action (default False)."""
        return False

    def resolve_phase10(self, defender_name: str) -> None:
        """Execute phase 10 action (default: no-op)."""
