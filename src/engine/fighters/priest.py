"""PriestFighter: Priest school-specific overrides.

SA: Has all 10 rituals (non-combat, no-op).
1st Dan: +1 die on precepts, 1 skill, and 1 type of combat roll.
         (We choose wound checks for the combat roll.)
2nd Dan: Free raise on Honor bonus rolls (non-combat, no-op).
3rd Dan: Dice swap pool (deferred).
4th Dan: Water +1 (builder). Free raise on contested rolls vs equal/higher
         skill (complex, minimal combat impact).
5th Dan: Conviction pool refreshes per round (non-combat focused).
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter


class PriestFighter(Fighter):
    """Priest fighter — minimal combat hooks.

    Most abilities are non-combat. In 1v1, the main benefit is
    1st Dan +1 die on wound checks.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

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
