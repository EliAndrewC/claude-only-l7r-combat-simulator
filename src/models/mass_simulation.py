"""Pydantic data models for mass simulation configuration and results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class StrategyConfig(BaseModel):
    """Strategy knobs for a fighter's combat decision-making."""

    label: str = "Default"
    void_threshold: float = 0.25
    parry_aggressiveness: float = 0.6
    da_threshold: float = 0.85
    lw_conversion: float = 0.8


class MatchupConfig(BaseModel):
    """Configuration for a single school-vs-school matchup."""

    school_a: str
    school_b: str
    earned_xp_a: int
    earned_xp_b: int
    non_combat_pct: float
    is_duel: bool
    strategy_a: StrategyConfig | None = None
    strategy_b: StrategyConfig | None = None


class MatchupResult(BaseModel):
    """Aggregated results from running a matchup N times."""

    config: MatchupConfig
    num_combats: int
    wins_a: int
    wins_b: int
    draws: int
    avg_rounds: float
    avg_wounds_a: float
    avg_wounds_b: float

    @property
    def win_rate_a(self) -> float:
        if self.num_combats == 0:
            return 0.0
        return self.wins_a / self.num_combats

    @property
    def win_rate_b(self) -> float:
        if self.num_combats == 0:
            return 0.0
        return self.wins_b / self.num_combats


class SimulationConfig(BaseModel):
    """Configuration for an entire mass simulation run."""

    schools: list[str]
    earned_xp_levels: list[int] = Field(
        default_factory=lambda: [0, 50, 100, 150, 200, 250, 300],
    )
    combats_per_matchup: int = 100
    non_combat_pct: float = 0.20
    is_duel: bool = False
    include_asymmetric_xp: bool = False
    xp_asymmetry_max: int = 50
    description: str = ""
    focus_school: str | None = None
    strategies: list[StrategyConfig] = Field(default_factory=list)


class SimulationResult(BaseModel):
    """Complete results from a mass simulation run."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    config: SimulationConfig
    matchup_results: list[MatchupResult]
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
    )
    label: str = ""
    analysis_notes: str = ""
