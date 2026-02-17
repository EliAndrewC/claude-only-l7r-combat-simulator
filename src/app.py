"""Streamlit dashboard for the L7R Combat Simulator."""

from __future__ import annotations

import streamlit as st

from src.engine.waveman import (
    WAVE_MAN_ABILITY_NAMES,
    compute_abilities,
    compute_waveman_stats_from_xp,
)
from src.engine.xp_builder import compute_stats_from_xp
from src.engine.simulation import simulate_combat
from src.models.character import Character, Ring, RingName, Rings, Skill, SkillType
from src.models.weapon import WEAPONS, WeaponType
from src.ui_helpers import (
    compute_combat_stats,
    render_character_card,
    render_combat_stats,
    render_round_log,
    render_winner_banner,
    render_wound_status,
)

st.set_page_config(page_title="L7R Combat Simulator", layout="wide")
st.title("L7R Combat Simulator")

_RING_NAMES = ["air", "fire", "earth", "water", "void"]


def _maybe_repopulate_stats(prefix: str, build_choice: str,
                            earned_xp: int, non_combat: int,
                            school_ring: RingName | None) -> None:
    """Recompute and write ring/skill values to session state when XP inputs change."""
    last_xp = st.session_state.get(f"{prefix}_last_xp")
    last_nc = st.session_state.get(f"{prefix}_last_nc")
    last_sr = st.session_state.get(f"{prefix}_last_school_ring")
    last_mode = st.session_state.get(f"{prefix}_last_preset")

    changed = (
        last_xp != earned_xp
        or last_nc != non_combat
        or last_sr != school_ring
        or last_mode != build_choice
    )

    if not changed:
        return

    if build_choice == "Wave Man":
        stats = compute_waveman_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    else:
        stats = compute_stats_from_xp(
            earned_xp=earned_xp,
            school_ring=school_ring,
            non_combat_pct=non_combat / 100.0,
        )

    for rn in _RING_NAMES:
        st.session_state[f"{prefix}_{rn}"] = stats.ring_values[rn]
    st.session_state[f"{prefix}_atk"] = stats.attack
    st.session_state[f"{prefix}_parry"] = stats.parry

    st.session_state[f"{prefix}_last_xp"] = earned_xp
    st.session_state[f"{prefix}_last_nc"] = non_combat
    st.session_state[f"{prefix}_last_school_ring"] = school_ring
    st.session_state[f"{prefix}_last_preset"] = build_choice


