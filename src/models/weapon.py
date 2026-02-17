"""Weapon models for the L7R combat system."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class WeaponType(str, Enum):
    KATANA = "katana"
    WAKIZASHI = "wakizashi"
    SPEAR = "spear"
    KNIFE = "knife"
    UNARMED = "unarmed"


class Weapon(BaseModel):
    """A weapon with base damage dice."""

    name: str
    weapon_type: WeaponType
    rolled: int = Field(ge=0)
    kept: int = Field(ge=1)

    @property
    def dice_str(self) -> str:
        """Human-readable dice notation like '4k2'."""
        return f"{self.rolled}k{self.kept}"


WEAPONS: dict[WeaponType, Weapon] = {
    WeaponType.KATANA: Weapon(
        name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2
    ),
    WeaponType.WAKIZASHI: Weapon(
        name="Wakizashi", weapon_type=WeaponType.WAKIZASHI, rolled=3, kept=2
    ),
    WeaponType.SPEAR: Weapon(
        name="Spear", weapon_type=WeaponType.SPEAR, rolled=3, kept=2
    ),
    WeaponType.KNIFE: Weapon(
        name="Knife", weapon_type=WeaponType.KNIFE, rolled=2, kept=2
    ),
    WeaponType.UNARMED: Weapon(
        name="Unarmed", weapon_type=WeaponType.UNARMED, rolled=0, kept=2
    ),
}
