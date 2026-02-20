"""Combat simulation orchestrator.

Runs a full combat between two characters using the core engine primitives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.fighters.base import Fighter

from src.engine.combat import (
    calculate_attack_tn,
    create_combat_log,
    make_wound_check,
    roll_attack,
    roll_damage,
    roll_initiative,
)
from src.engine.combat_state import CombatState
from src.engine.dice import reroll_tens, roll_and_keep
from src.engine.fighters import create_fighter
from src.engine.simulation_utils import (
    damage_pool_str as _damage_pool_str,
)
from src.engine.simulation_utils import (
    format_pool_with_overflow as _format_pool_with_overflow,
)
from src.engine.simulation_utils import (
    should_convert_light_to_serious as _should_convert_light_to_serious,
)
from src.engine.simulation_utils import (
    should_spend_void_on_wound_check as _should_spend_void_on_wound_check,
)
from src.engine.simulation_utils import (
    spend_void as _spend_void,
)
from src.engine.simulation_utils import (
    tiebreak_key as _tiebreak_key,
)
from src.engine.simulation_utils import (
    total_void as _total_void,
)
from src.engine.simulation_utils import (
    void_spent_label as _void_spent_label,
)
from src.models.character import Character, RingName
from src.models.combat import ActionType, CombatAction, CombatLog
from src.models.weapon import Weapon

__all__ = [
    "_damage_pool_str", "_resolve_attack",
    "_spend_void", "_total_void", "simulate_combat",
]






def simulate_combat(
    char_a: Character,
    char_b: Character,
    weapon_a: Weapon,
    weapon_b: Weapon,
    max_rounds: int = 20,
) -> CombatLog:
    """Run a full combat between two characters.

    Args:
        char_a: First combatant.
        char_b: Second combatant.
        weapon_a: First combatant's weapon.
        weapon_b: Second combatant's weapon.
        max_rounds: Maximum number of rounds before declaring a draw.

    Returns:
        A CombatLog with all actions, wounds, and winner (or None for draw).
    """
    log = create_combat_log(
        [char_a.name, char_b.name],
        [char_a.rings.earth.value, char_b.rings.earth.value],
    )

    # Build CombatState and create Fighter instances directly
    state = CombatState(log=log)
    fighter_map = {
        char_a.name: create_fighter(
            char_a.name, state,
            char=char_a, weapon=weapon_a,
            void_points=char_a.void_points_max,
        ),
        char_b.name: create_fighter(
            char_b.name, state,
            char=char_b, weapon=weapon_b,
            void_points=char_b.void_points_max,
        ),
    }

    # Thin dict view for _tiebreak_key only
    fighters = {
        n: {"char": f.char, "weapon": f.weapon}
        for n, f in fighter_map.items()
    }

    for round_num in range(1, max_rounds + 1):
        log.round_number = round_num

        # --- Round Start Hooks ---
        for name in [char_a.name, char_b.name]:
            fighter_map[name].on_round_start()

        # --- Lunge target bonus resets each round ---
        for ctx in state.fighters.values():
            ctx.lunge_target_bonus = 0

        # --- Initiative Phase ---
        extra_a = fighter_map[char_a.name].initiative_extra_unkept()
        init_a = roll_initiative(char_a, extra_unkept=extra_a)
        extra_b = fighter_map[char_b.name].initiative_extra_unkept()
        init_b = roll_initiative(char_b, extra_unkept=extra_b)

        state.fighters[char_a.name].actions_remaining = sorted(init_a.dice_kept)
        state.fighters[char_b.name].actions_remaining = sorted(init_b.dice_kept)

        # Post-initiative hooks
        for char, init_result in [(char_a, init_a), (char_b, init_b)]:
            ctx = state.fighters[char.name]
            old_actions = list(ctx.actions_remaining)
            new_actions = fighter_map[char.name].post_initiative(
                list(init_result.dice_rolled), list(ctx.actions_remaining),
            )
            if new_actions != old_actions:
                init_result.dice_kept = new_actions
                ctx.actions_remaining = sorted(new_actions)
                post_init_note = fighter_map[char.name].post_initiative_description(
                    old_actions, new_actions,
                )
                if post_init_note:
                    init_result.description += post_init_note

        init_a.status_after = state.snapshot_status()
        log.add_action(init_a)
        init_b.status_after = state.snapshot_status()
        log.add_action(init_b)

        # --- Phase 0 processing ---
        for name in [char_a.name, char_b.name]:
            fighter = fighter_map[name]
            if not fighter.has_phase0_action():
                continue
            if state.is_mortally_wounded(name):
                continue
            opp_name = char_b.name if name == char_a.name else char_a.name
            if state.is_mortally_wounded(opp_name):
                continue

            fighter.resolve_phase0(opp_name)

            if state.is_mortally_wounded(name) or state.is_mortally_wounded(opp_name):
                break

            # Convert remaining phase 0 dice to phase 1 (held actions)
            ar = state.fighters[name].actions_remaining
            while 0 in ar:
                ar.remove(0)
                ar.append(1)
            ar.sort()

        # Build action schedule
        schedule: list[tuple[int, int, str]] = []
        for name in [char_a.name, char_b.name]:
            for die_val in state.fighters[name].actions_remaining:
                schedule.append((die_val, die_val, name))

        # Tiebreak needs dict views of actions_remaining
        actions_remaining = {
            n: ctx.actions_remaining
            for n, ctx in state.fighters.items()
        }
        schedule.sort(
            key=lambda x: _tiebreak_key(x[2], actions_remaining, fighters, x[0])
        )

        # --- Action Phases ---
        for phase, _die_val, attacker_name in schedule:
            if state.is_mortally_wounded(char_a.name) or state.is_mortally_wounded(char_b.name):
                break

            defender_name = char_b.name if attacker_name == char_a.name else char_a.name
            _resolve_attack(
                state, fighter_map[attacker_name], fighter_map[defender_name], phase,
            )

        # --- Phase 10+ Attack ---
        for name in [char_a.name, char_b.name]:
            fighter = fighter_map[name]
            if not fighter.has_phase10_action():
                continue
            if not state.fighters[name].actions_remaining:
                continue
            opp_name = char_b.name if name == char_a.name else char_a.name
            fighter.resolve_phase10(opp_name)

        # Check for combat end
        if state.is_mortally_wounded(char_a.name):
            log.winner = char_b.name
            break
        if state.is_mortally_wounded(char_b.name):
            log.winner = char_a.name
            break

    return log









def _resolve_attack(
    state: CombatState,
    attacker_fighter: Fighter,
    defender_fighter: Fighter,
    phase: int,
) -> None:
    """Resolve a single attack action in a phase.

    All state flows through CombatState via Fighter instances.
    """
    log = state.log
    attacker_name = attacker_fighter.name
    defender_name = defender_fighter.name
    attacker: Character = attacker_fighter.char
    defender: Character = defender_fighter.char
    weapon: Weapon = attacker_fighter.weapon

    # Consume the phase die via Fighter hook
    consumed_die = attacker_fighter.consume_attack_die(phase)
    if consumed_die is None:
        return

    # --- Pre-attack counterattack (e.g. Hida SA) ---
    ca_margin = 0
    ca_sa_penalty = 0
    log_len_before_ca = len(log.actions)
    ca_result = defender_fighter.resolve_pre_attack_counterattack(
        attacker_name, phase,
    )
    if ca_result is not None:
        ca_margin, ca_sa_penalty = ca_result

        # Insert a declaration action *before* the counterattack actions
        # so the output reads: "X attacks — Y counterattacks first"
        decl_action = CombatAction(
            phase=phase,
            actor=attacker_name,
            action_type=ActionType.ATTACK,
            success=None,
            description=(
                f"{attacker_name} attacks"
                f" — {defender_name} counterattacks first"
            ),
            label=f"attacks — {defender_name} counterattacks first",
        )
        log.actions.insert(log_len_before_ca, decl_action)

        if log.wounds[attacker_name].is_mortally_wounded:
            return  # Pre-attack kill stops the attack

    # Get skill ranks
    atk_skill = attacker.get_skill("Attack")
    atk_rank = atk_skill.rank if atk_skill else 0

    def_parry_skill = defender.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # Feature 1: Crippled disables exploding 10s on attack rolls
    attacker_crippled = log.wounds[attacker_name].is_crippled
    attack_explode = not attacker_crippled

    # Calculate TN and roll attack
    tn = calculate_attack_tn(def_parry_rank)

    # Lunge target bonus: opponent's attack gets easier TN
    lunge_tn_reduction = attacker_fighter.lunge_target_bonus
    if lunge_tn_reduction > 0:
        tn = max(5, tn - lunge_tn_reduction)
        attacker_fighter.lunge_target_bonus = 0

    # Parry TN reduction (e.g. Shiba 5th Dan accumulated from parries)
    parry_tn_red = attacker_fighter.parry_tn_reduction
    if parry_tn_red > 0:
        tn -= parry_tn_red
        attacker_fighter.parry_tn_reduction = 0

    # Save TN after all reductions but before DA +20 for extra dice calc
    base_tn = tn

    # --- Double Attack / Lunge decision via Fighter hook ---
    is_double_attack = False
    is_lunge = False
    is_near_miss_da = False
    da_void_spend = 0
    lunge_void_spend = 0
    da_skill = attacker.get_skill("Double Attack")
    da_rank = da_skill.rank if da_skill else 0
    lunge_skill = attacker.get_skill("Lunge")
    lunge_rank = lunge_skill.rank if lunge_skill else 0

    # Check for forced lunge (e.g. Otaku counter-lunge) before choose_attack
    counter_lunge_label = ""
    if getattr(attacker_fighter, '_force_lunge', False):
        is_lunge = True
        cl_die = getattr(attacker_fighter, '_counter_lunge_die', None)
        die_note = f" (consuming phase {cl_die} die)" if cl_die else ""
        counter_lunge_label = f"SA counter-lunge{die_note}"
    else:
        attack_choice, choice_void = attacker_fighter.choose_attack(
            defender_name, phase,
        )
        if attack_choice == "double_attack":
            is_double_attack = True
            da_void_spend = choice_void
        elif attack_choice == "lunge":
            is_lunge = True
            lunge_void_spend = choice_void

    if is_double_attack:
        tn += 20

    # --- Parry pre-declaration (feature 4) ---
    has_action_in_phase = defender_fighter.has_action_in_phase(phase)

    predeclared = False
    if has_action_in_phase and def_parry_rank > 0:
        predeclared = defender_fighter.should_predeclare_parry(tn, phase)

    # If pre-declared, consume the parry die now (before attack roll)
    predeclare_parry_die = 0
    if predeclared:
        die = defender_fighter.select_parry_die(phase)
        if die is not None:
            defender_fighter.actions_remaining.remove(die)
            predeclare_parry_die = die

    # --- Roll attack ---
    # School-specific extra rolled die on attack
    atk_extra_rolled = attacker_fighter.attack_extra_rolled()
    effective_atk_rank = atk_rank + atk_extra_rolled

    if is_lunge:
        # Lunge attack: uses Lunge knack + Fire
        lunge_extra = attacker_fighter.lunge_extra_rolled()
        lng_rolled = lunge_rank + attacker.rings.fire.value + lunge_extra
        lng_kept = attacker.rings.fire.value

        # Void spending on lunge
        lng_void_label = ""
        actual_lunge_void = 0
        avail_void = attacker_fighter.total_void
        if lunge_void_spend > 0 and avail_void >= lunge_void_spend:
            lng_from_temp, lng_from_reg = attacker_fighter.spend_void(lunge_void_spend)
            lng_void_label = _void_spent_label(lng_from_temp, lng_from_reg)
            lng_rolled += lunge_void_spend
            lng_kept += lunge_void_spend
            actual_lunge_void = lunge_void_spend
            # Fighter hook: void spending side-effects (e.g. Matsu bonus)
            attacker_fighter.on_void_spent(actual_lunge_void, "lunge")

        all_dice, kept_dice, total = roll_and_keep(lng_rolled, lng_kept, explode=attack_explode)

        # SA bonus on lunge (e.g. Shinjo held-die bonus)
        sa_bonus, sa_note = attacker_fighter.sa_attack_bonus(phase, consumed_die)
        if sa_bonus > 0:
            total += sa_bonus

        success = total >= tn
        void_note = f" ({lng_void_label})" if lng_void_label else ""
        attack_action = CombatAction(
            phase=phase,
            actor=attacker_name,
            action_type=ActionType.LUNGE,
            target=defender_name,
            dice_rolled=all_dice,
            dice_kept=kept_dice,
            total=total,
            tn=tn,
            success=success,
            description=(
                f"{attacker_name} lunges: "
                f"{_format_pool_with_overflow(lng_rolled, lng_kept)}"
                f" vs TN {tn}{void_note}{sa_note}"
            ),
            dice_pool=_format_pool_with_overflow(lng_rolled, lng_kept),
            label=counter_lunge_label,
        )
        # Lunge: opponent's next attack gets -5 TN
        defender_fighter.lunge_target_bonus = 5

    elif is_double_attack:
        # Double attack uses Double Attack skill + Fire (not Attack skill)
        da_rolled = da_rank + attacker.rings.fire.value
        da_rolled += atk_extra_rolled
        da_kept = attacker.rings.fire.value

        # Apply void spending on double attack
        da_void_label = ""
        actual_da_void = 0
        da_avail = attacker_fighter.total_void
        if da_void_spend > 0 and da_avail >= da_void_spend:
            da_from_temp, da_from_reg = attacker_fighter.spend_void(da_void_spend)
            da_void_label = _void_spent_label(da_from_temp, da_from_reg)
            da_rolled += da_void_spend
            da_kept += da_void_spend
            actual_da_void = da_void_spend
            attacker_fighter.on_void_spent(actual_da_void, "double_attack")

        all_dice, kept_dice, total = roll_and_keep(da_rolled, da_kept, explode=attack_explode)
        fifth_dan_combat_bonus = attacker_fighter.fifth_dan_void_bonus(da_void_spend)
        total += fifth_dan_combat_bonus

        # SA bonus on double attack (e.g. Shinjo held-die bonus)
        sa_bonus, sa_note = attacker_fighter.sa_attack_bonus(phase, consumed_die)
        if sa_bonus > 0:
            total += sa_bonus

        success = total >= tn

        # Near-miss DA: school technique may still hit
        if not success and attacker_fighter.on_near_miss_da() and total >= tn - 20:
            success = True
            is_near_miss_da = True

        void_note = f" ({da_void_label})" if da_void_label else ""
        fifth_note = attacker_fighter.fifth_dan_void_description(fifth_dan_combat_bonus)
        near_miss_note = (
            attacker_fighter.near_miss_da_description()
            if is_near_miss_da else ""
        )
        attack_action = CombatAction(
            phase=phase,
            actor=attacker_name,
            action_type=ActionType.DOUBLE_ATTACK,
            target=defender_name,
            dice_rolled=all_dice,
            dice_kept=kept_dice,
            total=total,
            tn=tn,
            success=success,
            description=(
                f"{attacker_name} double attacks: "
                f"{_format_pool_with_overflow(da_rolled, da_kept)}"
                f" vs TN {tn}{void_note}{fifth_note}"
                f"{near_miss_note}{sa_note}"
            ),
            dice_pool=_format_pool_with_overflow(da_rolled, da_kept),
        )
    else:
        # Normal attack: void spending via Fighter hook
        atk_void_spend = attacker_fighter.attack_void_strategy(
            effective_atk_rank + attacker.rings.fire.value,
            attacker.rings.fire.value,
            tn,
        )
        atk_void_label = ""
        atk_avail = attacker_fighter.total_void
        if atk_void_spend > 0 and atk_avail >= atk_void_spend:
            atk_from_temp, atk_from_reg = attacker_fighter.spend_void(atk_void_spend)
            atk_void_label = _void_spent_label(atk_from_temp, atk_from_reg)
        else:
            atk_void_spend = 0

        if atk_void_spend > 0:
            # Inline roll_and_keep so void adds +1k1 (not +1k0 via roll_attack)
            atk_rolled = effective_atk_rank + attacker.rings.fire.value + atk_void_spend
            atk_kept = attacker.rings.fire.value + atk_void_spend
            all_dice, kept_dice, total = roll_and_keep(atk_rolled, atk_kept, explode=attack_explode)

            fifth_dan_combat_bonus = attacker_fighter.fifth_dan_void_bonus(atk_void_spend)
            total += fifth_dan_combat_bonus

            success = total >= tn
            void_note = f" ({atk_void_label})"
            fifth_note = attacker_fighter.fifth_dan_void_description(fifth_dan_combat_bonus)
            attack_action = CombatAction(
                phase=phase,
                actor=attacker_name,
                action_type=ActionType.ATTACK,
                target=defender_name,
                dice_rolled=all_dice,
                dice_kept=kept_dice,
                total=total,
                tn=tn,
                success=success,
                description=(
                    f"{attacker_name} attacks: "
                    f"{_format_pool_with_overflow(atk_rolled, atk_kept)}"
                    f" vs TN {tn}{void_note}{fifth_note}"
                ),
                dice_pool=_format_pool_with_overflow(atk_rolled, atk_kept),
            )
        else:
            attack_action = roll_attack(
                attacker, effective_atk_rank,
                RingName.FIRE, tn, explode=attack_explode,
            )
            attack_action.phase = phase
            attack_action.target = defender_name

    # School technique reroll on attack (e.g. Hida 3rd Dan)
    new_all, new_kept, new_total, reroll_note = attacker_fighter.post_attack_reroll(
        attack_action.dice_rolled, len(attack_action.dice_kept),
    )
    if reroll_note:
        attack_action.dice_rolled = new_all
        attack_action.dice_kept = new_kept
        attack_action.total = new_total
        attack_action.success = new_total >= tn
        attack_action.description += reroll_note

    # Ability 5: Free crippled reroll on attack (before void reroll)
    if attacker_crippled:
        new_all, new_kept, new_total, note = attacker_fighter.crippled_reroll(
            attack_action.dice_rolled, len(attack_action.dice_kept),
        )
        if note:
            attack_action.dice_rolled = new_all
            attack_action.dice_kept = new_kept
            attack_action.total = new_total
            attack_action.success = new_total >= tn
            attack_action.description += note

    # Feature 2: Crippled void reroll on attack
    if attacker_crippled and not attack_action.success:
        has_tens = any(d == 10 for d in attack_action.dice_rolled)
        max_void_spend = attacker.rings.lowest()
        atk_void_avail = attacker_fighter.total_void
        if has_tens and atk_void_avail > 0 and max_void_spend > 0:
            new_all, new_kept, new_total = reroll_tens(
                attack_action.dice_rolled, len(attack_action.dice_kept),
            )
            cr_from_temp, cr_from_reg = attacker_fighter.spend_void(1)
            cr_label = "temp void" if cr_from_temp else "void"
            attack_action.dice_rolled = new_all
            attack_action.dice_kept = new_kept
            attack_action.total = new_total
            attack_action.success = new_total >= tn
            attack_action.description += f" ({cr_label}: rerolled 10s)"
            attacker_fighter.on_void_spent(1, "crippled_reroll")

    # Ability 1: Free raise on miss — via Fighter hook
    parry_auto_succeeds = False
    if not attack_action.success:
        miss_bonus, parry_auto_succeeds, miss_note = attacker_fighter.post_attack_miss_bonus(
            attack_action.total, tn,
        )
        if miss_bonus > 0:
            attack_action.total += miss_bonus
            attack_action.success = True
            attack_action.description += miss_note

    # Post-roll attack bonus via Fighter hook
    post_atk_bonus, post_atk_note = attacker_fighter.post_attack_roll_bonus(
        attack_action.total, tn, phase, defender_name,
    )
    if post_atk_bonus > 0:
        attack_action.total += post_atk_bonus
        attack_action.success = attack_action.total >= tn
        attack_action.description += post_atk_note

    # Hida SA penalty: attacker gets +5 on their attack roll
    if ca_sa_penalty > 0:
        attack_action.total += ca_sa_penalty
        attack_action.success = attack_action.total >= tn
        attack_action.description += f" (hida SA: attacker +{ca_sa_penalty})"

    attack_action.status_after = state.snapshot_status()
    log.add_action(attack_action)

    # Attack missed — dice already consumed by pre-declaration (if any),
    # reflected in attack_action.status_after snapshot.
    if not attack_action.success:
        # SA counter-lunge fires even on a miss
        if (
            not log.wounds[attacker_name].is_mortally_wounded
            and not log.wounds[defender_name].is_mortally_wounded
        ):
            defender_fighter.resolve_post_attack_interrupt(
                attacker_name, phase,
            )
        return

    # Annotate attack hit with expected damage pool (assuming no parry)
    # For double attack, use base_tn (before +20) for extra dice calculation
    extra_tn = base_tn if is_double_attack else tn
    no_parry_extra = max(0, (attack_action.total - extra_tn) // 5)
    # Account for ability 3 weapon boost and lunge bonus in the preview
    preview_weapon_rolled = attacker_fighter.weapon_rolled_boost(weapon.rolled, weapon.kept)
    lunge_preview_bonus = (1 + attacker_fighter.lunge_extra_rolled()) if is_lunge else 0
    raw_rolled = (
        preview_weapon_rolled + attacker.rings.fire.value
        + no_parry_extra + lunge_preview_bonus
    )
    pool_display = _format_pool_with_overflow(raw_rolled, weapon.kept)
    da_wound_note = " plus 1 automatic serious wound" if is_double_attack else ""
    # Preview 5th Dan trade (Otaku trades 10 dice for 1 auto SW)
    trade_preview = ""
    if not is_double_attack:
        preview_trade, _, _ = attacker_fighter.should_trade_damage_for_wound(
            raw_rolled,
        )
        if preview_trade:
            post_trade = _format_pool_with_overflow(
                max(0, raw_rolled - 10), weapon.kept,
            )
            trade_preview = (
                f" (5th Dan: trading 10 dice for 1 auto SW,"
                f" rolling {post_trade})"
            )
    attack_action.description += (
        f" — damage will be {pool_display}{da_wound_note}{trade_preview}"
    )

    # --- Defender attempts parry ---
    parry_attempted = False
    parry_succeeded = False

    # Ability 2: Parry TN increase — via Fighter hook
    ab2_bonus = attacker_fighter.attacker_parry_tn_bonus()

    # Determine if defender can and should parry
    can_parry = False
    is_phase_shift = False
    phase_shift_die = 0
    phase_shift_cost = 0
    is_interrupt = False
    attacker_weapon: Weapon = attacker_fighter.weapon

    if predeclared:
        # Pre-declared: die already consumed, always parry
        can_parry = True
    elif has_action_in_phase and def_parry_rank > 0:
        if parry_auto_succeeds:
            can_parry = True
        else:
            can_parry = defender_fighter.should_reactive_parry(
                attack_action.total, tn,
                attacker_weapon.rolled, attacker.rings.fire.value,
            )
    elif not has_action_in_phase and def_parry_rank > 0:
        # Phase-shift parry (e.g. Mirumoto 3rd Dan)
        can_shift, shift_cost, shift_die = defender_fighter.can_phase_shift_parry(phase)
        if can_shift:
            can_parry = True
            is_phase_shift = True
            phase_shift_die = shift_die
            phase_shift_cost = shift_cost
    interrupt_cost = defender_fighter.min_interrupt_dice()
    if not can_parry and defender_fighter.can_interrupt() and (
        not has_action_in_phase
        and len(defender_fighter.actions_remaining) >= interrupt_cost
        and def_parry_rank > 0
    ):
        if parry_auto_succeeds:
            extra_dice = max(0, (attack_action.total - (base_tn if is_double_attack else tn)) // 5)
            damage_rolled = attacker_weapon.rolled + attacker.rings.fire.value + extra_dice
            can_parry = damage_rolled > 6
            is_interrupt = can_parry
        else:
            should_interrupt = defender_fighter.should_interrupt_parry(
                attack_action.total, tn,
                attacker_weapon.rolled, attacker.rings.fire.value,
            )
            if should_interrupt:
                can_parry = True
                is_interrupt = True

    parry_die_value = 0  # Track which die was spent on parry (for SA bonus)
    if can_parry and def_parry_rank > 0:
        parry_attempted = True

        if predeclared:
            # Die already consumed above during predeclare
            parry_die_value = predeclare_parry_die
        elif is_phase_shift:
            # Phase shift: consume the shifted die and spend dan points
            defender_fighter.actions_remaining.remove(phase_shift_die)
            defender_fighter.dan_points -= phase_shift_cost
        elif is_interrupt:
            # Interrupts consume dice via fighter hook (default: 2 highest)
            consumed, parry_die_value = defender_fighter.consume_interrupt_parry_dice()
        elif has_action_in_phase:
            # Regular or Shinjo reactive parry: consume via fighter hook
            die = defender_fighter.select_parry_die(phase)
            if die is not None:
                defender_fighter.actions_remaining.remove(die)
                parry_die_value = die

        # Ability 1: parry auto-succeeds (wave man free raise) — skip the roll
        if parry_auto_succeeds:
            parry_succeeded = True
            action_type = ActionType.INTERRUPT if is_interrupt else ActionType.PARRY
            interrupt_note = " (interrupt)" if is_interrupt else ""
            parry_action = CombatAction(
                phase=phase,
                actor=defender_name,
                action_type=action_type,
                target=attacker_name,
                dice_rolled=[],
                dice_kept=[],
                total=0,
                tn=attack_action.total,
                success=True,
                description=(
                    f"{defender_name} parries: auto-success"
                    f" (wave man free raise){interrupt_note}"
                ),
                dice_pool="",
            )
            # Log parry action BEFORE on_parry_attempt so any generated
            # actions (e.g. Shiba parry damage) appear after the parry.
            log.add_action(parry_action)
            _old_temp_void = defender_fighter.temp_void
            defender_fighter.on_parry_attempt(True, 0, attacker_name, phase)
            temp_void_delta = defender_fighter.temp_void - _old_temp_void
            parry_action.description += defender_fighter.post_parry_effect_description(
                temp_void_delta, False, None,
            )
            parry_action.status_after = state.snapshot_status()
            # SA counter-lunge fires even after auto-parry
            if (
                not log.wounds[attacker_name].is_mortally_wounded
                and not log.wounds[defender_name].is_mortally_wounded
            ):
                defender_fighter.resolve_post_attack_interrupt(
                    attacker_name, phase,
                )
            return

        air_value = defender.rings.air.value
        parry_rolled = def_parry_rank + air_value + defender_fighter.parry_extra_rolled()
        parry_kept = air_value

        # Feature 1: Crippled disables exploding 10s on parry rolls
        defender_crippled = log.wounds[defender_name].is_crippled
        parry_explode = not defender_crippled

        # Feature 4: Pre-declared parry gets +5 bonus (added to total)
        # Interrupts are reactive and never get the pre-declare bonus
        parry_tn = attack_action.total + ab2_bonus
        parry_bonus = 5 if (predeclared and not is_interrupt) else 0
        parry_bonus_note = " (pre-declared, +5 bonus)" if (predeclared and not is_interrupt) else ""

        # School technique parry bonus (e.g. 2nd Dan free raise)
        school_parry_bonus = defender_fighter.parry_bonus()
        if school_parry_bonus > 0:
            parry_bonus += school_parry_bonus
            parry_bonus_note += defender_fighter.parry_bonus_description(school_parry_bonus)

        # Void spending on parry via Fighter hook
        def_parry_void_spend = defender_fighter.parry_void_strategy(
            parry_rolled, parry_kept, parry_tn - parry_bonus,
        )
        def_parry_void_label = ""
        def_void_avail = defender_fighter.total_void
        if def_parry_void_spend > 0 and def_void_avail >= def_parry_void_spend:
            pv_from_temp, pv_from_reg = defender_fighter.spend_void(def_parry_void_spend)
            def_parry_void_label = _void_spent_label(pv_from_temp, pv_from_reg)
            parry_rolled += def_parry_void_spend
            parry_kept += def_parry_void_spend
        else:
            def_parry_void_spend = 0

        all_dice, kept_dice, parry_total = roll_and_keep(
            parry_rolled, parry_kept, explode=parry_explode,
        )

        fifth_dan_parry_bonus = defender_fighter.fifth_dan_void_bonus(def_parry_void_spend)
        if fifth_dan_parry_bonus > 0:
            parry_total += fifth_dan_parry_bonus
            parry_bonus_note += defender_fighter.fifth_dan_void_description(fifth_dan_parry_bonus)
        elif def_parry_void_label:
            parry_bonus_note += f" ({def_parry_void_label})"

        # Ability 5: Free crippled reroll on parry
        if defender_crippled:
            all_dice, kept_dice, parry_total, ab5_note = defender_fighter.crippled_reroll(
                all_dice, parry_kept,
            )
            parry_bonus_note += ab5_note

        # Feature 2: Crippled void reroll on parry
        if defender_crippled and (parry_total + parry_bonus) < parry_tn:
            has_tens = any(d == 10 for d in all_dice)
            max_void_spend = defender.rings.lowest()
            def_crip_void = defender_fighter.total_void
            if has_tens and def_crip_void > 0 and max_void_spend > 0:
                all_dice, kept_dice, parry_total = reroll_tens(
                    all_dice, parry_kept,
                )
                pcr_from_temp, pcr_from_reg = defender_fighter.spend_void(1)
                pcr_label = "temp void" if pcr_from_temp else "void"
                parry_bonus_note += f" ({pcr_label}: rerolled 10s)"
                defender_fighter.on_void_spent(1, "crippled_parry_reroll")

        effective_parry_total = parry_total + parry_bonus

        # SA bonus on parry (e.g. Shinjo held-die bonus)
        sa_parry_amt, sa_parry_note = defender_fighter.sa_parry_bonus(phase, parry_die_value)
        if sa_parry_amt > 0:
            effective_parry_total += sa_parry_amt
            parry_bonus_note += sa_parry_note

        # Post-roll parry bonus via Fighter hook
        post_parry_bonus, post_parry_note = defender_fighter.post_parry_roll_bonus(
            effective_parry_total, parry_tn,
        )
        if post_parry_bonus > 0:
            effective_parry_total += post_parry_bonus
            parry_bonus_note += post_parry_note

        parry_succeeded = effective_parry_total >= parry_tn

        action_type = ActionType.INTERRUPT if is_interrupt else ActionType.PARRY
        interrupt_note = " (interrupt)" if is_interrupt else ""
        phase_shift_note = (
            f" (3rd dan: shifted from phase"
            f" {phase_shift_die}, {phase_shift_cost} pts)"
            if is_phase_shift else ""
        )
        ab2_note = f" (wave man: parry TN +{ab2_bonus})" if ab2_bonus > 0 else ""
        parry_pool = (
            f"{parry_rolled}k{parry_kept} + 5"
            if predeclared
            else f"{parry_rolled}k{parry_kept}"
        )
        parry_action = CombatAction(
            phase=phase,
            actor=defender_name,
            action_type=action_type,
            target=attacker_name,
            dice_rolled=all_dice,
            dice_kept=kept_dice,
            total=effective_parry_total,
            tn=parry_tn,
            success=parry_succeeded,
            description=(
                f"{defender_name} parries: {parry_rolled}k{parry_kept} "
                f"vs TN {parry_tn}{ab2_note}{parry_bonus_note}{phase_shift_note}{interrupt_note}"
            ),
            dice_pool=parry_pool,
        )
        # Log parry action BEFORE post-parry effects so that any actions
        # generated by on_parry_attempt (e.g. Shiba parry damage) appear
        # after the parry in the combat log.
        log.add_action(parry_action)

        # Post-parry effects via Fighter hook
        old_actions = list(defender_fighter.actions_remaining)
        old_shinjo_count = len(defender_fighter.shinjo_bonuses)
        _old_temp_void = defender_fighter.temp_void
        margin = effective_parry_total - parry_tn
        defender_fighter.on_parry_attempt(parry_succeeded, margin, attacker_name, phase)
        temp_void_delta = defender_fighter.temp_void - _old_temp_void
        # Detect changes for description hook
        actions_changed = defender_fighter.actions_remaining != old_actions
        new_shinjo_count = len(defender_fighter.shinjo_bonuses)
        bonus_stored = (
            defender_fighter.shinjo_bonuses[-1]
            if new_shinjo_count > old_shinjo_count else None
        )
        parry_action.description += defender_fighter.post_parry_effect_description(
            temp_void_delta, actions_changed, bonus_stored,
        )

        parry_action.status_after = state.snapshot_status()

        if parry_succeeded:
            # SA counter-lunge fires even after successful parry
            if (
                not log.wounds[attacker_name].is_mortally_wounded
                and not log.wounds[defender_name].is_mortally_wounded
            ):
                defender_fighter.resolve_post_attack_interrupt(
                    attacker_name, phase,
                )
            return

        # Failed parry: reduce extra dice by defender's parry rank (not all)
        # Lunge dice are included in the reducible pool (unless immune)
        if not parry_succeeded:
            all_extra = max(0, (attack_action.total - (base_tn if is_double_attack else tn)) // 5)
            lunge_dice = lunge_preview_bonus
            all_extra_with_lunge = all_extra + lunge_dice
            parry_reduction = attacker_fighter.damage_parry_reduction(def_parry_rank)
            if all_extra_with_lunge > 0:
                reduced_extra = max(0, all_extra_with_lunge - parry_reduction)
                # Lunge die survives parry reduction (e.g. Otaku 4th Dan)
                if lunge_dice > 0 and attacker_fighter.lunge_damage_survives_parry():
                    reduced_extra = max(0, all_extra - parry_reduction) + lunge_dice
                full_rolled = (
                    preview_weapon_rolled + attacker.rings.fire.value
                    + all_extra + lunge_dice
                )
                reduced_rolled = (
                    preview_weapon_rolled + attacker.rings.fire.value
                    + reduced_extra
                )
                # DA failed parry: serious wound converts to +2 rolled dice
                da_conversion_dice = 2 if is_double_attack and not is_near_miss_da else 0
                reduced_rolled += da_conversion_dice
                full_raw = f"{full_rolled}k{weapon.kept}"
                reduced_display = _format_pool_with_overflow(reduced_rolled, weapon.kept)
                da_prevent_note = (
                    "automatic serious wound is converted"
                    " to +2 rolled dice, and "
                    if is_double_attack else ""
                )
                parry_action.description += (
                    f" — {da_prevent_note}{full_raw}"
                    f" is reduced to {reduced_display}"
                )

    # --- Roll damage ---
    # For double attack, extra dice use base_tn (before +20)
    extra_tn_for_dice = base_tn if is_double_attack else tn
    all_extra_dice = max(0, (attack_action.total - extra_tn_for_dice) // 5)

    # Lunge dice: included in the reducible pool
    lunge_damage_bonus = lunge_preview_bonus

    if parry_attempted:
        parry_reduction = attacker_fighter.damage_parry_reduction(def_parry_rank)
        all_reducible = all_extra_dice + lunge_damage_bonus
        reduced = max(0, all_reducible - parry_reduction)
        # Lunge die survives parry reduction (e.g. Otaku 4th Dan)
        if lunge_damage_bonus > 0 and attacker_fighter.lunge_damage_survives_parry():
            extra_dice = max(0, all_extra_dice - parry_reduction) + lunge_damage_bonus
        else:
            extra_dice = reduced
    else:
        extra_dice = all_extra_dice + lunge_damage_bonus

    # Ability 9: Failed parry bonus — via Fighter hook
    if parry_attempted and not parry_succeeded:
        parry_red = attacker_fighter.damage_parry_reduction(def_parry_rank)
        bonus_back = attacker_fighter.failed_parry_dice_recovery(
            all_extra_dice, parry_red,
        )
        extra_dice += bonus_back

    # Double attack: failed parry converts 1 serious wound to 2 extra rolled dice
    da_extra_rolled = 0
    da_serious_wound = 0
    if is_double_attack and not is_near_miss_da:
        if parry_attempted and not parry_succeeded:
            # Serious wound converts to 2 extra rolled dice instead
            da_extra_rolled = 2
        elif not parry_attempted:
            # No parry: inflict 1 extra serious wound directly
            da_serious_wound = 1

    # Near-miss DA: no extra dice, no auto serious wound
    if is_near_miss_da:
        extra_dice = 0

    # Ability 3: Weapon damage boost — via Fighter hook
    boosted_rolled = attacker_fighter.weapon_rolled_boost(weapon.rolled, weapon.kept)

    # 5th Dan trade: trade damage dice for automatic serious wound
    trade_sw = 0
    trade_note = ""
    full_pool = boosted_rolled + attacker.rings.fire.value + extra_dice + da_extra_rolled
    should_trade, dice_removed, t_note = attacker_fighter.should_trade_damage_for_wound(
        full_pool, is_double_attack=is_double_attack,
    )
    if should_trade and full_pool >= dice_removed:
        # Remove dice from extras first, then from weapon rolled
        remaining_to_remove = dice_removed
        extras_removed = min(extra_dice, remaining_to_remove)
        extra_dice -= extras_removed
        remaining_to_remove -= extras_removed
        boosted_rolled = max(0, boosted_rolled - remaining_to_remove)
        trade_sw = 1
        trade_note = t_note

    extra_dmg = extra_dice + da_extra_rolled
    damage_action = roll_damage(
        attacker, boosted_rolled, weapon.kept, extra_dmg,
    )
    damage_action.phase = phase
    damage_action.target = defender_name
    # Show overflow conversion in damage dice pool
    dmg_rolled = (
        boosted_rolled + attacker.rings.fire.value
        + extra_dice + da_extra_rolled
    )
    damage_action.dice_pool = _format_pool_with_overflow(dmg_rolled, weapon.kept)

    # Ability 4: Damage rounding — via Fighter hook
    damage_total, rounding_note = attacker_fighter.damage_rounding(damage_action.total)
    if rounding_note:
        damage_action.total = damage_total
        damage_action.description += rounding_note

    # Ability 8: Damage reduction — via Fighter hook
    had_extra_dice = all_extra_dice > 0 if not parry_attempted else extra_dice > 0
    damage_action.total, reduction_note = defender_fighter.damage_reduction(
        damage_action.total, had_extra_dice,
    )
    if reduction_note:
        damage_action.description += reduction_note

    log.add_action(damage_action)

    # Apply damage as light wounds
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += damage_action.total

    # Double attack: inflict extra serious wound directly (no parry case)
    if da_serious_wound > 0:
        wound_tracker.serious_wounds += da_serious_wound
        damage_action.description += f" (double attack: +{da_serious_wound} serious wound)"

    # 5th Dan trade: apply auto serious wound from damage trade
    if trade_sw > 0:
        wound_tracker.serious_wounds += trade_sw
        damage_action.description += trade_note

    # Post-damage effect via Fighter hook (e.g. Otaku 3rd Dan dice slowdown)
    post_dmg_note = attacker_fighter.post_damage_effect(defender_name)
    if post_dmg_note:
        damage_action.description += post_dmg_note

    # Snapshot after damage is applied
    damage_action.status_after = state.snapshot_status()

    # --- Post-damage counterattack (only if pre-attack counterattack didn't fire) ---
    if ca_result is None:
        defender_fighter.resolve_post_damage_counterattack(
            attacker_name, phase, damage_action.total,
        )

    # --- 4th Dan wound check replacement (e.g. Hida) ---
    should_replace, auto_sw, replace_note = defender_fighter.should_replace_wound_check(
        wound_tracker.light_wounds,
    )
    if should_replace:
        wound_tracker.serious_wounds += auto_sw
        wound_tracker.light_wounds = 0
        wc_action = CombatAction(
            phase=phase,
            actor=defender_name,
            action_type=ActionType.WOUND_CHECK,
            total=0,
            tn=None,
            success=None,
            description=(
                f"{defender_name} wound check: replaced with"
                f" {auto_sw} serious wounds{replace_note}"
            ),
            dice_pool="",
            label=f"{auto_sw} serious wounds instead of wound check",
        )
        wc_action.status_after = state.snapshot_status()
        log.add_action(wc_action)

        # Post-attack interrupt still fires
        if (
            not log.wounds[attacker_name].is_mortally_wounded
            and not log.wounds[defender_name].is_mortally_wounded
        ):
            defender_fighter.resolve_post_attack_interrupt(attacker_name, phase)
        return

    # --- Wound check ---
    water_value = defender.rings.water.value

    void_spent_note = ""

    # Compute wound check bonuses before void decision
    wc_extra_rolled = defender_fighter.wound_check_extra_rolled()
    ab10_bonus = attacker_fighter.wound_check_tn_bonus()

    # Wound check void strategy via Fighter hook
    wc_void_strategy = defender_fighter.wound_check_void_strategy(
        water_value, wound_tracker.light_wounds,
    )
    max_spend = defender.rings.lowest()
    if wc_void_strategy == 0:
        void_spend = 0
    else:
        wc_void_avail = defender_fighter.total_void
        void_spend = _should_spend_void_on_wound_check(
            water_value, wound_tracker.light_wounds, wc_void_avail,
            max_spend=max_spend,
            extra_rolled=wc_extra_rolled,
            tn_bonus=ab10_bonus,
        )
    wc_from_temp, wc_from_reg = defender_fighter.spend_void(void_spend)
    wc_void_label = _void_spent_label(wc_from_temp, wc_from_reg)

    # Wound check void spending generates bonus (via Fighter hook)
    if void_spend > 0:
        void_spent_note = defender_fighter.on_void_spent(void_spend, "wound_check")

    sw_before_wc = wound_tracker.serious_wounds

    wc_extra_kept = defender_fighter.wound_check_extra_kept()
    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=wc_extra_rolled, tn_bonus=ab10_bonus,
        extra_kept=wc_extra_kept,
    )

    # Wound check flat bonus via Fighter hook (e.g. Otaku 2nd Dan +5)
    wc_flat_bonus, wc_flat_note = defender_fighter.wound_check_flat_bonus()
    if wc_flat_bonus > 0:
        wc_total += wc_flat_bonus
        effective_tn = wound_tracker.light_wounds + ab10_bonus
        passed = wc_total >= effective_tn

    # Ability 5: Free crippled reroll on wound check
    if not passed and log.wounds[defender_name].is_crippled:
        wc_all_dice, wc_kept_dice, wc_total, _ = defender_fighter.crippled_reroll(
            wc_all_dice, water_value + void_spend,
        )
        effective_tn = wound_tracker.light_wounds + ab10_bonus
        if wc_total >= effective_tn:
            passed = True

    # Post wound check: apply stored bonuses via Fighter hook
    wc_bonus_note = ""
    if not passed:
        new_passed, new_total, wc_note = (
            defender_fighter.post_wound_check(
                passed, wc_total, attacker_name,
                sw_before_wc=sw_before_wc,
            )
        )
        if new_total != wc_total:
            wc_bonus_note = wc_note
            wc_total = new_total
            passed = new_passed

    void_note = f" ({wc_void_label})" if wc_void_label else ""

    # Record the TN before any conversion modifies light_wounds
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn + ab10_bonus

    # Feature 3: Wound check success choice
    convert_note = ""
    if passed:
        should_convert = _should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            shinjo_wc_bonus_pool=defender_fighter.wc_bonus_pool_total(),
        )
        if should_convert:
            wound_tracker.serious_wounds += 1
            wound_tracker.light_wounds = 0
            convert_note = " — converted light wounds to 1 serious wound"
        else:
            convert_note = f" — keeping {wound_tracker.light_wounds} light wounds"

    ab10_note = (
        f" (TN {wc_tn} from {wc_base_tn} LW due to wave man ability)"
        if ab10_bonus > 0 else ""
    )
    da_auto_sw_note = (
        f" (plus {da_serious_wound} automatic SW"
        f" from double attack)"
        if da_serious_wound > 0 else ""
    )
    wc_rolled = water_value + 1 + wc_extra_rolled + void_spend
    wc_kept = water_value + void_spend + wc_extra_kept
    wc_action = CombatAction(
        phase=phase,
        actor=defender_name,
        action_type=ActionType.WOUND_CHECK,
        dice_rolled=wc_all_dice,
        dice_kept=wc_kept_dice,
        total=wc_total,
        tn=wc_tn,
        base_tn=wc_base_tn if ab10_bonus > 0 else None,
        success=passed,
        description=(
            f"{defender_name} wound check: {'passed' if passed else 'failed'} "
            f"(rolled {wc_total}){void_note}{void_spent_note}{wc_flat_note}{wc_bonus_note}"
            f"{convert_note}{da_auto_sw_note}{ab10_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    # If wound check failed, light wounds reset to 0 (handled in make_wound_check via serious)
    if not passed:
        reset_value, reset_note = attacker_fighter.on_wound_check_failed(
            defender_name,
        )
        wound_tracker.light_wounds = reset_value
        if reset_note:
            wc_action.description += reset_note

    # Snapshot after wound check (reflects serious wound promotion if failed)
    wc_action.status_after = state.snapshot_status()

    # Post-attack interrupt via Fighter hook (e.g. Otaku SA counter-lunge)
    if (
        not log.wounds[attacker_name].is_mortally_wounded
        and not log.wounds[defender_name].is_mortally_wounded
    ):
        defender_fighter.resolve_post_attack_interrupt(attacker_name, phase)


