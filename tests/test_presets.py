"""Tests for preset characters."""

from src.engine.presets import PRESETS, get_preset, list_preset_names
from src.models.weapon import WeaponType


class TestPresets:
    def test_six_presets_exist(self) -> None:
        assert len(PRESETS) == 6

    def test_all_presets_pass_validation(self) -> None:
        """All presets are valid Pydantic Character models."""
        for name, (char, _weapon_type) in PRESETS.items():
            assert char.name == name

    def test_all_have_attack_skill(self) -> None:
        for _name, (char, _wt) in PRESETS.items():
            skill = char.get_skill("Attack")
            assert skill is not None, f"{char.name} missing Attack skill"
            assert skill.rank >= 2

    def test_all_have_parry_skill(self) -> None:
        for _name, (char, _wt) in PRESETS.items():
            skill = char.get_skill("Parry")
            assert skill is not None, f"{char.name} missing Parry skill"
            assert skill.rank >= 2

    def test_school_ring_is_boosted(self) -> None:
        for _name, (char, _wt) in PRESETS.items():
            assert char.school_ring is not None, f"{char.name} has no school_ring"
            ring_val = char.rings.get(char.school_ring).value
            assert ring_val >= 3, f"{char.name} school ring {char.school_ring} is {ring_val}"

    def test_all_have_weapon(self) -> None:
        for _name, (_char, wt) in PRESETS.items():
            assert isinstance(wt, WeaponType)

    def test_get_preset_by_name(self) -> None:
        char, wt = get_preset("Akodo Taro")
        assert char.name == "Akodo Taro"

    def test_get_preset_case_insensitive(self) -> None:
        char, wt = get_preset("akodo taro")
        assert char.name == "Akodo Taro"

    def test_get_preset_not_found(self) -> None:
        result = get_preset("Nonexistent")
        assert result is None

    def test_list_preset_names(self) -> None:
        names = list_preset_names()
        assert len(names) == 6
        assert all(isinstance(n, str) for n in names)
