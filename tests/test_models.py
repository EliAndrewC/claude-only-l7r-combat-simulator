"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from src.models.character import Character, Ring, RingName, Rings, Skill
from src.models.combat import ActionType, CombatAction, CombatLog, FighterStatus, WoundTracker
from src.models.school import Knack, School, Technique


class TestRings:
    def test_default_rings_are_2(self) -> None:
        rings = Rings()
        assert rings.air.value == 2
        assert rings.fire.value == 2
        assert rings.earth.value == 2
        assert rings.water.value == 2
        assert rings.void.value == 2

    def test_lowest_ring(self) -> None:
        rings = Rings(air=Ring(name=RingName.AIR, value=3))
        assert rings.lowest() == 2

    def test_get_ring_by_name(self) -> None:
        rings = Rings(fire=Ring(name=RingName.FIRE, value=4))
        assert rings.get(RingName.FIRE).value == 4

    def test_ring_value_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Ring(name=RingName.AIR, value=0)
        with pytest.raises(ValidationError):
            Ring(name=RingName.AIR, value=7)


class TestCharacter:
    def test_default_character(self) -> None:
        c = Character(name="Test Samurai")
        assert c.name == "Test Samurai"
        assert c.xp_total == 150
        assert c.void_points_max == 2

    def test_get_skill_found(self) -> None:
        c = Character(
            name="Akodo",
            skills=[Skill(name="Kenjutsu", rank=3, ring=RingName.FIRE)],
        )
        s = c.get_skill("kenjutsu")
        assert s is not None
        assert s.rank == 3

    def test_get_skill_not_found(self) -> None:
        c = Character(name="Akodo")
        assert c.get_skill("ninjutsu") is None

    def test_void_points_max_follows_lowest_ring(self) -> None:
        c = Character(
            name="Test",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=3),
                fire=Ring(name=RingName.FIRE, value=4),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=3),
                void=Ring(name=RingName.VOID, value=5),
            ),
        )
        assert c.void_points_max == 2


class TestWoundTracker:
    def test_not_crippled_by_default(self) -> None:
        wt = WoundTracker()
        assert not wt.is_crippled
        assert not wt.is_mortally_wounded

    def test_crippled_at_earth_serious(self) -> None:
        wt = WoundTracker(serious_wounds=2, earth_ring=2)
        assert wt.is_crippled

    def test_mortally_wounded_at_double_earth(self) -> None:
        wt = WoundTracker(serious_wounds=4, earth_ring=2)
        assert wt.is_mortally_wounded

    def test_crippled_but_not_mortal(self) -> None:
        wt = WoundTracker(serious_wounds=3, earth_ring=3)
        assert wt.is_crippled
        assert not wt.is_mortally_wounded


class TestCombatLog:
    def test_add_action(self) -> None:
        log = CombatLog(combatants=["A", "B"])
        action = CombatAction(
            phase=1,
            actor="A",
            action_type=ActionType.ATTACK,
            description="A attacks B",
        )
        log.add_action(action)
        assert len(log.actions) == 1
        assert log.actions[0].actor == "A"


class TestFighterStatus:
    def test_defaults(self) -> None:
        fs = FighterStatus()
        assert fs.light_wounds == 0
        assert fs.serious_wounds == 0
        assert fs.is_crippled is False
        assert fs.is_mortally_wounded is False
        assert fs.actions_remaining == []
        assert fs.void_points == 0
        assert fs.void_points_max == 0

    def test_custom_values(self) -> None:
        fs = FighterStatus(
            light_wounds=5,
            serious_wounds=2,
            is_crippled=True,
            actions_remaining=[3, 7],
            void_points_max=3,
        )
        assert fs.light_wounds == 5
        assert fs.serious_wounds == 2
        assert fs.is_crippled is True
        assert fs.actions_remaining == [3, 7]
        assert fs.void_points_max == 3


class TestCombatActionDicePool:
    def test_dice_pool_defaults_to_empty(self) -> None:
        action = CombatAction(
            phase=1, actor="A", action_type=ActionType.ATTACK,
        )
        assert action.dice_pool == ""

    def test_dice_pool_stores_value(self) -> None:
        action = CombatAction(
            phase=1, actor="A", action_type=ActionType.ATTACK, dice_pool="6k3",
        )
        assert action.dice_pool == "6k3"


class TestCombatActionStatusAfter:
    def test_status_after_defaults_to_none(self) -> None:
        action = CombatAction(
            phase=1,
            actor="A",
            action_type=ActionType.ATTACK,
        )
        assert action.status_after is None

    def test_status_after_accepts_dict(self) -> None:
        status = {
            "A": FighterStatus(light_wounds=3, actions_remaining=[4, 8]),
            "B": FighterStatus(serious_wounds=1, is_crippled=True),
        }
        action = CombatAction(
            phase=1,
            actor="A",
            action_type=ActionType.ATTACK,
            status_after=status,
        )
        assert action.status_after is not None
        assert action.status_after["A"].light_wounds == 3
        assert action.status_after["B"].is_crippled is True


class TestSchool:
    def test_school_creation(self) -> None:
        school = School(
            name="Akodo Bushi",
            school_ring=RingName.WATER,
            knacks=[Knack(name="Feint")],
            techniques=[Technique(rank=1, name="The Way of the Lion")],
        )
        assert school.name == "Akodo Bushi"
        assert school.school_ring == RingName.WATER
        assert len(school.knacks) == 1
