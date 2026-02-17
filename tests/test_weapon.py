"""Tests for the Weapon model."""

from src.models.weapon import WEAPONS, Weapon, WeaponType


class TestWeaponType:
    def test_all_weapon_types_exist(self) -> None:
        assert WeaponType.KATANA
        assert WeaponType.WAKIZASHI
        assert WeaponType.SPEAR
        assert WeaponType.KNIFE
        assert WeaponType.UNARMED


class TestWeapon:
    def test_weapon_creation(self) -> None:
        w = Weapon(name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2)
        assert w.name == "Katana"
        assert w.rolled == 4
        assert w.kept == 2

    def test_weapon_display(self) -> None:
        w = Weapon(name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2)
        assert w.dice_str == "4k2"


class TestWeaponsDict:
    def test_katana_is_4k2(self) -> None:
        w = WEAPONS[WeaponType.KATANA]
        assert w.rolled == 4 and w.kept == 2

    def test_wakizashi_is_3k2(self) -> None:
        w = WEAPONS[WeaponType.WAKIZASHI]
        assert w.rolled == 3 and w.kept == 2

    def test_spear_is_3k2(self) -> None:
        w = WEAPONS[WeaponType.SPEAR]
        assert w.rolled == 3 and w.kept == 2

    def test_knife_is_2k2(self) -> None:
        w = WEAPONS[WeaponType.KNIFE]
        assert w.rolled == 2 and w.kept == 2

    def test_unarmed_is_0k2(self) -> None:
        w = WEAPONS[WeaponType.UNARMED]
        assert w.rolled == 0 and w.kept == 2

    def test_all_weapon_types_have_entry(self) -> None:
        for wt in WeaponType:
            assert wt in WEAPONS
