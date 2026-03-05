"""ShinjoFighter: Shinjo Bushi school-specific overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import estimate_roll


def _shinjo_attack_choice(
    double_attack_rank: int,
    fire_ring: int,
    defender_parry: int,
    void_available: int,
    max_void_spend: int,
    dan: int,
    is_crippled: bool,
    sa_bonus: int = 0,
    da_threshold: float = 0.85,
) -> tuple[str, int]:
    """Decide whether Shinjo uses Double Attack or Lunge at phase 10.

    Returns:
        Tuple of ("double_attack" | "lunge", void_to_spend).
    """
    if is_crippled or double_attack_rank <= 0:
        return "lunge", 0

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    first_dan_bonus = 1 if dan >= 1 else 0

    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = estimate_roll(da_rolled, da_kept) + sa_bonus

    usable = (
        min(void_available - 1, max_void_spend)
        if void_available > 1 else 0
    )

    if da_expected >= da_tn:
        return "double_attack", 0

    if da_expected + usable * 5.5 >= da_tn * da_threshold:
        deficit = da_tn * da_threshold - da_expected
        void_spend = min(usable, max(1, int(deficit / 5.5 + 0.5)))
        return "double_attack", void_spend

    return "lunge", 0


def _resolve_shinjo_phase10_attack(
    state: CombatState,
    attacker_name: str,
    defender_name: str,
) -> None:
    """Execute a Shinjo phase 10 attack using held dice.

    Picks the LOWEST die from actions_remaining (biggest SA bonus)
    and resolves an attack at phase 10 via _resolve_attack.
    """
    from src.engine.fighters import create_fighter
    from src.engine.simulation import _resolve_attack

    atk_ctx = state.fighters[attacker_name]
    dice = atk_ctx.actions_remaining
    if not dice:
        return

    # Pick lowest die for maximum SA bonus
    die_value = min(dice)

    atk_fighter = create_fighter(attacker_name, state)
    def_fighter = create_fighter(defender_name, state)
    atk_fighter.set_pending_die(die_value)

    _resolve_attack(state, atk_fighter, def_fighter, 10)


class ShinjoFighter(Fighter):
    """Shinjo Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 unkept die on initiative; +1 rolled die on attack and parry.
      2nd Dan: +5 free-raise bonus on parry.
      3rd Dan: After each parry, remaining dice decrease by Attack rank;
               phase-shift-like held dice mechanics.
      4th Dan: Highest initiative die set to 1 (more held phases).
      5th Dan: Successful parry margin stored as wound-check bonus pool.

    School Ability (SA): Hold action dice until phase 10.  Each held phase
    grants +2 to the attack/parry roll per phase held.  Phase 10 attacks
    use one DA per remaining die.

    Shinjo CANNOT interrupt-parry.
    """

    # -- Initiative hooks ---------------------------------------------------

    def initiative_extra_unkept(self) -> int:
        """1st Dan: +1 unkept die on initiative."""
        return 1 if self.dan >= 1 else 0

    def post_initiative_description(
        self, old_actions: list[int], new_actions: list[int],
    ) -> str:
        """4th Dan: describe initiative die change."""
        if self.dan >= 4 and old_actions:
            max_die = max(old_actions)
            return (
                f" (4th Dan: highest action die"
                f" {max_die} -> 1)"
            )
        return ""

    def post_initiative(
        self, rolled_dice: list[int], kept_dice: list[int],
    ) -> list[int]:
        """4th Dan: set highest die to 1 (maximize held-phase bonus)."""
        if self.dan >= 4 and kept_dice:
            result = list(kept_dice)
            max_die = max(result)
            result.remove(max_die)
            result.append(1)
            result.sort()
            return result
        return kept_dice

    # -- Attack hooks -------------------------------------------------------

    _pending_die: int | None = None

    def set_pending_die(self, value: int) -> None:
        """Store a pending die value for the next consume_attack_die call."""
        self._pending_die = value

    def should_consume_phase_die(self, phase: int) -> bool:
        """SA: Hold dice until phase 10 -- do not consume at phases < 10."""
        return phase >= 10

    def consume_attack_die(
        self, phase: int, die_value: int | None = None,
    ) -> int | None:
        """Consume a die for attacking. Phase 10: consume specified or pending die."""
        # Check pending die from set_pending_die
        if die_value is None and self._pending_die is not None:
            die_value = self._pending_die
            self._pending_die = None
        if die_value is not None:
            if die_value in self.actions_remaining:
                self.actions_remaining.remove(die_value)
                self._last_consumed_die = die_value
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
        """Phase 10 DA (or lunge if crippled / no DA rank)."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0

        # SA bonus from consumed die (stored by consume_attack_die)
        consumed_die = getattr(self, '_last_consumed_die', None)
        die_value = consumed_die if consumed_die is not None else (
            min(self.actions_remaining)
            if self.actions_remaining else phase
        )
        sa_bonus = 2 * (10 - die_value)

        def_ctx = self.state.fighters[defender_name]
        def_parry_skill = def_ctx.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

        choice, void_spend = _shinjo_attack_choice(
            da_rank,
            self.char.rings.fire.value,
            def_parry_rank,
            self.total_void,
            self.char.rings.lowest(),
            self.dan,
            is_crippled,
            sa_bonus=sa_bonus,
            da_threshold=self.strategy.da_threshold,
        )
        return choice, void_spend

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """SA bonus from held phases on attack."""
        effective_die = die_value if die_value is not None else phase
        bonus = 2 * (10 - effective_die)
        if bonus > 0:
            held_phases = 10 - effective_die
            note = f" (shinjo SA: +{bonus} held {held_phases} phases)"
            return bonus, note
        return 0, ""

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    # -- Parry hooks (as defender) ------------------------------------------

    def has_action_in_phase(self, phase: int) -> bool:
        """Shinjo: any held die with value <= phase counts."""
        return any(d <= phase for d in self.actions_remaining)

    def select_parry_die(self, phase: int) -> int | None:
        """Shinjo: spend highest eligible die <= phase (smallest SA bonus)."""
        eligible = [
            d for d in self.actions_remaining if d <= phase
        ]
        return max(eligible) if eligible else None

    def should_predeclare_parry(
        self, attack_tn: int, phase: int
    ) -> bool:
        """Skip predeclare with <=2 dice (save for phase 10 attack).

        With 3+ dice: use generic heuristic.
        """
        from src.engine.simulation_utils import should_predeclare_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        if def_parry_rank <= 0:
            return False

        dice_count = len(self.actions_remaining)
        if dice_count <= 2:
            # Don't predeclare with 2 dice unless near mortal
            wound_info = self.state.log.wounds[self.name]
            near_mortal = (
                wound_info.serious_wounds
                >= wound_info.mortal_wound_threshold - 1
            )
            if not near_mortal:
                return False

        is_crippled = self.state.log.wounds[self.name].is_crippled
        known_bonus = 5 if self.dan >= 2 else 0
        return should_predeclare_parry(
            def_parry_rank,
            self.char.rings.air.value,
            attack_tn,
            is_crippled,
            is_shinjo=True,
            shinjo_dan=self.dan,
            known_bonus=known_bonus,
        )

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Shinjo parry depends on remaining dice count.

        3+ dice: always parry.
        2 dice: smart parry (only if damage is dangerous enough).
        1 die: only parry if near mortal wound.
        """
        from src.engine.simulation_utils import (
            shinjo_should_parry_with_two_dice,
        )

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        if def_parry_rank <= 0:
            return False

        wound_info = self.state.log.wounds[self.name]
        near_mortal = (
            wound_info.serious_wounds
            >= wound_info.mortal_wound_threshold - 1
        )
        dice_count = len(self.actions_remaining)

        if dice_count > 2:
            return True
        if dice_count == 2:
            return shinjo_should_parry_with_two_dice(
                attack_total=attack_total,
                attack_tn=attack_tn,
                weapon_rolled=weapon_rolled,
                weapon_kept=self.state.fighters[
                    self.state.get_opponent(self.name)
                ].weapon.kept,
                attacker_fire=attacker_fire,
                defender_serious_wounds=wound_info.serious_wounds,
                defender_earth_ring=wound_info.earth_ring,
                defender_light_wounds=wound_info.light_wounds,
                mortal_wound_threshold=wound_info.mortal_wound_threshold,
            )
        # 1 die: only if near mortal
        return near_mortal

    def can_interrupt(self) -> bool:
        """Shinjo cannot interrupt-parry."""
        return False

    def parry_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on parry."""
        return 1 if self.dan >= 1 else 0

    def parry_bonus(self) -> int:
        """2nd Dan: +5 free-raise bonus on parry."""
        return 5 if self.dan >= 2 else 0

    def parry_bonus_description(self, bonus: int) -> str:
        """2nd Dan: shinjo-specific parry bonus description."""
        return f" (shinjo 2nd Dan: free raise +{bonus})"

    def sa_parry_bonus(
        self, phase: int, parry_die_value: int,
    ) -> tuple[int, str]:
        """SA bonus from held die on parry."""
        if parry_die_value > 0:
            bonus = 2 * (phase - parry_die_value)
            if bonus > 0:
                held = phase - parry_die_value
                note = (
                    f" (shinjo SA: +{bonus},"
                    f" held {held} phases)"
                )
                return bonus, note
        return 0, ""

    def post_parry_effect_description(
        self,
        temp_void_delta: int,
        actions_changed: bool,
        bonus_stored: int | None,
    ) -> str:
        """3rd/5th Dan: describe dice decrease and bonus storage."""
        note = ""
        if actions_changed:
            atk_skill = self.char.get_skill("Attack")
            decrease = atk_skill.rank if atk_skill else 0
            note += f" (shinjo 3rd Dan: dice decreased by {decrease})"
        if bonus_stored is not None:
            note += (
                f" (shinjo 5th Dan: +{bonus_stored}"
                f" wound check bonus stored)"
            )
        return note

    def on_parry_attempt(
        self, parry_succeeded: bool, margin: int,
        attacker_name: str = "", phase: int = 0,
    ) -> None:
        """3rd Dan: decrease remaining dice by Attack rank.

        5th Dan: store parry margin as wound-check bonus.
        """
        # 3rd Dan: decrease dice
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            decrease = atk_skill.rank if atk_skill else 0
            if decrease > 0 and self.actions_remaining:
                self.actions_remaining[:] = sorted(
                    d - decrease
                    for d in self.actions_remaining
                )

        # 5th Dan: store parry margin as wound-check bonus
        if self.dan >= 5 and parry_succeeded and margin > 0:
            self.shinjo_bonuses.append(margin)

    # -- Wound check hooks (as defender) ------------------------------------

    def wound_check_void_strategy(
        self, water_ring: int, light_wounds: int
    ) -> int:
        """5th Dan: skip void when bonus pool covers the wound check."""
        if self.dan >= 5 and self.shinjo_bonuses:
            pool_total = sum(self.shinjo_bonuses)
            if pool_total >= light_wounds:
                return 0
        return -1  # use default logic

    def wc_bonus_pool_total(self) -> int:
        """5th Dan: total wound-check bonus pool."""
        if self.dan >= 5:
            return sum(self.shinjo_bonuses)
        return 0

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """5th Dan: apply stored parry margin bonuses to wound check."""
        from src.engine.simulation_utils import select_shinjo_wc_bonuses

        if (
            self.dan >= 5
            and not passed
            and self.shinjo_bonuses
        ):
            wound_tracker = self.state.log.wounds[self.name]
            base_tn = wound_tracker.light_wounds
            raw_deficit = base_tn - wc_total
            used = select_shinjo_wc_bonuses(
                raw_deficit, self.shinjo_bonuses,
            )
            if used:
                bonus_applied = sum(used)
                new_total = wc_total + bonus_applied
                # Remove spent bonuses
                remaining = list(self.shinjo_bonuses)
                for b in used:
                    remaining.remove(b)
                self.shinjo_bonuses[:] = remaining

                # Recalculate serious wounds
                sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
                new_deficit = base_tn - new_total
                if new_deficit <= 0:
                    new_sw = 0
                    new_passed = True
                else:
                    new_sw = 1 + (new_deficit // 10)
                    new_passed = False
                wound_tracker.serious_wounds += (new_sw - sw_added_by_wc)

                bonus_str = ", ".join(f"+{b}" for b in used)
                total_str = (
                    f" = +{bonus_applied}"
                    if len(used) > 1 else ""
                )
                if new_passed:
                    note = (
                        f" (shinjo 5th Dan: applied"
                        f" {bonus_str}{total_str},"
                        f" wound check passes)"
                    )
                else:
                    note = (
                        f" (shinjo 5th Dan: applied"
                        f" {bonus_str}{total_str})"
                    )
                return new_passed, new_total, note
        return passed, wc_total, ""

    # -- Special phase hooks ------------------------------------------------

    def has_phase10_action(self) -> bool:
        """SA: Shinjo attacks at phase 10 with held dice."""
        return True

    def resolve_phase10(self, defender_name: str) -> None:
        """Execute phase 10 multi-DA loop."""
        log = self.state.log
        name = self.name
        my_actions = self.actions_remaining

        while my_actions:
            if log.wounds[name].is_mortally_wounded:
                break
            if log.wounds[defender_name].is_mortally_wounded:
                break
            dice_before = len(my_actions)
            _resolve_shinjo_phase10_attack(
                self.state, name, defender_name,
            )
            if len(my_actions) >= dice_before:
                break  # safety: no die consumed
