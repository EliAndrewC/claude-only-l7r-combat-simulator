"""Tests for the skill check engine."""

from unittest.mock import patch

import pytest

from src.engine.skills import contested_roll, skill_roll, tn_check
from src.models.character import Character, Ring, RingName, Rings, Skill, SkillType


def _make_character(name: str, **ring_overrides: int) -> Character:
    """Helper to create a character with specific ring values."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    return Character(name=name, rings=Rings(**kwargs))


class TestSkillRoll:
    def test_basic_skill_roll(self) -> None:
        c = _make_character("Test", air=3)
        c.skills = [Skill(name="Etiquette", rank=2, ring=RingName.AIR)]
        with patch("src.engine.skills.roll_and_keep") as mock_rak:
            mock_rak.return_value = ([8, 6, 4, 3, 1], [8, 6, 4], 18)
            _, _, total = skill_roll(c, "Etiquette", RingName.AIR)
            # 2 (skill) + 3 (air) = 5 rolled, 3 kept
            mock_rak.assert_called_once_with(5, 3, explode=True)
            assert total == 18

    def test_skill_rank_0_no_explode(self) -> None:
        c = _make_character("Test", fire=2)
        with patch("src.engine.skills.roll_and_keep") as mock_rak:
            mock_rak.return_value = ([5, 3], [5, 3], 8)
            skill_roll(c, "Kenjutsu", RingName.FIRE)
            mock_rak.assert_called_once_with(2, 2, explode=False)

    def test_advanced_skill_rank_0_penalty(self) -> None:
        c = _make_character("Test", air=2)
        adv_skill = Skill(
            name="Commerce", rank=0, skill_type=SkillType.ADVANCED, ring=RingName.AIR,
        )
        c.skills = [adv_skill]
        with patch("src.engine.skills.roll_and_keep", return_value=([8, 5], [8, 5], 13)):
            _, _, total = skill_roll(c, "Commerce", RingName.AIR)
            assert total == 3  # 13 - 10

    def test_advanced_skill_rank_0_floors_at_zero(self) -> None:
        c = _make_character("Test", air=2)
        adv_skill = Skill(
            name="Commerce", rank=0, skill_type=SkillType.ADVANCED, ring=RingName.AIR,
        )
        c.skills = [adv_skill]
        with patch("src.engine.skills.roll_and_keep", return_value=([5, 3], [5, 3], 8)):
            _, _, total = skill_roll(c, "Commerce", RingName.AIR)
            assert total == 0  # 8 - 10, floored at 0

    def test_void_spend_adds_kept_dice(self) -> None:
        c = _make_character("Test", air=3)
        c.skills = [Skill(name="Etiquette", rank=2, ring=RingName.AIR)]
        with patch("src.engine.skills.roll_and_keep") as mock_rak:
            mock_rak.return_value = ([9, 8, 7, 5, 3], [9, 8, 7, 5], 29)
            skill_roll(c, "Etiquette", RingName.AIR, void_spend=1)
            # 5 rolled, 3 + 1 = 4 kept
            mock_rak.assert_called_once_with(5, 4, explode=True)

    def test_void_spend_exceeds_max_raises(self) -> None:
        c = _make_character("Test", air=2)
        with pytest.raises(ValueError, match="Cannot spend 3 void points"):
            skill_roll(c, "Etiquette", RingName.AIR, void_spend=3)


class TestTNCheck:
    def test_tn_check_pass(self) -> None:
        c = _make_character("Test", air=3)
        c.skills = [Skill(name="Etiquette", rank=3, ring=RingName.AIR)]
        mock_rv = ([9, 7, 5, 4, 2, 1], [9, 7, 5], 21)
        with patch("src.engine.skills.roll_and_keep", return_value=mock_rv):
            success, total = tn_check(c, "Etiquette", RingName.AIR, tn=15)
            assert success is True
            assert total == 21

    def test_tn_check_fail(self) -> None:
        c = _make_character("Test", air=2)
        c.skills = [Skill(name="Etiquette", rank=1, ring=RingName.AIR)]
        with patch("src.engine.skills.roll_and_keep", return_value=([4, 3, 1], [4, 3], 7)):
            success, total = tn_check(c, "Etiquette", RingName.AIR, tn=15)
            assert success is False


class TestContestedRoll:
    def test_higher_total_wins(self) -> None:
        a = _make_character("Akodo", air=3)
        b = _make_character("Bayushi", air=2)
        a.skills = [Skill(name="Sincerity", rank=2, ring=RingName.AIR)]
        b.skills = [Skill(name="Sincerity", rank=3, ring=RingName.AIR)]
        with patch("src.engine.skills.roll_and_keep", side_effect=[
            ([9, 7, 5, 4, 1], [9, 7, 5], 21),  # Akodo
            ([8, 6, 4, 3, 2], [8, 6], 14),       # Bayushi
        ]):
            winner, ta, tb = contested_roll(
                a, "Sincerity", RingName.AIR,
                b, "Sincerity", RingName.AIR,
            )
            assert winner == "Akodo"

    def test_tie_goes_to_first(self) -> None:
        a = _make_character("A", air=2)
        b = _make_character("B", air=2)
        with patch("src.engine.skills.roll_and_keep", side_effect=[
            ([5, 5], [5, 5], 10),
            ([5, 5], [5, 5], 10),
        ]):
            winner, _, _ = contested_roll(
                a, "Etiquette", RingName.AIR,
                b, "Etiquette", RingName.AIR,
            )
            assert winner == "A"
