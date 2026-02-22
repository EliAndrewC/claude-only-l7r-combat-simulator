"""DojiArtisanFighter: Doji Artisan school-specific overrides.

SA: Spend void to counterattack as interrupt for 1 die; void gives +1k1.
    Counterattack bonus = attacker's roll / 5.
1st Dan: +1 rolled die on counterattack, manipulation, and wound checks.
2nd Dan: Free raise on manipulation (non-combat, no-op).
3rd Dan: 2X free raises (X = culture skill), for counterattack and WC.
4th Dan: Water +1 (builder). When attacking a target who hasn't attacked you
         this round, bonus = current phase.
5th Dan: On any TN or contested roll, bonus = (TN - 10) / 5 (min 0).
"""

from __future__ import annotations

import math

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class DojiArtisanFighter(Fighter):
    """Doji Artisan fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        culture_skill = self.char.get_skill("Culture")
        culture_rank = culture_skill.rank if culture_skill else 0
        self._free_raises = 2 * culture_rank if self.dan >= 3 else 0
        self._max_per_roll = culture_rank if self.dan >= 3 else 0
        self._opponent_attacked_this_round = False
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Round hooks --------------------------------------------------------

    def on_round_start(self) -> None:
        """Reset per-round tracking."""
        self._opponent_attacked_this_round = False

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Doji Artisan uses normal attacks (CA is defensive/interrupt)."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """No extra die on normal attacks (1st Dan is CA/manipulation/WC)."""
        return 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Standard void spending."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """4th Dan: +phase bonus when target hasn't attacked this round.
        5th Dan: +(TN - 10) / 5 bonus.
        """
        bonus = 0
        notes: list[str] = []

        if self.dan >= 4 and not self._opponent_attacked_this_round:
            bonus += phase
            notes.append(f"doji 4th Dan: +{phase} (phase bonus)")

        note = f" ({'; '.join(notes)})" if notes else ""
        return bonus, note

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str,
    ) -> tuple[int, str]:
        """5th Dan: +(TN - 10) / 5 bonus on attack. 3rd Dan: free raises."""
        total_bonus = 0
        notes: list[str] = []

        if self.dan >= 5 and tn > 10:
            fifth_bonus = (tn - 10) // 5
            if fifth_bonus > 0:
                total_bonus += fifth_bonus
                notes.append(f"doji 5th Dan: +{fifth_bonus}")

        # 3rd Dan: free raises to bridge deficit
        if self.dan >= 3 and self._free_raises > 0:
            deficit = tn - (attack_total + total_bonus)
            if deficit > 0:
                raises_needed = math.ceil(deficit / 5)
                usable = min(self._max_per_roll, self._free_raises)
                if raises_needed <= usable:
                    self._free_raises -= raises_needed
                    raise_bonus = raises_needed * 5
                    total_bonus += raise_bonus
                    notes.append(
                        f"doji 3rd Dan: {raises_needed} free raise(s)"
                        f" +{raise_bonus}, {self._free_raises} remaining"
                    )

        note = f" ({'; '.join(notes)})" if notes else ""
        return total_bonus, note

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wc_bonus_pool_total(self) -> int:
        """3rd Dan: Remaining free raise pool for WC."""
        if self.dan >= 3:
            usable = min(self._free_raises, self._max_per_roll)
            return usable * 5
        return 0

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: Spend free raises on failed WC. Track opponent attacked."""
        self._opponent_attacked_this_round = True

        if self.dan < 3 or self._free_raises <= 0 or passed:
            return passed, wc_total, ""

        wound_tracker = self.state.log.wounds[self.name]
        base_tn = wound_tracker.light_wounds
        deficit = base_tn - wc_total
        if deficit <= 0:
            return passed, wc_total, ""

        earth = wound_tracker.earth_ring
        current_sw = 1 + deficit // 10
        would_die = (sw_before_wc + current_sw >= 2 * earth)

        usable = min(self._max_per_roll, self._free_raises)
        best_sw = current_sw
        best_spend = 0

        for spend in range(1, usable + 1):
            new_deficit = deficit - spend * 5
            if new_deficit <= 0:
                if would_die:
                    if spend < best_spend or best_sw > 0:
                        best_sw = 0
                        best_spend = spend
                break
            new_sw = 1 + new_deficit // 10
            if new_sw < best_sw:
                best_sw = new_sw
                best_spend = spend

        if best_spend <= 0 or best_sw >= current_sw:
            return passed, wc_total, ""

        self._free_raises -= best_spend
        bonus = best_spend * 5
        new_total = wc_total + bonus
        new_deficit = base_tn - new_total

        sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
        if new_deficit <= 0:
            new_sw_count = 0
            new_passed = True
        else:
            new_sw_count = 1 + new_deficit // 10
            new_passed = False
        wound_tracker.serious_wounds += (new_sw_count - sw_added_by_wc)

        note = (
            f" (doji 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note
