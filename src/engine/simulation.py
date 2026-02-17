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
import math

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


def _should_spend_void_on_combat_roll(
    rolled: int,
    kept: int,
    tn: int,
    void_available: int,
    max_spend: int,
    fifth_dan_bonus: int = 0,
) -> int:
    """Decide how many void points to spend on an attack or parry roll.

    Each void spent adds 1k1 (about +5.5) plus the fifth_dan_bonus to the roll.
    Only spends if it meaningfully increases the chance of success.
    Reserves at least 1 void point for wound checks.

    Args:
        rolled: Number of dice rolled.
        kept: Number of dice kept.
        tn: Target number to meet or exceed.
        void_available: Remaining void points.
        max_spend: Maximum void spendable on a single action.
        fifth_dan_bonus: Flat bonus per void spent (0 or 10 for 5th Dan Mirumoto).

    Returns:
        Number of void points to spend (0 to min(void_available-1, max_spend)).
    """
    if void_available <= 1 or tn <= 0:
        return 0

    # Reserve 1 void for wound checks
    usable = min(void_available - 1, max_spend)
    if usable <= 0:
        return 0

    # Estimate expected roll: kept dice * 5.5 average
    expected = kept * 5.5
    value_per_void = 5.5 + fifth_dan_bonus  # 1k1 + bonus

    # Only spend if expected roll is below TN and void spending bridges the gap
    if expected >= tn:
        return 0

    deficit = tn - expected
    needed = max(1, int(deficit / value_per_void + 0.5))
    return min(needed, usable)


def _should_use_double_attack(
    double_attack_rank: int,
    attack_skill: int,
    fire_ring: int,
    defender_parry: int,
    void_available: int,
    max_void_spend: int,
    dan: int,
    is_crippled: bool,
) -> tuple[bool, int]:
    """Decide whether to use Double Attack and how much void to spend.

    Double Attack uses Double Attack skill + Fire instead of Attack + Fire,
    but raises TN by 20. The benefit: extra damage dice based on base TN
    (not raised TN) plus 1 serious wound.

    Args:
        double_attack_rank: Character's Double Attack knack rank.
        attack_skill: Character's Attack skill rank.
        fire_ring: Character's Fire ring value.
        defender_parry: Defender's parry skill rank.
        void_available: Remaining void points.
        max_void_spend: Maximum void per action.
        dan: Character's dan level (for technique bonuses).
        is_crippled: Whether the attacker is crippled.

    Returns:
        Tuple of (use_double_attack, void_to_spend).
    """
    if double_attack_rank <= 0 or is_crippled:
        return False, 0

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    fifth_dan_bonus = 10 if dan >= 5 else 0
    first_dan_bonus = 1 if dan >= 1 else 0

    # Normal attack expected value
    normal_rolled = attack_skill + fire_ring + first_dan_bonus
    normal_kept = fire_ring
    normal_expected = normal_kept * 5.5

    # Double attack expected value
    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = da_kept * 5.5

    # Only consider DA if it has a reasonable chance of hitting
    # Account for void spending
    usable_void = min(void_available - 1, max_void_spend) if void_available > 1 else 0
    void_value_per = 5.5 + fifth_dan_bonus
    max_void_boost = usable_void * void_value_per

    if da_expected + max_void_boost < da_tn * 0.7:
        return False, 0

    # Use DA when the normal attack is likely to hit easily (extra dice benefit)
    # and the DA also has reasonable odds
    if normal_expected >= base_tn and da_expected + max_void_boost >= da_tn * 0.85:
        # Determine void to spend on DA
        if da_expected >= da_tn:
            return True, 0
        deficit = da_tn - da_expected
        void_spend = min(usable_void, max(1, int(deficit / void_value_per + 0.5)))
        return True, void_spend

    return False, 0


def _matsu_attack_choice(
    lunge_rank: int,
    double_attack_rank: int,
    attack_skill: int,
    fire_ring: int,
    defender_parry: int,
    void_available: int,
    max_void_spend: int,
    dan: int,
    is_crippled: bool,
) -> tuple[str, int]:
    """Decide whether Matsu uses Lunge or Double Attack, and void to spend.

    Matsu NEVER makes a normal attack — always Lunge or Double Attack.
    If crippled or double_attack_rank == 0: always Lunge.

    Args:
        lunge_rank: Character's Lunge knack rank.
        double_attack_rank: Character's Double Attack knack rank.
        attack_skill: Character's Attack skill rank.
        fire_ring: Character's Fire ring value.
        defender_parry: Defender's parry skill rank.
        void_available: Remaining void points.
        max_void_spend: Maximum void per action.
        dan: Character's dan level.
        is_crippled: Whether the attacker is crippled.

    Returns:
        Tuple of ("lunge" | "double_attack", void_to_spend).
    """
    if is_crippled or double_attack_rank <= 0:
        # Matsu 3rd Dan+: more aggressive void on attacks (no reserve)
        usable = min(void_available, max_void_spend) if dan >= 3 else (
            min(void_available - 1, max_void_spend) if void_available > 1 else 0
        )
        lunge_rolled = lunge_rank + fire_ring
        lunge_kept = fire_ring
        base_tn = 5 + 5 * defender_parry
        expected = lunge_kept * 5.5
        if expected >= base_tn or usable <= 0:
            return "lunge", 0
        deficit = base_tn - expected
        void_spend = min(usable, max(1, int(deficit / 5.5 + 0.5)))
        return "lunge", void_spend

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    first_dan_bonus = 1 if dan >= 1 else 0

    # DA expected value
    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = da_kept * 5.5

    # Matsu 3rd Dan+: more aggressive void on attacks (no reserve)
    usable_void = min(void_available, max_void_spend) if dan >= 3 else (
        min(void_available - 1, max_void_spend) if void_available > 1 else 0
    )
    max_void_boost = usable_void * 5.5

    # 4th Dan: near-miss DA (within 20 of TN) still hits
    if dan >= 4:
        effective_da_tn = da_tn - 20  # near-miss threshold
        # Much more aggressive: attempt DA if can get within 20 of TN
        if da_expected + max_void_boost >= effective_da_tn * 0.6:
            if da_expected >= effective_da_tn:
                return "double_attack", 0
            deficit = effective_da_tn - da_expected
            void_spend = min(usable_void, max(1, int(deficit / 5.5 + 0.5)))
            return "double_attack", void_spend
    else:
        # Without 4th Dan: similar to Mirumoto threshold (85%+ chance)
        if da_expected + max_void_boost >= da_tn * 0.85:
            if da_expected >= da_tn:
                return "double_attack", 0
            deficit = da_tn - da_expected
            void_spend = min(usable_void, max(1, int(deficit / 5.5 + 0.5)))
            return "double_attack", void_spend

    # DA not viable: Lunge
    lunge_kept = fire_ring
    expected = lunge_kept * 5.5
    if expected >= base_tn or usable_void <= 0:
        return "lunge", 0
    deficit = base_tn - expected
    void_spend = min(usable_void, max(1, int(deficit / 5.5 + 0.5)))
    return "lunge", void_spend


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


