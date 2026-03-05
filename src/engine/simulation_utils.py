"""Pure utility functions extracted from simulation.py.

No school-specific logic here -- only generic combat math and formatting.
"""

from __future__ import annotations

import json
import math
import pathlib
import random

from src.models.character import Character

# ---------------------------------------------------------------------------
# Precomputed expected-serious-wounds lookup table
# ---------------------------------------------------------------------------
# Generated offline by Monte Carlo (10 000 sims per entry) for all practical
# (rolled, kept, tn) combinations.  Loaded once at import time — every lookup
# is a single dict access with no simulation at runtime.

_TABLE_PATH = pathlib.Path(__file__).with_name("expected_sw_table.json")
_SW_TABLE: dict[str, float] = {}

if _TABLE_PATH.exists():
    with _TABLE_PATH.open() as _f:
        _SW_TABLE = json.load(_f)


def estimate_roll(rolled: int, kept: int) -> float:
    """Estimate expected total for an XkY dice pool using order statistics.

    Accounts for overflow rules (excess rolled->kept, excess kept->+2 bonus).
    Uses the continuous uniform approximation for expected value of the top Y
    out of X dice on [1, 10].
    """
    eff_rolled = rolled
    eff_kept = kept
    bonus = 0
    if eff_rolled > 10:
        eff_kept += eff_rolled - 10
        eff_rolled = 10
    if eff_kept > 10:
        bonus = (eff_kept - 10) * 2
        eff_kept = 10
    eff_kept = min(eff_kept, eff_rolled)
    if eff_rolled <= 0 or eff_kept <= 0:
        return float(bonus)
    return 10.0 * eff_kept * (2 * eff_rolled - eff_kept + 1) / (2.0 * (eff_rolled + 1)) + bonus


def _expected_serious_wounds(rolled: int, kept: int, tn: int) -> float:
    """Look up expected serious wounds from the precomputed table.

    Falls back to 0.0 for entries not in the table (meaning the wound check
    passes virtually every time at those parameters).
    """
    effective_kept = min(kept, rolled)
    if rolled <= 0 or effective_kept <= 0 or tn <= 0:
        return 0.0
    key = f"{rolled},{effective_kept},{tn}"
    return _SW_TABLE.get(key, 0.0)


def should_spend_void_on_wound_check(
    water_ring: int,
    light_wounds: int,
    void_available: int,
    max_spend: int,
    threshold: float = 0.25,
    extra_rolled: int = 0,
    tn_bonus: int = 0,
) -> int:
    """Decide how many void points to spend on a wound check via Monte Carlo.

    Uses _expected_serious_wounds (cached) so repeated calls with similar
    dice pools are fast.

    Args:
        water_ring: The character's Water ring value.
        light_wounds: Current light wound total (= base wound check TN).
        void_available: Remaining void points.
        max_spend: Maximum void spendable on a single action (lowest ring).
        threshold: Minimum expected serious-wounds-saved per void point spent.
        extra_rolled: Extra unkept dice on wound check (e.g. ability 7, Matsu 1st Dan).
        tn_bonus: Flat bonus added to TN (e.g. ability 10 wave man).

    Returns:
        Number of void points to spend (0 to min(void_available, max_spend)).
    """
    if void_available <= 0 or light_wounds <= 0:
        return 0

    limit = min(void_available, max_spend)
    tn = light_wounds + tn_bonus
    rolled = water_ring + 1 + extra_rolled

    baseline = _expected_serious_wounds(rolled, water_ring, tn)
    best_spend = 0
    best_improvement = 0.0

    for spend in range(1, limit + 1):
        expected = _expected_serious_wounds(rolled, water_ring + spend, tn)
        improvement = baseline - expected
        if improvement >= threshold and improvement > best_improvement:
            best_improvement = improvement
            best_spend = spend

    return best_spend


