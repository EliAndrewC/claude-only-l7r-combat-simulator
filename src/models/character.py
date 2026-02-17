"""Pydantic models for characters, rings, and skills."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RingName(str, Enum):
    AIR = "Air"
    FIRE = "Fire"
    EARTH = "Earth"
    WATER = "Water"
    VOID = "Void"


class Ring(BaseModel):
    """A single Ring with a value between 1 and 6."""

    name: RingName
    value: int = Field(default=2, ge=1, le=6)


class Rings(BaseModel):
    """The five Rings that define a character."""

    air: Ring = Field(default_factory=lambda: Ring(name=RingName.AIR))
    fire: Ring = Field(default_factory=lambda: Ring(name=RingName.FIRE))
    earth: Ring = Field(default_factory=lambda: Ring(name=RingName.EARTH))
    water: Ring = Field(default_factory=lambda: Ring(name=RingName.WATER))
    void: Ring = Field(default_factory=lambda: Ring(name=RingName.VOID))

    def lowest(self) -> int:
        """Return the value of the lowest ring."""
        return min(r.value for r in [self.air, self.fire, self.earth, self.water, self.void])

    def get(self, name: RingName) -> Ring:
        """Get a ring by name."""
        return getattr(self, name.value.lower())


class SkillType(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"


class Skill(BaseModel):
    """A character skill with rank 0-5."""

    name: str
    rank: int = Field(default=0, ge=0, le=5)
    skill_type: SkillType = SkillType.BASIC
    ring: RingName = RingName.AIR  # Associated ring for rolls


class Character(BaseModel):
    """A complete character in the L7R system."""

    name: str
    rings: Rings = Field(default_factory=Rings)
    skills: list[Skill] = Field(default_factory=list)
    school: Optional[str] = None
    school_ring: Optional[RingName] = None
    honor: float = Field(default=1.0, ge=1.0, le=5.0)
    recognition: int = Field(default=0, ge=0)
    xp_total: int = Field(default=150, ge=0)
    xp_spent: int = Field(default=0, ge=0)
    void_points: int = Field(default=0, ge=0)

    @property
    def void_points_max(self) -> int:
        """Max void points equals the lowest ring value."""
        return self.rings.lowest()

    @property
    def rank(self) -> int:
        """Character rank based on recognition and XP."""
        return max(1, self.recognition)

    def get_skill(self, name: str) -> Optional[Skill]:
        """Find a skill by name (case-insensitive)."""
        for skill in self.skills:
            if skill.name.lower() == name.lower():
                return skill
        return None
