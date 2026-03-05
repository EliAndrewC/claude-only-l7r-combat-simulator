"""Tests for mass simulation Pydantic data models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.models.mass_simulation import (
    MatchupConfig,
    MatchupResult,
    SimulationConfig,
    SimulationResult,
    StrategyConfig,
)


class TestFighterStrategy:
    def test_fighter_gets_default_strategy(self) -> None:
        from src.engine.combat import create_combat_log
        from src.engine.combat_state import CombatState
        from src.engine.fighters.base import Fighter

        log = create_combat_log(["A", "B"], [2, 2])
        state = CombatState(log=log)
        fighter = Fighter("A", state)
        assert fighter.strategy is not None
        assert fighter.strategy.void_threshold == 0.25

    def test_fighter_gets_custom_strategy(self) -> None:
        from src.engine.combat import create_combat_log
        from src.engine.combat_state import CombatState
        from src.engine.fighters.base import Fighter

        log = create_combat_log(["A", "B"], [2, 2])
        state = CombatState(log=log)
        strat = StrategyConfig(label="Custom", da_threshold=0.7)
        fighter = Fighter("A", state, strategy=strat)
        assert fighter.strategy.label == "Custom"
        assert fighter.strategy.da_threshold == 0.7

    def test_void_threshold_knob(self) -> None:
        """Void threshold param threads through to should_spend_void_on_wound_check."""
        from src.engine.simulation_utils import should_spend_void_on_wound_check

        # High threshold = less likely to spend void
        high_result = should_spend_void_on_wound_check(
            water_ring=2, light_wounds=15, void_available=3,
            max_spend=2, threshold=0.9,
        )
        # Low threshold = more likely to spend void
        low_result = should_spend_void_on_wound_check(
            water_ring=2, light_wounds=15, void_available=3,
            max_spend=2, threshold=0.01,
        )
        assert low_result >= high_result

    def test_parry_aggressiveness_knob(self) -> None:
        """Parry threshold param threads through to should_reactive_parry."""
        from src.engine.simulation_utils import should_reactive_parry

        # attack_total == attack_tn so extra_dice == 0 (no auto-parry)
        # High attack total so expected_parry (about 21) only meets high threshold.
        # parry_threshold=0.9: need >= 40*0.9 = 36 -> False
        # parry_threshold=0.4: need >= 40*0.4 = 16 -> True (21.4 >= 16)
        result_low_bar = should_reactive_parry(
            defender_parry_rank=3, air_ring=3,
            attack_total=40, attack_tn=40,
            weapon_rolled=3, attacker_fire=3,
            serious_wounds=0, earth_ring=4, is_crippled=False,
            parry_threshold=0.4,
        )
        result_high_bar = should_reactive_parry(
            defender_parry_rank=3, air_ring=3,
            attack_total=40, attack_tn=40,
            weapon_rolled=3, attacker_fire=3,
            serious_wounds=0, earth_ring=4, is_crippled=False,
            parry_threshold=0.9,
        )
        assert result_low_bar is True
        assert result_high_bar is False

    def test_da_threshold_knob_kakita(self) -> None:
        """DA threshold param changes kakita attack choice."""
        from src.engine.fighters.kakita import _kakita_attack_choice

        # With high threshold (conservative), less likely to DA
        choice_high = _kakita_attack_choice(
            lunge_rank=3, double_attack_rank=3,
            fire_ring=3, defender_parry=3,
            dan=1, is_crippled=False,
            da_threshold=0.99,
        )
        # With low threshold (aggressive), more likely to DA
        choice_low = _kakita_attack_choice(
            lunge_rank=3, double_attack_rank=3,
            fire_ring=3, defender_parry=3,
            dan=1, is_crippled=False,
            da_threshold=0.5,
        )
        assert choice_high == "lunge"
        assert choice_low == "double_attack"

    def test_lw_conversion_knob(self) -> None:
        """LW conversion param threads through to should_convert_light_to_serious."""
        from src.engine.simulation_utils import should_convert_light_to_serious

        # water_ring=2 -> avg_wc = 15
        # lw_conversion=0.99: threshold=max(10,round(15*0.99))=15, 12>15 -> False
        # lw_conversion=0.5: threshold=max(10,round(15*0.5))=10, 12>10 -> True
        result_high = should_convert_light_to_serious(
            light_wounds=12, serious_wounds=0, earth_ring=3,
            water_ring=2, lw_conversion=0.99,
        )
        result_low = should_convert_light_to_serious(
            light_wounds=12, serious_wounds=0, earth_ring=3,
            water_ring=2, lw_conversion=0.5,
        )
        assert result_low is True
        assert result_high is False

    def test_simulate_combat_accepts_strategy_params(self) -> None:
        from src.engine.school_registry import SCHOOL_BUILDERS, SCHOOL_DEFAULT_WEAPONS
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS

        school = "Akodo Bushi"
        builder = SCHOOL_BUILDERS[school]
        char_a = builder(school, 0, 0.20)
        char_b = builder(school, 0, 0.20)
        weapon = WEAPONS[SCHOOL_DEFAULT_WEAPONS[school]]
        strat = StrategyConfig(label="Test", void_threshold=0.1)

        log = simulate_combat(char_a, char_b, weapon, weapon, strategy_a=strat)
        assert log.winner is not None or log.winner is None  # just verify it runs


class TestStrategyConfig:
    def test_defaults(self) -> None:
        cfg = StrategyConfig()
        assert cfg.label == "Default"
        assert cfg.void_threshold == 0.25
        assert cfg.parry_aggressiveness == 0.6
        assert cfg.da_threshold == 0.85
        assert cfg.lw_conversion == 0.8

    def test_custom_values(self) -> None:
        cfg = StrategyConfig(
            label="Aggressive",
            void_threshold=0.1,
            parry_aggressiveness=0.3,
            da_threshold=0.7,
            lw_conversion=0.6,
        )
        assert cfg.label == "Aggressive"
        assert cfg.void_threshold == 0.1
        assert cfg.parry_aggressiveness == 0.3
        assert cfg.da_threshold == 0.7
        assert cfg.lw_conversion == 0.6

    def test_serialization_roundtrip(self) -> None:
        cfg = StrategyConfig(label="Test", void_threshold=0.5)
        json_str = cfg.model_dump_json()
        restored = StrategyConfig.model_validate_json(json_str)
        assert restored == cfg


class TestMatchupConfig:
    def test_creation(self) -> None:
        cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=100,
            non_combat_pct=0.20,
            is_duel=False,
        )
        assert cfg.school_a == "Akodo Bushi"
        assert cfg.school_b == "Matsu Bushi"
        assert cfg.earned_xp_a == 100
        assert cfg.earned_xp_b == 100
        assert cfg.non_combat_pct == 0.20
        assert cfg.is_duel is False

    def test_duel_mode(self) -> None:
        cfg = MatchupConfig(
            school_a="Kakita Duelist",
            school_b="Mirumoto Bushi",
            earned_xp_a=50,
            earned_xp_b=50,
            non_combat_pct=0.20,
            is_duel=True,
        )
        assert cfg.is_duel is True

    def test_strategy_fields_default_none(self) -> None:
        cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=100,
            non_combat_pct=0.20,
            is_duel=False,
        )
        assert cfg.strategy_a is None
        assert cfg.strategy_b is None

    def test_with_strategies(self) -> None:
        strat = StrategyConfig(label="Aggressive", da_threshold=0.7)
        cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=100,
            non_combat_pct=0.20,
            is_duel=False,
            strategy_a=strat,
        )
        assert cfg.strategy_a is not None
        assert cfg.strategy_a.label == "Aggressive"
        assert cfg.strategy_b is None

    def test_serialization_roundtrip(self) -> None:
        cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=150,
            non_combat_pct=0.15,
            is_duel=False,
        )
        json_str = cfg.model_dump_json()
        restored = MatchupConfig.model_validate_json(json_str)
        assert restored == cfg


class TestMatchupResult:
    def test_creation_and_computed_properties(self) -> None:
        cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=100,
            non_combat_pct=0.20,
            is_duel=False,
        )
        result = MatchupResult(
            config=cfg,
            num_combats=100,
            wins_a=60,
            wins_b=35,
            draws=5,
            avg_rounds=8.5,
            avg_wounds_a=3.2,
            avg_wounds_b=4.1,
        )
        assert result.win_rate_a == 0.60
        assert result.win_rate_b == 0.35
        assert result.num_combats == 100
        assert result.avg_rounds == 8.5

    def test_win_rates_zero_combats(self) -> None:
        cfg = MatchupConfig(
            school_a="A",
            school_b="B",
            earned_xp_a=0,
            earned_xp_b=0,
            non_combat_pct=0.20,
            is_duel=False,
        )
        result = MatchupResult(
            config=cfg,
            num_combats=0,
            wins_a=0,
            wins_b=0,
            draws=0,
            avg_rounds=0.0,
            avg_wounds_a=0.0,
            avg_wounds_b=0.0,
        )
        assert result.win_rate_a == 0.0
        assert result.win_rate_b == 0.0

    def test_serialization_roundtrip(self) -> None:
        cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=100,
            non_combat_pct=0.20,
            is_duel=False,
        )
        result = MatchupResult(
            config=cfg,
            num_combats=50,
            wins_a=30,
            wins_b=18,
            draws=2,
            avg_rounds=7.0,
            avg_wounds_a=2.5,
            avg_wounds_b=3.0,
        )
        json_str = result.model_dump_json()
        restored = MatchupResult.model_validate_json(json_str)
        assert restored == result
        assert restored.win_rate_a == result.win_rate_a


class TestSimulationConfig:
    def test_defaults(self) -> None:
        cfg = SimulationConfig(schools=["Akodo Bushi", "Matsu Bushi"])
        assert cfg.earned_xp_levels == [0, 50, 100, 150, 200, 250, 300]
        assert cfg.combats_per_matchup == 100
        assert cfg.non_combat_pct == 0.20
        assert cfg.is_duel is False
        assert cfg.include_asymmetric_xp is False
        assert cfg.xp_asymmetry_max == 50
        assert cfg.description == ""
        assert cfg.focus_school is None
        assert cfg.strategies == []

    def test_custom_values(self) -> None:
        cfg = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi", "Kakita Duelist"],
            earned_xp_levels=[0, 100, 200],
            combats_per_matchup=50,
            non_combat_pct=0.15,
            is_duel=True,
            include_asymmetric_xp=True,
            xp_asymmetry_max=100,
            description="Test run",
        )
        assert len(cfg.schools) == 3
        assert cfg.combats_per_matchup == 50
        assert cfg.is_duel is True
        assert cfg.description == "Test run"

    def test_with_focus_school_and_strategies(self) -> None:
        strats = [
            StrategyConfig(label="Default"),
            StrategyConfig(label="Aggressive", da_threshold=0.7),
        ]
        cfg = SimulationConfig(
            schools=["Akodo Bushi", "Matsu Bushi"],
            focus_school="Akodo Bushi",
            strategies=strats,
        )
        assert cfg.focus_school == "Akodo Bushi"
        assert len(cfg.strategies) == 2
        assert cfg.strategies[0].label == "Default"
        assert cfg.strategies[1].da_threshold == 0.7

    def test_serialization_roundtrip(self) -> None:
        cfg = SimulationConfig(
            schools=["Akodo Bushi"],
            earned_xp_levels=[0, 100],
            combats_per_matchup=10,
        )
        json_str = cfg.model_dump_json()
        restored = SimulationConfig.model_validate_json(json_str)
        assert restored == cfg


class TestSimulationResult:
    def test_creation(self) -> None:
        cfg = SimulationConfig(schools=["Akodo Bushi", "Matsu Bushi"])
        result = SimulationResult(config=cfg, matchup_results=[])
        assert isinstance(result.id, uuid.UUID)
        assert isinstance(result.timestamp, datetime)
        assert result.label == ""
        assert result.analysis_notes == ""
        assert result.matchup_results == []

    def test_with_matchup_results(self) -> None:
        cfg = SimulationConfig(schools=["Akodo Bushi", "Matsu Bushi"])
        matchup_cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=100,
            earned_xp_b=100,
            non_combat_pct=0.20,
            is_duel=False,
        )
        matchup = MatchupResult(
            config=matchup_cfg,
            num_combats=10,
            wins_a=6,
            wins_b=4,
            draws=0,
            avg_rounds=7.0,
            avg_wounds_a=2.0,
            avg_wounds_b=3.0,
        )
        result = SimulationResult(
            config=cfg,
            matchup_results=[matchup],
            label="Test",
            analysis_notes="Some notes",
        )
        assert len(result.matchup_results) == 1
        assert result.label == "Test"
        assert result.analysis_notes == "Some notes"

    def test_serialization_roundtrip(self) -> None:
        cfg = SimulationConfig(schools=["Akodo Bushi", "Matsu Bushi"])
        matchup_cfg = MatchupConfig(
            school_a="Akodo Bushi",
            school_b="Matsu Bushi",
            earned_xp_a=0,
            earned_xp_b=0,
            non_combat_pct=0.20,
            is_duel=False,
        )
        matchup = MatchupResult(
            config=matchup_cfg,
            num_combats=5,
            wins_a=3,
            wins_b=2,
            draws=0,
            avg_rounds=6.0,
            avg_wounds_a=1.5,
            avg_wounds_b=2.5,
        )
        sim_id = uuid.uuid4()
        ts = datetime.now(tz=timezone.utc)
        result = SimulationResult(
            id=sim_id,
            config=cfg,
            matchup_results=[matchup],
            timestamp=ts,
            label="Roundtrip test",
        )
        json_str = result.model_dump_json()
        restored = SimulationResult.model_validate_json(json_str)
        assert restored.id == sim_id
        assert restored.config == cfg
        assert len(restored.matchup_results) == 1
        assert restored.matchup_results[0].win_rate_a == matchup.win_rate_a
        assert restored.label == "Roundtrip test"
