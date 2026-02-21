"""Mutable combat state containers.

CombatState holds the shared combat log and fighter instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models.combat import CombatLog, FighterStatus


@dataclass
class CombatState:
    """All shared mutable state for one combat encounter."""

    log: CombatLog
    fighters: dict[str, Any] = field(default_factory=dict)

    def get_opponent(self, name: str) -> str:
        """Return the opponent's name."""
        names = list(self.fighters.keys())
        return names[1] if names[0] == name else names[0]

    def is_mortally_wounded(self, name: str) -> bool:
        """Check if a combatant is mortally wounded."""
        return self.log.wounds[name].is_mortally_wounded

    def snapshot_status(self) -> dict[str, FighterStatus]:
        """Build a snapshot of each fighter's current state."""
        result: dict[str, FighterStatus] = {}
        for name in self.log.combatants:
            wt = self.log.wounds[name]
            fighter = self.fighters[name]
            result[name] = FighterStatus(
                light_wounds=wt.light_wounds,
                serious_wounds=wt.serious_wounds,
                is_crippled=wt.is_crippled,
                is_mortally_wounded=wt.is_mortally_wounded,
                actions_remaining=list(fighter.actions_remaining),
                void_points=fighter.void_points,
                void_points_max=fighter.char.void_points_max,
                temp_void_points=fighter.temp_void,
                worldliness_void_points=fighter.worldliness_void,
                dan_points=fighter.dan_points,
                matsu_bonuses=list(fighter.matsu_bonuses),
                shinjo_bonuses=list(fighter.shinjo_bonuses),
            )
        return result
