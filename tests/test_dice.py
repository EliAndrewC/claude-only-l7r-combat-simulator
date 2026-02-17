"""Tests for the dice rolling engine."""

from unittest.mock import patch

from src.engine.dice import reroll_tens, roll_and_keep, roll_die


class TestRollDie:
    def test_roll_die_returns_value_in_range(self) -> None:
        """A single die roll without explosion is between 1 and 10."""
        for _ in range(100):
            result = roll_die(explode=False)
            assert 1 <= result <= 10

    def test_roll_die_no_explode_caps_at_10(self) -> None:
        """With explode=False, even rolling a 10 returns exactly 10."""
        with patch("src.engine.dice.random.randint", return_value=10):
            assert roll_die(explode=False) == 10

    def test_roll_die_explode_adds_reroll(self) -> None:
        """An exploding 10 followed by a 5 gives 15."""
        with patch("src.engine.dice.random.randint", side_effect=[10, 5]):
            assert roll_die(explode=True) == 15

    def test_roll_die_double_explode(self) -> None:
        """Two exploding 10s then a 3 gives 23."""
        with patch("src.engine.dice.random.randint", side_effect=[10, 10, 3]):
            assert roll_die(explode=True) == 23


class TestRollAndKeep:
    def test_keeps_highest_dice(self) -> None:
        """roll_and_keep should keep the highest N dice."""
        with patch("src.engine.dice.roll_die", side_effect=[3, 7, 1, 9, 5]):
            all_dice, kept_dice, total = roll_and_keep(5, 2, explode=True)
            assert kept_dice == [9, 7]
            assert total == 16

    def test_overflow_rolled_converts_to_kept(self) -> None:
        """Excess rolled dice beyond 10 convert to extra kept dice."""
        with patch("src.engine.dice.roll_die", side_effect=[5] * 10):
            all_dice, kept_dice, total = roll_and_keep(12, 3, explode=True)
            # 12 rolled → effective_kept = 3 + 2 = 5, effective_rolled = 10
            # top 5 of ten 5s = 25
            assert total == 25
            assert len(all_dice) == 10
            assert len(kept_dice) == 5

    def test_overflow_kept_adds_bonus(self) -> None:
        """Keeping more than 10 dice adds +1 per excess to total."""
        with patch("src.engine.dice.roll_die", side_effect=[5] * 10):
            _, _, total = roll_and_keep(10, 12, explode=True)
            # kept capped to 10, bonus +2, all dice kept = 50 + 2 = 52
            assert total == 52

    def test_overflow_rolled_converts_to_kept_and_beyond_10k10(self) -> None:
        """Excess rolled converts to kept; if kept > 10, further excess becomes bonus."""
        with patch("src.engine.dice.roll_die", side_effect=[5] * 10):
            all_dice, kept_dice, total = roll_and_keep(22, 3, explode=True)
            # 22 rolled → effective_kept = 3 + 12 = 15, effective_rolled = 10
            # kept 15 > 10 → bonus = 5, effective_kept = 10
            # 10 dice all 5 → keep 10 = 50, + 5 bonus = 55
            assert total == 55
            assert len(all_dice) == 10
            assert len(kept_dice) == 10

    def test_basic_roll(self) -> None:
        """Standard 3k2 roll works correctly."""
        with patch("src.engine.dice.roll_die", side_effect=[4, 8, 2]):
            all_dice, kept_dice, total = roll_and_keep(3, 2, explode=True)
            assert all_dice == [8, 4, 2]
            assert kept_dice == [8, 4]
            assert total == 12


class TestRerollTens:
    def test_replaces_tens_with_exploded_values(self) -> None:
        """Each die showing 10 is rerolled with explosion."""
        # Dice: [10, 7, 10, 3], kept_count=2
        # After reroll: 10s become exploded values (15 and 12)
        with patch("src.engine.dice.roll_die", side_effect=[15, 12]):
            all_dice, kept_dice, total = reroll_tens([10, 7, 10, 3], kept_count=2)
            # Re-sorted descending: [15, 12, 7, 3]
            assert all_dice == [15, 12, 7, 3]
            assert kept_dice == [15, 12]
            assert total == 27

    def test_no_op_when_no_tens(self) -> None:
        """When no dice are 10, the result is unchanged."""
        all_dice, kept_dice, total = reroll_tens([9, 7, 5, 3], kept_count=2)
        assert all_dice == [9, 7, 5, 3]
        assert kept_dice == [9, 7]
        assert total == 16

    def test_single_ten(self) -> None:
        """A single 10 among the dice is rerolled."""
        with patch("src.engine.dice.roll_die", return_value=18):
            all_dice, kept_dice, total = reroll_tens([10, 6, 4], kept_count=2)
            assert all_dice == [18, 6, 4]
            assert kept_dice == [18, 6]
            assert total == 24

    def test_all_tens(self) -> None:
        """All dice showing 10 are each rerolled."""
        with patch("src.engine.dice.roll_die", side_effect=[13, 11, 17]):
            all_dice, kept_dice, total = reroll_tens([10, 10, 10], kept_count=2)
            assert all_dice == [17, 13, 11]
            assert kept_dice == [17, 13]
            assert total == 30

    def test_reroll_preserves_kept_count(self) -> None:
        """Kept count is respected after reroll and re-sort."""
        with patch("src.engine.dice.roll_die", return_value=11):
            all_dice, kept_dice, total = reroll_tens([10, 8, 5, 2], kept_count=3)
            # After reroll: [11, 8, 5, 2], kept 3 = [11, 8, 5]
            assert kept_dice == [11, 8, 5]
            assert total == 24
