"""WaveManFighter: Wave Man profession ability overrides."""

from __future__ import annotations

import math

from src.engine.dice import reroll_tens
from src.engine.fighters.base import Fighter


class WaveManFighter(Fighter):
    """Fighter with Wave Man profession abilities.

    Overrides hook methods based on which abilities the character has
    (checked via ``self.char.ability_rank(N)``).

    Ability mapping:
      1  free raise on miss        → post_attack_miss_bonus
      2  raise parry TN            → attacker_parry_tn_bonus
      3  weapon damage boost       → weapon_rolled_boost
      4  round up damage           → damage_rounding
      5  crippled reroll           → crippled_reroll
      6  initiative boost          → initiative_extra_unkept
      7  wound check bonus         → wound_check_extra_rolled
      8  damage reduction          → damage_reduction
      9  failed parry bonus        → failed_parry_dice_recovery
      10 raise wound TN            → wound_check_tn_bonus
    """

    # -- Initiative hooks -----------------------------------------------

    def initiative_extra_unkept(self) -> int:
        """Ability 6: extra unkept dice on initiative."""
        return self.char.ability_rank(6)

    # -- Attack hooks ---------------------------------------------------

    def post_attack_miss_bonus(
        self, attack_total: int, tn: int,
    ) -> tuple[int, bool, str]:
        """Ability 1: add 5*rank on miss; if that succeeds, parry auto-succeeds."""
        rank = self.char.ability_rank(1)
        if rank <= 0:
            return 0, False, ""
        bonus = 5 * rank
        boosted = attack_total + bonus
        if boosted >= tn:
            return bonus, True, f" (wave man: +{bonus} on miss)"
        return 0, False, ""

    def attacker_parry_tn_bonus(self) -> int:
        """Ability 2: flat bonus to parry TN."""
        return 5 * self.char.ability_rank(2)

    def weapon_rolled_boost(self, weapon_rolled: int, weapon_kept: int) -> int:
        """Ability 3: boost weapon rolled dice if weapon < 4k2."""
        rank = self.char.ability_rank(3)
        if rank <= 0:
            return weapon_rolled
        if weapon_rolled < 4 or (weapon_rolled >= 4 and weapon_kept < 2):
            return min(weapon_rolled + rank, 4)
        return weapon_rolled

    def damage_rounding(self, damage_total: int) -> tuple[int, str]:
        """Ability 4: round up damage."""
        rank = self.char.ability_rank(4)
        if rank <= 0:
            return damage_total, ""
        original = damage_total
        total = damage_total
        for _ in range(rank):
            if total % 5 == 0:
                total += 3
            else:
                total = math.ceil(total / 5) * 5
        return total, f" (wave man: damage rounded {original} -> {total})"

    def crippled_reroll(
        self, all_dice: list[int], kept_count: int,
    ) -> tuple[list[int], list[int], int, str]:
        """Ability 5: free crippled reroll of 10s."""
        rank = self.char.ability_rank(5)
        tens_count = sum(1 for d in all_dice if d == 10)
        if rank > 0 and tens_count > 0:
            rerolled = min(tens_count, rank)
            all_dice, kept_dice, total = reroll_tens(
                all_dice, kept_count, max_reroll=rank,
            )
            tens_word = "ten" if rerolled == 1 else "tens"
            note = f" (crippled reroll: rerolled {rerolled} {tens_word})"
            return all_dice, kept_dice, total, note
        kept_dice = sorted(all_dice, reverse=True)[:kept_count]
        return all_dice, kept_dice, sum(kept_dice), ""

    # -- Wound check hooks (as defender) --------------------------------

    def wound_check_extra_rolled(self) -> int:
        """Ability 7: extra rolled dice on wound check."""
        return 2 * self.char.ability_rank(7)

    def damage_reduction(
        self, damage_total: int, had_extra_dice: bool,
    ) -> tuple[int, str]:
        """Ability 8: reduce incoming damage when attacker had extra dice."""
        rank = self.char.ability_rank(8)
        if rank <= 0 or not had_extra_dice:
            return damage_total, ""
        reduction = 5 * rank
        new_total = max(0, damage_total - reduction)
        return new_total, f" (wave man: -{reduction} damage reduction)"

    def failed_parry_dice_recovery(
        self, all_extra_dice: int, parry_reduction: int,
    ) -> int:
        """Ability 9: recover some removed extra dice after failed parry."""
        rank = self.char.ability_rank(9)
        if rank <= 0:
            return 0
        removed = min(all_extra_dice, parry_reduction)
        return min(removed, 2 * rank)

    def wound_check_tn_bonus(self) -> int:
        """Ability 10: flat bonus to wound check TN."""
        return 5 * self.char.ability_rank(10)
