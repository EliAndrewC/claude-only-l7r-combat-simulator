"""Dice rolling engine for the L7R system.

Core mechanic: Roll X 10-sided dice, keep Y highest.
- 10s explode (reroll and add) unless at skill rank 0 or crippled.
- When rolled dice exceed 10, each excess converts to one extra kept die.
- When kept dice exceed 10, each excess adds a flat +2 bonus.
"""

from __future__ import annotations

import random


def roll_die(explode: bool = True) -> int:
    """Roll a single d10, exploding on 10 if allowed.

    Args:
        explode: Whether to reroll and add on a 10.

    Returns:
        The total value of the die roll.
    """
    total = 0
    while True:
        roll = random.randint(1, 10)
        total += roll
        if roll != 10 or not explode:
            break
    return total


def roll_and_keep(
    rolled: int,
    kept: int,
    explode: bool = True,
) -> tuple[list[int], list[int], int]:
    """Roll X dice and keep Y highest.

    Overflow rules (per 02-skills.md):
    - When rolled dice exceed 10, each excess becomes one extra kept die.
    - When kept dice exceed 10, each excess adds a flat +2 bonus.

    Args:
        rolled: Number of dice to roll.
        kept: Number of dice to keep (highest).
        explode: Whether 10s explode.

    Returns:
        Tuple of (all_dice, kept_dice, total).
    """
    bonus = 0

    effective_rolled = rolled
    effective_kept = kept

    # Step 1: excess rolled dice convert to extra kept dice
    if effective_rolled > 10:
        effective_kept += effective_rolled - 10
        effective_rolled = 10

    # Step 2: excess kept dice beyond 10 convert to flat +2 bonus each
    if effective_kept > 10:
        bonus += (effective_kept - 10) * 2
        effective_kept = 10

    effective_kept = min(effective_kept, effective_rolled)

    all_dice = sorted([roll_die(explode=explode) for _ in range(effective_rolled)], reverse=True)
    kept_dice = all_dice[:effective_kept]
    total = sum(kept_dice) + bonus

    return all_dice, kept_dice, total


def reroll_tens(
    all_dice: list[int],
    kept_count: int,
    max_reroll: int | None = None,
) -> tuple[list[int], list[int], int]:
    """Reroll any dice showing exactly 10 with explosion enabled.

    Used when a crippled character spends void to reroll 10s.

    Args:
        all_dice: All dice from the original roll (descending order).
        kept_count: Number of dice to keep (highest).
        max_reroll: Maximum number of 10s to reroll. None means reroll all.

    Returns:
        Tuple of (all_dice, kept_dice, total) after rerolling 10s.
    """
    rerolled = 0
    new_dice: list[int] = []
    for d in all_dice:
        if d == 10 and (max_reroll is None or rerolled < max_reroll):
            new_dice.append(roll_die(explode=True))
            rerolled += 1
        else:
            new_dice.append(d)

    new_dice.sort(reverse=True)
    kept_dice = new_dice[:kept_count]
    total = sum(kept_dice)
    return new_dice, kept_dice, total
