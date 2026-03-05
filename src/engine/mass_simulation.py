"""Mass simulation engine for running many combats across school matchups."""

from __future__ import annotations

from collections.abc import Callable

from src.engine.school_registry import SCHOOL_BUILDERS, SCHOOL_DEFAULT_WEAPONS
from src.engine.simulation import simulate_combat
from src.models.mass_simulation import (
    MatchupConfig,
    MatchupResult,
    SimulationConfig,
    SimulationResult,
    StrategyConfig,
)
from src.models.weapon import WEAPONS


def _generate_xp_pairs(
    levels: list[int],
    include_asymmetric: bool,
    asymmetry_max: int,
) -> list[tuple[int, int]]:
    """Generate XP pairs for simulation.

    Symmetric pairs: (xp, xp) for each level.
    Asymmetric pairs: (xp_a, xp_b) where xp_a < xp_b and diff <= asymmetry_max.
    """
    pairs: list[tuple[int, int]] = [(xp, xp) for xp in levels]
    if include_asymmetric:
        for i, xp_a in enumerate(levels):
            for xp_b in levels[i + 1:]:
                if xp_b - xp_a <= asymmetry_max:
                    pairs.append((xp_a, xp_b))
    return pairs


def _generate_school_pairs(schools: list[str]) -> list[tuple[str, str]]:
    """Generate unordered school pairs including mirror matches.

    Returns N*(N+1)/2 pairs for N schools.
    """
    pairs: list[tuple[str, str]] = []
    for i, school_a in enumerate(schools):
        for school_b in schools[i:]:
            pairs.append((school_a, school_b))
    return pairs


def _run_matchup(cfg: MatchupConfig, num_combats: int) -> MatchupResult:
    """Run a single matchup N times and aggregate results."""
    builder_a = SCHOOL_BUILDERS[cfg.school_a]
    builder_b = SCHOOL_BUILDERS[cfg.school_b]
    weapon_a = WEAPONS[SCHOOL_DEFAULT_WEAPONS[cfg.school_a]]
    weapon_b = WEAPONS[SCHOOL_DEFAULT_WEAPONS[cfg.school_b]]

    wins_a = 0
    wins_b = 0
    draws = 0
    total_rounds = 0
    total_wounds_a = 0.0
    total_wounds_b = 0.0

    for _ in range(num_combats):
        char_a = builder_a(cfg.school_a, cfg.earned_xp_a, cfg.non_combat_pct)
        char_b = builder_b(cfg.school_b, cfg.earned_xp_b, cfg.non_combat_pct)
        log = simulate_combat(
            char_a, char_b, weapon_a, weapon_b,
            is_duel=cfg.is_duel,
            strategy_a=cfg.strategy_a,
            strategy_b=cfg.strategy_b,
        )

        if log.winner == char_a.name:
            wins_a += 1
        elif log.winner == char_b.name:
            wins_b += 1
        else:
            draws += 1

        total_rounds += log.round_number
        if char_a.name in log.wounds:
            total_wounds_a += log.wounds[char_a.name].serious_wounds
        if char_b.name in log.wounds:
            total_wounds_b += log.wounds[char_b.name].serious_wounds

    divisor = max(num_combats, 1)
    return MatchupResult(
        config=cfg,
        num_combats=num_combats,
        wins_a=wins_a,
        wins_b=wins_b,
        draws=draws,
        avg_rounds=total_rounds / divisor,
        avg_wounds_a=total_wounds_a / divisor,
        avg_wounds_b=total_wounds_b / divisor,
    )


def _generate_strategy_matchups(
    focus_school: str,
    strategies: list[StrategyConfig],
    all_schools: list[str],
    xp_pairs: list[tuple[int, int]],
    non_combat_pct: float,
    is_duel: bool,
) -> list[MatchupConfig]:
    """Generate matchups for strategy comparison mode.

    Focus school is always school_a. Opponents are all other schools.
    Each strategy is tested against each opponent at each XP pair.
    For asymmetric XP pairs, both directions are tested.
    """
    opponents = [s for s in all_schools if s != focus_school]
    matchups: list[MatchupConfig] = []

    for strategy in strategies:
        for opponent in opponents:
            for xp_a, xp_b in xp_pairs:
                matchups.append(MatchupConfig(
                    school_a=focus_school,
                    school_b=opponent,
                    earned_xp_a=xp_a,
                    earned_xp_b=xp_b,
                    non_combat_pct=non_combat_pct,
                    is_duel=is_duel,
                    strategy_a=strategy,
                ))
                # For asymmetric XP, also test the reverse direction
                if xp_a != xp_b:
                    matchups.append(MatchupConfig(
                        school_a=focus_school,
                        school_b=opponent,
                        earned_xp_a=xp_b,
                        earned_xp_b=xp_a,
                        non_combat_pct=non_combat_pct,
                        is_duel=is_duel,
                        strategy_a=strategy,
                    ))

    return matchups


def run_mass_simulation(
    config: SimulationConfig,
    progress_callback: Callable[[int, int], None] | None = None,
) -> SimulationResult:
    """Run a full mass simulation across all school/XP combinations.

    Args:
        config: Simulation configuration.
        progress_callback: Optional callback(completed, total) for progress updates.

    Returns:
        SimulationResult with all matchup results.
    """
    xp_pairs = _generate_xp_pairs(
        config.earned_xp_levels,
        include_asymmetric=config.include_asymmetric_xp,
        asymmetry_max=config.xp_asymmetry_max,
    )

    # Strategy comparison mode vs legacy all-vs-all mode
    if config.focus_school and config.strategies:
        matchup_configs = _generate_strategy_matchups(
            focus_school=config.focus_school,
            strategies=config.strategies,
            all_schools=config.schools,
            xp_pairs=xp_pairs,
            non_combat_pct=config.non_combat_pct,
            is_duel=config.is_duel,
        )
    else:
        school_pairs = _generate_school_pairs(config.schools)
        matchup_configs = []
        for school_a, school_b in school_pairs:
            for xp_a, xp_b in xp_pairs:
                matchup_configs.append(MatchupConfig(
                    school_a=school_a,
                    school_b=school_b,
                    earned_xp_a=xp_a,
                    earned_xp_b=xp_b,
                    non_combat_pct=config.non_combat_pct,
                    is_duel=config.is_duel,
                ))

    total_matchups = len(matchup_configs)
    matchup_results: list[MatchupResult] = []
    completed = 0

    for matchup_cfg in matchup_configs:
        result = _run_matchup(matchup_cfg, config.combats_per_matchup)
        matchup_results.append(result)
        completed += 1
        if progress_callback is not None:
            progress_callback(completed, total_matchups)

    return SimulationResult(
        config=config,
        matchup_results=matchup_results,
    )
