"""IsawaIshiFighter: Isawa Ishi school-specific overrides.

SA: Max void = highest ring + school rank. Regain lowest ring per rest.
    Max void per roll = lowest ring - 1.
1st Dan: +1 die on precepts and two chosen skills (non-combat).
2nd Dan: Free raise on chosen skill (non-combat).
3rd Dan: Spend void to add Xk1 to another character's roll (no-op in 1v1).
4th Dan: Void +1 (builder). Opponents can't spend void in contested rolls
         (complex, tracked as informational).
5th Dan: Negate another character's school (extremely powerful but complex).
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter


class IsawaIshiFighter(Fighter):
    """Isawa Ishi fighter — mostly non-combat, minimal hooks.

    In 1v1, this school functions as a generic fighter with modified void
    rules. Most abilities are non-combat or require allies.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # SA: Max void = highest ring + school_rank
        # Override max void if the SA formula is higher
        highest_ring = max(
            self.char.rings.air.value,
            self.char.rings.fire.value,
            self.char.rings.earth.value,
            self.char.rings.water.value,
            self.char.rings.void.value,
        )
        self._ishi_max_void = highest_ring + self.dan
        # SA: Max void per roll = lowest ring - 1
        self._max_void_per_roll = max(0, self.char.rings.lowest() - 1)
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Isawa Ishi uses normal attacks."""
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """No combat-relevant extra rolled die."""
        return 0

    def wound_check_extra_rolled(self) -> int:
        """No extra rolled die on WC."""
        return 0