def _spend_void(
    void_points: dict[str, int],
    temp_void: dict[str, int],
    name: str,
    amount: int,
) -> tuple[int, int]:
    """Spend void points, consuming temp void first.

    Returns:
        Tuple of (from_temp, from_regular).
    """
    from_temp = min(amount, temp_void.get(name, 0))
    if from_temp > 0:
        temp_void[name] -= from_temp
    remainder = amount - from_temp
    from_regular = 0
    if remainder > 0:
        from_regular = min(remainder, void_points.get(name, 0))
        void_points[name] -= from_regular
    return from_temp, from_regular


def _void_spent_label(from_temp: int, from_regular: int) -> str:
    """Format a human-readable label for void spending.

    Examples:
        (1, 0) -> "1 temp void spent"
        (0, 2) -> "2 void spent"
        (1, 1) -> "2 void spent (1 temp)"
    """
    total = from_temp + from_regular
    if total == 0:
        return ""
    if from_regular == 0:
        return f"{total} temp void spent"
    if from_temp == 0:
        return f"{total} void spent"
    return f"{total} void spent ({from_temp} temp)"


def _total_void(
    void_points: dict[str, int],
    temp_void: dict[str, int],
    name: str,
) -> int:
    """Total available void = regular + temp."""
    return void_points.get(name, 0) + temp_void.get(name, 0)


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

    temp_void: dict[str, int] = {char_a.name: 0, char_b.name: 0}

    dan_points: dict[str, int] = {
        char_a.name: 0,
        char_b.name: 0,
    }

    # Matsu 3rd Dan wound check bonus pool — persists across rounds
    matsu_bonuses: dict[str, list[int]] = {char_a.name: [], char_b.name: []}

    for round_num in range(1, max_rounds + 1):
        log.round_number = round_num

        # --- Dan Points Generation (3rd Dan+ Mirumoto) ---
        for name, info in fighters.items():
            char: Character = info["char"]
            if char.school == "Mirumoto Bushi" and char.dan >= 3:
                atk_skill = char.get_skill("Attack")
                atk_rank = atk_skill.rank if atk_skill else 0
                dan_points[name] = 2 * atk_rank
            else:
                dan_points[name] = 0

        # --- Lunge target bonus resets each round ---
        lunge_target_bonus: dict[str, int] = {char_a.name: 0, char_b.name: 0}

        # --- Initiative Phase ---
        # Ability 6: extra unkept die on initiative
        # Matsu SA: always rolls 10 dice for initiative
        matsu_extra_a = max(0, 9 - char_a.rings.void.value) if char_a.school == "Matsu Bushi" else 0
        matsu_extra_b = max(0, 9 - char_b.rings.void.value) if char_b.school == "Matsu Bushi" else 0
        init_a = roll_initiative(char_a, extra_unkept=char_a.ability_rank(6) + matsu_extra_a)
        init_b = roll_initiative(char_b, extra_unkept=char_b.ability_rank(6) + matsu_extra_b)

        actions_remaining: dict[str, list[int]] = {
            char_a.name: sorted(init_a.dice_kept),
            char_b.name: sorted(init_b.dice_kept),
        }

        init_a.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)
        log.add_action(init_a)
        init_b.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)
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
                dan_points=dan_points,
                temp_void=temp_void,
                matsu_bonuses=matsu_bonuses,
                lunge_target_bonus=lunge_target_bonus,
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
    dan_points: dict[str, int] | None = None,
    temp_void: dict[str, int] | None = None,
    matsu_bonuses: dict[str, list[int]] | None = None,
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
            temp_void_points=temp_void.get(name, 0) if temp_void else 0,
            dan_points=dan_points.get(name, 0) if dan_points else 0,
            matsu_bonuses=list(matsu_bonuses.get(name, [])) if matsu_bonuses else [],
        )
    return result


def _is_mortally_wounded(log: CombatLog, name: str) -> bool:
    """Check if a combatant is mortally wounded."""
    return log.wounds[name].is_mortally_wounded


