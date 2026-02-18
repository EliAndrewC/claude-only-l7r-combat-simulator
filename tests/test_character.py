"""Tests for Character model profession abilities."""

import pytest
from pydantic import ValidationError

from src.models.character import Character, ProfessionAbility, RingName, Skill, SkillType


class TestProfessionAbilityValidation:
    def test_valid_ability(self) -> None:
        ab = ProfessionAbility(number=1, rank=1)
        assert ab.number == 1
        assert ab.rank == 1

    def test_rank_defaults_to_1(self) -> None:
        ab = ProfessionAbility(number=5)
        assert ab.rank == 1

    def test_rank_2_valid(self) -> None:
        ab = ProfessionAbility(number=10, rank=2)
        assert ab.rank == 2

    def test_number_below_1_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ProfessionAbility(number=0, rank=1)

    def test_number_above_10_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ProfessionAbility(number=11, rank=1)

    def test_rank_above_2_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ProfessionAbility(number=1, rank=3)

    def test_rank_below_1_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ProfessionAbility(number=1, rank=0)


class TestAbilityRank:
    def test_returns_0_for_no_abilities(self) -> None:
        char = Character(name="Test")
        assert char.ability_rank(1) == 0

    def test_returns_rank_for_existing_ability(self) -> None:
        char = Character(
            name="Test",
            profession_abilities=[ProfessionAbility(number=4, rank=2)],
        )
        assert char.ability_rank(4) == 2

    def test_returns_0_for_missing_ability(self) -> None:
        char = Character(
            name="Test",
            profession_abilities=[ProfessionAbility(number=1, rank=1)],
        )
        assert char.ability_rank(5) == 0

    def test_multiple_abilities(self) -> None:
        char = Character(
            name="Test",
            profession_abilities=[
                ProfessionAbility(number=1, rank=2),
                ProfessionAbility(number=4, rank=1),
                ProfessionAbility(number=7, rank=1),
            ],
        )
        assert char.ability_rank(1) == 2
        assert char.ability_rank(4) == 1
        assert char.ability_rank(7) == 1
        assert char.ability_rank(10) == 0


class TestDanProperty:
    def test_dan_no_knacks(self) -> None:
        """Dan is 0 when character has no school knacks."""
        char = Character(name="Test")
        assert char.dan == 0

    def test_dan_with_knacks(self) -> None:
        """Dan equals minimum knack skill rank."""
        char = Character(
            name="Test",
            school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
            skills=[
                Skill(
                    name="Counterattack", rank=3,
                    skill_type=SkillType.ADVANCED,
                    ring=RingName.FIRE,
                ),
                Skill(
                    name="Double Attack", rank=3,
                    skill_type=SkillType.ADVANCED,
                    ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=3,
                    skill_type=SkillType.ADVANCED,
                    ring=RingName.FIRE,
                ),
            ],
        )
        assert char.dan == 3

    def test_dan_mixed_ranks(self) -> None:
        """Dan equals the minimum when knacks have different ranks."""
        char = Character(
            name="Test",
            school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
            skills=[
                Skill(
                    name="Counterattack", rank=4,
                    skill_type=SkillType.ADVANCED,
                    ring=RingName.FIRE,
                ),
                Skill(
                    name="Double Attack", rank=2,
                    skill_type=SkillType.ADVANCED,
                    ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED,
                    ring=RingName.FIRE,
                ),
            ],
        )
        assert char.dan == 2
