"""Tests for CombatState and Fighter mutable state."""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from tests.conftest import make_character, make_combat_state


class TestFighterMutableState:
    """Tests for Fighter mutable state (total_void, spend_void)."""

    def test_total_void(self) -> None:
        char_a = make_character("A")
        char_b = make_character("B")
        state = make_combat_state(char_a, char_b, void_a=3)
        fighter = state.fighters["A"]
        fighter.temp_void = 2
        assert fighter.total_void == 5

    def test_spend_void_temp_first(self) -> None:
        char_a = make_character("A")
        char_b = make_character("B")
        state = make_combat_state(char_a, char_b, void_a=3)
        fighter = state.fighters["A"]
        fighter.temp_void = 2
        from_temp, from_reg, from_wl = fighter.spend_void(3)
        assert from_temp == 2
        assert from_reg == 1
        assert from_wl == 0
        assert fighter.temp_void == 0
        assert fighter.void_points == 2

    def test_spend_void_only_temp(self) -> None:
        char_a = make_character("A")
        char_b = make_character("B")
        state = make_combat_state(char_a, char_b, void_a=3)
        fighter = state.fighters["A"]
        fighter.temp_void = 2
        from_temp, from_reg, from_wl = fighter.spend_void(1)
        assert from_temp == 1
        assert from_reg == 0
        assert from_wl == 0
        assert fighter.temp_void == 1

    def test_spend_void_no_temp(self) -> None:
        char_a = make_character("A")
        char_b = make_character("B")
        state = make_combat_state(char_a, char_b, void_a=3)
        fighter = state.fighters["A"]
        from_temp, from_reg, from_wl = fighter.spend_void(2)
        assert from_temp == 0
        assert from_reg == 2
        assert from_wl == 0
        assert fighter.void_points == 1


class TestCombatState:
    """Tests for CombatState dataclass."""

    def test_get_opponent(self) -> None:
        a = make_character("Alice")
        b = make_character("Bob")
        state = make_combat_state(a, b)
        assert state.get_opponent("Alice") == "Bob"
        assert state.get_opponent("Bob") == "Alice"

    def test_is_mortally_wounded(self) -> None:
        a = make_character("Alice")
        b = make_character("Bob")
        state = make_combat_state(a, b)
        assert state.is_mortally_wounded("Alice") is False
        state.log.wounds["Alice"].serious_wounds = 4  # >= 2*earth(2)
        assert state.is_mortally_wounded("Alice") is True

    def test_snapshot_status(self) -> None:
        a = make_character("Alice")
        b = make_character("Bob")
        state = make_combat_state(a, b)
        state.fighters["Alice"].actions_remaining = [3, 5]
        snapshot = state.snapshot_status()
        assert "Alice" in snapshot
        assert "Bob" in snapshot
        assert snapshot["Alice"].actions_remaining == [3, 5]

    def test_fighters_are_fighter_instances(self) -> None:
        a = make_character("Alice")
        b = make_character("Bob")
        state = make_combat_state(a, b)
        assert isinstance(state.fighters["Alice"], Fighter)
        assert isinstance(state.fighters["Bob"], Fighter)