def should_convert_light_to_serious(
    light_wounds: int,
    serious_wounds: int,
    earth_ring: int,
    water_ring: int = 2,
    shinjo_wc_bonus_pool: int = 0,
    lw_severity_divisor: int = 1,
    mortal_wound_threshold: int | None = None,
    lw_conversion: float = 0.8,
) -> bool:
    """Decide whether to convert light wounds to 1 serious wound on a passed wound check.

    ``lw_severity_divisor`` accounts for abilities that reduce the severity of
    accumulated light wounds (e.g. Bayushi 5th Dan halves LW for serious wound
    calculation on a failed wound check, so passes ``2``).  The threshold is
    multiplied by this divisor so the fighter tolerates proportionally more LW.
    """
    mwt = mortal_wound_threshold if mortal_wound_threshold is not None else 2 * earth_ring
    if serious_wounds + 1 >= mwt:
        return False

    if light_wounds <= 10 * lw_severity_divisor:
        return False

    avg_wc = water_ring * 6.5 + 2
    threshold = max(10, round(avg_wc * lw_conversion))

    would_cripple = serious_wounds + 1 >= earth_ring
    if would_cripple:
        threshold = round(threshold * 1.5)

    threshold += shinjo_wc_bonus_pool
    threshold *= lw_severity_divisor

    return light_wounds > threshold


def should_spend_void_on_combat_roll(
    rolled: int,
    kept: int,
    tn: int,
    void_available: int,
    max_spend: int,
    fifth_dan_bonus: int = 0,
    known_bonus: int = 0,
) -> int:
    """Decide how many void points to spend on an attack or parry roll.

    Each void spent adds 1k1 (about +5.5) plus the fifth_dan_bonus to the roll.
    Only spends if it meaningfully increases the chance of success.
    Reserves at least 1 void point for wound checks.
    """
    if void_available <= 1 or tn <= 0:
        return 0

    usable = min(void_available - 1, max_spend)
    if usable <= 0:
        return 0

    expected = estimate_roll(rolled, kept) + known_bonus
    value_per_void = 5.5 + fifth_dan_bonus

    if expected >= tn:
        return 0

    deficit = tn - expected
    needed = max(1, int(deficit / value_per_void + 0.5))
    return min(needed, usable)


def format_pool_with_overflow(
    rolled: int, kept: int, overflow_bonus: int = 2,
) -> str:
    """Format a dice pool string, showing overflow conversion if applicable."""
    raw = f"{rolled}k{kept}"
    if rolled <= 10:
        return raw
    eff_kept = kept + (rolled - 10)
    eff_rolled = 10
    bonus = 0
    if eff_kept > 10:
        bonus = (eff_kept - 10) * overflow_bonus
        eff_kept = 10
    eff = f"{eff_rolled}k{eff_kept}"
    if bonus:
        eff += f"+{bonus}"
    return f"{raw}, which becomes {eff}"


def damage_pool_str(weapon_rolled: int, weapon_kept: int, fire_ring: int, extra_dice: int) -> str:
    """Format a damage dice pool string."""
    return f"{weapon_rolled + fire_ring + extra_dice}k{weapon_kept}"


