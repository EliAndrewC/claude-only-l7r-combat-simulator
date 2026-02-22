"""KitsukiFighter: Kitsuki Magistrate school-specific overrides.

SA: Add 2x Water to all attack rolls.
1st Dan: +1 rolled die on wound check rolls.
2nd Dan: Free raise on interrogation (non-combat, no-op).
3rd Dan: 2X free raises per adventure (X = investigation), for attack and WC.
4th Dan: Water +1 (builder). Know opponent's stats (informational, no-op).
5th Dan: Reduce opponent's Air, Fire, and Water by 1.
"""

from __future__ import annotations

import math

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class KitsukiFighter(Fighter):
    """Kitsuki Magistrate fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        investigation_skill = self.char.get_skill("Investigation")
        investigation_rank = investigation_skill.rank if investigation_skill else 0
        self._free_raises = 2 * investigation_rank if self.dan >= 3 else 0
        self._max_per_roll = investigation_rank if self.dan >= 3 else 0

        # 5th Dan: Debuff applied to opponent at combat start
        self._debuff_applied = False

        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Kitsuki uses normal attacks (non-combat knacks)."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """No extra rolled die on attacks (1st Dan is WC only)."""
        return 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Void spending with known SA bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        known_bonus = 2 * self.char.rings.water.value
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=known_bonus,
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """SA: +2x Water to all attack rolls."""
        bonus = 2 * self.char.rings.water.value
        return bonus, f" (kitsuki SA: +{bonus} from 2x Water)"

    # -- 3rd Dan: Free raise pool -------------------------------------------

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str,
    ) -> tuple[int, str]:
        """3rd Dan: Spend free raises to bridge attack deficit."""
        if self.dan < 3 or self._free_raises <= 0:
            return 0, ""

        deficit = tn - attack_total
        if deficit <= 0:
            return 0, ""

        raises_needed = math.ceil(deficit / 5)
        usable = min(self._max_per_roll, self._free_raises)
        if raises_needed > usable:
            return 0, ""

        self._free_raises -= raises_needed
        bonus = raises_needed * 5
        note = (
            f" (kitsuki 3rd Dan: {raises_needed} free raise(s)"
            f" +{bonus}, {self._free_raises} remaining)"
        )
        return bonus, note

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
        """3rd Dan: Spend free raises to reduce SW on failed WC."""
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
            f" (kitsuki 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- 5th Dan: Ring debuff -----------------------------------------------

    def apply_5th_dan_debuff(self, opponent_name: str) -> str:
        """5th Dan: Reduce opponent's Air, Fire, Water by 1.

        Called at combat start. Modifies opponent's character rings directly.
        """
        if self.dan < 5 or self._debuff_applied:
            return ""

        opponent = self.state.fighters.get(opponent_name)
        if opponent is None:
            return ""

        opp_char = opponent.char
        rings_debuffed: list[str] = []
        if opp_char.rings.air.value > 1:
            opp_char.rings.air.value -= 1
            rings_debuffed.append("Air")
        if opp_char.rings.fire.value > 1:
            opp_char.rings.fire.value -= 1
            rings_debuffed.append("Fire")
        if opp_char.rings.water.value > 1:
            opp_char.rings.water.value -= 1
            rings_debuffed.append("Water")

        self._debuff_applied = True
        if rings_debuffed:
            return (
                f" (kitsuki 5th Dan: {opponent_name}'s"
                f" {', '.join(rings_debuffed)} reduced by 1)"
            )
        return ""
