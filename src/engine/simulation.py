"""Combat simulation orchestrator.

Runs a full combat between two characters using the core engine primitives.
"""

from __future__ import annotations

import math
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
    - Excess kept dice beyond 10 become +2 bonuses each.

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
        bonus = (eff_kept - 10) * 2
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
    extra_rolled: int = 0,
    tn_bonus: int = 0,
) -> int:
    """Decide how many void points to spend on a wound check via Monte Carlo.

    Uses a separate RNG seeded from the inputs so it is deterministic for
    the same game state and does not disturb the main combat dice stream.

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
    seed = hash((water_ring, light_wounds, void_available, max_spend, extra_rolled, tn_bonus))
    rng = random.Random(seed)
    n_sims = 2000
    tn = light_wounds + tn_bonus

    def _simulate_serious(kept: int) -> float:
        rolled = water_ring + 1 + extra_rolled
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
    shinjo_wc_bonus_pool: int = 0,
) -> bool:
    """Decide whether to convert light wounds to 1 serious wound on a passed wound check.

    The decision balances the 1 serious wound cost of converting against the
    long-term danger of carrying high light wounds into future wound checks.

    Keeping N light wounds saves 1 serious wound now, but raises every future
    wound check TN by N.  If the next wound check fails, the character takes
    1 serious wound plus 1 additional serious wound per full 10 the roll
    falls short.  High carried light wounds make catastrophic multi-SW
    failures much more likely.

    The key risk: carried light wounds add directly to the wound check TN
    on the next hit.  If you would have failed the wound check anyway, the
    extra `light_wounds` TN means `light_wounds // 10` additional serious
    wounds on top.  We convert when that risk exceeds 1 (the cost of
    converting now).

    The threshold is set so that the carried light wounds alone could cause
    2+ extra serious wounds if the wound check roll is poor.  We use the
    average wound check roll as a baseline for "what you can absorb" and
    convert when the light wounds push the TN far enough past that baseline.

    Shinjo 5th Dan banked wound check bonuses effectively raise the
    threshold: a pool of +33 means the character can safely absorb 33
    more light wounds before the risk outweighs converting.

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
        shinjo_wc_bonus_pool: Sum of banked Shinjo 5th Dan wound check
            bonuses.  Raises the keep-threshold by this amount.

    Returns:
        True if the character should take 1 serious wound and reset light wounds to 0.
    """
    # Never convert if it would mortally wound (serious + 1 >= 2 * earth)
    if serious_wounds + 1 >= 2 * earth_ring:
        return False

    # Below 10 light wounds, keeping is always safe: even a worst-case
    # failure adds at most 1 extra serious wound (deficit < 10), exactly
    # cancelling the 1 serious saved by not converting.
    if light_wounds <= 10:
        return False

    # Estimate expected wound check total for (Water+1)k(Water) w/ explosions.
    # Each kept die averages ~6.5 (selection bias from keeping highest of a
    # slightly larger pool pushes it above the raw 6.11 mean of an exploding
    # d10).  The dropped minimum die is small (~2–4), so we add a flat +2.
    avg_wc = water_ring * 6.5 + 2

    # Keep threshold: 80% of expected wound check total, floored at 10.
    # The 0.8 factor provides margin for variance and for the fact that
    # future hits will stack additional damage on top of the carried wounds.
    threshold = max(10, round(avg_wc * 0.8))

    # If converting would cripple (but not mortally wound), raise the bar:
    # only convert if light wounds are very dangerous (> 1.5× threshold),
    # since becoming crippled is a steep cost (lose 10-rerolling on skills).
    would_cripple = serious_wounds + 1 >= earth_ring
    if would_cripple:
        threshold = round(threshold * 1.5)

    # Shinjo 5th Dan: banked wound check bonuses act as a safety net,
    # letting the character absorb more light wounds before needing to
    # convert.  Add the full pool to the threshold.
    threshold += shinjo_wc_bonus_pool

    return light_wounds > threshold


def _should_spend_void_on_combat_roll(
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

    Args:
        rolled: Number of dice rolled.
        kept: Number of dice kept.
        tn: Target number to meet or exceed.
        void_available: Remaining void points.
        max_spend: Maximum void spendable on a single action.
        fifth_dan_bonus: Flat bonus per void spent (0 or 10 for 5th Dan Mirumoto).
        known_bonus: Flat bonus that will be added to the roll (e.g. free raises).

    Returns:
        Number of void points to spend (0 to min(void_available-1, max_spend)).
    """
    if void_available <= 1 or tn <= 0:
        return 0

    # Reserve 1 void for wound checks
    usable = min(void_available - 1, max_spend)
    if usable <= 0:
        return 0

    expected = _estimate_roll(rolled, kept) + known_bonus
    value_per_void = 5.5 + fifth_dan_bonus  # 1k1 + bonus

    # Only spend if expected roll is below TN and void spending bridges the gap
    if expected >= tn:
        return 0

    deficit = tn - expected
    needed = max(1, int(deficit / value_per_void + 0.5))
    return min(needed, usable)


