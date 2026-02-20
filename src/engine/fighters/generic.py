"""GenericFighter: default behavior for characters with no school (Wave Man)."""

from __future__ import annotations

from src.engine.fighters.base import Fighter


class GenericFighter(Fighter):
    """Fighter with no school-specific overrides.

    All behavior comes from the base Fighter defaults.
    """
