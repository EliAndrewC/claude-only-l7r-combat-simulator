"""Pydantic models for schools and knacks."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.character import RingName


class Knack(BaseModel):
    """A school knack (special ability)."""

    name: str
    description: str = ""


class Technique(BaseModel):
    """A school technique unlocked at a specific rank."""

    rank: int = Field(ge=1, le=5)
    name: str
    description: str = ""


class School(BaseModel):
    """A character school with its ring, knacks, and techniques."""

    name: str
    school_ring: RingName
    special_ability: str = ""
    knacks: list[Knack] = Field(default_factory=list)
    techniques: list[Technique] = Field(default_factory=list)
    is_samurai: bool = True
    npc_only: bool = False
