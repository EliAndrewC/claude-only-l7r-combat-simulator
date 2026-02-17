"""Streamlit dashboard for the L7R Combat Simulator."""

from __future__ import annotations

import streamlit as st

from src.engine.presets import PRESETS, list_preset_names
from src.engine.xp_builder import build_character_from_xp
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


def _build_character_sidebar(label: str, key_prefix: str) -> tuple[Character, WeaponType]:
    """Build character configuration in the sidebar, returning character and weapon type."""
    st.sidebar.header(f"{label}")

    preset_names = ["Custom", "XP-Based"] + list_preset_names()
    preset_choice = st.sidebar.selectbox(
        f"{label} Preset", preset_names, index=1, key=f"{key_prefix}_preset"
    )

    if preset_choice == "XP-Based":
        earned_xp = st.sidebar.slider(
            f"{label} Earned XP", 0, 350, 0, step=10, key=f"{key_prefix}_earned_xp"
        )
        non_combat = st.sidebar.slider(
            f"{label} Non-combat XP %", 0, 50, 20, key=f"{key_prefix}_noncombat"
        )
        ring_options = [None] + list(RingName)
        school_ring_choice = st.sidebar.selectbox(
            f"{label} School Ring",
            ring_options,
            format_func=lambda r: "None" if r is None else r.value,
            key=f"{key_prefix}_school_ring",
        )
        char = build_character_from_xp(
            name=f"{label}",
            earned_xp=earned_xp,
            school_ring=school_ring_choice,
            non_combat_pct=non_combat / 100.0,
        )
        weapon_type_choice = st.sidebar.selectbox(
            f"{label} Weapon",
            list(WeaponType),
            format_func=lambda w: f"{WEAPONS[w].name} ({WEAPONS[w].dice_str})",
            key=f"{key_prefix}_weapon",
        )
        return char, weapon_type_choice

    if preset_choice != "Custom":
        char, weapon_type = PRESETS[preset_choice]
        weapon_type_choice = st.sidebar.selectbox(
            f"{label} Weapon",
            list(WeaponType),
            index=list(WeaponType).index(weapon_type),
            format_func=lambda w: f"{WEAPONS[w].name} ({WEAPONS[w].dice_str})",
            key=f"{key_prefix}_weapon",
        )
        return char, weapon_type_choice

    # Custom character builder
    name = st.sidebar.text_input(
        f"{label} Name", value=f"Fighter {key_prefix[-1]}", key=f"{key_prefix}_name"
    )

    st.sidebar.markdown("**Rings**")
    ring_cols = st.sidebar.columns(5)
    ring_names = ["Air", "Fire", "Earth", "Water", "Void"]
    ring_values = {}
    for i, rn in enumerate(ring_names):
        ring_values[rn.lower()] = ring_cols[i].number_input(
            rn, min_value=1, max_value=6, value=2, key=f"{key_prefix}_{rn.lower()}"
        )

    st.sidebar.markdown("**Skills**")
    atk_rank = st.sidebar.slider(f"{label} Attack", 0, 5, 3, key=f"{key_prefix}_atk")
    parry_rank = st.sidebar.slider(f"{label} Parry", 0, 5, 2, key=f"{key_prefix}_parry")

    weapon_type_choice = st.sidebar.selectbox(
        f"{label} Weapon",
        list(WeaponType),
        format_func=lambda w: f"{WEAPONS[w].name} ({WEAPONS[w].dice_str})",
        key=f"{key_prefix}_weapon",
    )

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
    char = Character(name=name, rings=rings, skills=skills)
    return char, weapon_type_choice


# --- Restore slider values from URL on page refresh ---
for _pf in ("f1", "f2"):
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
