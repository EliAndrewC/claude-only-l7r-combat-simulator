"""Tests for the school registry module."""

from __future__ import annotations

from src.engine.school_registry import (
    SCHOOL_BUILDERS,
    SCHOOL_DEFAULT_WEAPONS,
    get_combat_schools,
)
from src.models.character import Character
from src.models.weapon import WeaponType


class TestSchoolBuilders:
    def test_all_schools_present(self) -> None:
        expected_schools = {
            "Akodo Bushi", "Bayushi Bushi", "Brotherhood Monk",
            "Courtier", "Daidoji Yojimbo", "Doji Artisan",
            "Hida Bushi", "Hiruma Scout", "Ide Diplomat",
            "Ikoma Bard", "Isawa Duelist", "Isawa Ishi",
            "Kakita Duelist", "Kitsuki Magistrate", "Kuni Witch Hunter",
            "Matsu Bushi", "Merchant", "Mirumoto Bushi",
            "Otaku Bushi", "Priest", "Shiba Bushi",
            "Shinjo Bushi", "Shosuro Actor", "Togashi Ise Zumi",
            "Wave Man", "Yogo Warden",
        }
        assert set(SCHOOL_BUILDERS.keys()) == expected_schools

    def test_builders_produce_valid_characters(self) -> None:
        for school_name, builder in SCHOOL_BUILDERS.items():
            char = builder(school_name, 0, 0.20)
            assert isinstance(char, Character), f"{school_name} builder didn't return Character"
            assert char.name == school_name

    def test_builders_with_earned_xp(self) -> None:
        for school_name, builder in SCHOOL_BUILDERS.items():
            char = builder(school_name, 100, 0.20)
            assert isinstance(char, Character), f"{school_name} builder failed with 100 XP"
            assert char.xp_total == 250  # 150 base + 100 earned

    def test_builders_with_custom_non_combat_pct(self) -> None:
        for school_name, builder in SCHOOL_BUILDERS.items():
            char = builder(school_name, 50, 0.10)
            assert isinstance(char, Character), (
                f"{school_name} builder failed with non_combat_pct=0.10"
            )


class TestSchoolDefaultWeapons:
    def test_all_schools_have_default_weapon(self) -> None:
        for school_name in SCHOOL_BUILDERS:
            assert school_name in SCHOOL_DEFAULT_WEAPONS, (
                f"{school_name} missing from SCHOOL_DEFAULT_WEAPONS"
            )

    def test_wave_man_uses_spear(self) -> None:
        assert SCHOOL_DEFAULT_WEAPONS["Wave Man"] == WeaponType.SPEAR

    def test_brotherhood_monk_uses_unarmed(self) -> None:
        assert SCHOOL_DEFAULT_WEAPONS["Brotherhood Monk"] == WeaponType.UNARMED

    def test_most_schools_use_katana(self) -> None:
        katana_expected = {
            "Akodo Bushi", "Bayushi Bushi", "Courtier",
            "Daidoji Yojimbo", "Doji Artisan", "Hida Bushi",
            "Hiruma Scout", "Ide Diplomat", "Ikoma Bard",
            "Isawa Duelist", "Isawa Ishi", "Kakita Duelist",
            "Kitsuki Magistrate", "Kuni Witch Hunter",
            "Matsu Bushi", "Merchant", "Mirumoto Bushi",
            "Otaku Bushi", "Priest", "Shiba Bushi",
            "Shinjo Bushi", "Shosuro Actor", "Togashi Ise Zumi",
            "Yogo Warden",
        }
        for school in katana_expected:
            assert SCHOOL_DEFAULT_WEAPONS[school] == WeaponType.KATANA, (
                f"{school} should default to KATANA"
            )


class TestGetCombatSchools:
    def test_returns_list_of_strings(self) -> None:
        schools = get_combat_schools()
        assert isinstance(schools, list)
        assert all(isinstance(s, str) for s in schools)

    def test_returns_all_schools(self) -> None:
        schools = get_combat_schools()
        assert set(schools) == set(SCHOOL_BUILDERS.keys())

    def test_returns_sorted(self) -> None:
        schools = get_combat_schools()
        assert schools == sorted(schools)
