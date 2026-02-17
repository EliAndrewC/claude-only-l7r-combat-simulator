"""Combat simulation orchestrator.

Runs a full combat between two characters using the core engine primitives.
"""

from __future__ import annotations

import random

from src.engine.combat import (
    calculate_attack_tn,
    create_combat_log,
    make_wound_check,
    roll_attack,
    roll_damage,
    roll_initiative,
)
from src.engine.dice import reroll_tens, roll_and_keep
from src.models.character import Character, RingName
from src.models.combat import ActionType, CombatAction, CombatLog, FighterStatus
from src.models.weapon import Weapon


def _damage_pool_str(weapon_rolled: int, weapon_kept: int, fire_ring: int, extra_dice: int) -> str:
    """Format a damage dice pool string.

    Args:
        weapon_rolled: Base rolled dice from weapon.
        weapon_kept: Base kept dice from weapon.
        fire_ring: Attacker's Fire ring value.
        extra_dice: Bonus rolled dice from raises.

    Returns:
        String like "7k2".
    """
    return f"{weapon_rolled + fire_ring + extra_dice}k{weapon_kept}"


def _format_pool_with_overflow(rolled: int, kept: int) -> str:
    """Format a dice pool string, showing overflow conversion if applicable.

    Mirrors the overflow rules from roll_and_keep:
    - Excess rolled dice beyond 10 become extra kept dice.
    - Excess kept dice beyond 10 become +1 bonuses.

    Returns:
        String like "7k2" or "18k2, which becomes 10k10".
    """
    raw = f"{rolled}k{kept}"
    if rolled <= 10:
        return raw
    eff_kept = kept + (rolled - 10)
    eff_rolled = 10
    bonus = 0
    if eff_kept > 10:
        bonus = eff_kept - 10
        eff_kept = 10
    eff = f"{eff_rolled}k{eff_kept}"
    if bonus:
        eff += f"+{bonus}"
    return f"{raw}, which becomes {eff}"


