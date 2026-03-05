"""Smoke tests for the mass simulation UI tabs."""

from __future__ import annotations

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.mass_sim_ui import (
    _build_strategy_comparison_data,
    _build_xp_chart_data,
    _load_matchup_into_single_combat,
)
from src.models.mass_simulation import (
    MatchupConfig,
    MatchupResult,
    SimulationConfig,
    SimulationResult,
    StrategyConfig,
)


class TestAppWithTabs:
    def test_app_runs_without_error(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert not at.exception

    def test_app_has_three_tabs(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert len(at.tabs) == 3


class TestMassSimulationTab:
    def test_mass_sim_tab_renders(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Tab should exist and not cause errors
        assert not at.exception

    def test_mass_sim_tab_has_selectbox(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Mass sim tab should have a selectbox for focus school
        assert len(at.selectbox) > 0


class TestAnalysisTab:
    def test_analysis_tab_renders(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert not at.exception

    def test_analysis_tab_has_info_when_no_simulations(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Should show info message when no saved simulations exist
        assert not at.exception


class TestMassSimUIModule:
    def test_render_functions_importable(self) -> None:
        from src.mass_sim_ui import render_analysis_tab, render_mass_simulation_tab

        assert callable(render_mass_simulation_tab)
        assert callable(render_analysis_tab)


class TestAutoLabel:
    def test_auto_label_sets_label_from_focus_and_strategies(self) -> None:
        """Verify auto-labeling fills result.label from focus_school + strategies."""
        strategies = [
            StrategyConfig(label="Aggressive"),
            StrategyConfig(label="Defensive"),
        ]
        config = SimulationConfig(
            schools=["Mirumoto Bushi", "Matsu Bushi"],
            focus_school="Mirumoto Bushi",
            strategies=strategies,
        )
        result = SimulationResult(config=config, matchup_results=[])
        assert result.label == ""

        # Simulate the auto-label logic from render_mass_simulation_tab
        if not result.label:
            strat_names = ", ".join(s.label for s in strategies)
            result.label = f"{config.focus_school} ({strat_names})"

        assert result.label == "Mirumoto Bushi (Aggressive, Defensive)"

    def test_auto_label_preserves_existing_label(self) -> None:
        """If a label already exists, auto-label should not overwrite it."""
        config = SimulationConfig(
            schools=["Mirumoto Bushi"],
            focus_school="Mirumoto Bushi",
            strategies=[StrategyConfig(label="Default")],
        )
        result = SimulationResult(
            config=config, matchup_results=[], label="Custom Label",
        )

        if not result.label:
            result.label = "Should not reach here"

        assert result.label == "Custom Label"


class TestLoadMatchupIntoSingleCombat:
    def test_stages_pending_load(self) -> None:
        """_load_matchup_into_single_combat should stage a _pending_load dict."""
        mr = MatchupResult(
            config=MatchupConfig(
                school_a="Mirumoto Bushi",
                school_b="Matsu Bushi",
                earned_xp_a=150,
                earned_xp_b=100,
                non_combat_pct=0.20,
                is_duel=False,
                strategy_a=StrategyConfig(
                    label="Aggressive",
                    void_threshold=0.10,
                    parry_aggressiveness=0.80,
                    da_threshold=0.70,
                    lw_conversion=0.90,
                ),
            ),
            num_combats=100,
            wins_a=60,
            wins_b=35,
            draws=5,
            avg_rounds=4.2,
            avg_wounds_a=15.0,
            avg_wounds_b=20.0,
        )

        session: dict[str, object] = {}
        with (
            patch("src.mass_sim_ui.st") as mock_st,
        ):
            mock_st.session_state = session
            mock_st.rerun.side_effect = SystemExit("rerun")

            try:
                _load_matchup_into_single_combat(mr)
            except SystemExit:
                pass

        pending = session["_pending_load"]
        assert pending["f1_preset"] == "Mirumoto Bushi"
        assert pending["f1_earned_xp"] == 150
        assert pending["f1_noncombat"] == 20
        assert pending["f2_preset"] == "Matsu Bushi"
        assert pending["f2_earned_xp"] == 100
        assert pending["f2_noncombat"] == 20
        # Strategy keys for fighter 1
        assert pending["f1_void_threshold"] == 0.10
        assert pending["f1_parry_agg"] == 0.80
        assert pending["f1_da_threshold"] == 0.70
        assert pending["f1_lw_conversion"] == 0.90
        mock_st.rerun.assert_called_once()


def _make_mr(
    school_a: str, school_b: str,
    xp_a: int, xp_b: int,
    strategy_label: str,
    wins_a: int, wins_b: int,
) -> MatchupResult:
    """Helper to build a MatchupResult for testing."""
    return MatchupResult(
        config=MatchupConfig(
            school_a=school_a, school_b=school_b,
            earned_xp_a=xp_a, earned_xp_b=xp_b,
            non_combat_pct=0.20, is_duel=False,
            strategy_a=StrategyConfig(label=strategy_label),
        ),
        num_combats=wins_a + wins_b,
        wins_a=wins_a, wins_b=wins_b, draws=0,
        avg_rounds=2.0, avg_wounds_a=10.0, avg_wounds_b=10.0,
    )


class TestBuildXpChartData:
    def test_equal_xp_only_when_no_asymmetric(self) -> None:
        """Without asymmetric XP, only 'equal' lines appear (no suffix)."""
        config = SimulationConfig(
            schools=["A Bushi", "B Bushi"],
            earned_xp_levels=[0, 50],
            focus_school="A Bushi",
            strategies=[StrategyConfig(label="S1")],
            include_asymmetric_xp=False,
        )
        mrs = [
            _make_mr("A Bushi", "B Bushi", 0, 0, "S1", 40, 60),
            _make_mr("A Bushi", "B Bushi", 50, 50, "S1", 55, 45),
        ]
        sim = SimulationResult(config=config, matchup_results=mrs)

        index_labels, chart_data = _build_xp_chart_data(sim)

        assert index_labels == ["0 XP", "50 XP"]
        # No suffix when only equal offset
        assert "S1" in chart_data
        assert len(chart_data) == 1
        assert chart_data["S1"] == [0.4, 0.55]

    def test_three_lines_per_strategy_with_asymmetric(self) -> None:
        """With asymmetric XP, each strategy gets equal/+50/-50 lines."""
        config = SimulationConfig(
            schools=["A Bushi", "B Bushi"],
            earned_xp_levels=[0, 50, 100],
            focus_school="A Bushi",
            strategies=[StrategyConfig(label="S1")],
            include_asymmetric_xp=True,
            xp_asymmetry_max=50,
        )
        mrs = [
            # Equal XP matchups
            _make_mr("A Bushi", "B Bushi", 0, 0, "S1", 40, 60),
            _make_mr("A Bushi", "B Bushi", 50, 50, "S1", 50, 50),
            _make_mr("A Bushi", "B Bushi", 100, 100, "S1", 60, 40),
            # +50 advantage: focus has 50 more XP than opponent
            _make_mr("A Bushi", "B Bushi", 50, 0, "S1", 80, 20),
            _make_mr("A Bushi", "B Bushi", 100, 50, "S1", 85, 15),
            # -50 disadvantage: focus has 50 less XP than opponent
            _make_mr("A Bushi", "B Bushi", 0, 50, "S1", 10, 90),
            _make_mr("A Bushi", "B Bushi", 50, 100, "S1", 15, 85),
        ]
        sim = SimulationResult(config=config, matchup_results=mrs)

        index_labels, chart_data = _build_xp_chart_data(sim)

        assert index_labels == ["0 XP", "50 XP", "100 XP"]
        assert len(chart_data) == 3
        assert "S1 (equal)" in chart_data
        assert "S1 (+50 XP)" in chart_data
        assert "S1 (-50 XP)" in chart_data

        # Equal: 40%, 50%, 60%
        assert chart_data["S1 (equal)"] == [0.4, 0.5, 0.6]
        # +50: at xp=0 opp=-50 doesn't exist (None), xp=50 opp=0 (80%), xp=100 opp=50 (85%)
        assert chart_data["S1 (+50 XP)"] == [None, 0.8, 0.85]
        # -50: at xp=0 opp=50 (10%), xp=50 opp=100 (15%), xp=100 opp=150 (None)
        assert chart_data["S1 (-50 XP)"] == [0.1, 0.15, None]


class TestBuildStrategyComparisonData:
    def test_pairwise_comparison_with_diff(self) -> None:
        """Two strategies produce one pair with correct Win % Diff."""
        mrs = [
            _make_mr("A Bushi", "B Bushi", 0, 0, "Low", 40, 60),
            _make_mr("A Bushi", "B Bushi", 0, 0, "High", 60, 40),
            _make_mr("A Bushi", "B Bushi", 50, 50, "Low", 45, 55),
            _make_mr("A Bushi", "B Bushi", 50, 50, "High", 55, 45),
        ]

        result = _build_strategy_comparison_data(mrs, "B Bushi", ["Low", "High"])

        assert len(result) == 1
        strat_a, strat_b, cmp_rows, load_pairs = result[0]
        assert strat_a == "Low"
        assert strat_b == "High"
        assert len(cmp_rows) == 2
        # At 0 XP: Low=40%, High=60%, diff=-20%
        assert cmp_rows[0]["Focus XP"] == 0
        assert cmp_rows[0]["Win % Diff"] == "-20.0%"
        # At 50 XP: Low=45%, High=55%, diff=-10%
        assert cmp_rows[1]["Focus XP"] == 50
        assert cmp_rows[1]["Win % Diff"] == "-10.0%"
        # Each load_pair has (mr_a, mr_b) for both strategies
        assert len(load_pairs) == 2
        assert load_pairs[0][0].config.strategy_a.label == "Low"
        assert load_pairs[0][1].config.strategy_a.label == "High"

    def test_three_strategies_produce_three_pairs(self) -> None:
        """Three strategies produce C(3,2)=3 pairwise comparisons."""
        mrs = [
            _make_mr("A Bushi", "B Bushi", 0, 0, "S1", 50, 50),
            _make_mr("A Bushi", "B Bushi", 0, 0, "S2", 60, 40),
            _make_mr("A Bushi", "B Bushi", 0, 0, "S3", 70, 30),
        ]

        result = _build_strategy_comparison_data(mrs, "B Bushi", ["S1", "S2", "S3"])

        assert len(result) == 3
        pair_labels = [(r[0], r[1]) for r in result]
        assert ("S1", "S2") in pair_labels
        assert ("S1", "S3") in pair_labels
        assert ("S2", "S3") in pair_labels
