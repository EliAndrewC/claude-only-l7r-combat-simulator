"""Tests for the mass simulation engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.engine.mass_simulation import (
    _generate_school_pairs,
    _generate_strategy_matchups,
    _generate_xp_pairs,
    _run_matchup,
    run_mass_simulation,
)
from src.models.combat import CombatLog
from src.models.mass_simulation import (
    MatchupConfig,
    SimulationConfig,
    SimulationResult,
    StrategyConfig,
)


class TestGenerateXpPairs:
    def test_symmetric_only(self) -> None:
        levels = [0, 100, 200]
        pairs = _generate_xp_pairs(levels, include_asymmetric=False, asymmetry_max=50)
        assert pairs == [(0, 0), (100, 100), (200, 200)]

    def test_asymmetric_pairs(self) -> None:
        levels = [0, 50, 100]
        pairs = _generate_xp_pairs(levels, include_asymmetric=True, asymmetry_max=50)
        # Should include symmetric pairs
        assert (0, 0) in pairs
        assert (50, 50) in pairs
        assert (100, 100) in pairs
        # Should include asymmetric pairs where diff <= 50
        assert (0, 50) in pairs
        assert (50, 100) in pairs
        # Should NOT include (0, 100) since diff=100 > asymmetry_max=50
        assert (0, 100) not in pairs

    def test_asymmetric_avoids_duplicates(self) -> None:
        levels = [0, 50]
        pairs = _generate_xp_pairs(levels, include_asymmetric=True, asymmetry_max=50)
        # (0, 50) should appear but not (50, 0) since we use unordered pairs
        assert (0, 50) in pairs
        assert (50, 0) not in pairs

    def test_empty_levels(self) -> None:
        pairs = _generate_xp_pairs([], include_asymmetric=False, asymmetry_max=50)
        assert pairs == []


class TestGenerateSchoolPairs:
    def test_two_schools(self) -> None:
        pairs = _generate_school_pairs(["A", "B"])
        assert ("A", "A") in pairs
        assert ("B", "B") in pairs
        assert ("A", "B") in pairs
        assert len(pairs) == 3  # AA, BB, AB

    def test_three_schools(self) -> None:
        pairs = _generate_school_pairs(["A", "B", "C"])
        # N*(N+1)/2 = 3*4/2 = 6
        assert len(pairs) == 6

    def test_avoids_reverse_duplicates(self) -> None:
        pairs = _generate_school_pairs(["A", "B"])
        # Should have (A, B) but not (B, A)
        assert ("A", "B") in pairs
        assert ("B", "A") not in pairs

    def test_single_school(self) -> None:
        pairs = _generate_school_pairs(["A"])
        assert pairs == [("A", "A")]


class TestRunMatchup:
    @patch("src.engine.mass_simulation.simulate_combat")
    def test_basic_matchup(self, mock_sim: MagicMock) -> None:
        name_a = "Akodo Bushi"
        name_b = "Matsu Bushi"
        # Set up mock to return alternating winners
        logs = []
        for i in range(10):
            log = CombatLog(combatants=[name_a, name_b], wounds={})
            log.winner = name_a if i < 6 else (name_b if i < 9 else None)
            log.round_number = 5 + i
            logs.append(log)
        mock_sim.side_effect = logs

        cfg = MatchupConfig(
            school_a=name_a,
            school_b=name_b,
            earned_xp_a=0,
            earned_xp_b=0,
            non_combat_pct=0.20,
            is_duel=False,
        )
        result = _run_matchup(cfg, num_combats=10)
        assert result.wins_a == 6
        assert result.wins_b == 3
        assert result.draws == 1
        assert result.num_combats == 10
        assert mock_sim.call_count == 10


class TestRunMassSimulation:
    @patch("src.engine.mass_simulation.simulate_combat")
    def test_small_simulation(self, mock_sim: MagicMock) -> None:
        # Simple mock: first school always wins
        def mock_combat(char_a, char_b, weapon_a, weapon_b, is_duel=False, **kwargs):
            log = CombatLog(
                combatants=[char_a.name, char_b.name],
                wounds={},
            )
            log.winner = char_a.name
            log.round_number = 5
            return log

        mock_sim.side_effect = mock_combat

        config = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            earned_xp_levels=[0, 100],
            combats_per_matchup=5,
        )
        result = run_mass_simulation(config)
        assert isinstance(result, SimulationResult)
        assert result.config == config
        assert len(result.matchup_results) > 0

    @patch("src.engine.mass_simulation.simulate_combat")
    def test_progress_callback(self, mock_sim: MagicMock) -> None:
        def mock_combat(char_a, char_b, weapon_a, weapon_b, is_duel=False, **kwargs):
            log = CombatLog(
                combatants=[char_a.name, char_b.name],
                wounds={},
            )
            log.winner = char_a.name
            log.round_number = 5
            return log

        mock_sim.side_effect = mock_combat

        callback = MagicMock()
        config = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            earned_xp_levels=[0],
            combats_per_matchup=3,
        )
        run_mass_simulation(config, progress_callback=callback)
        assert callback.call_count > 0

    @patch("src.engine.mass_simulation.simulate_combat")
    def test_duel_mode_passed_through(self, mock_sim: MagicMock) -> None:
        def mock_combat(char_a, char_b, weapon_a, weapon_b, is_duel=False, **kwargs):
            log = CombatLog(
                combatants=[char_a.name, char_b.name],
                wounds={},
            )
            log.winner = char_a.name
            log.round_number = 3
            return log

        mock_sim.side_effect = mock_combat

        config = SimulationConfig(
            schools=["Akodo Bushi"],
            earned_xp_levels=[0],
            combats_per_matchup=2,
            is_duel=True,
        )
        run_mass_simulation(config)
        # Verify is_duel was passed through
        for call in mock_sim.call_args_list:
            assert call.kwargs.get("is_duel") is True or call[1].get("is_duel") is True

    def test_integration_small_run(self) -> None:
        """Integration test: 2 schools x 1 XP level x 3 combats (real combat)."""
        config = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            earned_xp_levels=[0],
            combats_per_matchup=3,
        )
        result = run_mass_simulation(config)
        assert isinstance(result, SimulationResult)
        # 2 schools -> 3 pairs (AA, BB, AB) x 1 XP level = 3 matchups
        assert len(result.matchup_results) == 3
        for mr in result.matchup_results:
            assert mr.num_combats == 3
            assert mr.wins_a + mr.wins_b + mr.draws == 3


class TestGenerateStrategyMatchups:
    def test_generates_matchups_for_each_strategy(self) -> None:
        strats = [
            StrategyConfig(label="Default"),
            StrategyConfig(label="Aggressive", da_threshold=0.7),
        ]
        schools = ["Akodo Bushi", "Matsu Bushi"]
        xp_pairs = [(0, 0)]
        matchups = _generate_strategy_matchups(
            focus_school="Akodo Bushi",
            strategies=strats,
            all_schools=schools,
            xp_pairs=xp_pairs,
            non_combat_pct=0.20,
            is_duel=False,
        )
        # 2 strategies x 1 opponent x 1 XP pair = 2 matchups
        assert len(matchups) == 2
        # Focus school is always school_a
        for cfg in matchups:
            assert cfg.school_a == "Akodo Bushi"
            assert cfg.school_b == "Matsu Bushi"
            assert cfg.strategy_a is not None
            assert cfg.strategy_b is None

    def test_strategy_labels_preserved(self) -> None:
        strats = [
            StrategyConfig(label="Conservative"),
            StrategyConfig(label="Risky"),
        ]
        schools = ["Akodo Bushi", "Matsu Bushi"]
        xp_pairs = [(0, 0)]
        matchups = _generate_strategy_matchups(
            focus_school="Akodo Bushi",
            strategies=strats,
            all_schools=schools,
            xp_pairs=xp_pairs,
            non_combat_pct=0.20,
            is_duel=False,
        )
        labels = [m.strategy_a.label for m in matchups]
        assert "Conservative" in labels
        assert "Risky" in labels

    def test_with_multiple_opponents_and_xp(self) -> None:
        strats = [StrategyConfig(label="Default")]
        schools = ["Akodo Bushi", "Matsu Bushi", "Kakita Duelist"]
        xp_pairs = [(0, 0), (100, 100)]
        matchups = _generate_strategy_matchups(
            focus_school="Akodo Bushi",
            strategies=strats,
            all_schools=schools,
            xp_pairs=xp_pairs,
            non_combat_pct=0.20,
            is_duel=False,
        )
        # 1 strategy x 2 opponents x 2 XP pairs = 4 matchups
        assert len(matchups) == 4

    def test_asymmetric_xp_both_directions(self) -> None:
        """Asymmetric XP should test both focus-school-ahead and behind."""
        strats = [StrategyConfig(label="Default")]
        schools = ["Akodo Bushi", "Matsu Bushi"]
        xp_pairs = [(0, 50)]  # asymmetric
        matchups = _generate_strategy_matchups(
            focus_school="Akodo Bushi",
            strategies=strats,
            all_schools=schools,
            xp_pairs=xp_pairs,
            non_combat_pct=0.20,
            is_duel=False,
        )
        # 1 strategy x 1 opponent x 1 XP pair x 2 directions = 2 matchups
        assert len(matchups) == 2
        xp_combos = [(m.earned_xp_a, m.earned_xp_b) for m in matchups]
        assert (0, 50) in xp_combos
        assert (50, 0) in xp_combos


class TestStrategyComparisonMode:
    @patch("src.engine.mass_simulation.simulate_combat")
    def test_strategy_mode_uses_strategy_matchups(self, mock_sim: MagicMock) -> None:
        def mock_combat(
            char_a, char_b, weapon_a, weapon_b,
            is_duel=False, strategy_a=None, strategy_b=None,
        ):
            log = CombatLog(
                combatants=[char_a.name, char_b.name],
                wounds={},
            )
            log.winner = char_a.name
            log.round_number = 5
            return log

        mock_sim.side_effect = mock_combat

        config = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            earned_xp_levels=[0],
            combats_per_matchup=3,
            focus_school="Akodo Bushi",
            strategies=[
                StrategyConfig(label="Default"),
                StrategyConfig(label="Aggressive", da_threshold=0.7),
            ],
        )
        result = run_mass_simulation(config)
        assert isinstance(result, SimulationResult)
        assert len(result.matchup_results) > 0
        # All matchups should have focus school as school_a
        for mr in result.matchup_results:
            assert mr.config.school_a == "Akodo Bushi"
            assert mr.config.strategy_a is not None

    def test_legacy_mode_still_works(self) -> None:
        """Without focus_school, legacy all-vs-all mode works."""
        config = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            earned_xp_levels=[0],
            combats_per_matchup=3,
        )
        result = run_mass_simulation(config)
        assert isinstance(result, SimulationResult)
        assert len(result.matchup_results) == 3  # AA, BB, AB

    def test_strategy_integration(self) -> None:
        """Integration: real combat with strategies."""
        config = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            earned_xp_levels=[0],
            combats_per_matchup=2,
            focus_school="Akodo Bushi",
            strategies=[StrategyConfig(label="Default")],
        )
        result = run_mass_simulation(config)
        assert isinstance(result, SimulationResult)
        assert len(result.matchup_results) > 0
        for mr in result.matchup_results:
            assert mr.config.school_a == "Akodo Bushi"
            assert mr.num_combats == 2
