"""Pydantic models for characters, rings, and skills."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Advantage(str, Enum):
    GREAT_DESTINY = "Great Destiny"
    PERMANENT_WOUND = "Permanent Wound"
    STRENGTH_OF_THE_EARTH = "Strength of the Earth"
    LUCKY = "Lucky"


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


class ProfessionAbility(BaseModel):
    """A single profession ability with rank 1-2."""

    number: int = Field(ge=1, le=10)
    rank: int = Field(default=1, ge=1, le=2)


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
    profession_abilities: list[ProfessionAbility] = Field(default_factory=list)
    school_knacks: list[str] = Field(default_factory=list)
    advantages: list[Advantage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_advantages(self) -> Character:
        has_gd = Advantage.GREAT_DESTINY in self.advantages
        has_pw = Advantage.PERMANENT_WOUND in self.advantages
        if has_gd and has_pw:
            msg = "Great Destiny and Permanent Wound are mutually exclusive"
            raise ValueError(msg)
        return self

    @property
    def dan(self) -> int:
        """Dan level: minimum rank among all school knacks, or 0 if none."""
        if not self.school_knacks:
            return 0
        ranks = []
        for name in self.school_knacks:
            skill = self.get_skill(name)
            ranks.append(skill.rank if skill else 0)
        return min(ranks) if ranks else 0

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

    def ability_rank(self, ability_number: int) -> int:
        """Return the rank of a profession ability, or 0 if not present."""
        for ab in self.profession_abilities:
            if ab.number == ability_number:
                return ab.rank
        return 0