def _build_character_sidebar(label: str, key_prefix: str) -> tuple[Character, WeaponType]:
    """Build character configuration in the sidebar, returning character and weapon type."""
    st.sidebar.header(f"{label}")

    build_options = ["Base", "Wave Man"]
    build_choice = st.sidebar.selectbox(
        f"{label} Build", build_options, index=0, key=f"{key_prefix}_preset"
    )

    # --- XP sliders (both modes) ---
    earned_xp = st.sidebar.slider(
        f"{label} Earned XP", 0, 350, 0, step=10, key=f"{key_prefix}_earned_xp"
    )
    non_combat = st.sidebar.slider(
        f"{label} Non-combat XP %", 0, 50, 20, key=f"{key_prefix}_noncombat"
    )

    # --- School Ring (Base only) ---
    school_ring_choice: RingName | None = None
    if build_choice == "Base":
        ring_options: list[RingName | None] = [None] + list(RingName)
        school_ring_choice = st.sidebar.selectbox(
            f"{label} School Ring",
            ring_options,
            format_func=lambda r: "None" if r is None else r.value,
            key=f"{key_prefix}_school_ring",
        )

    # --- Repopulate stats if XP inputs changed ---
    _maybe_repopulate_stats(key_prefix, build_choice, earned_xp, non_combat, school_ring_choice)

    # --- Editable ring number_inputs ---
    st.sidebar.markdown("**Rings**")
    ring_cols = st.sidebar.columns(5)
    ring_display = ["Air", "Fire", "Earth", "Water", "Void"]
    ring_values: dict[str, int] = {}
    for i, rn in enumerate(ring_display):
        default = st.session_state.get(f"{key_prefix}_{rn.lower()}", 2)
        ring_values[rn.lower()] = ring_cols[i].number_input(
            rn, min_value=1, max_value=6, value=default, key=f"{key_prefix}_{rn.lower()}"
        )

    # --- Editable attack/parry sliders ---
    st.sidebar.markdown("**Skills**")
    atk_default = st.session_state.get(f"{key_prefix}_atk", 0)
    atk_rank = st.sidebar.slider(
        f"{label} Attack", 0, 5, atk_default, key=f"{key_prefix}_atk"
    )
    parry_default = st.session_state.get(f"{key_prefix}_parry", 0)
    parry_rank = st.sidebar.slider(
        f"{label} Parry", 0, 5, parry_default, key=f"{key_prefix}_parry"
    )

    # --- Abilities display (Wave Man only, read-only) ---
    if build_choice == "Wave Man":
        abilities = compute_abilities(earned_xp)
        if abilities:
            st.sidebar.markdown("**Abilities**")
            for ab in abilities:
                name = WAVE_MAN_ABILITY_NAMES.get(ab.number, f"Ability {ab.number}")
                st.sidebar.text(f"#{ab.number} {name} (rank {ab.rank})")

    # --- Weapon selectbox ---
    weapon_type_choice = st.sidebar.selectbox(
        f"{label} Weapon",
        list(WeaponType),
        format_func=lambda w: f"{WEAPONS[w].name} ({WEAPONS[w].dice_str})",
        key=f"{key_prefix}_weapon",
    )

    # --- Construct Character from widget values ---
    rings = Rings(
        air=Ring(name=RingName.AIR, value=ring_values["air"]),
        fire=Ring(name=RingName.FIRE, value=ring_values["fire"]),
        earth=Ring(name=RingName.EARTH, value=ring_values["earth"]),
        water=Ring(name=RingName.WATER, value=ring_values["water"]),
        void=Ring(name=RingName.VOID, value=ring_values["void"]),
    )
    skills = [
        Skill(name="Attack", rank=atk_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        Skill(name="Parry", rank=parry_rank, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
    ]

    profession_abilities = compute_abilities(earned_xp) if build_choice == "Wave Man" else []
    school_ring_val = school_ring_choice if build_choice == "Base" else None

    char = Character(
        name=label,
        rings=rings,
        skills=skills,
        school_ring=school_ring_val,
        profession_abilities=profession_abilities,
    )
    return char, weapon_type_choice


_VALID_BUILD_MODES = {"Base", "Wave Man"}

# --- Restore slider values from URL on page refresh ---
for _pf in ("f1", "f2"):
    _key = f"{_pf}_preset"
    if _key not in st.session_state and f"{_pf}_build" in st.query_params:
        _bval = st.query_params[f"{_pf}_build"]
        if _bval in _VALID_BUILD_MODES:
            st.session_state[_key] = _bval
    _key = f"{_pf}_earned_xp"
    if _key not in st.session_state and f"{_pf}_xp" in st.query_params:
        try:
            _val = int(st.query_params[f"{_pf}_xp"])
            st.session_state[_key] = max(0, min(350, (_val // 10) * 10))
        except ValueError:
            pass
    _key = f"{_pf}_noncombat"
    if _key not in st.session_state and f"{_pf}_nc" in st.query_params:
        try:
            _val = int(st.query_params[f"{_pf}_nc"])
            st.session_state[_key] = max(0, min(50, _val))
        except ValueError:
            pass

# --- Sidebar: Character configuration ---
char_a, wt_a = _build_character_sidebar("Fighter 1", "f1")
char_b, wt_b = _build_character_sidebar("Fighter 2", "f2")

# --- Sync slider values to URL for persistence across refreshes ---
for _pf in ("f1", "f2"):
    _key = f"{_pf}_preset"
    if _key in st.session_state:
        st.query_params[f"{_pf}_build"] = str(st.session_state[_key])
    _key = f"{_pf}_earned_xp"
    if _key in st.session_state:
        st.query_params[f"{_pf}_xp"] = str(st.session_state[_key])
    _key = f"{_pf}_noncombat"
    if _key in st.session_state:
        st.query_params[f"{_pf}_nc"] = str(st.session_state[_key])

# --- Main area: Character cards ---
col1, col2 = st.columns(2)
weapon_a = WEAPONS[wt_a]
weapon_b = WEAPONS[wt_b]
render_character_card(char_a, weapon_a, col1)
render_character_card(char_b, weapon_b, col2)

# --- Fight button ---
st.divider()
if st.button("Fight!", type="primary", use_container_width=True):
    with st.spinner("Simulating combat..."):
        log = simulate_combat(char_a, char_b, weapon_a, weapon_b)
        st.session_state["combat_log"] = log

# --- Results ---
if "combat_log" in st.session_state:
    log = st.session_state["combat_log"]

    render_winner_banner(log)

    stats = compute_combat_stats(log)
    render_combat_stats(stats)

    st.divider()
    render_wound_status(log)

    st.divider()
    render_round_log(log)
