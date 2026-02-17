"""Pydantic models for combat tracking and logging."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    ATTACK = "attack"
    PARRY = "parry"
    INITIATIVE = "initiative"
    DAMAGE = "damage"
    WOUND_CHECK = "wound_check"
    IAIJUTSU = "iaijutsu"
    SPELL = "spell"
    INTERRUPT = "interrupt"


class WoundTracker(BaseModel):
    """Tracks wound state for a character in combat."""

    light_wounds: int = Field(default=0, ge=0)
    serious_wounds: int = Field(default=0, ge=0)
    earth_ring: int = Field(default=2, ge=1)

    @property
    def is_crippled(self) -> bool:
        """Crippled when serious wounds >= Earth Ring."""
        return self.serious_wounds >= self.earth_ring

    @property
    def is_mortally_wounded(self) -> bool:
        """Mortally wounded when serious wounds >= 2 * Earth Ring."""
        return self.serious_wounds >= 2 * self.earth_ring


class FighterStatus(BaseModel):
    """Snapshot of a fighter's state after a combat action."""

    light_wounds: int = 0
    serious_wounds: int = 0
    is_crippled: bool = False
    is_mortally_wounded: bool = False
    actions_remaining: list[int] = Field(default_factory=list)
    void_points: int = 0
    void_points_max: int = 0


class CombatAction(BaseModel):
    """A single action taken during combat."""

    phase: int = Field(ge=0, le=10)
    actor: str
    action_type: ActionType
    target: Optional[str] = None
    dice_rolled: list[int] = Field(default_factory=list)
    dice_kept: list[int] = Field(default_factory=list)
    total: int = 0
    tn: Optional[int] = None
    success: Optional[bool] = None
    description: str = ""
    dice_pool: str = ""
    status_after: Optional[dict[str, FighterStatus]] = None


class CombatLog(BaseModel):
    """Complete log of a combat encounter."""

    round_number: int = Field(default=1, ge=1)
    actions: list[CombatAction] = Field(default_factory=list)
    combatants: list[str] = Field(default_factory=list)
    wounds: dict[str, WoundTracker] = Field(default_factory=dict)
    winner: Optional[str] = None

    def add_action(self, action: CombatAction) -> None:
        """Append an action to the combat log."""
        self.actions.append(action)
