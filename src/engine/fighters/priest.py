"""PriestFighter: Priest school-specific overrides.

SA: Has all 10 rituals (non-combat, no-op).
1st Dan: +1 die on precepts, 1 skill, and 1 type of combat roll.
         (We choose wound checks for the combat roll.)
2nd Dan: Free raise on Honor bonus rolls (non-combat, no-op).
3rd Dan: Dice swap pool from Precepts rank.
4th Dan: Water +1 (builder). Free raise on contested rolls vs equal/higher
         skill (complex, minimal combat impact).
5th Dan: Conviction pool refreshes per round (non-combat focused).
"""

from __future__ import annotations

from src.engine.dice import roll_die
from src.engine.fighters.base import Fighter


class PriestFighter(Fighter):
    """Priest fighter — dice pool at 3rd Dan.

    Most abilities are non-combat. In 1v1, the main benefits are
    1st Dan +1 die on wound checks and 3rd Dan dice swap pool.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

        # 3rd Dan: dice swap pool
        precepts = self.char.get_skill("Precepts")
        precepts_rank = precepts.rank if precepts else 0
        self._dice_pool: list[int] = []
        if self.dan >= 3 and precepts_rank > 0:
            self._dice_pool = sorted(
                [roll_die(explode=True) for _ in range(precepts_rank)],
                reverse=True,
            )

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Priest uses normal attacks."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """No extra die on attacks."""
        return 0

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    # -- Post-roll modify (3rd Dan dice pool) --------------------------------

    def post_roll_modify(
        self,
        all_dice: list[int],
        kept_count: int,
        total: int,
        tn: int,
        context: str,
        explode: bool = True,
    ) -> tuple[list[int], list[int], int, int, str]:
        """3rd Dan: swap dice from pool to improve rolls.

        Three phases:
        1. Free swaps on unkept dice
        2. Downgrade kept dice to refresh pool (context-sensitive)
        3. Spend pool dice to improve outcome

        Returns (all_dice, kept_dice, new_total, void_spent, note).
        """
        if not self._dice_pool:
            kept_dice = sorted(all_dice, reverse=True)[:kept_count]
            return all_dice, kept_dice, total, 0, ""

        pool = list(self._dice_pool)
        dice = sorted(all_dice, reverse=True)
        original_total = total

        # Phase 1: Free swaps on unkept dice
        new_total = self._phase1_free_swaps(dice, kept_count, pool)

        # Phase 2: Downgrade kept dice to refresh pool
        new_total = self._phase2_downgrade_kept(
            dice, kept_count, pool, new_total, tn, context,
        )

        # Phase 3: Spend pool dice to improve outcome
        new_total = self._phase3_spend_pool(
            dice, kept_count, pool, new_total, tn, context,
        )

        # Commit pool changes
        self._dice_pool = pool

        dice.sort(reverse=True)
        kept_dice = dice[:kept_count]
        final_total = sum(kept_dice)

        if final_total == original_total and dice == sorted(all_dice, reverse=True):
            return all_dice, kept_dice, original_total, 0, ""

        note = f" (priest pool: {original_total}\u2192{final_total})"
        return dice, kept_dice, final_total, 0, note

    # -- Phase helpers -------------------------------------------------------

    def _phase1_free_swaps(
        self, dice: list[int], kept_count: int, pool: list[int],
    ) -> int:
        """Phase 1: swap pool dice with unkept dice for free improvement."""
        for i in range(kept_count, len(dice)):
            if not pool:
                break
            unkept_val = dice[i]
            if pool[0] > unkept_val:
                # High pool die replaces low unkept die (potential upgrade)
                dice[i], pool[0] = pool[0], unkept_val
                pool.sort(reverse=True)
            elif unkept_val > pool[-1]:
                # High unkept die goes to pool (refresh), low pool die into roll
                dice[i], pool[-1] = pool[-1], unkept_val
                pool.sort(reverse=True)

        dice.sort(reverse=True)
        return sum(dice[:kept_count])

    def _phase2_downgrade_kept(
        self,
        dice: list[int],
        kept_count: int,
        pool: list[int],
        new_total: int,
        tn: int,
        context: str,
    ) -> int:
        """Phase 2: downgrade kept dice to refresh pool when functionally free."""
        if context == "damage":
            return new_total
        if context == "parry" and new_total < tn:
            return new_total

        made_swap = True
        while made_swap:
            made_swap = False
            dice.sort(reverse=True)
            for i in range(kept_count - 1, -1, -1):
                kept_val = dice[i]
                # Highest pool die lower than this kept die
                best_j = None
                for j in range(len(pool)):
                    if pool[j] < kept_val:
                        best_j = j
                        break
                if best_j is None:
                    continue

                # Simulate swap
                trial_dice = list(dice)
                trial_dice[i] = pool[best_j]
                trial_dice.sort(reverse=True)
                trial_total = sum(trial_dice[:kept_count])

                if self._can_downgrade(context, trial_total, tn, new_total):
                    old_kept = dice[i]
                    dice[:] = trial_dice
                    pool[best_j] = old_kept
                    pool.sort(reverse=True)
                    new_total = trial_total
                    made_swap = True
                    break

        return new_total

    @staticmethod
    def _can_downgrade(
        context: str, trial_total: int, tn: int, current_total: int,
    ) -> bool:
        """Check if downgrading a kept die is functionally free."""
        if context == "attack":
            if current_total < tn or trial_total < tn:
                return False
            old_raises = (current_total - tn) // 5
            new_raises = (trial_total - tn) // 5
            return new_raises >= old_raises

        if context == "wound_check":
            if current_total >= tn:
                return trial_total >= tn
            # Failing: SW count must not increase
            old_sw = 1 + (tn - current_total) // 10
            new_sw = 1 + (tn - trial_total) // 10
            return new_sw <= old_sw

        if context == "parry":
            # Only called when currently passing (failing parry skipped above)
            return trial_total >= tn

        return False

    def _phase3_spend_pool(
        self,
        dice: list[int],
        kept_count: int,
        pool: list[int],
        new_total: int,
        tn: int,
        context: str,
    ) -> int:
        """Phase 3: spend pool dice to improve outcome."""
        if not pool or kept_count == 0:
            return new_total

        dice.sort(reverse=True)

        if context == "attack" and new_total < tn:
            return self._spend_pool_attack(dice, kept_count, pool, new_total, tn)

        if context == "wound_check" and new_total < tn:
            return self._spend_pool_wound_check(
                dice, kept_count, pool, new_total, tn,
            )

        return new_total

    @staticmethod
    def _spend_pool_attack(
        dice: list[int],
        kept_count: int,
        pool: list[int],
        new_total: int,
        tn: int,
    ) -> int:
        """Spend pool die to turn a miss into a hit."""
        for i in range(kept_count - 1, -1, -1):
            needed = tn - (new_total - dice[i])
            # Smallest pool die >= needed (pool sorted descending)
            best_j = None
            for j in range(len(pool)):
                if pool[j] >= needed:
                    best_j = j
                else:
                    break
            if best_j is not None:
                old_die = dice[i]
                dice[i] = pool[best_j]
                pool[best_j] = old_die
                pool.sort(reverse=True)
                dice.sort(reverse=True)
                return sum(dice[:kept_count])
        return new_total

    def _spend_pool_wound_check(
        self,
        dice: list[int],
        kept_count: int,
        pool: list[int],
        new_total: int,
        tn: int,
    ) -> int:
        """Spend pool die to reduce SW or pass wound check."""
        wounds = self.state.log.wounds[self.name]
        current_sw = wounds.serious_wounds
        pending_sw = 1 + (tn - new_total) // 10
        mortal_threshold = wounds.mortal_wound_threshold
        would_be_mortal = (current_sw + pending_sw) >= mortal_threshold

        if pending_sw < 2 and not would_be_mortal:
            return new_total

        # Replace lowest kept die with highest pool die
        i = kept_count - 1
        if pool[0] > dice[i]:
            old_die = dice[i]
            dice[i] = pool[0]
            pool[0] = old_die
            pool.sort(reverse=True)
            dice.sort(reverse=True)
            return sum(dice[:kept_count])

        return new_total
