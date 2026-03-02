"""Tests for stance discernment phase."""

from __future__ import annotations

from unittest.mock import patch

from src.engine.simulation import simulate_combat
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.combat import ActionType
from tests.conftest import KATANA, make_character


def _make_char(
    name: str,
    air: int = 2,
    fire: int = 2,
    xp_total: int = 150,
    iaijutsu_rank: int | None = None,
) -> Character:
    """Helper to create a character with specific stats for stance tests."""
    skills = [
        Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
    ]
    if iaijutsu_rank is not None:
        skills.append(
            Skill(
                name="Iaijutsu", rank=iaijutsu_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        )
    return Character(
        name=name,
        rings=Rings(
            air=Ring(name=RingName.AIR, value=air),
            fire=Ring(name=RingName.FIRE, value=fire),
            earth=Ring(name=RingName.EARTH, value=2),
            water=Ring(name=RingName.WATER, value=2),
            void=Ring(name=RingName.VOID, value=2),
        ),
        skills=skills,
        xp_total=xp_total,
    )


def test_stance_actions_in_combat_log() -> None:
    """simulate_combat produces 2 STANCE actions before any INITIATIVE actions."""
    char_a = make_character("Alice")
    char_b = make_character("Bob")

    log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_actions = [a for a in log.actions if a.action_type == ActionType.STANCE]
    assert len(stance_actions) == 2

    # STANCE actions must come before INITIATIVE actions
    first_init_idx = next(
        i for i, a in enumerate(log.actions) if a.action_type == ActionType.INITIATIVE
    )
    for i, a in enumerate(log.actions):
        if a.action_type == ActionType.STANCE:
            assert i < first_init_idx


def test_stance_fire_discernment_exact() -> None:
    """When floor(roll/5) >= opponent Fire, learn exact Fire value."""
    char_a = _make_char("Alice", air=3)
    char_b = _make_char("Bob", fire=3)

    # Alice rolls 25 -> floor(25/5) = 5 >= 3 -> "Fire 3"
    with patch("src.engine.simulation.roll_and_keep") as mock_rak:
        mock_rak.return_value = ([10, 8, 7], [10, 8, 7], 25)
        log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_a = [
        a for a in log.actions
        if a.action_type == ActionType.STANCE and a.actor == "Alice"
    ][0]
    assert "Fire 3" in stance_a.description
    assert "Fire ~" not in stance_a.description


def test_stance_fire_discernment_approximate() -> None:
    """When floor(roll/5) < opponent Fire, learn lower bound."""
    char_a = _make_char("Alice", air=3)
    char_b = _make_char("Bob", fire=4)

    # Alice rolls 12 -> floor(12/5) = 2 < 4 -> "Fire ~2"
    with patch("src.engine.simulation.roll_and_keep") as mock_rak:
        mock_rak.return_value = ([6, 4, 2], [6, 4, 2], 12)
        log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_a = [
        a for a in log.actions
        if a.action_type == ActionType.STANCE and a.actor == "Alice"
    ][0]
    assert "Fire ~2" in stance_a.description


def test_stance_tn_discernment_success() -> None:
    """When roll >= opponent TN, learn 'TN >= {actual_TN}'."""
    char_a = _make_char("Alice", air=3)
    char_b = _make_char("Bob", xp_total=150)  # TN = 150 // 10 = 15

    # Alice rolls 20 >= 15 -> "TN >= 15"
    with patch("src.engine.simulation.roll_and_keep") as mock_rak:
        mock_rak.return_value = ([10, 6, 4], [10, 6, 4], 20)
        log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_a = [
        a for a in log.actions
        if a.action_type == ActionType.STANCE and a.actor == "Alice"
    ][0]
    assert "TN >= 15" in stance_a.description


def test_stance_tn_discernment_failure() -> None:
    """When roll < opponent TN, learn 'TN >= {roll}'."""
    char_a = _make_char("Alice", air=3)
    char_b = _make_char("Bob", xp_total=150)  # TN = 15

    # Alice rolls 10 < 15 -> "TN >= 10"
    with patch("src.engine.simulation.roll_and_keep") as mock_rak:
        mock_rak.return_value = ([5, 3, 2], [5, 3, 2], 10)
        log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_a = [
        a for a in log.actions
        if a.action_type == ActionType.STANCE and a.actor == "Alice"
    ][0]
    assert "TN >= 10" in stance_a.description


def test_stance_dice_pool_no_iaijutsu() -> None:
    """Character with no Iaijutsu rolls AirkAir."""
    char_a = _make_char("Alice", air=2)  # No Iaijutsu
    char_b = _make_char("Bob")

    with patch("src.engine.simulation.roll_and_keep") as mock_rak:
        mock_rak.return_value = ([5, 3], [5, 3], 8)
        log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_a = [
        a for a in log.actions
        if a.action_type == ActionType.STANCE and a.actor == "Alice"
    ][0]
    assert stance_a.dice_pool == "2k2"


def test_stance_dice_pool_with_iaijutsu() -> None:
    """Air 3 + Iaijutsu 3 -> 6k3."""
    char_a = _make_char("Alice", air=3, iaijutsu_rank=3)
    char_b = _make_char("Bob")

    with patch("src.engine.simulation.roll_and_keep") as mock_rak:
        mock_rak.return_value = ([8, 6, 5, 4, 3, 2], [8, 6, 5], 19)
        log = simulate_combat(char_a, char_b, KATANA, KATANA, max_rounds=1, is_duel=True)

    stance_a = [
        a for a in log.actions
        if a.action_type == ActionType.STANCE and a.actor == "Alice"
    ][0]
    assert stance_a.dice_pool == "6k3"