def _apply_ability5_reroll(
    character: Character,
    all_dice: list[int],
    kept_count: int,
    description_suffix: str = "",
) -> tuple[list[int], list[int], int, str]:
    """Apply ability 5 free crippled reroll of 10s (NOT for initiative).

    Args:
        character: Character with potential ability 5.
        all_dice: All dice from the roll.
        kept_count: Number of dice to keep.
        description_suffix: Accumulated annotation text.

    Returns:
        Tuple of (all_dice, kept_dice, total, description_suffix).
    """
    rank = character.ability_rank(5)
    if rank > 0 and any(d == 10 for d in all_dice):
        all_dice, kept_dice, total = reroll_tens(all_dice, kept_count, max_reroll=rank)
        description_suffix += f" (wave man: free rerolled {rank} ten(s))"
        return all_dice, kept_dice, total, description_suffix
    kept_dice = sorted(all_dice, reverse=True)[:kept_count]
    total = sum(kept_dice)
    return all_dice, kept_dice, total, description_suffix


def _apply_ability4_rounding(total: int, rank: int) -> tuple[int, str]:
    """Apply ability 4 damage rounding.

    Args:
        total: Damage total.
        rank: Ability 4 rank (1 or 2).

    Returns:
        Tuple of (new_total, annotation).
    """
    original = total
    for _ in range(rank):
        if total % 5 == 0:
            total += 3
        else:
            total = math.ceil(total / 5) * 5
    annotation = f" (wave man: damage rounded {original} → {total})"
    return total, annotation


def _try_phase_shift_parry(
    phase: int,
    defender_name: str,
    actions_remaining: dict[str, list[int]],
    dan_points: dict[str, int],
    serious_wounds: int,
    earth_ring: int,
) -> tuple[bool, int, int]:
    """Try to phase-shift a die to enable a parry using 3rd Dan points.

    Args:
        phase: Current combat phase.
        defender_name: Defender's name key.
        actions_remaining: All characters' remaining action dice.
        dan_points: All characters' current dan points.
        serious_wounds: Defender's current serious wounds.
        earth_ring: Defender's Earth ring.

    Returns:
        Tuple of (can_shift, shift_cost, die_phase). If can_shift is False,
        the other values are 0.
    """
    available = dan_points.get(defender_name, 0)
    if available <= 0:
        return False, 0, 0

    # Find the cheapest die above the current phase
    dice_above = sorted(d for d in actions_remaining.get(defender_name, []) if d > phase)
    if not dice_above:
        return False, 0, 0

    best_die = dice_above[0]
    cost = best_die - phase

    # Spending threshold: willing to spend up to 4 pts normally, up to 6 if near cripple
    wounds_to_cripple = earth_ring - serious_wounds
    max_spend = 6 if wounds_to_cripple <= 1 else 4

    if cost > available or cost > max_spend:
        return False, 0, 0

    return True, cost, best_die