def tiebreak_key(
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
    """
    dice = sorted(actions_remaining.get(name, []))
    char: Character = fighters[name]["char"]
    void_ring = char.rings.void.value
    padded = dice + [11] * (10 - len(dice))
    return (phase, tuple(padded), -void_ring, random.random())


def spend_void(
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


def void_spent_label(
    from_temp: int, from_regular: int, from_worldliness: int = 0,
) -> str:
    """Format a human-readable label for void spending."""
    total = from_temp + from_regular + from_worldliness
    if total == 0:
        return ""
    # Collect special source annotations
    annotations: list[str] = []
    if from_temp > 0:
        annotations.append(f"{from_temp} temp")
    if from_worldliness > 0:
        annotations.append(f"{from_worldliness} worldliness")
    if not annotations:
        return f"{total} void spent"
    # All from temp (no worldliness, no regular) — preserve legacy format
    if from_regular == 0 and from_worldliness == 0:
        return f"{total} temp void spent"
    detail = ", ".join(annotations)
    return f"{total} void spent ({detail})"


def total_void(
    void_points: dict[str, int],
    temp_void: dict[str, int],
    name: str,
) -> int:
    """Total available void = regular + temp."""
    return void_points.get(name, 0) + temp_void.get(name, 0)



def apply_ability4_rounding(total: int, rank: int) -> tuple[int, str]:
    """Apply ability 4 damage rounding."""
    original = total
    for _ in range(rank):
        if total % 5 == 0:
            total += 3
        else:
            total = math.ceil(total / 5) * 5
    annotation = f" (wave man: damage rounded {original} -> {total})"
    return total, annotation


def compute_dan_roll_bonus(
    current_total: int,
    tn: int,
    dan_points_available: int,
    is_parry: bool = False,
) -> int:
    """Compute how many 3rd Dan points to spend for a post-roll +2/point bonus."""
    if dan_points_available <= 0:
        return 0

    deficit = tn - current_total
    if deficit <= 0:
        return 0

    points_needed = math.ceil(deficit / 2)

    threshold = math.ceil(dan_points_available / 2) + (3 if is_parry else 2)

    if points_needed > threshold or points_needed > dan_points_available:
        return 0

    return points_needed


def try_phase_shift_parry(
    phase: int,
    defender_name: str,
    actions_remaining: dict[str, list[int]],
    dan_points: dict[str, int],
    serious_wounds: int,
    earth_ring: int,
) -> tuple[bool, int, int]:
    """Try to phase-shift a die to enable a parry using 3rd Dan points."""
    available = dan_points.get(defender_name, 0)
    if available <= 0:
        return False, 0, 0

    dice_above = sorted(d for d in actions_remaining.get(defender_name, []) if d > phase)
    if not dice_above:
        return False, 0, 0

    best_die = dice_above[0]
    cost = best_die - phase

    wounds_to_cripple = earth_ring - serious_wounds
    max_spend = 6 if wounds_to_cripple <= 1 else 4

    if cost > available or cost > max_spend:
        return False, 0, 0

    return True, cost, best_die


def select_shinjo_wc_bonuses(
    deficit: int,
    available: list[int],
) -> list[int]:
    """Select the minimum set of Shinjo 5th Dan bonuses to spend.

    Applied AFTER the wound check roll is seen.  Goals (in priority order):
      1. Minimise the number of serious wounds taken.
      2. Use the smallest pool total that achieves that minimum.
    """
    if deficit <= 0 or not available:
        return []

    current_sw = 1 + (deficit - 1) // 10
    pool = sum(available)

    if pool <= 0:
        return []

    if pool >= deficit:
        best_sw = 0
    else:
        best_sw = 1 + (deficit - pool - 1) // 10

    if best_sw >= current_sw:
        return []

    if best_sw == 0:
        needed = deficit
    else:
        needed = deficit - (10 * best_sw - 1)

    n = len(available)
    best_subset: list[int] = list(available)
    best_cost = pool
    for mask in range(1, 1 << n):
        subset = [available[i] for i in range(n) if mask & (1 << i)]
        total = sum(subset)
        if total >= needed and total < best_cost:
            best_cost = total
            best_subset = subset

    return best_subset


def should_predeclare_parry(
    defender_parry_rank: int,
    air_ring: int,
    attack_tn: int,
    is_crippled: bool,
    *,
    is_kakita: bool = False,
    is_shinjo: bool = False,
    shinjo_dan: int = 0,
    known_bonus: int = 0,
) -> bool:
    """Decide whether to pre-declare a parry for the +5 bonus."""
    if is_kakita:
        return False

    parry_dice = defender_parry_rank + air_ring
    parry_kept = air_ring
    expected_parry = estimate_roll(parry_dice, parry_kept) + known_bonus
    if is_crippled:
        expected_parry *= 0.9

    if is_shinjo and shinjo_dan >= 3:
        return True

    if is_shinjo:
        return expected_parry + 5 >= attack_tn * 0.8

    return expected_parry < attack_tn


def should_reactive_parry(
    defender_parry_rank: int,
    air_ring: int,
    attack_total: int,
    attack_tn: int,
    weapon_rolled: int,
    attacker_fire: int,
    serious_wounds: int,
    earth_ring: int,
    is_crippled: bool,
    *,
    is_kakita: bool = False,
    is_mirumoto: bool = False,
    known_bonus: int = 0,
    parry_threshold: float = 0.6,
) -> bool:
    """Decide whether to parry with an action die already in this phase (1 die cost)."""
    if defender_parry_rank <= 0:
        return False

    extra_dice = max(0, (attack_total - attack_tn) // 5)
    damage_rolled = weapon_rolled + attacker_fire + extra_dice

    if is_mirumoto:
        return True

    if is_kakita:
        return damage_rolled > 12

    wounds_to_cripple = earth_ring - serious_wounds

    if wounds_to_cripple <= 1:
        return True

    if extra_dice >= 1:
        return True

    parry_dice = defender_parry_rank + air_ring
    crippled_mult = 0.9 if is_crippled else 1.0
    expected_parry = (
        estimate_roll(parry_dice, air_ring) * crippled_mult
        + known_bonus
    )
    if expected_parry >= attack_total * parry_threshold:
        return True

    return False


def should_interrupt_parry(
    defender_parry_rank: int,
    air_ring: int,
    attack_total: int,
    attack_tn: int,
    weapon_rolled: int,
    attacker_fire: int,
    dice_remaining: int,
    serious_wounds: int,
    earth_ring: int,
    *,
    is_kakita: bool = False,
    is_mirumoto: bool = False,
    known_bonus: int = 0,
) -> bool:
    """Decide whether to spend 2 action dice for a reactive interrupt parry."""
    if dice_remaining < 2 or defender_parry_rank <= 0:
        return False

    extra_dice = max(0, (attack_total - attack_tn) // 5)
    damage_rolled = weapon_rolled + attacker_fire + extra_dice
    wounds_to_cripple = earth_ring - serious_wounds

    if is_kakita:
        if damage_rolled > 15 and extra_dice >= defender_parry_rank + 3:
            return True
        return False

    if is_mirumoto:
        if damage_rolled > 9:
            return True
        if wounds_to_cripple <= 1 and extra_dice >= 1:
            return True
        return False

    if damage_rolled > 10:
        return True
    if wounds_to_cripple <= 1 and extra_dice >= 2:
        return True
    return False


def shinjo_should_parry_with_two_dice(
    attack_total: int,
    attack_tn: int,
    weapon_rolled: int,
    weapon_kept: int,
    attacker_fire: int,
    defender_serious_wounds: int,
    defender_earth_ring: int,
    defender_light_wounds: int,
    mortal_wound_threshold: int | None = None,
) -> bool:
    """Decide whether a Shinjo with exactly 2 dice should parry or save for a second DA."""
    if mortal_wound_threshold is not None:
        mortal_threshold = mortal_wound_threshold
    else:
        mortal_threshold = 2 * defender_earth_ring
    wounds_to_mortal = mortal_threshold - defender_serious_wounds

    if wounds_to_mortal <= 1:
        return True

    extra_dice = max(0, (attack_total - attack_tn) // 5)
    total_rolled = weapon_rolled + attacker_fire + extra_dice
    expected_damage = estimate_roll(total_rolled, weapon_kept)

    projected_lw = defender_light_wounds + expected_damage

    sw_threshold = defender_earth_ring * 10
    projected_new_sw = int(projected_lw // sw_threshold) if sw_threshold > 0 else 0

    if projected_new_sw >= 2:
        return True

    if projected_new_sw >= 1 and wounds_to_mortal <= 2:
        return True

    return False