def _should_spend_void_on_wound_check(
    water_ring: int,
    light_wounds: int,
    void_available: int,
    max_spend: int,
    threshold: float = 0.25,
) -> int:
    """Decide how many void points to spend on a wound check via Monte Carlo.

    Uses a separate RNG seeded from the inputs so it is deterministic for
    the same game state and does not disturb the main combat dice stream.

    Args:
        water_ring: The character's Water ring value.
        light_wounds: Current light wound total (= wound check TN).
        void_available: Remaining void points.
        max_spend: Maximum void spendable on a single action (lowest ring).
        threshold: Minimum expected serious-wounds-saved per void point spent.

    Returns:
        Number of void points to spend (0 to min(void_available, max_spend)).
    """
    if void_available <= 0 or light_wounds <= 0:
        return 0

    limit = min(void_available, max_spend)
    seed = hash((water_ring, light_wounds, void_available, max_spend))
    rng = random.Random(seed)
    n_sims = 2000
    tn = light_wounds

    def _simulate_serious(kept: int) -> float:
        rolled = water_ring + 1
        effective_kept = min(kept, rolled)
        total_serious = 0
        for _ in range(n_sims):
            dice: list[int] = []
            for _ in range(rolled):
                total = 0
                while True:
                    roll = rng.randint(1, 10)
                    total += roll
                    if roll != 10:
                        break
                dice.append(total)
            dice.sort(reverse=True)
            roll_total = sum(dice[:effective_kept])
            if roll_total < tn:
                deficit = tn - roll_total
                total_serious += 1 + (deficit // 10)
        return total_serious / n_sims

    baseline = _simulate_serious(kept=water_ring)
    best_spend = 0
    best_improvement = 0.0

    for spend in range(1, limit + 1):
        expected = _simulate_serious(kept=water_ring + spend)
        improvement = baseline - expected
        # Only spend if improvement per void point meets threshold
        if improvement >= threshold and improvement > best_improvement:
            best_improvement = improvement
            best_spend = spend

    return best_spend


def _should_convert_light_to_serious(
    light_wounds: int,
    serious_wounds: int,
    earth_ring: int,
    water_ring: int = 2,
) -> bool:
    """Decide whether to convert light wounds to 1 serious wound on a passed wound check.

    The decision balances the 1 serious wound cost of converting against the
    long-term danger of carrying high light wounds into future wound checks.

    Keeping N light wounds saves 1 serious wound now, but raises every future
    wound check TN by N.  The break-even depends on how well the character
    can absorb that higher TN, i.e. their wound check power.

    Wound check = (Water+1)k(Water) with exploding 10s.  We estimate the
    average roll and set the keep-threshold as a fraction of it:

        avg_wc ≈ Water × 6.5 + 2      (rough mean of (Water+1)kWater)
        threshold = max(10, round(avg_wc × 0.8))

    Below 10 light wounds there is zero downside to keeping: even the worst-
    case future failure adds at most 1 extra serious wound (deficit < 10),
    exactly cancelling the 1 serious saved by not converting.  Above the
    threshold the accumulated TN becomes dangerous enough that converting
    is the safer play.

    Threshold examples (placeholder — intended to be tuned by simulation):
        Water 1 → 10   (bad wound check, converts anything above 10)
        Water 2 → 12
        Water 3 → 17
        Water 4 → 22
        Water 5 → 28   (great wound check, still won't hold 40)

    Args:
        light_wounds: Current light wound total.
        serious_wounds: Current serious wound count.
        earth_ring: Character's Earth ring value.
        water_ring: Character's Water ring value (determines wound check power).

    Returns:
        True if the character should take 1 serious wound and reset light wounds to 0.
    """
    # Never convert if it would cripple (serious + 1 >= earth)
    if serious_wounds + 1 >= earth_ring:
        return False

    # Estimate expected wound check total for (Water+1)k(Water) w/ explosions.
    # Each kept die averages ~6.5 (selection bias from keeping highest of a
    # slightly larger pool pushes it above the raw 6.11 mean of an exploding
    # d10).  The dropped minimum die is small (~2–4), so we add a flat +2.
    avg_wc_total = water_ring * 6.5 + 2

    # Keep threshold: 80% of expected wound check total, floored at 10.
    # The 0.8 factor provides margin for variance and for the fact that
    # future hits will stack additional damage on top of the carried wounds.
    threshold = max(10, round(avg_wc_total * 0.8))

    return light_wounds > threshold


def _should_predeclare_parry(
    defender_parry_rank: int,
    air_ring: int,
    attack_tn: int,
    is_crippled: bool,
) -> bool:
    """Decide whether to pre-declare a parry for the +5 bonus.

    Pre-declare when the +5 bonus meaningfully increases the chance of success.
    The tradeoff: pre-declaring wastes the action die if the attack misses.

    Args:
        defender_parry_rank: Defender's parry skill rank.
        air_ring: Defender's Air ring value.
        attack_tn: The TN the attacker needs to hit (proxy for expected attack total).
        is_crippled: Whether the defender is crippled.

    Returns:
        True if pre-declaring is worthwhile.
    """
    parry_dice = defender_parry_rank + air_ring
    parry_kept = air_ring
    # Rough expected parry total: kept_dice * 5.5 (avg d10)
    expected_parry = parry_kept * 5.5
    if is_crippled:
        expected_parry = parry_kept * 5.0  # No exploding lowers average slightly

    # Pre-declare when the expected parry total is below the attack TN
    # (meaning the +5 bonus is needed to have a reasonable chance)
    return expected_parry < attack_tn


def _should_interrupt_parry(
    defender_parry_rank: int,
    air_ring: int,
    attack_total: int,
    attack_tn: int,
    weapon_rolled: int,
    attacker_fire: int,
    dice_remaining: int,
    serious_wounds: int,
    earth_ring: int,
) -> bool:
    """Decide whether to spend 2 action dice for a reactive interrupt parry.

    Called AFTER the attack hits. Triggers only when expected damage is
    catastrophic (dice overflow beyond 10) or when near cripple with
    significant extra dice.

    Args:
        defender_parry_rank: Defender's parry skill rank.
        air_ring: Defender's Air ring value.
        attack_total: The actual attack roll total.
        attack_tn: The TN the attacker needed to hit.
        weapon_rolled: Attacker's weapon rolled dice.
        attacker_fire: Attacker's Fire ring value.
        dice_remaining: Number of action dice the defender has left.
        serious_wounds: Defender's current serious wounds.
        earth_ring: Defender's Earth ring value.

    Returns:
        True if the defender should spend 2 dice for an interrupt parry.
    """
    if dice_remaining < 2 or defender_parry_rank <= 0:
        return False

    extra_dice = max(0, (attack_total - attack_tn) // 5)
    damage_rolled = weapon_rolled + attacker_fire + extra_dice
    wounds_to_cripple = earth_ring - serious_wounds

    if damage_rolled > 10:  # catastrophic overflow
        return True
    if wounds_to_cripple <= 1 and extra_dice >= 2:  # near cripple + significant extras
        return True
    return False


def _tiebreak_key(
    name: str,
    actions_remaining: dict[str, list[int]],
    fighters: dict[str, dict],
    phase: int,
) -> tuple:
    """Generate a sort key for initiative tiebreaking.

    Tiebreaking order:
    1. Phase (lower first)
    2. Compare action dice ascending (lower second-die first, etc.)
    3. Higher Void ring first
    4. Random coin flip

    Args:
        name: Character name.
        actions_remaining: All characters' remaining action dice.
        fighters: Fighter info dict.
        phase: The current phase value.

    Returns:
        A tuple suitable for sorting (lower = acts first).
    """
    dice = sorted(actions_remaining.get(name, []))
    char: Character = fighters[name]["char"]
    void_ring = char.rings.void.value
    # Pad dice list to ensure consistent comparison (pad with 11 = higher than max die)
    padded = dice + [11] * (10 - len(dice))
    return (phase, tuple(padded), -void_ring, random.random())


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

    fighters = {
        char_a.name: {"char": char_a, "weapon": weapon_a},
        char_b.name: {"char": char_b, "weapon": weapon_b},
    }

    void_points: dict[str, int] = {
        char_a.name: char_a.void_points_max,
        char_b.name: char_b.void_points_max,
    }

    for round_num in range(1, max_rounds + 1):
        log.round_number = round_num

        # --- Initiative Phase ---
        init_a = roll_initiative(char_a)
        init_b = roll_initiative(char_b)

        actions_remaining: dict[str, list[int]] = {
            char_a.name: sorted(init_a.dice_kept),
            char_b.name: sorted(init_b.dice_kept),
        }

        init_a.status_after = _snapshot_status(log, fighters, actions_remaining, void_points)
        log.add_action(init_a)
        init_b.status_after = _snapshot_status(log, fighters, actions_remaining, void_points)
        log.add_action(init_b)

        # Build action schedule: list of (phase, die_value, character_name)
        schedule: list[tuple[int, int, str]] = []
        for die_val in init_a.dice_kept:
            schedule.append((die_val, die_val, char_a.name))
        for die_val in init_b.dice_kept:
            schedule.append((die_val, die_val, char_b.name))

        # Sort with full tiebreaking rules (feature 6)
        schedule.sort(
            key=lambda x: _tiebreak_key(x[2], actions_remaining, fighters, x[0])
        )

        # --- Action Phases ---
        for phase, _die_val, attacker_name in schedule:
            # Check if combat is over
            if _is_mortally_wounded(log, char_a.name) or _is_mortally_wounded(log, char_b.name):
                break

            defender_name = char_b.name if attacker_name == char_a.name else char_a.name
            attacker_info = fighters[attacker_name]
            defender_info = fighters[defender_name]

            _resolve_attack(
                log, phase, attacker_info, defender_info, attacker_name, defender_name,
                fighters, actions_remaining, void_points,
            )

        # Check for combat end
        if _is_mortally_wounded(log, char_a.name):
            log.winner = char_b.name
            break
        if _is_mortally_wounded(log, char_b.name):
            log.winner = char_a.name
            break

    return log


def _snapshot_status(
    log: CombatLog,
    fighters: dict[str, dict],
    actions_remaining: dict[str, list[int]],
    void_points: dict[str, int],
) -> dict[str, FighterStatus]:
    """Build a snapshot of each fighter's current state."""
    result: dict[str, FighterStatus] = {}
    for name in log.combatants:
        wt = log.wounds[name]
        char = fighters[name]["char"]
        result[name] = FighterStatus(
            light_wounds=wt.light_wounds,
            serious_wounds=wt.serious_wounds,
            is_crippled=wt.is_crippled,
            is_mortally_wounded=wt.is_mortally_wounded,
            actions_remaining=list(actions_remaining.get(name, [])),
            void_points=void_points.get(name, 0),
            void_points_max=char.void_points_max,
        )
    return result


def _is_mortally_wounded(log: CombatLog, name: str) -> bool:
    """Check if a combatant is mortally wounded."""
    return log.wounds[name].is_mortally_wounded


def _resolve_attack(
    log: CombatLog,
    phase: int,
    attacker_info: dict,
    defender_info: dict,
    attacker_name: str,
    defender_name: str,
    fighters: dict[str, dict],
    actions_remaining: dict[str, list[int]],
    void_points: dict[str, int],
) -> None:
    """Resolve a single attack action in a phase."""
    attacker: Character = attacker_info["char"]
    defender: Character = defender_info["char"]
    weapon: Weapon = attacker_info["weapon"]

    # Consume the phase die — if already gone (e.g. spent on a parry), skip
    if phase in actions_remaining[attacker_name]:
        actions_remaining[attacker_name].remove(phase)
    else:
        return

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

    # --- Parry pre-declaration (feature 4) ---
    # Only regular parries (defender has action in this phase) can be pre-declared.
    # Interrupts are reactive — decided AFTER seeing the attack roll.
    has_action_in_phase = phase in actions_remaining[defender_name]

    predeclared = False
    if has_action_in_phase and def_parry_rank > 0:
        defender_crippled = log.wounds[defender_name].is_crippled
        predeclared = _should_predeclare_parry(
            def_parry_rank, defender.rings.air.value, tn, defender_crippled,
        )

    # If pre-declared, consume the parry die now (before attack roll)
    if predeclared:
        actions_remaining[defender_name].remove(phase)

    # --- Roll attack ---
    attack_action = roll_attack(attacker, atk_rank, RingName.FIRE, tn, explode=attack_explode)
    attack_action.phase = phase
    attack_action.target = defender_name

    # Feature 2: Crippled void reroll on attack
    if attacker_crippled and not attack_action.success:
        has_tens = any(d == 10 for d in attack_action.dice_rolled)
        max_void_spend = attacker.rings.lowest()
        if has_tens and void_points.get(attacker_name, 0) > 0 and max_void_spend > 0:
            new_all, new_kept, new_total = reroll_tens(
                attack_action.dice_rolled, len(attack_action.dice_kept),
            )
            void_points[attacker_name] -= 1
            attack_action.dice_rolled = new_all
            attack_action.dice_kept = new_kept
            attack_action.total = new_total
            attack_action.success = new_total >= tn
            attack_action.description += " (void: rerolled 10s)"

    attack_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points)
    log.add_action(attack_action)

    # Attack missed — dice already consumed by pre-declaration (if any),
    # reflected in attack_action.status_after snapshot.
    if not attack_action.success:
        return

    # Annotate attack hit with expected damage pool (assuming no parry)
    no_parry_extra = max(0, (attack_action.total - tn) // 5)
    raw_rolled = weapon.rolled + attacker.rings.fire.value + no_parry_extra
    pool_display = _format_pool_with_overflow(raw_rolled, weapon.kept)
    attack_action.description += f" — damage will be {pool_display}"

    # --- Defender attempts parry ---
    parry_attempted = False
    parry_succeeded = False
    is_interrupt = False

    # Determine if defender can parry
    can_parry = False
    if has_action_in_phase and def_parry_rank > 0:
        can_parry = True
    elif (
        not has_action_in_phase
        and len(actions_remaining[defender_name]) >= 2
        and def_parry_rank > 0
    ):
        # Reactive interrupt decision — called AFTER seeing actual attack roll
        attacker_weapon: Weapon = attacker_info["weapon"]
        should_interrupt = _should_interrupt_parry(
            def_parry_rank, defender.rings.air.value,
            attack_action.total, tn,
            attacker_weapon.rolled, attacker.rings.fire.value,
            len(actions_remaining[defender_name]),
            log.wounds[defender_name].serious_wounds,
            log.wounds[defender_name].earth_ring,
        )
        if should_interrupt:
            can_parry = True
            is_interrupt = True

    if can_parry and def_parry_rank > 0:
        parry_attempted = True

        # Consume dice for the parry
        if is_interrupt:
            # Interrupts always consume 2 dice (never pre-declared)
            remaining = sorted(actions_remaining[defender_name], reverse=True)
            for die in remaining[:2]:
                actions_remaining[defender_name].remove(die)
        elif not predeclared and has_action_in_phase:
            # Regular parry not pre-declared: consume now
            actions_remaining[defender_name].remove(phase)

        air_value = defender.rings.air.value
        parry_rolled = def_parry_rank + air_value
        parry_kept = air_value

        # Feature 1: Crippled disables exploding 10s on parry rolls
        defender_crippled = log.wounds[defender_name].is_crippled
        parry_explode = not defender_crippled

        # Feature 4: Pre-declared parry gets +5 bonus (added to total)
        # Interrupts are reactive and never get the pre-declare bonus
        parry_tn = attack_action.total
        parry_bonus = 5 if (predeclared and not is_interrupt) else 0
        parry_bonus_note = " (pre-declared, +5 bonus)" if (predeclared and not is_interrupt) else ""

        all_dice, kept_dice, parry_total = roll_and_keep(
            parry_rolled, parry_kept, explode=parry_explode,
        )

        # Feature 2: Crippled void reroll on parry
        if defender_crippled and (parry_total + parry_bonus) < parry_tn:
            has_tens = any(d == 10 for d in all_dice)
            max_void_spend = defender.rings.lowest()
            if has_tens and void_points.get(defender_name, 0) > 0 and max_void_spend > 0:
                all_dice, kept_dice, parry_total = reroll_tens(all_dice, parry_kept)
                void_points[defender_name] -= 1
                parry_bonus_note += " (void: rerolled 10s)"

        effective_parry_total = parry_total + parry_bonus
        parry_succeeded = effective_parry_total >= parry_tn

        action_type = ActionType.INTERRUPT if is_interrupt else ActionType.PARRY
        interrupt_note = " (interrupt)" if is_interrupt else ""
        parry_pool = f"{parry_rolled}k{parry_kept} + 5" if predeclared else f"{parry_rolled}k{parry_kept}"
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
                f"vs TN {parry_tn}{parry_bonus_note}{interrupt_note}"
            ),
            dice_pool=parry_pool,
        )
        parry_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points)
        log.add_action(parry_action)

        if parry_succeeded:
            return

        # Failed parry: reduce extra dice by defender's parry rank (not all)
        if not parry_succeeded:
            all_extra = max(0, (attack_action.total - tn) // 5)
            if all_extra > 0:
                reduced_extra = max(0, all_extra - def_parry_rank)
                full_rolled = weapon.rolled + attacker.rings.fire.value + all_extra
                reduced_rolled = weapon.rolled + attacker.rings.fire.value + reduced_extra
                full_raw = f"{full_rolled}k{weapon.kept}"
                reduced_display = _format_pool_with_overflow(reduced_rolled, weapon.kept)
                parry_action.description += f" — {full_raw} is reduced to {reduced_display}"

    # --- Roll damage ---
    # Extra damage dice from raises, reduced by parry rank if parry was attempted
    all_extra_dice = max(0, (attack_action.total - tn) // 5)
    if parry_attempted:
        extra_dice = max(0, all_extra_dice - def_parry_rank)
    else:
        extra_dice = all_extra_dice

    damage_action = roll_damage(attacker, weapon.rolled, weapon.kept, extra_dice)
    damage_action.phase = phase
    damage_action.target = defender_name
    log.add_action(damage_action)

    # Apply damage as light wounds
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += damage_action.total

    # Snapshot after damage is applied
    damage_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points)

    # --- Wound check ---
    water_value = defender.rings.water.value

    # Decide how many void points to spend
    max_spend = defender.rings.lowest()
    void_spend = _should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, void_points.get(defender_name, 0),
        max_spend=max_spend,
    )
    void_points[defender_name] -= void_spend

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
    )

    void_note = f" ({void_spend} void point spent)" if void_spend else ""

    # Record the TN before any conversion modifies light_wounds
    wc_tn = wound_tracker.light_wounds

    # Feature 3: Wound check success choice
    convert_note = ""
    if passed:
        should_convert = _should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
        )
        if should_convert:
            wound_tracker.serious_wounds += 1
            wound_tracker.light_wounds = 0
            convert_note = " — converted light wounds to 1 serious wound"

    wc_rolled = water_value + 1
    wc_kept = water_value + void_spend
    wc_action = CombatAction(
        phase=phase,
        actor=defender_name,
        action_type=ActionType.WOUND_CHECK,
        dice_rolled=wc_all_dice,
        dice_kept=wc_kept_dice,
        total=wc_total,
        tn=wc_tn,
        success=passed,
        description=(
            f"{defender_name} wound check: {'passed' if passed else 'failed'} "
            f"(rolled {wc_total}){void_note}{convert_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    # If wound check failed, light wounds reset to 0 (handled in make_wound_check via serious)
    if not passed:
        wound_tracker.light_wounds = 0

    # Snapshot after wound check (reflects serious wound promotion if failed)
    wc_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points)
