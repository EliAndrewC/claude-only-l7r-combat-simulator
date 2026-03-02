"""TogashiFighter: Togashi Ise Zumi school-specific overrides.

SA: Roll 1 or 3 extra initiative dice. If 1, only for athletics; if 3, all
    dice only for athletics. In 1v1, always pick 1 (wasted athletics die).
1st Dan: +1 rolled die on attack, parry, and athletics rolls.
2nd Dan: Free raise on athletics (non-combat, no-op).
3rd Dan: Free raises for athletics (non-combat, no-op).
4th Dan: Ring +1 (builder). Reroll any contested roll once (post_roll_modify).
5th Dan: Spend 1 void to heal 2 serious wounds.
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class TogashiFighter(Fighter):
    """Togashi Ise Zumi fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._5th_dan_healed_this_round = False

    # -- Round hooks --------------------------------------------------------

    def on_round_start(self) -> None:
        """Reset per-round healing flag."""
        self._5th_dan_healed_this_round = False

    # -- SA: Extra initiative die (athletics-only, effectively wasted) -------

    def initiative_extra_unkept(self) -> int:
        """SA: Roll 1 extra initiative die (athletics-only, improves quality)."""
        return 1

    # -- 1st Dan: +1 die on attack and parry --------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Togashi uses normal attacks."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

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

    def parry_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on parry."""
        return 1 if self.dan >= 1 else 0

    # -- 5th Dan: Heal serious wounds ----------------------------------------

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """5th Dan: Spend void to heal 2 SW if in danger."""
        if self.dan < 5 or self._5th_dan_healed_this_round:
            return passed, wc_total, ""

        wound_tracker = self.state.log.wounds[self.name]
        earth = wound_tracker.earth_ring
        if wound_tracker.serious_wounds < earth:
            return passed, wc_total, ""

        if self.total_void <= 0:
            return passed, wc_total, ""

        self.spend_void(1)
        heal = min(2, wound_tracker.serious_wounds)
        wound_tracker.serious_wounds -= heal
        self._5th_dan_healed_this_round = True
        note = f" (togashi 5th Dan: spent 1 void, healed {heal} SW)"
        return passed, wc_total, note

    def wound_check_extra_rolled(self) -> int:
        """No extra rolled die on WC."""
        return 0
