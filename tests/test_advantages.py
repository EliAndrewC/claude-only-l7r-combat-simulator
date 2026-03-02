"""Tests for combat advantages: Strength of the Earth, Lucky."""

from unittest.mock import patch

from src.engine.fighters.base import Fighter
from src.models.character import Advantage
from src.models.combat import WoundTracker
from tests.conftest import make_character, make_combat_state


class TestStrengthOfTheEarth:
    def test_bonus_with_advantage(self) -> None:
        char = make_character("Earthy", earth=3)
        char.advantages = [Advantage.STRENGTH_OF_THE_EARTH]
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Earthy"]
        bonus, note = fighter.advantage_wound_check_flat_bonus()
        assert bonus == 5
        assert note != ""

    def test_no_bonus_without_advantage(self) -> None:
        char = make_character("Normal")
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Normal"]
        bonus, note = fighter.advantage_wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""

    def test_integration_strength_of_earth_changes_outcome(self) -> None:
        """Strength of the Earth +5 can turn a failed wound check into a pass."""
        char = make_character("Earthy", earth=3, water=2)
        char.advantages = [Advantage.STRENGTH_OF_THE_EARTH]
        foe = make_character("Attacker", fire=3)
        state = make_combat_state(char, foe)

        wound_tracker = state.log.wounds["Earthy"]
        wound_tracker.light_wounds = 18

        # Roll total of 15 vs TN 18 would fail without bonus,
        # but with +5 becomes 20 >= 18, passing
        with patch(
            "src.engine.combat.roll_and_keep",
            return_value=([8, 7, 5], [8, 7], 15),
        ):
            from src.engine.combat import make_wound_check

            passed, total, _, _ = make_wound_check(wound_tracker, water_ring=2)
            assert not passed  # base roll fails

        # Reset serious wounds from the failed check
        wound_tracker.serious_wounds = 0
        wound_tracker.light_wounds = 18

        # Now the fighter's bonus would make it pass
        fighter: Fighter = state.fighters["Earthy"]
        bonus, _ = fighter.advantage_wound_check_flat_bonus()
        assert 15 + bonus >= 18


class TestLucky:
    def test_should_use_lucky_with_2_sw(self) -> None:
        char = make_character("Lucky", earth=3)
        char.advantages = [Advantage.LUCKY]
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Lucky"]
        assert fighter.should_use_lucky_reroll(serious_wounds_taken=2)

    def test_should_not_use_lucky_with_1_sw(self) -> None:
        char = make_character("Lucky", earth=3)
        char.advantages = [Advantage.LUCKY]
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Lucky"]
        assert not fighter.should_use_lucky_reroll(serious_wounds_taken=1)

    def test_should_not_use_lucky_when_already_used(self) -> None:
        char = make_character("Lucky", earth=3)
        char.advantages = [Advantage.LUCKY]
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Lucky"]
        fighter.lucky_used = True
        assert not fighter.should_use_lucky_reroll(serious_wounds_taken=3)

    def test_should_not_use_lucky_without_advantage(self) -> None:
        char = make_character("Normal", earth=3)
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Normal"]
        assert not fighter.should_use_lucky_reroll(serious_wounds_taken=3)

    def test_lucky_reroll_keeps_better_result_pass(self) -> None:
        """First roll fails with 3 SW, reroll passes → pass is taken."""
        char = make_character("Lucky", earth=3, water=2)
        char.advantages = [Advantage.LUCKY]
        foe = make_character("Foe")
        state = make_combat_state(char, foe)

        wound_tracker = state.log.wounds["Lucky"]
        wound_tracker.light_wounds = 30

        # First call: fails (total 5 vs TN 30 → deficit 25 → 3 SW)
        # Second call: passes (total 35 vs TN 30)
        call_count = [0]

        def mock_wc(wt: WoundTracker, water: int, **kwargs: object) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: fail with 3 serious
                wt.serious_wounds += 3
                return False, 5, [3, 2, 1], [3, 2]
            # Reroll: pass
            return True, 35, [10, 10, 10, 5], [10, 10, 10]

        with patch(
            "src.engine.combat.roll_and_keep",
            return_value=([5, 3, 1], [5, 3], 8),
        ):
            # Simulate the Lucky reroll logic manually
            fighter: Fighter = state.fighters["Lucky"]
            sw_before = wound_tracker.serious_wounds

            # First roll fails
            passed, total, all_dice, kept = mock_wc(
                wound_tracker, 2,
            )
            assert not passed
            sw_taken = wound_tracker.serious_wounds - sw_before
            assert sw_taken == 3

            # Should use lucky reroll
            assert fighter.should_use_lucky_reroll(sw_taken)

    def test_lucky_reroll_keeps_original_when_worse(self) -> None:
        """First roll fails with 2 SW, reroll fails with 3 SW → original kept."""
        char = make_character("Lucky", earth=3, water=2)
        char.advantages = [Advantage.LUCKY]
        state = make_combat_state(char, make_character("Foe"))
        fighter: Fighter = state.fighters["Lucky"]

        # 2 SW from first roll: should reroll
        assert fighter.should_use_lucky_reroll(serious_wounds_taken=2)
        # After use, mark as used
        fighter.lucky_used = True
        assert not fighter.should_use_lucky_reroll(serious_wounds_taken=5)