def _estimate_roll(rolled: int, kept: int) -> float:
    """Estimate expected total for an XkY dice pool using order statistics.

    Accounts for overflow rules (excess rolled→kept, excess kept→+2 bonus).
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
    # Order statistics: E[sum of top Y of X uniform on [1,10]]
    # ≈ 10 * Y * (2X - Y + 1) / (2 * (X + 1))
    return 10.0 * eff_kept * (2 * eff_rolled - eff_kept + 1) / (2.0 * (eff_rolled + 1)) + bonus


def _should_use_double_attack(
    double_attack_rank: int,
    attack_skill: int,
    fire_ring: int,
    defender_parry: int,
    void_available: int,
    max_void_spend: int,
    dan: int,
    is_crippled: bool,
    known_bonus: int = 0,
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
        known_bonus: Flat bonus that will be added to the roll.

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
    normal_expected = _estimate_roll(normal_rolled, normal_kept) + known_bonus

    # Double attack expected value
    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = _estimate_roll(da_rolled, da_kept) + known_bonus

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
    known_bonus: int = 0,
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
        known_bonus: Flat bonus that will be added to the roll.

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
        expected = _estimate_roll(lunge_rolled, lunge_kept) + known_bonus
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
    da_expected = _estimate_roll(da_rolled, da_kept) + known_bonus

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
    lunge_rolled = lunge_rank + fire_ring
    lunge_kept = fire_ring
    expected = _estimate_roll(lunge_rolled, lunge_kept) + known_bonus
    if expected >= base_tn or usable_void <= 0:
        return "lunge", 0
    deficit = base_tn - expected
    void_spend = min(usable_void, max(1, int(deficit / 5.5 + 0.5)))
    return "lunge", void_spend


def _kakita_attack_choice(
    lunge_rank: int,
    double_attack_rank: int,
    fire_ring: int,
    defender_parry: int,
    dan: int,
    is_crippled: bool,
    known_bonus: int = 0,
) -> str:
    """Decide whether Kakita uses Lunge or Double Attack (never spends void).

    Args:
        lunge_rank: Character's Lunge knack rank.
        double_attack_rank: Character's Double Attack knack rank.
        fire_ring: Character's Fire ring value.
        defender_parry: Defender's parry skill rank.
        dan: Character's dan level.
        is_crippled: Whether the attacker is crippled.
        known_bonus: Flat bonus that will be added to the roll (e.g. 3rd Dan phase gap).

    Returns:
        "lunge" or "double_attack".
    """
    if is_crippled or double_attack_rank <= 0:
        return "lunge"

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    first_dan_bonus = 1 if dan >= 1 else 0

    # DA expected value including known bonuses
    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = _estimate_roll(da_rolled, da_kept) + known_bonus

    # Use DA if expected >= 0.85 * da_tn
    if da_expected >= da_tn * 0.85:
        return "double_attack"

    return "lunge"


def _kakita_should_phase0_attack(
    dan: int,
    attack_skill: int,
    phase0_count: int,
    total_dice: int,
    defender_next_phase: int,
) -> bool:
    """Decide whether to make a Phase 0 iaijutsu attack.

    If the Kakita has a phase 0 die (from rolling a 10 on initiative), the
    attack costs only 1 die — always worth it.  Without a phase 0 die, the
    Kakita can still interrupt-attack at phase 0 by spending 2 dice.

    The Kakita is a highly offensive school — phase 0 attacks are their
    signature ability and should be used aggressively.

    Args:
        dan: Kakita's dan level.
        attack_skill: Kakita's Attack skill rank.
        phase0_count: Number of phase 0 dice.
        total_dice: Total remaining action dice.
        defender_next_phase: Defender's next action phase (11 if none).

    Returns:
        True if the Kakita should make a phase 0 attack.
    """
    # With a phase 0 die: costs only 1 die — always attack
    if phase0_count > 0:
        return True

    # Interrupt (no phase 0 die): costs 2 highest dice
    if total_dice < 2:
        return False

    # Still always attack — striking before the opponent acts is the
    # Kakita's defining advantage, even at the cost of 2 dice.
    return True


def _resolve_kakita_phase0_attack(
    log: CombatLog,
    attacker_name: str,
    defender_name: str,
    fighters: dict[str, dict],
    actions_remaining: dict[str, list[int]],
    void_points: dict[str, int],
    dan_points: dict[str, int],
    temp_void: dict[str, int],
    matsu_bonuses: dict[str, list[int]],
    lunge_target_bonus: dict[str, int],
    shinjo_bonuses: dict[str, list[int]] | None = None,
) -> None:
    """Execute a Phase 0 iaijutsu interrupt attack.

    Consumes 2 dice (the phase 0 die + lowest remaining die) and resolves
    an iaijutsu attack at phase 0.
    """
    attacker: Character = fighters[attacker_name]["char"]
    defender: Character = fighters[defender_name]["char"]

    dan = attacker.dan

    # Consume dice: 1 die if using a phase 0 action, 2 highest dice if interrupting
    has_phase0 = 0 in actions_remaining[attacker_name]
    if has_phase0:
        # Regular phase 0 action: spend only the phase 0 die
        actions_remaining[attacker_name].remove(0)
    else:
        # Interrupt: spend 2 highest (least valuable) dice
        highest = sorted(actions_remaining[attacker_name], reverse=True)[:2]
        for die in highest:
            actions_remaining[attacker_name].remove(die)

    # Get skill ranks
    iaijutsu_skill = attacker.get_skill("Iaijutsu")
    iaijutsu_rank = iaijutsu_skill.rank if iaijutsu_skill else 0
    atk_skill = attacker.get_skill("Attack")
    atk_rank = atk_skill.rank if atk_skill else 0
    def_parry_skill = defender.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # Roll iaijutsu + Fire (keep Fire)
    fire_ring = attacker.rings.fire.value
    rolled = iaijutsu_rank + fire_ring
    kept = fire_ring

    # 1st Dan: +1 rolled die on iaijutsu
    if dan >= 1:
        rolled += 1

    attacker_crippled = log.wounds[attacker_name].is_crippled
    explode = not attacker_crippled

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=explode)

    # 2nd Dan: free raise (+5 to total)
    bonus_note = ""
    if dan >= 2:
        total += 5
        bonus_note += " (kakita 2nd Dan: free raise +5)"

    # 3rd Dan: + attack_skill * defender_next_phase
    defender_actions = sorted(actions_remaining.get(defender_name, []))
    defender_future = [a for a in defender_actions if a > 0]
    defender_next = defender_future[0] if defender_future else 11
    if dan >= 3:
        gap = defender_next
        kakita_bonus = atk_rank * gap
        if kakita_bonus > 0:
            total += kakita_bonus
            phase_word = 'phase' if gap == 1 else 'phases'
            bonus_note += (
                f" (kakita 3rd Dan: +{kakita_bonus},"
                f" {gap} {phase_word})"
            )

    # TN = standard attack TN
    tn = 5 + 5 * def_parry_rank
    success = total >= tn

    attack_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.IAIJUTSU,
        target=defender_name,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=tn,
        success=success,
        description=(
            f"{attacker_name} phase 0 iaijutsu"
            f"{'' if has_phase0 else ' (interrupt)'}: "
            f"{_format_pool_with_overflow(rolled, kept)}"
            f" vs TN {tn}{bonus_note}"
        ),
        dice_pool=_format_pool_with_overflow(rolled, kept),
    )
    attack_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )
    log.add_action(attack_action)

    if not success:
        return

    # Roll damage
    weapon: Weapon = fighters[attacker_name]["weapon"]
    extra_dice = max(0, (total - tn) // 5)
    damage_rolled = weapon.rolled + fire_ring + extra_dice
    damage_kept = weapon.kept

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(damage_rolled, damage_kept, explode=True)

    # 4th Dan: +5 on iaijutsu damage
    dmg_note = ""
    if dan >= 4:
        dmg_total += 5
        dmg_note = " (kakita 4th Dan: iaijutsu damage +5)"

    damage_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.DAMAGE,
        target=defender_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=f"{attacker_name} deals {dmg_total} damage{dmg_note}",
        dice_pool=_format_pool_with_overflow(damage_rolled, damage_kept),
    )

    # Apply damage
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )
    log.add_action(damage_action)

    # --- Wound check (reuse standard wound check logic) ---
    water_value = defender.rings.water.value
    def_is_matsu = defender.school == "Matsu Bushi"
    def_dan_matsu = defender.dan if def_is_matsu else 0

    # Compute wound check bonuses before void decision so they inform the decision
    ab7_extra = 2 * defender.ability_rank(7)
    matsu_wc_extra = 1 if def_is_matsu and def_dan_matsu >= 1 else 0
    ab10_bonus = 5 * attacker.ability_rank(10)

    # Decide how many void points to spend
    max_spend = defender.rings.lowest()
    void_spend = _should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, _total_void(void_points, temp_void, defender_name),
        max_spend=max_spend, extra_rolled=ab7_extra + matsu_wc_extra, tn_bonus=ab10_bonus,
    )
    wc_from_temp, wc_from_reg = _spend_void(void_points, temp_void, defender_name, void_spend)
    wc_void_label = _void_spent_label(wc_from_temp, wc_from_reg)

    def_is_shinjo = defender.school == "Shinjo Bushi"
    def_dan_shinjo = defender.dan if def_is_shinjo else 0

    sw_before_wc = wound_tracker.serious_wounds

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=ab7_extra + matsu_wc_extra, tn_bonus=ab10_bonus,
    )

    # Shinjo 5th Dan: apply stored bonuses after seeing the roll
    shinjo_bonus_note = ""
    if (def_is_shinjo and def_dan_shinjo >= 5
            and not passed and shinjo_bonuses
            and shinjo_bonuses[defender_name]):
        base_tn = wound_tracker.light_wounds
        raw_deficit = base_tn - wc_total
        used = _select_shinjo_wc_bonuses(
            raw_deficit, shinjo_bonuses[defender_name],
        )
        if used:
            bonus_applied = sum(used)
            wc_total += bonus_applied
            remaining = list(shinjo_bonuses[defender_name])
            for b in used:
                remaining.remove(b)
            shinjo_bonuses[defender_name][:] = remaining
            sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
            new_deficit = base_tn - wc_total
            if new_deficit <= 0:
                new_sw = 0
                passed = True
            else:
                new_sw = 1 + (new_deficit // 10)
            wound_tracker.serious_wounds += (new_sw - sw_added_by_wc)
            bonus_str = ", ".join(f"+{b}" for b in used)
            total_str = f" = +{bonus_applied}" if len(used) > 1 else ""
            if passed:
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" wound check passes)"
                )
            else:
                sw_saved = sw_added_by_wc - new_sw
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" {sw_saved} serious wound"
                    f"{'s' if sw_saved != 1 else ''}"
                    f" prevented)"
                )

    void_note = f" ({wc_void_label})" if wc_void_label else ""
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn + ab10_bonus

    # Feature 3: Wound check success choice
    convert_note = ""
    if passed:
        def_shinjo_pool = 0
        if (shinjo_bonuses
                and def_is_shinjo and def_dan_shinjo >= 5):
            def_shinjo_pool = sum(
                shinjo_bonuses[defender_name]
            )
        should_convert = _should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            shinjo_wc_bonus_pool=def_shinjo_pool,
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
    wc_rolled = water_value + 1 + ab7_extra + matsu_wc_extra + void_spend
    wc_kept = water_value + void_spend
    wc_action = CombatAction(
        phase=0,
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
            f"(rolled {wc_total}){void_note}{shinjo_bonus_note}{convert_note}{ab10_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    if not passed:
        wound_tracker.light_wounds = 0

    wc_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )


def _resolve_kakita_5th_dan(
    log: CombatLog,
    attacker_name: str,
    defender_name: str,
    fighters: dict[str, dict],
    actions_remaining: dict[str, list[int]],
    void_points: dict[str, int],
    dan_points: dict[str, int],
    temp_void: dict[str, int],
    matsu_bonuses: dict[str, list[int]],
    shinjo_bonuses: dict[str, list[int]] | None = None,
) -> None:
    """Resolve 5th Dan Kakita contested iaijutsu at phase 0.

    Automatic at the beginning of each round:
    1. Kakita rolls (iaijutsu + Fire)k(Fire), +1 if 1st Dan, +5 if 2nd Dan
    2. Opponent rolls (iaijutsu + Fire)k(Fire) or (Attack + Fire)k(Fire)
    3. Compare totals, roll damage with bonus/penalty dice
    """
    attacker: Character = fighters[attacker_name]["char"]
    defender: Character = fighters[defender_name]["char"]
    dan = attacker.dan
    weapon: Weapon = fighters[attacker_name]["weapon"]

    # Kakita's iaijutsu roll
    iaijutsu_skill = attacker.get_skill("Iaijutsu")
    iaijutsu_rank = iaijutsu_skill.rank if iaijutsu_skill else 0
    fire_ring = attacker.rings.fire.value

    kakita_rolled = iaijutsu_rank + fire_ring
    kakita_kept = fire_ring
    if dan >= 1:
        kakita_rolled += 1

    attacker_crippled = log.wounds[attacker_name].is_crippled
    k_all, k_kept, kakita_total = roll_and_keep(
        kakita_rolled, kakita_kept, explode=not attacker_crippled,
    )

    # Accumulate bonuses with descriptions
    bonus_notes: list[str] = []

    # 2nd Dan: free raise on iaijutsu (+5)
    if dan >= 2:
        kakita_total += 5
        bonus_notes.append("2nd Dan free raise: +5")

    # Opponent's contested roll
    def_iaijutsu = defender.get_skill("Iaijutsu")
    def_atk_skill = defender.get_skill("Attack")
    no_iaijutsu = False
    if def_iaijutsu and def_iaijutsu.rank > 0:
        opp_skill_rank = def_iaijutsu.rank
        opp_skill_name = "iaijutsu"
    elif def_atk_skill:
        opp_skill_rank = def_atk_skill.rank
        opp_skill_name = "attack"
        no_iaijutsu = True
    else:
        opp_skill_rank = 0
        opp_skill_name = "attack"
        no_iaijutsu = True

    def_fire = defender.rings.fire.value
    opp_rolled = opp_skill_rank + def_fire
    opp_kept = def_fire
    defender_crippled = log.wounds[defender_name].is_crippled
    o_all, o_kept, opp_total = roll_and_keep(opp_rolled, opp_kept, explode=not defender_crippled)

    # Contested skill difference: +5 per point Kakita's skill exceeds opponent's
    skill_diff = iaijutsu_rank - opp_skill_rank
    if skill_diff > 0:
        skill_diff_bonus = skill_diff * 5
        kakita_total += skill_diff_bonus
        bonus_notes.append(f"skill {iaijutsu_rank} vs {opp_skill_rank}: +{skill_diff_bonus}")

    # Extra raise if opponent has no iaijutsu (uses attack instead)
    if no_iaijutsu:
        kakita_total += 5
        bonus_notes.append("no opponent iaijutsu: +5")

    # Log contested roll
    margin = kakita_total - opp_total
    won = margin >= 0
    contest_note = f"won by {margin}" if won else f"lost by {abs(margin)}"
    bonus_str = f" ({', '.join(bonus_notes)})" if bonus_notes else ""
    opp_pool = _format_pool_with_overflow(opp_rolled, opp_kept)

    # Format opponent's dice: bold for kept, strikethrough for unkept
    opp_kept_remaining = list(o_kept)
    opp_dice_display: list[str] = []
    for d in o_all:
        if d in opp_kept_remaining:
            opp_dice_display.append(f"**{d}**")
            opp_kept_remaining.remove(d)
        else:
            opp_dice_display.append(f"~~{d}~~")
    opp_dice_str = f"[{', '.join(opp_dice_display)}]"

    opp_tn_desc = (
        f"vs TN {opp_total} ({defender_name}'s"
        f" {opp_pool} {opp_skill_name} {opp_dice_str})"
    )
    contest_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.IAIJUTSU,
        target=defender_name,
        dice_rolled=k_all,
        dice_kept=k_kept,
        total=kakita_total,
        tn=opp_total,
        success=won,
        description=(
            f"{attacker_name} 5th Dan iaijutsu: "
            f"{_format_pool_with_overflow(kakita_rolled, kakita_kept)} = {kakita_total}{bonus_str}"
            f" vs {defender_name} {opp_pool} = {opp_total}"
            f" ({contest_note})"
        ),
        dice_pool=_format_pool_with_overflow(kakita_rolled, kakita_kept),
        label="5th Dan iaijutsu",
        tn_description=opp_tn_desc,
    )
    contest_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )
    log.add_action(contest_action)

    # Damage roll
    damage_rolled = weapon.rolled + fire_ring
    damage_kept = weapon.kept

    dmg_notes: list[str] = []
    if won:
        extra_damage_dice = max(0, margin // 5)
        damage_rolled += extra_damage_dice
        if extra_damage_dice > 0:
            dmg_notes.append(f"won by {margin}: +{extra_damage_dice} rolled")
    else:
        fewer_dice = min(weapon.rolled - 1, abs(margin) // 5)
        damage_rolled = max(1, damage_rolled - fewer_dice)
        if fewer_dice > 0:
            dmg_notes.append(f"lost by {abs(margin)}: -{fewer_dice} rolled")

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(damage_rolled, damage_kept, explode=True)

    # 4th Dan: +5 on iaijutsu damage
    if dan >= 4:
        dmg_total += 5
        dmg_notes.append("4th Dan free raise: +5")

    dmg_note_str = f" ({', '.join(dmg_notes)})" if dmg_notes else ""

    damage_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.DAMAGE,
        target=defender_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=(
            f"{attacker_name} 5th Dan iaijutsu damage: "
            f"{_format_pool_with_overflow(damage_rolled, damage_kept)}"
            f" = {dmg_total}{dmg_note_str}"
        ),
        dice_pool=_format_pool_with_overflow(damage_rolled, damage_kept),
        label="5th Dan iaijutsu damage",
    )

    # Apply damage
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )
    log.add_action(damage_action)

    # Wound check
    water_value = defender.rings.water.value
    def_is_matsu = defender.school == "Matsu Bushi"
    def_dan_matsu = defender.dan if def_is_matsu else 0

    # Compute wound check bonuses before void decision so they inform the decision
    ab7_extra = 2 * defender.ability_rank(7)
    matsu_wc_extra = 1 if def_is_matsu and def_dan_matsu >= 1 else 0
    ab10_bonus = 5 * attacker.ability_rank(10)

    max_spend = defender.rings.lowest()
    void_spend = _should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, _total_void(void_points, temp_void, defender_name),
        max_spend=max_spend, extra_rolled=ab7_extra + matsu_wc_extra, tn_bonus=ab10_bonus,
    )
    wc_from_temp, wc_from_reg = _spend_void(void_points, temp_void, defender_name, void_spend)
    wc_void_label = _void_spent_label(wc_from_temp, wc_from_reg)

    def_is_shinjo = defender.school == "Shinjo Bushi"
    def_dan_shinjo = defender.dan if def_is_shinjo else 0

    sw_before_wc = wound_tracker.serious_wounds

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=ab7_extra + matsu_wc_extra, tn_bonus=ab10_bonus,
    )

    # Shinjo 5th Dan: apply stored bonuses after seeing the roll
    shinjo_bonus_note = ""
    if (def_is_shinjo and def_dan_shinjo >= 5
            and not passed and shinjo_bonuses
            and shinjo_bonuses[defender_name]):
        base_tn = wound_tracker.light_wounds
        raw_deficit = base_tn - wc_total
        used = _select_shinjo_wc_bonuses(
            raw_deficit, shinjo_bonuses[defender_name],
        )
        if used:
            bonus_applied = sum(used)
            wc_total += bonus_applied
            remaining = list(shinjo_bonuses[defender_name])
            for b in used:
                remaining.remove(b)
            shinjo_bonuses[defender_name][:] = remaining
            sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
            new_deficit = base_tn - wc_total
            if new_deficit <= 0:
                new_sw = 0
                passed = True
            else:
                new_sw = 1 + (new_deficit // 10)
            wound_tracker.serious_wounds += (new_sw - sw_added_by_wc)
            bonus_str = ", ".join(f"+{b}" for b in used)
            total_str = f" = +{bonus_applied}" if len(used) > 1 else ""
            if passed:
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" wound check passes)"
                )
            else:
                sw_saved = sw_added_by_wc - new_sw
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" {sw_saved} serious wound"
                    f"{'s' if sw_saved != 1 else ''}"
                    f" prevented)"
                )

    void_note = f" ({wc_void_label})" if wc_void_label else ""
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn + ab10_bonus

    convert_note = ""
    if passed:
        def_shinjo_pool = 0
        if (shinjo_bonuses
                and def_is_shinjo and def_dan_shinjo >= 5):
            def_shinjo_pool = sum(
                shinjo_bonuses[defender_name]
            )
        should_convert = _should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            shinjo_wc_bonus_pool=def_shinjo_pool,
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
    wc_rolled = water_value + 1 + ab7_extra + matsu_wc_extra + void_spend
    wc_kept = water_value + void_spend
    wc_action = CombatAction(
        phase=0,
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
            f"(rolled {wc_total}){void_note}{shinjo_bonus_note}{convert_note}{ab10_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    if not passed:
        wound_tracker.light_wounds = 0

    wc_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )


def _should_predeclare_parry(
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
    """Decide whether to pre-declare a parry for the +5 bonus.

    Pre-declare when the +5 bonus meaningfully increases the chance of success.
    The tradeoff: pre-declaring wastes the action die if the attack misses.

    Kakita Duelists never pre-declare parries — they are purely offensive and
    would rather attack than commit an action die to a parry before seeing the
    attack roll.

    Shinjo Bushi 3rd Dan+ are *more* inclined to pre-declare because every
    parry (even failed) triggers the 3rd Dan dice decrease, and the +5
    free raise makes the parry more likely to succeed (blocking damage AND
    decreasing dice).  They pre-declare whenever they have a non-trivial
    parry chance, even if the base expected parry already exceeds the TN.

    Args:
        defender_parry_rank: Defender's parry skill rank.
        air_ring: Defender's Air ring value.
        attack_tn: The TN the attacker needs to hit (proxy for expected attack total).
        is_crippled: Whether the defender is crippled.
        is_kakita: Whether the defender is a Kakita Duelist.
        is_shinjo: Whether the defender is a Shinjo Bushi.
        shinjo_dan: Shinjo's dan level (relevant at 3+).
        known_bonus: Flat bonus that will be added to the parry roll (e.g. free raises).

    Returns:
        True if pre-declaring is worthwhile.
    """
    if is_kakita:
        return False

    parry_dice = defender_parry_rank + air_ring
    parry_kept = air_ring
    expected_parry = _estimate_roll(parry_dice, parry_kept) + known_bonus
    if is_crippled:
        expected_parry *= 0.9  # No exploding lowers average slightly

    # Shinjo 3rd Dan+: strongly prefer pre-declaring.  The dice decrease
    # triggers on any parry attempt, so the cost of a "wasted" pre-declare
    # (attack misses) is just losing 1 held die — but the benefit of the
    # +5 making the parry succeed is high (blocks damage + decreases dice).
    # Pre-declare as long as parry rank > 0 (always have some chance).
    if is_shinjo and shinjo_dan >= 3:
        return True

    # Shinjo below 3rd Dan: still somewhat more willing to pre-declare
    # since they hold dice anyway (no lost attack opportunity at this phase).
    if is_shinjo:
        # Pre-declare whenever expected parry + 5 would reach the TN,
        # even if expected parry alone is close.
        return expected_parry + 5 >= attack_tn * 0.8

    # Pre-declare when the expected parry total is below the attack TN
    # (meaning the +5 bonus is needed to have a reasonable chance)
    return expected_parry < attack_tn


def _should_reactive_parry(
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
) -> bool:
    """Decide whether to parry with an action die already in this phase (1 die cost).

    Called AFTER the attack hits. The defender has an action die in this phase
    so the cost is 1 die (opportunity cost of not attacking).

    School-specific behaviour:
    - **Default / Matsu**: Parry when there's a reasonable chance of success
      and expected damage is meaningful. Since the cost is only 1 die, the
      threshold is relatively low.
    - **Mirumoto**: Always attempt — they gain temp void from parrying,
      making even failed parries valuable.
    - **Kakita**: Only parry against very high damage (damage_rolled > 12).
      They are purely offensive and would rather keep attacking.

    Args:
        defender_parry_rank: Defender's parry skill rank.
        air_ring: Defender's Air ring value.
        attack_total: The actual attack roll total.
        attack_tn: The TN the attacker needed to hit.
        weapon_rolled: Attacker's weapon rolled dice.
        attacker_fire: Attacker's Fire ring value.
        serious_wounds: Defender's current serious wounds.
        earth_ring: Defender's Earth ring value.
        is_crippled: Whether the defender is crippled.
        is_kakita: Whether the defender is a Kakita Duelist.
        is_mirumoto: Whether the defender is a Mirumoto Bushi.
        known_bonus: Flat bonus that will be added to the parry roll (e.g. free raises).

    Returns:
        True if the defender should spend 1 die to parry.
    """
    if defender_parry_rank <= 0:
        return False

    extra_dice = max(0, (attack_total - attack_tn) // 5)
    damage_rolled = weapon_rolled + attacker_fire + extra_dice

    # Mirumoto: always attempt — temp void gain makes even failed parries worthwhile
    if is_mirumoto:
        return True

    # Kakita: only parry against very heavy damage (offensive school)
    if is_kakita:
        return damage_rolled > 12

    # Default / Matsu: parry when damage is significant or parry has decent odds
    wounds_to_cripple = earth_ring - serious_wounds

    # Always parry if near cripple
    if wounds_to_cripple <= 1:
        return True

    # Parry if expected damage is meaningful (overflow dice)
    if extra_dice >= 1:
        return True

    # Parry if we have a reasonable chance of succeeding
    parry_dice = defender_parry_rank + air_ring
    crippled_mult = 0.9 if is_crippled else 1.0
    expected_parry = (
        _estimate_roll(parry_dice, air_ring) * crippled_mult
        + known_bonus
    )
    if expected_parry >= attack_total * 0.6:
        return True

    return False


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
    *,
    is_kakita: bool = False,
    is_mirumoto: bool = False,
    known_bonus: int = 0,
) -> bool:
    """Decide whether to spend 2 action dice for a reactive interrupt parry.

    Called AFTER the attack hits when the defender does NOT have an action in
    the current phase. Costs 2 dice, so the threshold is higher than for a
    regular 1-die reactive parry.

    School-specific behaviour:
    - **Default / Matsu**: Interrupt when damage would overflow (> 10 rolled)
      or when near cripple with significant extra dice.
    - **Mirumoto**: Similar to default but slightly more willing (they gain
      temp void from parrying).
    - **Kakita**: Extremely reluctant — only interrupt when damage is truly
      massive (rolled > 15 with large overflow).

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
        is_kakita: Whether the defender is a Kakita Duelist.
        is_mirumoto: Whether the defender is a Mirumoto Bushi.
        known_bonus: Flat bonus that will be added to the parry roll (e.g. free raises).

    Returns:
        True if the defender should spend 2 dice for an interrupt parry.
    """
    if dice_remaining < 2 or defender_parry_rank <= 0:
        return False

    extra_dice = max(0, (attack_total - attack_tn) // 5)
    damage_rolled = weapon_rolled + attacker_fire + extra_dice
    wounds_to_cripple = earth_ring - serious_wounds

    # Kakita: only if damage is truly massive
    if is_kakita:
        if damage_rolled > 15 and extra_dice >= defender_parry_rank + 3:
            return True
        return False

    # Mirumoto: slightly more willing (temp void gain)
    if is_mirumoto:
        if damage_rolled > 9:
            return True
        if wounds_to_cripple <= 1 and extra_dice >= 1:
            return True
        return False

    # Default / Matsu
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


def _select_shinjo_wc_bonuses(
    deficit: int,
    available: list[int],
) -> list[int]:
    """Select the minimum set of Shinjo 5th Dan bonuses to spend.

    Applied AFTER the wound check roll is seen.  Goals (in priority order):
      1. Minimise the number of serious wounds taken.
      2. Use the smallest pool total that achieves that minimum.

    Serious wounds on failure = 1 + (deficit // 10).
    Reducing the deficit below 1 means passing (0 SW).
    Each 10-point reduction that crosses a boundary saves 1 SW.

    Args:
        deficit: base_tn - wc_total (positive means failed).
        available: List of stored bonus values.

    Returns:
        The bonuses to spend (a subset of *available*).  Empty list if
        spending any bonus would not reduce the serious wound count.
    """
    if deficit <= 0 or not available:
        return []

    current_sw = 1 + (deficit - 1) // 10
    pool = sum(available)

    # Nothing in the pool can help at all
    if pool <= 0:
        return []

    # Determine the best achievable SW count
    if pool >= deficit:
        best_sw = 0
    else:
        best_sw = 1 + (deficit - pool - 1) // 10

    # If bonuses can't reduce SW at all, don't spend any
    if best_sw >= current_sw:
        return []

    # Determine the minimum bonus total needed to reach best_sw.
    # To achieve 0 SW: need total >= deficit.
    # To achieve K SW (K >= 1): need total >= deficit - (10 * K - 1),
    #   i.e. remaining deficit <= 10 * K - 1.
    if best_sw == 0:
        needed = deficit
    else:
        needed = deficit - (10 * best_sw - 1)

    # Select the minimum-cost subset whose sum >= `needed`.
    # Pool is typically small (< 10 bonuses), so enumerate all
    # 2^N subsets and pick the one with the smallest total.
    n = len(available)
    best_subset: list[int] = list(available)  # fallback: use all
    best_cost = pool
    for mask in range(1, 1 << n):
        subset = [available[i] for i in range(n) if mask & (1 << i)]
        total = sum(subset)
        if total >= needed and total < best_cost:
            best_cost = total
            best_subset = subset

    return best_subset


def _shinjo_attack_choice(
    double_attack_rank: int,
    fire_ring: int,
    defender_parry: int,
    void_available: int,
    max_void_spend: int,
    dan: int,
    is_crippled: bool,
    sa_bonus: int = 0,
) -> tuple[str, int]:
    """Decide whether Shinjo uses Double Attack or Lunge at phase 10.

    Shinjo always uses DA unless crippled or DA rank 0, in which case lunge.
    Balanced void spending: reserve at least 1 void when possible.

    Args:
        double_attack_rank: Character's Double Attack knack rank.
        fire_ring: Character's Fire ring value.
        defender_parry: Defender's parry skill rank.
        void_available: Remaining void points.
        max_void_spend: Maximum void per action.
        dan: Character's dan level.
        is_crippled: Whether the attacker is crippled.
        sa_bonus: Shinjo SA bonus from held die.

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
    da_expected = _estimate_roll(da_rolled, da_kept) + sa_bonus

    # Balanced: reserve at least 1 void for wound checks when possible
    usable = min(void_available - 1, max_void_spend) if void_available > 1 else 0

    # Spend enough void to reach 85% of DA TN
    if da_expected >= da_tn:
        return "double_attack", 0

    if da_expected + usable * 5.5 >= da_tn * 0.85:
        deficit = da_tn * 0.85 - da_expected
        void_spend = min(usable, max(1, int(deficit / 5.5 + 0.5)))
        return "double_attack", void_spend

    # DA not viable even with void: fall back to lunge
    return "lunge", 0


def _resolve_shinjo_phase10_attack(
    log: CombatLog,
    attacker_name: str,
    defender_name: str,
    fighters: dict[str, dict],
    actions_remaining: dict[str, list[int]],
    void_points: dict[str, int],
    dan_points: dict[str, int],
    temp_void: dict[str, int],
    matsu_bonuses: dict[str, list[int]],
    shinjo_bonuses: dict[str, list[int]],
    lunge_target_bonus: dict[str, int],
) -> None:
    """Execute a Shinjo phase 10 attack using held dice.

    Picks the LOWEST die from actions_remaining (biggest SA bonus)
    and resolves an attack at phase 10 via _resolve_attack.
    """
    dice = actions_remaining[attacker_name]
    if not dice:
        return

    # Pick lowest die for maximum SA bonus
    die_value = min(dice)

    attacker_info = fighters[attacker_name]
    defender_info = fighters[defender_name]

    _resolve_attack(
        log, 10, attacker_info, defender_info, attacker_name, defender_name,
        fighters, actions_remaining, void_points,
        dan_points=dan_points,
        temp_void=temp_void,
        matsu_bonuses=matsu_bonuses,
        lunge_target_bonus=lunge_target_bonus,
        shinjo_bonuses=shinjo_bonuses,
        shinjo_die_value=die_value,
    )


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

    # Shinjo 5th Dan parry margin → wound check bonus pool
    shinjo_bonuses: dict[str, list[int]] = {char_a.name: [], char_b.name: []}

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
        # Kakita 1st Dan: +1 unkept die on initiative
        # Shinjo 1st Dan: +1 unkept die on initiative
        matsu_extra_a = max(0, 9 - char_a.rings.void.value) if char_a.school == "Matsu Bushi" else 0
        matsu_extra_b = max(0, 9 - char_b.rings.void.value) if char_b.school == "Matsu Bushi" else 0
        kakita_init_a = 1 if (char_a.school == "Kakita Duelist" and char_a.dan >= 1) else 0
        kakita_init_b = 1 if (char_b.school == "Kakita Duelist" and char_b.dan >= 1) else 0
        shinjo_init_a = 1 if (char_a.school == "Shinjo Bushi" and char_a.dan >= 1) else 0
        shinjo_init_b = 1 if (char_b.school == "Shinjo Bushi" and char_b.dan >= 1) else 0
        extra_a = (
            char_a.ability_rank(6) + matsu_extra_a
            + kakita_init_a + shinjo_init_a
        )
        init_a = roll_initiative(char_a, extra_unkept=extra_a)
        extra_b = (
            char_b.ability_rank(6) + matsu_extra_b
            + kakita_init_b + shinjo_init_b
        )
        init_b = roll_initiative(char_b, extra_unkept=extra_b)

        actions_remaining: dict[str, list[int]] = {
            char_a.name: sorted(init_a.dice_kept),
            char_b.name: sorted(init_b.dice_kept),
        }

        # Kakita SA: 10s become phase 0 actions.
        # Convert 10→0 in the rolled dice, re-sort, then re-pick the lowest
        # Void-count dice.  Total kept dice stays equal to the Void ring.
        for init_result, char in [(init_a, char_a), (init_b, char_b)]:
            if char.school != "Kakita Duelist":
                continue
            void_ring = char.rings.void.value
            converted = sorted(0 if d == 10 else d for d in init_result.dice_rolled)
            drop_count = len(converted) - void_ring
            new_kept = converted[:-drop_count] if drop_count > 0 else list(converted)
            init_result.dice_kept = new_kept
            actions_remaining[char.name] = sorted(new_kept)

        # Shinjo 4th Dan: highest die set to 1
        for char, init_action in [(char_a, init_a), (char_b, init_b)]:
            if char.school == "Shinjo Bushi" and char.dan >= 4:
                dice = actions_remaining[char.name]
                if dice:
                    max_die = max(dice)
                    dice.remove(max_die)
                    dice.append(1)
                    dice.sort()
                    init_action.description += (
                        f" (4th Dan: highest action die"
                        f" {max_die} -> 1)"
                    )

        init_a.status_after = _snapshot_status(
            log, fighters, actions_remaining, void_points,
            dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
        )
        log.add_action(init_a)
        init_b.status_after = _snapshot_status(
            log, fighters, actions_remaining, void_points,
            dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
        )
        log.add_action(init_b)

        # --- Phase 0 processing (Kakita) ---
        for name in [char_a.name, char_b.name]:
            char: Character = fighters[name]["char"]
            if char.school != "Kakita Duelist":
                continue
            if _is_mortally_wounded(log, name):
                continue
            opp_name = char_b.name if name == char_a.name else char_a.name
            if _is_mortally_wounded(log, opp_name):
                continue

            # 5th Dan: contested iaijutsu (automatic)
            if char.dan >= 5:
                _resolve_kakita_5th_dan(
                    log, name, opp_name, fighters, actions_remaining,
                    void_points, dan_points, temp_void, matsu_bonuses,
                    shinjo_bonuses,
                )
                if _is_mortally_wounded(log, name) or _is_mortally_wounded(log, opp_name):
                    break

            # Phase 0 iaijutsu attack decision
            # If the Kakita has a phase 0 die: costs 1 die (regular action)
            # If no phase 0 die: costs 2 highest dice (interrupt)
            phase0_count = actions_remaining[name].count(0)
            has_phase0 = phase0_count > 0
            can_attack = has_phase0 or len(actions_remaining[name]) >= 2
            if can_attack:
                opp_actions = sorted(actions_remaining.get(opp_name, []))
                opp_future = [a for a in opp_actions if a > 0]
                defender_next = opp_future[0] if opp_future else 11
                atk_s = char.get_skill("Attack")
                atk_r = atk_s.rank if atk_s else 0
                if _kakita_should_phase0_attack(
                    char.dan, atk_r, phase0_count,
                    len(actions_remaining[name]), defender_next,
                ):
                    _resolve_kakita_phase0_attack(
                        log, name, opp_name, fighters, actions_remaining,
                        void_points, dan_points, temp_void, matsu_bonuses,
                        lunge_target_bonus, shinjo_bonuses,
                    )
                    if _is_mortally_wounded(log, name) or _is_mortally_wounded(log, opp_name):
                        break

            # Convert remaining phase 0 dice to phase 1 (held actions)
            while 0 in actions_remaining[name]:
                actions_remaining[name].remove(0)
                actions_remaining[name].append(1)
            actions_remaining[name].sort()

        # Build action schedule: list of (phase, die_value, character_name)
        schedule: list[tuple[int, int, str]] = []
        for die_val in actions_remaining[char_a.name]:
            schedule.append((die_val, die_val, char_a.name))
        for die_val in actions_remaining[char_b.name]:
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
                shinjo_bonuses=shinjo_bonuses,
            )

        # --- Shinjo Phase 10 Attack ---
        for name in [char_a.name, char_b.name]:
            char_s: Character = fighters[name]["char"]
            if char_s.school != "Shinjo Bushi" or not actions_remaining[name]:
                continue
            if _is_mortally_wounded(log, char_a.name) or _is_mortally_wounded(log, char_b.name):
                continue
            opp_name = char_b.name if name == char_a.name else char_a.name
            _resolve_shinjo_phase10_attack(
                log, name, opp_name, fighters, actions_remaining,
                void_points, dan_points, temp_void, matsu_bonuses,
                shinjo_bonuses, lunge_target_bonus,
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
    shinjo_bonuses: dict[str, list[int]] | None = None,
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
            shinjo_bonuses=list(shinjo_bonuses.get(name, [])) if shinjo_bonuses else [],
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
    tens_count = sum(1 for d in all_dice if d == 10)
    if rank > 0 and tens_count > 0:
        rerolled = min(tens_count, rank)
        all_dice, kept_dice, total = reroll_tens(all_dice, kept_count, max_reroll=rank)
        tens_word = "ten" if rerolled == 1 else "tens"
        description_suffix += f" (crippled reroll: rerolled {rerolled} {tens_word})"
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
    shinjo_bonuses: dict[str, list[int]] | None = None,
    shinjo_die_value: int | None = None,
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
    if shinjo_bonuses is None:
        shinjo_bonuses = {attacker_name: [], defender_name: []}

    attacker: Character = attacker_info["char"]
    defender: Character = defender_info["char"]
    weapon: Weapon = attacker_info["weapon"]

    # Shinjo school detection (before die consumption)
    atk_is_shinjo = attacker.school == "Shinjo Bushi"
    def_is_shinjo = defender.school == "Shinjo Bushi"
    atk_dan_shinjo = attacker.dan if atk_is_shinjo else 0
    def_dan_shinjo = defender.dan if def_is_shinjo else 0

    # Shinjo SA bonus from held die
    shinjo_sa_bonus = 0

    # Consume the phase die — if already gone (e.g. spent on a parry), skip
    if shinjo_die_value is not None:
        # Shinjo phase 10 attack: consume the specified die
        if shinjo_die_value in actions_remaining[attacker_name]:
            actions_remaining[attacker_name].remove(shinjo_die_value)
            shinjo_sa_bonus = 2 * (10 - shinjo_die_value)
        else:
            return
    elif atk_is_shinjo and phase < 10:
        # Shinjo holds action dice — do NOT consume or attack at phases < 10
        return
    elif phase in actions_remaining[attacker_name]:
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

    # Kakita school technique detection
    atk_is_kakita = attacker.school == "Kakita Duelist"
    def_is_kakita = defender.school == "Kakita Duelist"
    atk_dan_kakita = attacker.dan if atk_is_kakita else 0

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
    elif atk_is_kakita and not attacker_crippled:
        # Kakita uses Lunge or Double Attack (never spends void on attacks)
        # Compute known bonus (3rd Dan phase gap) to inform the decision
        kakita_known_bonus = 0
        if atk_dan_kakita >= 3:
            def_actions = sorted(actions_remaining.get(defender_name, []))
            def_future = [a for a in def_actions if a > phase]
            def_next = def_future[0] if def_future else 11
            kakita_known_bonus = atk_rank * (def_next - phase)
        choice = _kakita_attack_choice(
            lunge_rank, da_rank, attacker.rings.fire.value,
            def_parry_rank, atk_dan_kakita, attacker_crippled,
            known_bonus=kakita_known_bonus,
        )
        if choice == "double_attack":
            is_double_attack = True
        else:
            is_lunge = True
    elif atk_is_kakita and attacker_crippled:
        # Crippled Kakita always lunges
        is_lunge = True
    elif atk_is_shinjo and shinjo_die_value is not None:
        # Shinjo phase 10 attack: always DA (or lunge if crippled/DA rank 0)
        attack_choice, shinjo_void = _shinjo_attack_choice(
            da_rank, attacker.rings.fire.value, def_parry_rank,
            _total_void(void_points, temp_void, attacker_name),
            attacker.rings.lowest(), atk_dan_shinjo, attacker_crippled,
            sa_bonus=shinjo_sa_bonus,
        )
        if attack_choice == "double_attack":
            is_double_attack = True
            da_void_spend = shinjo_void
        else:
            is_lunge = True
            lunge_void_spend = shinjo_void
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
    # Shinjo: any held die with value ≤ current phase counts as reactive
    if def_is_shinjo:
        has_action_in_phase = any(d <= phase for d in actions_remaining[defender_name])
    else:
        has_action_in_phase = phase in actions_remaining[defender_name]

    # Compute known parry bonus for decision-making
    # (e.g. Mirumoto 2nd Dan free raise, Shinjo 2nd Dan)
    def_parry_known_bonus = 0
    if def_is_mirumoto and def_dan >= 2:
        def_parry_known_bonus += 5
    if def_is_shinjo and def_dan_shinjo >= 2:
        def_parry_known_bonus += 5

    predeclared = False
    if has_action_in_phase and def_parry_rank > 0:
        # Shinjo: don't pre-declare with only 1 die (save for phase 10
        # attack), unless near mortal wound.
        shinjo_skip_predeclare = False
        if def_is_shinjo and len(actions_remaining[defender_name]) <= 1:
            near_mortal = (
                log.wounds[defender_name].serious_wounds
                >= 2 * log.wounds[defender_name].earth_ring - 1
            )
            if not near_mortal:
                shinjo_skip_predeclare = True

        if not shinjo_skip_predeclare:
            defender_crippled = log.wounds[defender_name].is_crippled
            predeclared = _should_predeclare_parry(
                def_parry_rank, defender.rings.air.value, tn,
                defender_crippled,
                is_kakita=def_is_kakita,
                is_shinjo=def_is_shinjo,
                shinjo_dan=def_dan_shinjo,
                known_bonus=def_parry_known_bonus,
            )

    # If pre-declared, consume the parry die now (before attack roll)
    shinjo_parry_predeclare_die = 0
    if predeclared:
        if def_is_shinjo:
            # Shinjo: spend highest eligible die ≤ phase (same logic as
            # reactive parry — smallest held bonus sacrificed)
            eligible = [
                d for d in actions_remaining[defender_name]
                if d <= phase
            ]
            die_to_spend = max(eligible)
            actions_remaining[defender_name].remove(die_to_spend)
            shinjo_parry_predeclare_die = die_to_spend
        else:
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
        avail_void = _total_void(void_points, temp_void, attacker_name)
        if lunge_void_spend > 0 and avail_void >= lunge_void_spend:
            lng_from_temp, lng_from_reg = _spend_void(
                void_points, temp_void, attacker_name, lunge_void_spend,
            )
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

        # Shinjo SA bonus on lunge
        shinjo_sa_note = ""
        if atk_is_shinjo and shinjo_sa_bonus > 0:
            total += shinjo_sa_bonus
            held_phases = 10 - (shinjo_die_value if shinjo_die_value is not None else phase)
            shinjo_sa_note = f" (shinjo SA: +{shinjo_sa_bonus} held {held_phases} phases)"

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
                f" vs TN {tn}{void_note}{shinjo_sa_note}"
            ),
            dice_pool=_format_pool_with_overflow(lng_rolled, lng_kept),
        )
        # Lunge: opponent's next attack gets -5 TN
        lunge_target_bonus[defender_name] = 5

    elif is_double_attack:
        # Double attack uses Double Attack skill + Fire (not Attack skill)
        da_rolled = da_rank + attacker.rings.fire.value
        # First Dan bonus: Mirumoto, Matsu, Kakita, or Shinjo
        if (
            (atk_is_mirumoto and atk_dan >= 1)
            or (atk_is_matsu and atk_dan_matsu >= 1)
            or (atk_is_kakita and atk_dan_kakita >= 1)
            or (atk_is_shinjo and atk_dan_shinjo >= 1)
        ):
            da_rolled += 1
        da_kept = attacker.rings.fire.value

        # Apply void spending on double attack
        da_void_label = ""
        actual_da_void = 0
        da_avail = _total_void(void_points, temp_void, attacker_name)
        if da_void_spend > 0 and da_avail >= da_void_spend:
            da_from_temp, da_from_reg = _spend_void(
                void_points, temp_void, attacker_name, da_void_spend,
            )
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

        # Shinjo SA bonus on double attack
        shinjo_sa_note = ""
        if atk_is_shinjo and shinjo_sa_bonus > 0:
            total += shinjo_sa_bonus
            held_phases = 10 - (shinjo_die_value if shinjo_die_value is not None else phase)
            shinjo_sa_note = f" (shinjo SA: +{shinjo_sa_bonus} held {held_phases} phases)"

        success = total >= tn

        # Matsu 4th Dan: near-miss double attack still hits
        if atk_is_matsu and atk_dan_matsu >= 4 and not success and total >= tn - 20:
            success = True
            is_near_miss_da = True

        void_note = f" ({da_void_label})" if da_void_label else ""
        fifth_note = (
            f" (mirumoto: +{fifth_dan_combat_bonus} 5th Dan)"
            if fifth_dan_combat_bonus > 0 else ""
        )
        near_miss_note = (
            " (matsu 4th Dan: near-miss hit, base damage only)"
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
                f"{near_miss_note}{shinjo_sa_note}"
            ),
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
            atk_avail = _total_void(
                void_points, temp_void, attacker_name,
            )
            if atk_void_spend > 0 and atk_avail >= atk_void_spend:
                atk_from_temp, atk_from_reg = _spend_void(
                    void_points, temp_void,
                    attacker_name, atk_void_spend,
                )
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
            fifth_note = (
                f" (mirumoto: +{fifth_dan_combat_bonus} 5th Dan)"
                if fifth_dan_combat_bonus > 0 else ""
            )
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

    # Ability 5: Free crippled reroll on attack (before void reroll)
    if attacker_crippled:
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
        atk_void_avail = _total_void(
            void_points, temp_void, attacker_name,
        )
        if has_tens and atk_void_avail > 0 and max_void_spend > 0:
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
            attack_action.description += f" (wave man: +{5 * ab1_rank} on miss)"

    # 3rd Dan Mirumoto: post-roll +2 per point on attack
    if atk_is_mirumoto and atk_dan >= 3 and not attack_action.success:
        dan_bonus_pts = _compute_dan_roll_bonus(
            attack_action.total, tn, dan_points.get(attacker_name, 0),
        )
        if dan_bonus_pts > 0:
            attack_action.total += dan_bonus_pts * 2
            attack_action.success = attack_action.total >= tn
            dan_points[attacker_name] -= dan_bonus_pts
            attack_action.description += (
                f" (3rd dan: +{dan_bonus_pts * 2} bonus,"
                f" {dan_bonus_pts} pts)"
            )

    # Kakita 3rd Dan: phase gap attack bonus (applies to all attack types)
    if atk_is_kakita and atk_dan_kakita >= 3:
        defender_actions = sorted(actions_remaining.get(defender_name, []))
        defender_future = [a for a in defender_actions if a > phase]
        defender_next = defender_future[0] if defender_future else 11
        gap = defender_next - phase
        kakita_bonus = atk_rank * gap
        if kakita_bonus > 0:
            attack_action.total += kakita_bonus
            attack_action.success = attack_action.total >= tn
            phase_word = 'phase' if gap == 1 else 'phases'
            attack_action.description += (
                f" (kakita 3rd Dan: +{kakita_bonus},"
                f" {gap} {phase_word})"
            )

    attack_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )
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
    raw_rolled = (
        preview_weapon_rolled + attacker.rings.fire.value
        + no_parry_extra + lunge_preview_bonus
    )
    pool_display = _format_pool_with_overflow(raw_rolled, weapon.kept)
    da_wound_note = " plus 1 automatic serious wound" if is_double_attack else ""
    attack_action.description += f" — damage will be {pool_display}{da_wound_note}"

    # --- Defender attempts parry ---
    parry_attempted = False
    parry_succeeded = False

    # Ability 2: Parry TN increase
    ab2_bonus = 5 * attacker.ability_rank(2)

    # Determine if defender can and should parry
    can_parry = False
    is_phase_shift = False
    phase_shift_die = 0
    phase_shift_cost = 0
    is_interrupt = False
    attacker_weapon: Weapon = attacker_info["weapon"]

    if predeclared:
        # Pre-declared: die already consumed, always parry
        can_parry = True
    elif def_is_shinjo and has_action_in_phase and def_parry_rank > 0:
        # Shinjo reactive parry: only parry if 2+ dice remain (keep ≥1 for phase 10 attack)
        # Unless near mortal wound, then always parry
        wound_info = log.wounds[defender_name]
        near_mortal = (
            wound_info.serious_wounds >= 2 * wound_info.earth_ring - 1
        )
        if len(actions_remaining[defender_name]) > 1 or near_mortal:
            can_parry = True
        # Shinjo never interrupts
    elif has_action_in_phase and def_parry_rank > 0:
        if parry_auto_succeeds:
            # Ability 1: guaranteed success — always worth spending 1 die
            can_parry = True
        else:
            # Reactive regular parry (1 die) — threshold depends on school
            can_parry = _should_reactive_parry(
                def_parry_rank, defender.rings.air.value,
                attack_action.total, tn,
                attacker_weapon.rolled, attacker.rings.fire.value,
                log.wounds[defender_name].serious_wounds,
                log.wounds[defender_name].earth_ring,
                log.wounds[defender_name].is_crippled,
                is_kakita=def_is_kakita,
                is_mirumoto=def_is_mirumoto,
                known_bonus=def_parry_known_bonus,
            )
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
    if not can_parry and not def_is_shinjo and (
        not has_action_in_phase
        and len(actions_remaining[defender_name]) >= 2
        and def_parry_rank > 0
    ):
        if parry_auto_succeeds:
            # Ability 1: guaranteed success — worth spending 2 dice only if damage is meaningful
            extra_dice = max(0, (attack_action.total - (base_tn if is_double_attack else tn)) // 5)
            damage_rolled = attacker_weapon.rolled + attacker.rings.fire.value + extra_dice
            can_parry = damage_rolled > 6
            is_interrupt = can_parry
        else:
            # Reactive interrupt decision (2 dice) — higher threshold than regular parry
            should_interrupt = _should_interrupt_parry(
                def_parry_rank, defender.rings.air.value,
                attack_action.total, tn,
                attacker_weapon.rolled, attacker.rings.fire.value,
                len(actions_remaining[defender_name]),
                log.wounds[defender_name].serious_wounds,
                log.wounds[defender_name].earth_ring,
                is_kakita=def_is_kakita,
                is_mirumoto=def_is_mirumoto,
                known_bonus=def_parry_known_bonus,
            )
            if should_interrupt:
                can_parry = True
                is_interrupt = True

    shinjo_parry_die_value = 0  # Track which die Shinjo spent on parry (for SA bonus)
    if can_parry and def_parry_rank > 0:
        parry_attempted = True

        # For Shinjo predeclared parries, die was already consumed above
        if def_is_shinjo and predeclared:
            shinjo_parry_die_value = shinjo_parry_predeclare_die

        # Consume dice for the parry
        if def_is_shinjo and not is_interrupt and not predeclared:
            # Shinjo: spend highest eligible die (value ≤ phase) — smallest held bonus
            eligible = [d for d in actions_remaining[defender_name] if d <= phase]
            die_to_spend = max(eligible)
            actions_remaining[defender_name].remove(die_to_spend)
            shinjo_parry_die_value = die_to_spend
        elif is_phase_shift:
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
            if def_is_mirumoto:
                temp_void[defender_name] = temp_void.get(defender_name, 0) + 1
                parry_action.description += " (mirumoto SA: +1 temp void)"
            parry_action.status_after = _snapshot_status(
                log, fighters, actions_remaining, void_points,
                dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
            )
            log.add_action(parry_action)
            return

        air_value = defender.rings.air.value
        parry_rolled = def_parry_rank + air_value
        parry_kept = air_value

        # First Dan Mirumoto defender: +1 rolled die on parry
        if def_is_mirumoto and def_dan >= 1:
            parry_rolled += 1
        # First Dan Shinjo defender: +1 rolled die on parry
        if def_is_shinjo and def_dan_shinjo >= 1:
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

        # Second Dan Shinjo defender: free raise (+5) on parry
        if def_is_shinjo and def_dan_shinjo >= 2:
            parry_bonus += 5
            parry_bonus_note += " (shinjo 2nd Dan: free raise +5)"

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
            def_void_avail = _total_void(
                void_points, temp_void, defender_name,
            )
            if def_parry_void_spend > 0 and def_void_avail >= def_parry_void_spend:
                pv_from_temp, pv_from_reg = _spend_void(
                    void_points, temp_void,
                    defender_name, def_parry_void_spend,
                )
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
            def_crip_void = _total_void(
                void_points, temp_void, defender_name,
            )
            if has_tens and def_crip_void > 0 and max_void_spend > 0:
                all_dice, kept_dice, parry_total = reroll_tens(
                    all_dice, parry_kept,
                )
                pcr_from_temp, pcr_from_reg = _spend_void(
                    void_points, temp_void, defender_name, 1,
                )
                pcr_label = "temp void" if pcr_from_temp else "void"
                parry_bonus_note += f" ({pcr_label}: rerolled 10s)"
                # Matsu 3rd Dan: crippled parry reroll void spending generates bonus
                if def_is_matsu and def_dan_matsu >= 3:
                    def_atk_s = defender.get_skill("Attack")
                    def_atk_r = def_atk_s.rank if def_atk_s else 0
                    bonus_value = 3 * def_atk_r
                    matsu_bonuses[defender_name].append(bonus_value)

        effective_parry_total = parry_total + parry_bonus

        # Shinjo SA bonus on parry
        if def_is_shinjo and shinjo_parry_die_value > 0:
            shinjo_parry_sa = 2 * (phase - shinjo_parry_die_value)
            if shinjo_parry_sa > 0:
                effective_parry_total += shinjo_parry_sa
                held = phase - shinjo_parry_die_value
                parry_bonus_note += (
                    f" (shinjo SA: +{shinjo_parry_sa},"
                    f" held {held} phases)"
                )

        # 3rd Dan Mirumoto: post-roll +2 per point on parry
        if def_is_mirumoto and def_dan >= 3 and effective_parry_total < parry_tn:
            dan_parry_pts = _compute_dan_roll_bonus(
                effective_parry_total, parry_tn, dan_points.get(defender_name, 0),
                is_parry=True,
            )
            if dan_parry_pts > 0:
                effective_parry_total += dan_parry_pts * 2
                dan_points[defender_name] -= dan_parry_pts
                parry_bonus_note += (
                    f" (3rd dan: +{dan_parry_pts * 2} bonus,"
                    f" {dan_parry_pts} pts)"
                )

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
        # Mirumoto special ability: temp void on parry attempt (success or fail)
        if def_is_mirumoto:
            temp_void[defender_name] = temp_void.get(defender_name, 0) + 1
            parry_action.description += " (mirumoto SA: +1 temp void)"

        # Shinjo 3rd Dan: decrease remaining dice by attack skill after parry (success or fail)
        if def_is_shinjo and def_dan_shinjo >= 3 and parry_attempted:
            atk_skill_def = defender.get_skill("Attack")
            decrease = atk_skill_def.rank if atk_skill_def else 0
            if decrease > 0 and actions_remaining[defender_name]:
                actions_remaining[defender_name] = sorted(
                    d - decrease for d in actions_remaining[defender_name]
                )
                parry_action.description += f" (shinjo 3rd Dan: dice decreased by {decrease})"

        # Shinjo 5th Dan: store parry margin as wound check bonus
        if def_is_shinjo and def_dan_shinjo >= 5 and parry_succeeded:
            margin = effective_parry_total - parry_tn
            if margin > 0:
                shinjo_bonuses[defender_name].append(margin)
                parry_action.description += f" (shinjo 5th Dan: +{margin} wound check bonus stored)"

        parry_action.status_after = _snapshot_status(
            log, fighters, actions_remaining, void_points,
            dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
        )
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
                full_rolled = (
                    preview_weapon_rolled + attacker.rings.fire.value
                    + all_extra + lunge_preview_bonus
                )
                reduced_rolled = (
                    preview_weapon_rolled + attacker.rings.fire.value
                    + reduced_extra + lunge_preview_bonus
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

    extra_dmg = extra_dice + da_extra_rolled + lunge_damage_bonus
    damage_action = roll_damage(
        attacker, boosted_rolled, weapon.kept, extra_dmg,
    )
    damage_action.phase = phase
    damage_action.target = defender_name
    # Show overflow conversion in damage dice pool
    dmg_rolled = (
        boosted_rolled + attacker.rings.fire.value
        + extra_dice + da_extra_rolled + lunge_damage_bonus
    )
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
    damage_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )

    # --- Wound check ---
    water_value = defender.rings.water.value

    # Matsu 3rd Dan: check if stored matsu bonuses can pass the wound check before deciding void
    wc_tn_estimate = wound_tracker.light_wounds
    matsu_bonus_note = ""
    shinjo_bonus_note = ""
    skip_void_for_matsu = False
    if def_is_matsu and def_dan_matsu >= 3 and matsu_bonuses[defender_name]:
        # Check if any stored bonus can plausibly help — if so, save void
        for bonus in matsu_bonuses[defender_name]:
            if bonus >= wc_tn_estimate * 0.3:
                skip_void_for_matsu = True
                break

    # Shinjo 5th Dan: skip void only when the bonus pool is large
    # enough to plausibly cover the entire wound check on its own.
    # Bonuses are applied after the roll, so void still helps the
    # base roll — only skip when the pool makes void unnecessary.
    skip_void_for_shinjo = False
    if def_is_shinjo and def_dan_shinjo >= 5 and shinjo_bonuses[defender_name]:
        shinjo_pool_total = sum(shinjo_bonuses[defender_name])
        if shinjo_pool_total >= wc_tn_estimate:
            skip_void_for_shinjo = True

    # Compute wound check bonuses before void decision so they inform the decision
    ab7_extra = 2 * defender.ability_rank(7)
    matsu_wc_extra = 1 if def_is_matsu and def_dan_matsu >= 1 else 0
    ab10_bonus = 5 * attacker.ability_rank(10)

    # Decide how many void points to spend
    max_spend = defender.rings.lowest()
    if skip_void_for_matsu or skip_void_for_shinjo:
        void_spend = 0
    else:
        wc_void_avail = _total_void(
            void_points, temp_void, defender_name,
        )
        void_spend = _should_spend_void_on_wound_check(
            water_value, wound_tracker.light_wounds, wc_void_avail,
            max_spend=max_spend,
            extra_rolled=ab7_extra + matsu_wc_extra,
            tn_bonus=ab10_bonus,
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

    sw_before_wc = wound_tracker.serious_wounds

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

    # Shinjo 5th Dan: apply stored parry margin bonuses after seeing
    # the wound check result.  Select the minimum set of bonuses that
    # minimises the serious wound count.
    if def_is_shinjo and def_dan_shinjo >= 5 and not passed and shinjo_bonuses[defender_name]:
        base_tn = wound_tracker.light_wounds  # base TN (no ab10)
        raw_deficit = base_tn - wc_total
        used = _select_shinjo_wc_bonuses(
            raw_deficit, shinjo_bonuses[defender_name],
        )
        if used:
            bonus_applied = sum(used)
            wc_total += bonus_applied
            # Remove spent bonuses from the pool
            remaining = list(shinjo_bonuses[defender_name])
            for b in used:
                remaining.remove(b)
            shinjo_bonuses[defender_name][:] = remaining
            # Recalculate serious wounds: undo what make_wound_check
            # added and recompute with the boosted total.
            sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
            new_deficit = base_tn - wc_total
            if new_deficit <= 0:
                new_sw = 0
                passed = True
            else:
                new_sw = 1 + (new_deficit // 10)
            wound_tracker.serious_wounds += (new_sw - sw_added_by_wc)
            bonus_str = ", ".join(f"+{b}" for b in used)
            total_str = f" = +{bonus_applied}" if len(used) > 1 else ""
            if passed:
                shinjo_bonus_note += (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" wound check passes)"
                )
            else:
                sw_saved = sw_added_by_wc - new_sw
                shinjo_bonus_note += (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" {sw_saved} serious wound"
                    f"{'s' if sw_saved != 1 else ''}"
                    f" prevented)"
                )

    void_note = f" ({wc_void_label})" if wc_void_label else ""

    # Record the TN before any conversion modifies light_wounds
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn + ab10_bonus

    # Feature 3: Wound check success choice
    convert_note = ""
    if passed:
        shinjo_pool = (
            sum(shinjo_bonuses[defender_name])
            if def_is_shinjo and def_dan_shinjo >= 5
            else 0
        )
        should_convert = _should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            shinjo_wc_bonus_pool=shinjo_pool,
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
    wc_rolled = water_value + 1 + ab7_extra + matsu_wc_extra + void_spend
    wc_kept = water_value + void_spend
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
            f"(rolled {wc_total}){void_note}{matsu_bonus_note}{shinjo_bonus_note}"
            f"{convert_note}{da_auto_sw_note}{ab10_note}"
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
    wc_action.status_after = _snapshot_status(
        log, fighters, actions_remaining, void_points,
        dan_points, temp_void, matsu_bonuses, shinjo_bonuses,
    )