def _compute_dan_roll_bonus(
    current_total: int,
    tn: int,
    dan_points_available: int,
    is_parry: bool = False,
) -> int:
    """Compute how many 3rd Dan points to spend for a post-roll +2/point bonus.

    Only spends if the bonus would make the roll succeed. Uses a threshold
    to avoid overspending on marginal rolls.

    Args:
        current_total: Current roll total (including other bonuses).
        tn: Target number to meet or exceed.
        dan_points_available: Remaining dan points.
        is_parry: If True, use a more generous threshold.

    Returns:
        Number of points to spend (0 if not worth it).
    """
    if dan_points_available <= 0:
        return 0

    deficit = tn - current_total
    if deficit <= 0:
        return 0

    points_needed = math.ceil(deficit / 2)

    # Threshold: ceil(available/2) + 2 for attack, + 3 for parry
    threshold = math.ceil(dan_points_available / 2) + (3 if is_parry else 2)

    if points_needed > threshold or points_needed > dan_points_available:
        return 0

    return points_needed


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
    dan_points: dict[str, int] | None = None,
    temp_void: dict[str, int] | None = None,
    matsu_bonuses: dict[str, list[int]] | None = None,
    lunge_target_bonus: dict[str, int] | None = None,
) -> None:
    """Resolve a single attack action in a phase."""
    if dan_points is None:
        dan_points = {attacker_name: 0, defender_name: 0}
    if temp_void is None:
        temp_void = {attacker_name: 0, defender_name: 0}
    if matsu_bonuses is None:
        matsu_bonuses = {attacker_name: [], defender_name: []}
    if lunge_target_bonus is None:
        lunge_target_bonus = {attacker_name: 0, defender_name: 0}

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

    # Mirumoto school technique detection
    atk_is_mirumoto = attacker.school == "Mirumoto Bushi"
    def_is_mirumoto = defender.school == "Mirumoto Bushi"
    atk_dan = attacker.dan if atk_is_mirumoto else 0
    def_dan = defender.dan if def_is_mirumoto else 0

    # Matsu school technique detection
    atk_is_matsu = attacker.school == "Matsu Bushi"
    def_is_matsu = defender.school == "Matsu Bushi"
    atk_dan_matsu = attacker.dan if atk_is_matsu else 0
    def_dan_matsu = defender.dan if def_is_matsu else 0

    # Calculate TN and roll attack
    tn = calculate_attack_tn(def_parry_rank)
    base_tn = tn  # Save for double attack extra dice calculation

    # Lunge target bonus: opponent's attack gets easier TN
    lunge_tn_reduction = lunge_target_bonus.get(attacker_name, 0)
    if lunge_tn_reduction > 0:
        tn = max(5, tn - lunge_tn_reduction)
        lunge_target_bonus[attacker_name] = 0

    # --- Double Attack / Lunge decision ---
    is_double_attack = False
    is_lunge = False
    is_near_miss_da = False
    da_void_spend = 0
    lunge_void_spend = 0
    da_skill = attacker.get_skill("Double Attack")
    da_rank = da_skill.rank if da_skill else 0
    lunge_skill = attacker.get_skill("Lunge")
    lunge_rank = lunge_skill.rank if lunge_skill else 0

    if atk_is_matsu and not attacker_crippled:
        # Matsu always uses Lunge or Double Attack
        attack_choice, matsu_void = _matsu_attack_choice(
            lunge_rank, da_rank, atk_rank, attacker.rings.fire.value,
            def_parry_rank, _total_void(void_points, temp_void, attacker_name),
            attacker.rings.lowest(), atk_dan_matsu, attacker_crippled,
        )
        if attack_choice == "double_attack":
            is_double_attack = True
            da_void_spend = matsu_void
        else:
            is_lunge = True
            lunge_void_spend = matsu_void
    elif atk_is_matsu and attacker_crippled:
        # Crippled Matsu always lunges
        is_lunge = True
    elif atk_is_mirumoto and da_rank > 0 and not attacker_crippled:
        is_double_attack, da_void_spend = _should_use_double_attack(
            da_rank, atk_rank, attacker.rings.fire.value,
            def_parry_rank, _total_void(void_points, temp_void, attacker_name),
            attacker.rings.lowest(), atk_dan, attacker_crippled,
        )

    if is_double_attack:
        tn += 20

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
    # First Dan: +1 rolled die on attack (Mirumoto)
    effective_atk_rank = atk_rank
    if atk_is_mirumoto and atk_dan >= 1:
        effective_atk_rank += 1

    if is_lunge:
        # Lunge attack: uses Lunge knack + Fire
        lng_rolled = lunge_rank + attacker.rings.fire.value
        lng_kept = attacker.rings.fire.value

        # Void spending on lunge
        lng_void_label = ""
        actual_lunge_void = 0
        if lunge_void_spend > 0 and _total_void(void_points, temp_void, attacker_name) >= lunge_void_spend:
            lng_from_temp, lng_from_reg = _spend_void(void_points, temp_void, attacker_name, lunge_void_spend)
            lng_void_label = _void_spent_label(lng_from_temp, lng_from_reg)
            lng_rolled += lunge_void_spend
            lng_kept += lunge_void_spend
            actual_lunge_void = lunge_void_spend
            # Matsu 3rd Dan: void spending generates wound check bonus
            if atk_is_matsu and atk_dan_matsu >= 3:
                bonus_value = 3 * atk_rank
                for _ in range(actual_lunge_void):
                    matsu_bonuses[attacker_name].append(bonus_value)

        all_dice, kept_dice, total = roll_and_keep(lng_rolled, lng_kept, explode=attack_explode)
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
            description=f"{attacker_name} lunges: {_format_pool_with_overflow(lng_rolled, lng_kept)} vs TN {tn}{void_note}",
            dice_pool=_format_pool_with_overflow(lng_rolled, lng_kept),
        )
        # Lunge: opponent's next attack gets -5 TN
        lunge_target_bonus[defender_name] = 5

    elif is_double_attack:
        # Double attack uses Double Attack skill + Fire (not Attack skill)
        da_rolled = da_rank + attacker.rings.fire.value
        # First Dan bonus: Mirumoto or Matsu
        if (atk_is_mirumoto and atk_dan >= 1) or (atk_is_matsu and atk_dan_matsu >= 1):
            da_rolled += 1
        da_kept = attacker.rings.fire.value

        # Apply void spending on double attack
        da_void_label = ""
        actual_da_void = 0
        if da_void_spend > 0 and _total_void(void_points, temp_void, attacker_name) >= da_void_spend:
            da_from_temp, da_from_reg = _spend_void(void_points, temp_void, attacker_name, da_void_spend)
            da_void_label = _void_spent_label(da_from_temp, da_from_reg)
            da_rolled += da_void_spend
            da_kept += da_void_spend
            actual_da_void = da_void_spend
            # Matsu 3rd Dan: void spending generates wound check bonus
            if atk_is_matsu and atk_dan_matsu >= 3:
                bonus_value = 3 * atk_rank
                for _ in range(actual_da_void):
                    matsu_bonuses[attacker_name].append(bonus_value)

        all_dice, kept_dice, total = roll_and_keep(da_rolled, da_kept, explode=attack_explode)
        # Fifth Dan Mirumoto: +10 per void spent
        fifth_dan_combat_bonus = 0
        if atk_is_mirumoto and atk_dan >= 5 and da_void_spend > 0:
            fifth_dan_combat_bonus = 10 * da_void_spend
            total += fifth_dan_combat_bonus

        success = total >= tn

        # Matsu 4th Dan: near-miss double attack still hits
        if atk_is_matsu and atk_dan_matsu >= 4 and not success and total >= tn - 20:
            success = True
            is_near_miss_da = True

        void_note = f" ({da_void_label})" if da_void_label else ""
        fifth_note = f" (mirumoto: +{fifth_dan_combat_bonus} 5th Dan)" if fifth_dan_combat_bonus > 0 else ""
        near_miss_note = " (matsu 4th Dan: near-miss hit, base damage only)" if is_near_miss_da else ""
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
            description=f"{attacker_name} double attacks: {_format_pool_with_overflow(da_rolled, da_kept)} vs TN {tn}{void_note}{fifth_note}{near_miss_note}",
            dice_pool=_format_pool_with_overflow(da_rolled, da_kept),
        )
    else:
        # Normal attack: void spending on combat roll (Mirumoto)
        atk_void_spend = 0
        atk_void_label = ""
        if atk_is_mirumoto and not attacker_crippled:
            fifth_dan_bonus = 10 if atk_dan >= 5 else 0
            atk_void_spend = _should_spend_void_on_combat_roll(
                effective_atk_rank + attacker.rings.fire.value,
                attacker.rings.fire.value,
                tn,
                _total_void(void_points, temp_void, attacker_name),
                attacker.rings.lowest(),
                fifth_dan_bonus=fifth_dan_bonus,
            )
            if atk_void_spend > 0 and _total_void(void_points, temp_void, attacker_name) >= atk_void_spend:
                atk_from_temp, atk_from_reg = _spend_void(void_points, temp_void, attacker_name, atk_void_spend)
                atk_void_label = _void_spent_label(atk_from_temp, atk_from_reg)

        if atk_void_spend > 0:
            # Inline roll_and_keep so void adds +1k1 (not +1k0 via roll_attack)
            atk_rolled = effective_atk_rank + attacker.rings.fire.value + atk_void_spend
            atk_kept = attacker.rings.fire.value + atk_void_spend
            all_dice, kept_dice, total = roll_and_keep(atk_rolled, atk_kept, explode=attack_explode)

            # Fifth Dan: +10 per void spent on attack
            fifth_dan_combat_bonus = 0
            if atk_dan >= 5:
                fifth_dan_combat_bonus = 10 * atk_void_spend
                total += fifth_dan_combat_bonus

            success = total >= tn
            void_note = f" ({atk_void_label})"
            fifth_note = f" (mirumoto: +{fifth_dan_combat_bonus} 5th Dan)" if fifth_dan_combat_bonus > 0 else ""
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
                description=f"{attacker_name} attacks: {_format_pool_with_overflow(atk_rolled, atk_kept)} vs TN {tn}{void_note}{fifth_note}",
                dice_pool=_format_pool_with_overflow(atk_rolled, atk_kept),
            )
        else:
            attack_action = roll_attack(attacker, effective_atk_rank, RingName.FIRE, tn, explode=attack_explode)
            attack_action.phase = phase
            attack_action.target = defender_name

    # Ability 5: Free crippled reroll on attack (before void reroll)
    if attacker_crippled and not attack_action.success:
        new_all, new_kept, new_total, note = _apply_ability5_reroll(
            attacker, attack_action.dice_rolled, len(attack_action.dice_kept),
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
        if has_tens and _total_void(void_points, temp_void, attacker_name) > 0 and max_void_spend > 0:
            new_all, new_kept, new_total = reroll_tens(
                attack_action.dice_rolled, len(attack_action.dice_kept),
            )
            cr_from_temp, cr_from_reg = _spend_void(void_points, temp_void, attacker_name, 1)
            cr_label = "temp void" if cr_from_temp else "void"
            attack_action.dice_rolled = new_all
            attack_action.dice_kept = new_kept
            attack_action.total = new_total
            attack_action.success = new_total >= tn
            attack_action.description += f" ({cr_label}: rerolled 10s)"
            # Matsu 3rd Dan: crippled reroll void spending generates bonus
            if atk_is_matsu and atk_dan_matsu >= 3:
                bonus_value = 3 * atk_rank
                matsu_bonuses[attacker_name].append(bonus_value)

    # Ability 1: Attack reroll — if attack misses, add 5 * rank
    parry_auto_succeeds = False
    ab1_rank = attacker.ability_rank(1)
    if not attack_action.success and ab1_rank > 0:
        boosted_total = attack_action.total + 5 * ab1_rank
        if boosted_total >= tn:
            attack_action.total = boosted_total
            attack_action.success = True
            parry_auto_succeeds = True
            attack_action.description += f" (wave man: +{5 * ab1_rank} free raise)"

    # 3rd Dan Mirumoto: post-roll +2 per point on attack
    if atk_is_mirumoto and atk_dan >= 3 and not attack_action.success:
        dan_bonus_pts = _compute_dan_roll_bonus(
            attack_action.total, tn, dan_points.get(attacker_name, 0),
        )
        if dan_bonus_pts > 0:
            attack_action.total += dan_bonus_pts * 2
            attack_action.success = attack_action.total >= tn
            dan_points[attacker_name] -= dan_bonus_pts
            attack_action.description += f" (3rd dan: +{dan_bonus_pts * 2} bonus, {dan_bonus_pts} pts)"

    attack_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)
    log.add_action(attack_action)

    # Attack missed — dice already consumed by pre-declaration (if any),
    # reflected in attack_action.status_after snapshot.
    if not attack_action.success:
        return

    # Annotate attack hit with expected damage pool (assuming no parry)
    # For double attack, use base_tn (before +20) for extra dice calculation
    extra_tn = base_tn if is_double_attack else tn
    no_parry_extra = max(0, (attack_action.total - extra_tn) // 5)
    # Account for ability 3 weapon boost and lunge bonus in the preview
    preview_weapon_rolled = weapon.rolled
    ab3_rank = attacker.ability_rank(3)
    if ab3_rank > 0 and (weapon.rolled < 4 or (weapon.rolled >= 4 and weapon.kept < 2)):
        preview_weapon_rolled = min(weapon.rolled + ab3_rank, 4)
    lunge_preview_bonus = 1 if is_lunge else 0
    raw_rolled = preview_weapon_rolled + attacker.rings.fire.value + no_parry_extra + lunge_preview_bonus
    pool_display = _format_pool_with_overflow(raw_rolled, weapon.kept)
    da_wound_note = " plus 1 automatic serious wound" if is_double_attack else ""
    attack_action.description += f" — damage will be {pool_display}{da_wound_note}"

    # --- Defender attempts parry ---
    parry_attempted = False
    parry_succeeded = False
    is_interrupt = False

    # Ability 1: If parry auto succeeds, log it and skip actual parry roll
    if parry_auto_succeeds:
        parry_attempted = True
        parry_succeeded = True
        # Consume the parry die if defender had one in this phase
        if has_action_in_phase and not predeclared:
            if phase in actions_remaining[defender_name]:
                actions_remaining[defender_name].remove(phase)
        parry_action = CombatAction(
            phase=phase,
            actor=defender_name,
            action_type=ActionType.PARRY,
            target=attacker_name,
            dice_rolled=[],
            dice_kept=[],
            total=0,
            tn=attack_action.total,
            success=True,
            description=f"{defender_name} parries: auto-success (wave man free raise)",
            dice_pool="",
        )
        # Mirumoto special ability: temp void on parry (even auto-success)
        if def_is_mirumoto:
            temp_void[defender_name] = temp_void.get(defender_name, 0) + 1
            parry_action.description += " (mirumoto SA: +1 temp void)"
        parry_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)
        log.add_action(parry_action)
        return

    # Ability 2: Parry TN increase
    ab2_bonus = 5 * attacker.ability_rank(2)

    # Determine if defender can parry
    can_parry = False
    is_phase_shift = False
    phase_shift_die = 0
    phase_shift_cost = 0
    if has_action_in_phase and def_parry_rank > 0:
        can_parry = True
    elif def_is_mirumoto and def_dan >= 3 and def_parry_rank > 0 and not has_action_in_phase:
        # 3rd Dan phase shift: spend points to shift a die to this phase
        can_shift, shift_cost, shift_die = _try_phase_shift_parry(
            phase, defender_name, actions_remaining, dan_points,
            log.wounds[defender_name].serious_wounds,
            log.wounds[defender_name].earth_ring,
        )
        if can_shift:
            can_parry = True
            is_phase_shift = True
            phase_shift_die = shift_die
            phase_shift_cost = shift_cost
    if not can_parry and (
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
        if is_phase_shift:
            # Phase shift: consume the shifted die and spend dan points
            actions_remaining[defender_name].remove(phase_shift_die)
            dan_points[defender_name] -= phase_shift_cost
        elif is_interrupt:
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

        # First Dan Mirumoto defender: +1 rolled die on parry
        if def_is_mirumoto and def_dan >= 1:
            parry_rolled += 1

        # Feature 1: Crippled disables exploding 10s on parry rolls
        defender_crippled = log.wounds[defender_name].is_crippled
        parry_explode = not defender_crippled

        # Feature 4: Pre-declared parry gets +5 bonus (added to total)
        # Interrupts are reactive and never get the pre-declare bonus
        parry_tn = attack_action.total + ab2_bonus
        parry_bonus = 5 if (predeclared and not is_interrupt) else 0
        parry_bonus_note = " (pre-declared, +5 bonus)" if (predeclared and not is_interrupt) else ""

        # Second Dan Mirumoto defender: free raise (+5) on parry
        if def_is_mirumoto and def_dan >= 2:
            parry_bonus += 5
            parry_bonus_note += " (mirumoto: free raise +5)"

        # Mirumoto defender: void spending on parry
        def_parry_void_spend = 0
        def_parry_void_label = ""
        if def_is_mirumoto and not defender_crippled:
            fifth_dan_bonus = 10 if def_dan >= 5 else 0
            def_parry_void_spend = _should_spend_void_on_combat_roll(
                parry_rolled, parry_kept, parry_tn - parry_bonus,
                _total_void(void_points, temp_void, defender_name),
                defender.rings.lowest(),
                fifth_dan_bonus=fifth_dan_bonus,
            )
            if def_parry_void_spend > 0 and _total_void(void_points, temp_void, defender_name) >= def_parry_void_spend:
                pv_from_temp, pv_from_reg = _spend_void(void_points, temp_void, defender_name, def_parry_void_spend)
                def_parry_void_label = _void_spent_label(pv_from_temp, pv_from_reg)
                parry_rolled += def_parry_void_spend
                parry_kept += def_parry_void_spend

        all_dice, kept_dice, parry_total = roll_and_keep(
            parry_rolled, parry_kept, explode=parry_explode,
        )

        # Fifth Dan Mirumoto defender: +10 per void on parry
        if def_is_mirumoto and def_dan >= 5 and def_parry_void_spend > 0:
            parry_total += 10 * def_parry_void_spend
            parry_bonus_note += f" (mirumoto: +{10 * def_parry_void_spend} 5th Dan)"
        elif def_parry_void_label:
            parry_bonus_note += f" ({def_parry_void_label})"

        # Ability 5: Free crippled reroll on parry
        if defender_crippled:
            all_dice, kept_dice, parry_total, ab5_note = _apply_ability5_reroll(
                defender, all_dice, parry_kept,
            )
            parry_bonus_note += ab5_note

        # Feature 2: Crippled void reroll on parry
        if defender_crippled and (parry_total + parry_bonus) < parry_tn:
            has_tens = any(d == 10 for d in all_dice)
            max_void_spend = defender.rings.lowest()
            if has_tens and _total_void(void_points, temp_void, defender_name) > 0 and max_void_spend > 0:
                all_dice, kept_dice, parry_total = reroll_tens(all_dice, parry_kept)
                pcr_from_temp, pcr_from_reg = _spend_void(void_points, temp_void, defender_name, 1)
                pcr_label = "temp void" if pcr_from_temp else "void"
                parry_bonus_note += f" ({pcr_label}: rerolled 10s)"
                # Matsu 3rd Dan: crippled parry reroll void spending generates bonus
                if def_is_matsu and def_dan_matsu >= 3:
                    def_atk_s = defender.get_skill("Attack")
                    def_atk_r = def_atk_s.rank if def_atk_s else 0
                    bonus_value = 3 * def_atk_r
                    matsu_bonuses[defender_name].append(bonus_value)

        effective_parry_total = parry_total + parry_bonus

        # 3rd Dan Mirumoto: post-roll +2 per point on parry
        if def_is_mirumoto and def_dan >= 3 and effective_parry_total < parry_tn:
            dan_parry_pts = _compute_dan_roll_bonus(
                effective_parry_total, parry_tn, dan_points.get(defender_name, 0),
                is_parry=True,
            )
            if dan_parry_pts > 0:
                effective_parry_total += dan_parry_pts * 2
                dan_points[defender_name] -= dan_parry_pts
                parry_bonus_note += f" (3rd dan: +{dan_parry_pts * 2} bonus, {dan_parry_pts} pts)"

        parry_succeeded = effective_parry_total >= parry_tn

        action_type = ActionType.INTERRUPT if is_interrupt else ActionType.PARRY
        interrupt_note = " (interrupt)" if is_interrupt else ""
        phase_shift_note = f" (3rd dan: shifted from phase {phase_shift_die}, {phase_shift_cost} pts)" if is_phase_shift else ""
        ab2_note = f" (wave man: parry TN +{ab2_bonus})" if ab2_bonus > 0 else ""
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
                f"vs TN {parry_tn}{ab2_note}{parry_bonus_note}{phase_shift_note}{interrupt_note}"
            ),
            dice_pool=parry_pool,
        )
        # Mirumoto special ability: temp void on parry attempt (success or fail)
        if def_is_mirumoto:
            temp_void[defender_name] = temp_void.get(defender_name, 0) + 1
            parry_action.description += " (mirumoto SA: +1 temp void)"
        parry_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)
        log.add_action(parry_action)

        if parry_succeeded:
            return

        # Failed parry: reduce extra dice by defender's parry rank (not all)
        # Fourth Dan Mirumoto attacker: subtract only half parry rank
        if not parry_succeeded:
            all_extra = max(0, (attack_action.total - (base_tn if is_double_attack else tn)) // 5)
            parry_reduction = def_parry_rank
            if atk_is_mirumoto and atk_dan >= 4:
                parry_reduction = def_parry_rank // 2
            if all_extra > 0:
                reduced_extra = max(0, all_extra - parry_reduction)
                full_rolled = preview_weapon_rolled + attacker.rings.fire.value + all_extra + lunge_preview_bonus
                reduced_rolled = preview_weapon_rolled + attacker.rings.fire.value + reduced_extra + lunge_preview_bonus
                # DA failed parry: serious wound converts to +2 rolled dice
                da_conversion_dice = 2 if is_double_attack and not is_near_miss_da else 0
                reduced_rolled += da_conversion_dice
                full_raw = f"{full_rolled}k{weapon.kept}"
                reduced_display = _format_pool_with_overflow(reduced_rolled, weapon.kept)
                da_prevent_note = "automatic serious wound is converted to +2 rolled dice, and " if is_double_attack else ""
                parry_action.description += f" — {da_prevent_note}{full_raw} is reduced to {reduced_display}"

    # --- Roll damage ---
    # For double attack, extra dice use base_tn (before +20)
    extra_tn_for_dice = base_tn if is_double_attack else tn
    all_extra_dice = max(0, (attack_action.total - extra_tn_for_dice) // 5)
    if parry_attempted:
        # Fourth Dan Mirumoto attacker: subtract only half parry rank
        parry_reduction = def_parry_rank
        if atk_is_mirumoto and atk_dan >= 4:
            parry_reduction = def_parry_rank // 2
        extra_dice = max(0, all_extra_dice - parry_reduction)
    else:
        extra_dice = all_extra_dice

    # Ability 9: Failed parry bonus — recover some removed extra dice
    if parry_attempted and not parry_succeeded:
        ab9_rank = attacker.ability_rank(9)
        if ab9_rank > 0:
            parry_red = def_parry_rank
            if atk_is_mirumoto and atk_dan >= 4:
                parry_red = def_parry_rank // 2
            removed = min(all_extra_dice, parry_red)
            bonus_back = min(removed, 2 * ab9_rank)
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

    # Ability 3: Weapon damage boost — add rolled dice if weapon < 4k2
    boosted_rolled = weapon.rolled
    ab3_rank = attacker.ability_rank(3)
    if ab3_rank > 0:
        if weapon.rolled < 4 or (weapon.rolled >= 4 and weapon.kept < 2):
            boosted_rolled = min(weapon.rolled + ab3_rank, 4)

    # Lunge: +1 rolled damage die
    lunge_damage_bonus = 1 if is_lunge else 0

    damage_action = roll_damage(attacker, boosted_rolled, weapon.kept, extra_dice + da_extra_rolled + lunge_damage_bonus)
    damage_action.phase = phase
    damage_action.target = defender_name
    # Show overflow conversion in damage dice pool
    dmg_rolled = boosted_rolled + attacker.rings.fire.value + extra_dice + da_extra_rolled + lunge_damage_bonus
    damage_action.dice_pool = _format_pool_with_overflow(dmg_rolled, weapon.kept)

    # Ability 4: Damage rounding
    ab4_rank = attacker.ability_rank(4)
    damage_total = damage_action.total
    ab4_note = ""
    if ab4_rank > 0:
        damage_total, ab4_note = _apply_ability4_rounding(damage_total, ab4_rank)
        damage_action.total = damage_total
        damage_action.description += ab4_note

    # Ability 8: Excessive damage reduction (defensive)
    ab8_rank = defender.ability_rank(8)
    had_extra_dice = all_extra_dice > 0 if not parry_attempted else extra_dice > 0
    if ab8_rank > 0 and had_extra_dice:
        reduction = 5 * ab8_rank
        damage_action.total = max(0, damage_action.total - reduction)
        damage_action.description += f" (wave man: -{reduction} damage reduction)"

    log.add_action(damage_action)

    # Apply damage as light wounds
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += damage_action.total

    # Double attack: inflict extra serious wound directly (no parry case)
    if da_serious_wound > 0:
        wound_tracker.serious_wounds += da_serious_wound
        damage_action.description += f" (double attack: +{da_serious_wound} serious wound)"

    # Snapshot after damage is applied
    damage_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)

    # --- Wound check ---
    water_value = defender.rings.water.value

    # Matsu 3rd Dan: check if stored matsu bonuses can pass the wound check before deciding void
    wc_tn_estimate = wound_tracker.light_wounds
    matsu_bonus_note = ""
    skip_void_for_matsu = False
    if def_is_matsu and def_dan_matsu >= 3 and matsu_bonuses[defender_name]:
        # Check if any stored bonus can plausibly help — if so, save void
        for bonus in matsu_bonuses[defender_name]:
            if bonus >= wc_tn_estimate * 0.3:
                skip_void_for_matsu = True
                break

    # Decide how many void points to spend
    max_spend = defender.rings.lowest()
    if skip_void_for_matsu:
        void_spend = 0
    else:
        void_spend = _should_spend_void_on_wound_check(
            water_value, wound_tracker.light_wounds, _total_void(void_points, temp_void, defender_name),
            max_spend=max_spend,
        )
    wc_from_temp, wc_from_reg = _spend_void(void_points, temp_void, defender_name, void_spend)
    wc_void_label = _void_spent_label(wc_from_temp, wc_from_reg)

    # Matsu 3rd Dan: void spending on wound check generates bonus
    if def_is_matsu and def_dan_matsu >= 3 and void_spend > 0:
        def_atk_skill = defender.get_skill("Attack")
        def_atk_rank = def_atk_skill.rank if def_atk_skill else 0
        bonus_value = 3 * def_atk_rank
        for _ in range(void_spend):
            matsu_bonuses[defender_name].append(bonus_value)
        matsu_bonus_note += f" (matsu 3rd Dan: +{bonus_value} wound check bonus stored)"

    # Ability 7: Extra unkept dice on wound check
    ab7_extra = 2 * defender.ability_rank(7)
    # Matsu 1st Dan: +1 unkept die on wound check
    matsu_wc_extra = 1 if def_is_matsu and def_dan_matsu >= 1 else 0
    # Ability 10: Wound check TN increase
    ab10_bonus = 5 * attacker.ability_rank(10)

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=ab7_extra + matsu_wc_extra, tn_bonus=ab10_bonus,
    )

    # Ability 5: Free crippled reroll on wound check
    if not passed and log.wounds[defender_name].is_crippled:
        wc_all_dice, wc_kept_dice, wc_total, _ = _apply_ability5_reroll(
            defender, wc_all_dice, water_value + void_spend,
        )
        effective_tn = wound_tracker.light_wounds + ab10_bonus
        if wc_total >= effective_tn:
            passed = True

    # Matsu 3rd Dan: apply stored bonuses to failed wound check
    if def_is_matsu and def_dan_matsu >= 3 and not passed and matsu_bonuses[defender_name]:
        effective_tn = wound_tracker.light_wounds + ab10_bonus
        for i, bonus in enumerate(matsu_bonuses[defender_name]):
            if wc_total + bonus >= effective_tn:
                wc_total += bonus
                matsu_bonuses[defender_name].pop(i)
                passed = True
                matsu_bonus_note += f" (matsu 3rd Dan: applied +{bonus} bonus)"
                break

    void_note = f" ({wc_void_label})" if wc_void_label else ""

    # Record the TN before any conversion modifies light_wounds
    wc_tn = wound_tracker.light_wounds + ab10_bonus

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
        else:
            convert_note = f" — keeping {wound_tracker.light_wounds} light wounds"

    wc_rolled = water_value + 1 + ab7_extra + matsu_wc_extra
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
            f"(rolled {wc_total}){void_note}{matsu_bonus_note}{convert_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    # If wound check failed, light wounds reset to 0 (handled in make_wound_check via serious)
    if not passed:
        # Matsu 5th Dan: light wounds reset to 15 instead of 0
        reset_value = 15 if atk_is_matsu and atk_dan_matsu >= 5 else 0
        wound_tracker.light_wounds = reset_value
        if reset_value > 0:
            wc_action.description += " (matsu 5th Dan: light wounds reset to 15)"

    # Snapshot after wound check (reflects serious wound promotion if failed)
    wc_action.status_after = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void, matsu_bonuses)
