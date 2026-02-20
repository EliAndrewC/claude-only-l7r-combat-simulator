"""Tests for GenericFighter (Wave Man / no school) default behavior."""

from __future__ import annotations

from src.engine.fighters import create_fighter
from src.engine.fighters.generic import GenericFighter
from tests.conftest import make_character, make_combat_state


class TestGenericFighterDefaults:
    """GenericFighter uses all base class defaults."""

    def test_factory_returns_generic_for_no_school(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = create_fighter("A", state)
        assert isinstance(fighter, GenericFighter)

    def test_initiative_extra_unkept_zero(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.initiative_extra_unkept() == 0

    def test_attack_extra_rolled_zero(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.attack_extra_rolled() == 0

    def test_parry_bonus_zero(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.parry_bonus() == 0

    def test_can_interrupt_true(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.can_interrupt() is True

    def test_has_no_special_phase(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.has_phase0_action() is False
        assert fighter.has_phase10_action() is False

    def test_fifth_dan_void_bonus_zero(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.fifth_dan_void_bonus(2) == 0

    def test_damage_parry_reduction_full(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.damage_parry_reduction(4) == 4

    def test_on_near_miss_da_false(self) -> None:
        a = make_character("A")
        b = make_character("B")
        state = make_combat_state(a, b)
        fighter = GenericFighter("A", state)
        assert fighter.on_near_miss_da() is False
