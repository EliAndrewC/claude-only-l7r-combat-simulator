"""Preset characters for quick combat simulation."""

from __future__ import annotations

from typing import Optional

from src.models.character import Character, Ring, RingName, Rings, Skill, SkillType
from src.models.weapon import WeaponType


def _make_rings(
    air: int = 2, fire: int = 2, earth: int = 2, water: int = 2, void: int = 2
) -> Rings:
    return Rings(
        air=Ring(name=RingName.AIR, value=air),
        fire=Ring(name=RingName.FIRE, value=fire),
        earth=Ring(name=RingName.EARTH, value=earth),
        water=Ring(name=RingName.WATER, value=water),
        void=Ring(name=RingName.VOID, value=void),
    )


PRESETS: dict[str, tuple[Character, WeaponType]] = {
    "Akodo Taro": (
        Character(
            name="Akodo Taro",
            school="Akodo Bushi",
            school_ring=RingName.WATER,
            rings=_make_rings(air=2, fire=2, earth=2, water=3, void=2),
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            ],
        ),
        WeaponType.KATANA,
    ),
    "Kakita Yuri": (
        Character(
            name="Kakita Yuri",
            school="Kakita Duelist",
            school_ring=RingName.FIRE,
            rings=_make_rings(air=2, fire=3, earth=2, water=2, void=2),
            skills=[
                Skill(name="Attack", rank=4, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            ],
        ),
        WeaponType.KATANA,
    ),
    "Hida Goro": (
        Character(
            name="Hida Goro",
            school="Hida Bushi",
            school_ring=RingName.WATER,
            rings=_make_rings(air=2, fire=2, earth=3, water=3, void=2),
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            ],
        ),
        WeaponType.KATANA,
    ),
    "Mirumoto Rei": (
        Character(
            name="Mirumoto Rei",
            school="Mirumoto Bushi",
            school_ring=RingName.VOID,
            rings=_make_rings(air=2, fire=2, earth=2, water=2, void=3),
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            ],
        ),
        WeaponType.KATANA,
    ),
    "Bayushi Kage": (
        Character(
            name="Bayushi Kage",
            school="Bayushi Bushi",
            school_ring=RingName.FIRE,
            rings=_make_rings(air=2, fire=3, earth=2, water=2, void=2),
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            ],
        ),
        WeaponType.KATANA,
    ),
    "Matsu Hana": (
        Character(
            name="Matsu Hana",
            school="Matsu Bushi",
            school_ring=RingName.FIRE,
            rings=_make_rings(air=2, fire=3, earth=2, water=2, void=2),
            skills=[
                Skill(name="Attack", rank=4, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            ],
        ),
        WeaponType.KATANA,
    ),
}


def get_preset(name: str) -> Optional[tuple[Character, WeaponType]]:
    """Get a preset by name (case-insensitive)."""
    for preset_name, value in PRESETS.items():
        if preset_name.lower() == name.lower():
            return value
    return None


def list_preset_names() -> list[str]:
    """Return all preset character names."""
    return list(PRESETS.keys())
