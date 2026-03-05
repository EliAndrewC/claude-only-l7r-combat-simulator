"""Streamlit UI for mass simulation and analysis."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd
import streamlit as st

from src.engine.mass_simulation import run_mass_simulation
from src.engine.school_registry import get_combat_schools
from src.engine.simulation_storage import (
    delete_simulation,
    list_simulations,
    load_simulation,
    save_simulation,
)
from src.models.mass_simulation import (
    MatchupResult,
    SimulationConfig,
    SimulationResult,
    StrategyConfig,
)

_STORAGE_DIR = Path("simulations")


def _build_xp_chart_data(
    sim: SimulationResult,
) -> tuple[list[str], dict[str, list[float | None]]]:
    """Build chart data with separate lines per strategy x XP offset.

    Returns (index_labels, chart_data) where chart_data maps line labels
    to lists of win rates (one per XP level).
    """
    xp_levels = sorted(sim.config.earned_xp_levels)
    strategy_labels = [s.label for s in sim.config.strategies] if sim.config.strategies else []

    xp_offsets: list[tuple[int, str]] = [(0, "equal")]
    if sim.config.include_asymmetric_xp and sim.config.xp_asymmetry_max > 0:
        asym = sim.config.xp_asymmetry_max
        xp_offsets.append((asym, f"+{asym} XP"))
        xp_offsets.append((-asym, f"-{asym} XP"))

    chart_data: dict[str, list[float | None]] = {}
    for strat_label in strategy_labels:
        for xp_diff, suffix in xp_offsets:
            rates_by_xp: list[float | None] = []
            for xp in xp_levels:
                opp_xp = xp - xp_diff
                xp_rates: list[float] = []
                for mr in sim.matchup_results:
                    if (
                        mr.config.strategy_a
                        and mr.config.strategy_a.label == strat_label
                        and mr.config.earned_xp_a == xp
                        and mr.config.earned_xp_b == opp_xp
                    ):
                        xp_rates.append(mr.win_rate_a)
                if xp_rates:
                    rates_by_xp.append(sum(xp_rates) / len(xp_rates))
                else:
                    rates_by_xp.append(None)
            line_label = (
                f"{strat_label} ({suffix})" if len(xp_offsets) > 1
                else strat_label
            )
            chart_data[line_label] = rates_by_xp

    index_labels = [f"{xp} XP" for xp in xp_levels]
    return index_labels, chart_data


def _build_strategy_comparison_data(
    matchup_results: list[MatchupResult],
    opponent: str,
    strategy_labels: list[str],
) -> list[tuple[str, str, list[dict[str, str | int]], list[MatchupResult]]]:
    """Build pairwise strategy comparison data for an opponent.

    Returns list of (strat_a, strat_b, comparison_rows, load_matchups)
    for each strategy pair.
    """
    mr_index: dict[tuple[str, int, int], MatchupResult] = {}
    for mr in matchup_results:
        if mr.config.strategy_a and mr.config.school_b == opponent:
            key = (
                mr.config.strategy_a.label,
                mr.config.earned_xp_a,
                mr.config.earned_xp_b,
            )
            mr_index[key] = mr

    xp_pairs = sorted({(k[1], k[2]) for k in mr_index})
    strat_pairs = list(combinations(strategy_labels, 2))

    pair_type = tuple[
        str, str,
        list[dict[str, str | int]],
        list[tuple[MatchupResult, MatchupResult]],
    ]
    results: list[pair_type] = []
    for strat_a, strat_b in strat_pairs:
        cmp_rows: list[dict[str, str | int]] = []
        load_pairs: list[tuple[MatchupResult, MatchupResult]] = []
        for focus_xp, opp_xp in xp_pairs:
            mr_a = mr_index.get((strat_a, focus_xp, opp_xp))
            mr_b = mr_index.get((strat_b, focus_xp, opp_xp))
            if mr_a and mr_b:
                diff = mr_a.win_rate_a - mr_b.win_rate_a
                cmp_rows.append({
                    "Focus XP": focus_xp,
                    "Opp XP": opp_xp,
                    f"Win % ({strat_a})": f"{mr_a.win_rate_a:.1%}",
                    f"Win % ({strat_b})": f"{mr_b.win_rate_a:.1%}",
                    "Win % Diff": f"{diff:+.1%}",
                })
                load_pairs.append((mr_a, mr_b))
        results.append((strat_a, strat_b, cmp_rows, load_pairs))
    return results


def _load_matchup_into_single_combat(mr: MatchupResult) -> None:
    """Stage a matchup load for the next rerun.

    We can't set widget-bound keys (f1_preset, etc.) directly because
    the sidebar widgets are already instantiated by the time the Analysis
    tab renders.  Instead, stash the values in a non-widget key and let
    app.py apply them before widget creation on the next rerun.
    """
    pending: dict[str, object] = {
        "f1_preset": mr.config.school_a,
        "f1_earned_xp": mr.config.earned_xp_a,
        "f1_noncombat": int(mr.config.non_combat_pct * 100),
        "f2_preset": mr.config.school_b,
        "f2_earned_xp": mr.config.earned_xp_b,
        "f2_noncombat": int(mr.config.non_combat_pct * 100),
    }
    if mr.config.strategy_a:
        s = mr.config.strategy_a
        pending["f1_void_threshold"] = s.void_threshold
        pending["f1_parry_agg"] = s.parry_aggressiveness
        pending["f1_da_threshold"] = s.da_threshold
        pending["f1_lw_conversion"] = s.lw_conversion
    st.session_state["_pending_load"] = pending
    st.rerun()


def render_mass_simulation_tab() -> None:
    """Render the mass simulation configuration and execution tab."""
    st.header("Mass Simulation")

    all_schools = get_combat_schools()

    focus_school = st.selectbox(
        "Focus school",
        options=all_schools,
        help="The school whose strategies you want to compare",
        key="mass_focus_school",
    )

    # --- Strategy definitions ---
    st.subheader("Strategy Configurations")
    if "strategy_count" not in st.session_state:
        st.session_state["strategy_count"] = 2

    num_strategies = st.session_state["strategy_count"]
    strategies: list[StrategyConfig] = []

    for i in range(num_strategies):
        with st.expander(f"Strategy {i + 1}", expanded=i < 2):
            label = st.text_input(
                "Label", value=f"Strategy {i + 1}" if i > 0 else "Default",
                key=f"strat_label_{i}",
            )
            col_v, col_p = st.columns(2)
            with col_v:
                void_threshold = st.slider(
                    "Void threshold", 0.0, 1.0, 0.25, step=0.05,
                    key=f"strat_void_{i}",
                    help="Min expected SW saved per void spent on wound check",
                )
            with col_p:
                parry_agg = st.slider(
                    "Parry aggressiveness", 0.0, 1.0, 0.6, step=0.05,
                    key=f"strat_parry_{i}",
                    help="Expected parry / attack total threshold for reactive parry",
                )
            col_d, col_l = st.columns(2)
            with col_d:
                da_thresh = st.slider(
                    "DA threshold", 0.5, 1.0, 0.85, step=0.05,
                    key=f"strat_da_{i}",
                    help="Expected hit / DA TN threshold for double attack",
                )
            with col_l:
                lw_conv = st.slider(
                    "LW conversion", 0.5, 1.0, 0.8, step=0.05,
                    key=f"strat_lw_{i}",
                    help="avg WC multiplier threshold for converting light to serious",
                )
            strategies.append(StrategyConfig(
                label=label,
                void_threshold=void_threshold,
                parry_aggressiveness=parry_agg,
                da_threshold=da_thresh,
                lw_conversion=lw_conv,
            ))

    col_add, col_rem = st.columns(2)
    with col_add:
        if st.button("Add strategy", key="add_strat"):
            st.session_state["strategy_count"] = num_strategies + 1
            st.rerun()
    with col_rem:
        if num_strategies > 2 and st.button("Remove last strategy", key="rem_strat"):
            st.session_state["strategy_count"] = num_strategies - 1
            st.rerun()

    # --- XP and combat settings ---
    st.subheader("Simulation Settings")
    col1, col2 = st.columns(2)
    with col1:
        min_xp = st.slider("Min Earned XP", 0, 300, 0, step=50, key="mass_min_xp")
        max_xp = st.slider("Max Earned XP", 0, 300, 300, step=50, key="mass_max_xp")
        xp_step = st.slider("XP Step", 25, 100, 50, step=25, key="mass_xp_step")
    with col2:
        combats_per = st.slider(
            "Combats per matchup", 10, 500, 100, step=10, key="mass_combats",
        )
        non_combat_pct = st.slider(
            "Non-combat XP %", 0, 50, 20, key="mass_noncombat",
        )

    is_duel = st.checkbox("Iaijutsu Duel Mode", key="mass_duel")

    description = st.text_input("Simulation description (optional)", key="mass_desc")

    # Compute XP levels
    if max_xp >= min_xp:
        xp_levels = list(range(min_xp, max_xp + 1, xp_step))
    else:
        xp_levels = [min_xp]

    # Asymmetric XP is automatic: +/- 50
    xp_pairs_count = len(xp_levels)
    for i, xp_a in enumerate(xp_levels):
        for xp_b in xp_levels[i + 1:]:
            if xp_b - xp_a <= 50:
                xp_pairs_count += 1
    # Each asymmetric pair tested in both directions
    asym_count = xp_pairs_count - len(xp_levels)
    total_xp_matchups = len(xp_levels) + asym_count * 2

    n_opponents = len(all_schools) - 1
    n_strategies = len(strategies)
    total_matchups = n_strategies * n_opponents * total_xp_matchups
    total_combats = total_matchups * combats_per

    st.info(
        f"**{n_strategies}** strategies x **{n_opponents}** opponents x "
        f"**{total_xp_matchups}** XP levels = "
        f"**{total_matchups}** matchups x **{combats_per}** combats = "
        f"**{total_combats:,}** total combats"
    )

    if st.button("Run Simulation", type="primary", use_container_width=True, key="mass_run"):
        if not focus_school:
            st.error("Select a focus school.")
            return
        if len(strategies) < 2:
            st.error("Define at least 2 strategies.")
            return

        config = SimulationConfig(
            schools=all_schools,
            earned_xp_levels=xp_levels,
            combats_per_matchup=combats_per,
            non_combat_pct=non_combat_pct / 100.0,
            is_duel=is_duel,
            include_asymmetric_xp=True,
            xp_asymmetry_max=50,
            description=description,
            focus_school=focus_school,
            strategies=strategies,
        )

        progress_bar = st.progress(0, text="Starting simulation...")

        def update_progress(completed: int, total: int) -> None:
            pct = completed / total if total > 0 else 1.0
            progress_bar.progress(pct, text=f"Matchup {completed}/{total}")

        result = run_mass_simulation(config, progress_callback=update_progress)
        progress_bar.progress(1.0, text="Complete!")

        if not result.label:
            strat_names = ", ".join(s.label for s in strategies)
            result.label = f"{focus_school} ({strat_names})"

        save_simulation(result, storage_dir=_STORAGE_DIR)
        st.session_state["last_mass_sim_id"] = str(result.id)
        st.success(f"Simulation complete! {len(result.matchup_results)} matchups saved.")

        _render_result_summary(result)


def _render_result_summary(result: SimulationResult) -> None:
    """Render a quick summary of simulation results."""
    st.subheader("Results Summary")

    if result.config.focus_school and result.config.strategies:
        _render_strategy_summary(result)
    else:
        # Legacy mode: school rankings
        school_wins: dict[str, list[float]] = {}
        for mr in result.matchup_results:
            if mr.config.school_a not in school_wins:
                school_wins[mr.config.school_a] = []
            if mr.config.school_b not in school_wins:
                school_wins[mr.config.school_b] = []
            if mr.config.school_a != mr.config.school_b:
                school_wins[mr.config.school_a].append(mr.win_rate_a)
                school_wins[mr.config.school_b].append(mr.win_rate_b)

        if school_wins:
            rankings = {
                school: sum(rates) / len(rates) if rates else 0.0
                for school, rates in school_wins.items()
            }
            ranking_df = pd.DataFrame(
                [
                    {"School": school, "Avg Win Rate": f"{rate:.1%}"}
                    for school, rate in sorted(
                        rankings.items(), key=lambda x: x[1], reverse=True,
                    )
                ]
            )
            st.dataframe(ranking_df, use_container_width=True, hide_index=True)


def _render_strategy_summary(result: SimulationResult) -> None:
    """Render strategy comparison summary."""
    strategy_rates: dict[str, list[float]] = defaultdict(list)
    for mr in result.matchup_results:
        if mr.config.strategy_a:
            strategy_rates[mr.config.strategy_a.label].append(mr.win_rate_a)

    if strategy_rates:
        rows = []
        for label, rates in sorted(
            strategy_rates.items(),
            key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0,
            reverse=True,
        ):
            avg = sum(rates) / len(rates) if rates else 0.0
            rows.append({
                "Strategy": label,
                "Avg Win Rate": f"{avg:.1%}",
                "Matchups": len(rates),
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True, hide_index=True,
        )


def render_analysis_tab() -> None:
    """Render the analysis tab for viewing saved simulations."""
    st.header("Analysis")

    saved = list_simulations(storage_dir=_STORAGE_DIR)

    if not saved:
        st.info("No saved simulations. Run a mass simulation first.")
        return

    # Selection dropdown
    sim_options = {
        f"{s.label or 'Unnamed'} ({s.timestamp.strftime('%Y-%m-%d %H:%M')}) - "
        f"{len(s.matchup_results)} matchups": s
        for s in saved
    }
    selected_label = st.selectbox(
        "Select simulation", list(sim_options.keys()), key="analysis_select",
    )
    if selected_label is None:
        return

    sim = sim_options[selected_label]

    # Delete button
    col_del, col_spacer = st.columns([1, 5])
    with col_del:
        if st.button("Delete", key="analysis_delete", type="secondary"):
            delete_simulation(sim.id, storage_dir=_STORAGE_DIR)
            st.rerun()

    # Configuration summary
    with st.expander("Configuration", expanded=False):
        cfg = sim.config
        if cfg.focus_school:
            st.write(f"**Focus School:** {cfg.focus_school}")
            if cfg.strategies:
                strat_labels = [s.label for s in cfg.strategies]
                st.write(f"**Strategies:** {', '.join(strat_labels)}")
        st.write(f"**Schools:** {', '.join(cfg.schools)}")
        st.write(f"**XP Levels:** {cfg.earned_xp_levels}")
        st.write(f"**Combats per matchup:** {cfg.combats_per_matchup}")
        st.write(f"**Non-combat XP %:** {cfg.non_combat_pct:.0%}")
        st.write(f"**Duel mode:** {cfg.is_duel}")
        if cfg.include_asymmetric_xp:
            st.write(f"**Asymmetric XP:** up to {cfg.xp_asymmetry_max} difference")
        if cfg.description:
            st.write(f"**Description:** {cfg.description}")

    # Render appropriate view
    if sim.config.focus_school and sim.config.strategies:
        _render_strategy_comparison(sim)
    else:
        _render_win_rate_heatmap(sim)
        _render_xp_line_chart(sim)
        _render_school_rankings(sim)

    # Analysis notes
    st.subheader("Notes")
    notes = st.text_area(
        "Analysis notes",
        value=sim.analysis_notes,
        key="analysis_notes",
        height=150,
    )
    if st.button("Save notes", key="analysis_save_notes"):
        full_sim = load_simulation(sim.id, storage_dir=_STORAGE_DIR)
        full_sim.analysis_notes = notes
        save_simulation(full_sim, storage_dir=_STORAGE_DIR)
        st.success("Notes saved!")


def _render_strategy_comparison(sim: SimulationResult) -> None:
    """Render strategy comparison view for focus school simulations."""
    # --- Strategy comparison table ---
    st.subheader("Strategy Comparison")

    strategy_rates: dict[str, list[float]] = defaultdict(list)
    for mr in sim.matchup_results:
        if mr.config.strategy_a:
            strategy_rates[mr.config.strategy_a.label].append(mr.win_rate_a)

    if strategy_rates:
        rows = []
        for label, rates in sorted(
            strategy_rates.items(),
            key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0,
            reverse=True,
        ):
            avg = sum(rates) / len(rates) if rates else 0.0
            rows.append({
                "Strategy": label,
                "Avg Win Rate": f"{avg:.1%}",
                "Matchups": len(rates),
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True, hide_index=True,
        )

    # --- Win rate by XP level per strategy (line chart) ---
    st.subheader("Win Rate by XP Level")

    strategy_labels = [s.label for s in sim.config.strategies] if sim.config.strategies else []

    index_labels, chart_data = _build_xp_chart_data(sim)
    if chart_data:
        chart_df = pd.DataFrame(chart_data, index=index_labels)
        st.line_chart(chart_df)

    # --- Per-opponent breakdown ---
    st.subheader("Per-Opponent Breakdown")

    opponents = sorted({
        mr.config.school_b for mr in sim.matchup_results
        if mr.config.school_b != sim.config.focus_school
    })

    for opponent in opponents:
        with st.expander(f"vs {opponent}"):
            # Aggregate strategy comparison (existing behavior)
            rows = []
            for strat_label in strategy_labels:
                opp_rates: list[float] = []
                for mr in sim.matchup_results:
                    if (
                        mr.config.strategy_a
                        and mr.config.strategy_a.label == strat_label
                        and mr.config.school_b == opponent
                    ):
                        opp_rates.append(mr.win_rate_a)
                if opp_rates:
                    avg = sum(opp_rates) / len(opp_rates)
                    rows.append({
                        "Strategy": strat_label,
                        "Win Rate": f"{avg:.1%}",
                        "Matchups": len(opp_rates),
                    })
            if rows:
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True, hide_index=True,
                )

            # Per-XP pairwise strategy comparison drill-down
            with st.expander("Matchup Details"):
                pair_data = _build_strategy_comparison_data(
                    sim.matchup_results, opponent, strategy_labels,
                )
                for pair_idx, (strat_a, strat_b, cmp_rows, load_pairs) in enumerate(pair_data):
                    if len(pair_data) > 1:
                        st.markdown(f"**{strat_a} vs {strat_b}**")

                    if cmp_rows:
                        st.dataframe(
                            pd.DataFrame(cmp_rows),
                            use_container_width=True, hide_index=True,
                        )
                        for mr_a, mr_b in load_pairs:
                            xp_label = (
                                f"{mr_a.config.earned_xp_a}xp"
                                f" vs {mr_a.config.earned_xp_b}xp"
                            )
                            col_l, col_r = st.columns(2)
                            with col_l:
                                key_a = (
                                    f"load_{sim.id}_{opponent}_{pair_idx}"
                                    f"_a_{mr_a.config.earned_xp_a}_{mr_a.config.earned_xp_b}"
                                )
                                if st.button(
                                    f"Load {strat_a} {xp_label}",
                                    key=key_a,
                                ):
                                    _load_matchup_into_single_combat(mr_a)
                            with col_r:
                                key_b = (
                                    f"load_{sim.id}_{opponent}_{pair_idx}"
                                    f"_b_{mr_b.config.earned_xp_a}_{mr_b.config.earned_xp_b}"
                                )
                                if st.button(
                                    f"Load {strat_b} {xp_label}",
                                    key=key_b,
                                ):
                                    _load_matchup_into_single_combat(mr_b)


def _render_win_rate_heatmap(sim: SimulationResult) -> None:
    """Render a school-vs-school win rate heatmap."""
    st.subheader("Win Rate Heatmap")

    # Get unique XP levels for filtering
    xp_levels = sorted({mr.config.earned_xp_a for mr in sim.matchup_results})
    if len(xp_levels) > 1:
        selected_xp = st.selectbox(
            "Filter by earned XP level",
            ["All"] + [str(xp) for xp in xp_levels],
            key="heatmap_xp_filter",
        )
    else:
        selected_xp = "All"

    # Build win rate matrix
    schools = sorted(sim.config.schools)
    matrix: dict[str, dict[str, float | None]] = {
        s: {s2: None for s2 in schools} for s in schools
    }
    counts: dict[str, dict[str, list[float]]] = {
        s: {s2: [] for s2 in schools} for s in schools
    }

    for mr in sim.matchup_results:
        if selected_xp != "All":
            xp_val = int(selected_xp)
            if mr.config.earned_xp_a != xp_val or mr.config.earned_xp_b != xp_val:
                continue

        a, b = mr.config.school_a, mr.config.school_b
        if a in counts and b in counts[a]:
            counts[a][b].append(mr.win_rate_a)
        if b in counts and a in counts[b]:
            counts[b][a].append(mr.win_rate_b)

    for s1 in schools:
        for s2 in schools:
            rates = counts[s1][s2]
            if rates:
                matrix[s1][s2] = sum(rates) / len(rates)

    df = pd.DataFrame(matrix).T
    df.index.name = "School A (rows) vs School B (cols)"

    # Format as percentages
    styled = df.style.format(
        lambda x: f"{x:.0%}" if x is not None else "-", na_rep="-",
    ).background_gradient(cmap="RdYlGn", vmin=0.0, vmax=1.0)

    st.dataframe(styled, use_container_width=True)


def _render_xp_line_chart(sim: SimulationResult) -> None:
    """Render win rate trends across XP levels for a selected school."""
    st.subheader("Win Rate by XP Level")

    schools = sorted(sim.config.schools)
    if len(schools) < 2:
        st.info("Need at least 2 schools for this chart.")
        return

    selected_school = st.selectbox(
        "Select school to analyze",
        schools,
        key="xp_chart_school",
    )

    # Collect win rates per opponent per XP level (symmetric only)
    xp_levels = sorted(sim.config.earned_xp_levels)
    chart_data: dict[str, list[float | None]] = {}

    for opponent in schools:
        if opponent == selected_school:
            continue
        rates_by_xp: list[float | None] = []
        for xp in xp_levels:
            found = False
            for mr in sim.matchup_results:
                if mr.config.earned_xp_a != xp or mr.config.earned_xp_b != xp:
                    continue
                if mr.config.school_a == selected_school and mr.config.school_b == opponent:
                    rates_by_xp.append(mr.win_rate_a)
                    found = True
                    break
                if mr.config.school_a == opponent and mr.config.school_b == selected_school:
                    rates_by_xp.append(mr.win_rate_b)
                    found = True
                    break
            if not found:
                rates_by_xp.append(None)
        chart_data[f"vs {opponent}"] = rates_by_xp

    chart_df = pd.DataFrame(chart_data, index=[f"{xp} XP" for xp in xp_levels])
    st.line_chart(chart_df)


def _render_school_rankings(sim: SimulationResult) -> None:
    """Render overall school rankings by average win rate."""
    st.subheader("Overall School Rankings")

    school_wins: dict[str, list[float]] = {s: [] for s in sim.config.schools}

    for mr in sim.matchup_results:
        # Skip mirror matches
        if mr.config.school_a == mr.config.school_b:
            continue
        school_wins[mr.config.school_a].append(mr.win_rate_a)
        school_wins[mr.config.school_b].append(mr.win_rate_b)

    rankings = []
    for school, rates in school_wins.items():
        avg_rate = sum(rates) / len(rates) if rates else 0.0
        rankings.append({
            "Rank": 0,
            "School": school,
            "Avg Win Rate": avg_rate,
            "Matchups": len(rates),
        })

    rankings.sort(key=lambda x: x["Avg Win Rate"], reverse=True)
    for i, r in enumerate(rankings):
        r["Rank"] = i + 1

    df = pd.DataFrame(rankings)
    df["Avg Win Rate"] = df["Avg Win Rate"].apply(lambda x: f"{x:.1%}")
    st.dataframe(df, use_container_width=True, hide_index=True)
