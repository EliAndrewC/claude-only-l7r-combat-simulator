"""Streamlit dashboard for the L7R Combat Simulator."""

from __future__ import annotations

import streamlit as st

from src.engine.character_builders.kakita import compute_kakita_stats_from_xp
from src.engine.character_builders.matsu import compute_matsu_stats_from_xp
from src.engine.character_builders.mirumoto import compute_mirumoto_stats_from_xp
from src.engine.character_builders.otaku import compute_otaku_stats_from_xp
from src.engine.character_builders.shinjo import compute_shinjo_stats_from_xp
from src.engine.character_builders.waveman import (
    WAVE_MAN_ABILITY_NAMES,
    compute_abilities,
    compute_waveman_stats_from_xp,
)
from src.engine.character_builders.xp_builder import compute_stats_from_xp
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

    # Default weapon when build mode changes
    if last_mode != build_choice:
        if build_choice == "Wave Man":
            st.session_state[f"{prefix}_weapon"] = WeaponType.SPEAR
        else:
            st.session_state[f"{prefix}_weapon"] = WeaponType.KATANA

    if build_choice == "Mirumoto Bushi":
        stats = compute_mirumoto_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Matsu Bushi":
        stats = compute_matsu_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Kakita Duelist":
        stats = compute_kakita_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Shinjo Bushi":
        stats = compute_shinjo_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Otaku Bushi":
        stats = compute_otaku_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Wave Man":
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

    # School knack ranks
    school_builds = (
        "Mirumoto Bushi", "Matsu Bushi", "Kakita Duelist",
        "Shinjo Bushi", "Otaku Bushi",
    )
    if build_choice in school_builds:
        for knack_key, rank in stats.knack_ranks.items():
            st.session_state[f"{prefix}_knack_{knack_key}"] = rank

    st.session_state[f"{prefix}_last_xp"] = earned_xp
    st.session_state[f"{prefix}_last_nc"] = non_combat
    st.session_state[f"{prefix}_last_school_ring"] = school_ring
    st.session_state[f"{prefix}_last_preset"] = build_choice


def _build_character_sidebar(label: str, key_prefix: str) -> tuple[Character, WeaponType, str]:
    """Build character configuration in the sidebar.

    Returns character, weapon type, and build choice.
    """
    st.sidebar.header(f"{label}")

    build_options = [
        "Base", "Wave Man", "Mirumoto Bushi",
        "Matsu Bushi", "Kakita Duelist", "Shinjo Bushi",
        "Otaku Bushi",
    ]
    build_choice = st.sidebar.selectbox(
        f"{label} Build", build_options, index=0, key=f"{key_prefix}_preset"
    )

    # --- XP sliders (both modes) ---
    earned_xp = st.sidebar.slider(
        f"{build_choice} Earned XP", 0, 350, 0, step=10, key=f"{key_prefix}_earned_xp"
    )
    non_combat = st.sidebar.slider(
        f"{build_choice} Non-combat XP %", 0, 50, 20, key=f"{key_prefix}_noncombat"
    )

    # --- School Ring (Base only) ---
    school_ring_choice: RingName | None = None
    if build_choice == "Base":
        ring_options: list[RingName | None] = [None] + list(RingName)
        school_ring_choice = st.sidebar.selectbox(
            f"{build_choice} School Ring",
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
        f"{build_choice} Attack", 0, 5, atk_default, key=f"{key_prefix}_atk"
    )
    parry_default = st.session_state.get(f"{key_prefix}_parry", 0)
    parry_rank = st.sidebar.slider(
        f"{build_choice} Parry", 0, 5, parry_default, key=f"{key_prefix}_parry"
    )

    # --- Knack sliders (school builds only) ---
    knack_ranks: dict[str, int] = {}
    if build_choice == "Mirumoto Bushi":
        knack_display = {
            "counterattack": "Counterattack",
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu",
        }
        st.sidebar.markdown("**School Knacks**")
        for knack_key, knack_name in knack_display.items():
            default = st.session_state.get(f"{key_prefix}_knack_{knack_key}", 1)
            knack_ranks[knack_key] = st.sidebar.slider(
                f"{build_choice} {knack_name}", 0, 5, default, key=f"{key_prefix}_knack_{knack_key}"
            )
        # Dan level display (read-only)
        dan_level = min(knack_ranks.values()) if knack_ranks else 0
        st.sidebar.text(f"Dan: {dan_level}")
        # Active techniques display
        techniques = []
        if dan_level >= 1:
            techniques.append("1st: +1 die attack/parry")
        if dan_level >= 2:
            techniques.append("2nd: free raise on parry")
        if dan_level >= 3:
            techniques.append("3rd: phase shift + roll bonus")
        if dan_level >= 4:
            techniques.append("4th: half parry reduction")
        if dan_level >= 5:
            techniques.append("5th: +10/void on combat")
        if dan_level >= 1:
            techniques.append("SA: temp void on parry")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Matsu Bushi":
        knack_display = {"double_attack": "Double Attack", "iaijutsu": "Iaijutsu", "lunge": "Lunge"}
        st.sidebar.markdown("**School Knacks**")
        for knack_key, knack_name in knack_display.items():
            default = st.session_state.get(f"{key_prefix}_knack_{knack_key}", 1)
            knack_ranks[knack_key] = st.sidebar.slider(
                f"{build_choice} {knack_name}", 0, 5, default, key=f"{key_prefix}_knack_{knack_key}"
            )
        # Dan level display (read-only)
        dan_level = min(knack_ranks.values()) if knack_ranks else 0
        st.sidebar.text(f"Dan: {dan_level}")
        # Active techniques display
        techniques = []
        if dan_level >= 1:
            techniques.append("1st: +1 die DA/iaijutsu/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise iaijutsu")
        if dan_level >= 3:
            techniques.append("3rd: void -> WC bonus")
        if dan_level >= 4:
            techniques.append("4th: near-miss DA + Fire")
        if dan_level >= 5:
            techniques.append("5th: light wounds reset 15")
        if dan_level >= 1:
            techniques.append("SA: 10 initiative dice")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Kakita Duelist":
        knack_display = {"double_attack": "Double Attack", "iaijutsu": "Iaijutsu", "lunge": "Lunge"}
        st.sidebar.markdown("**School Knacks**")
        for knack_key, knack_name in knack_display.items():
            default = st.session_state.get(f"{key_prefix}_knack_{knack_key}", 1)
            knack_ranks[knack_key] = st.sidebar.slider(
                f"{build_choice} {knack_name}", 0, 5, default, key=f"{key_prefix}_knack_{knack_key}"
            )
        # Dan level display (read-only)
        dan_level = min(knack_ranks.values()) if knack_ranks else 0
        st.sidebar.text(f"Dan: {dan_level}")
        # Active techniques display
        techniques = []
        if dan_level >= 1:
            techniques.append("1st: +1 die DA/iaijutsu/init")
        if dan_level >= 2:
            techniques.append("2nd: free raise iaijutsu")
        if dan_level >= 3:
            techniques.append("3rd: phase gap attack bonus")
        if dan_level >= 4:
            techniques.append("4th: Fire +1 / iaijutsu dmg raise")
        if dan_level >= 5:
            techniques.append("5th: contested iaijutsu opener")
        if dan_level >= 1:
            techniques.append("SA: 10s → Phase 0")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Shinjo Bushi":
        knack_display = {"double_attack": "Double Attack", "iaijutsu": "Iaijutsu", "lunge": "Lunge"}
        st.sidebar.markdown("**School Knacks**")
        for knack_key, knack_name in knack_display.items():
            default = st.session_state.get(f"{key_prefix}_knack_{knack_key}", 1)
            knack_ranks[knack_key] = st.sidebar.slider(
                f"{build_choice} {knack_name}", 0, 5, default, key=f"{key_prefix}_knack_{knack_key}"
            )
        # Dan level display (read-only)
        dan_level = min(knack_ranks.values()) if knack_ranks else 0
        st.sidebar.text(f"Dan: {dan_level}")
        # Active techniques display
        techniques = []
        if dan_level >= 1:
            techniques.append("1st: +1 die DA/init/parry")
        if dan_level >= 2:
            techniques.append("2nd: free raise parry")
        if dan_level >= 3:
            techniques.append("3rd: post-parry dice decrease")
        if dan_level >= 4:
            techniques.append("4th: Air +1 / highest die → 1")
        if dan_level >= 5:
            techniques.append("5th: parry margin → WC bonus")
        if dan_level >= 1:
            techniques.append("SA: held die bonus 2X")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Otaku Bushi":
        knack_display = {"double_attack": "Double Attack", "iaijutsu": "Iaijutsu", "lunge": "Lunge"}
        st.sidebar.markdown("**School Knacks**")
        for knack_key, knack_name in knack_display.items():
            default = st.session_state.get(f"{key_prefix}_knack_{knack_key}", 1)
            knack_ranks[knack_key] = st.sidebar.slider(
                f"{build_choice} {knack_name}", 0, 5, default, key=f"{key_prefix}_knack_{knack_key}"
            )
        # Dan level display (read-only)
        dan_level = min(knack_ranks.values()) if knack_ranks else 0
        st.sidebar.text(f"Dan: {dan_level}")
        # Active techniques display
        techniques = []
        if dan_level >= 1:
            techniques.append("1st: +1 die lunge/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise WC")
        if dan_level >= 3:
            techniques.append("3rd: opponent dice slowdown")
        if dan_level >= 4:
            techniques.append("4th: Fire +1 / lunge immune parry")
        if dan_level >= 5:
            techniques.append("5th: trade dmg for auto SW")
        if dan_level >= 1:
            techniques.append("SA: counter-lunge")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

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
        f"{build_choice} Weapon",
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

    # School knack skills
    if build_choice == "Mirumoto Bushi":
        knack_display_names = {
            "counterattack": "Counterattack",
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Matsu Bushi":
        knack_display_names = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu", "lunge": "Lunge",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Kakita Duelist":
        knack_display_names = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu", "lunge": "Lunge",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Shinjo Bushi":
        knack_display_names = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu", "lunge": "Lunge",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Otaku Bushi":
        knack_display_names = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu", "lunge": "Lunge",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))

    profession_abilities = compute_abilities(earned_xp) if build_choice == "Wave Man" else []

    school_name = None
    school_ring_val = None
    school_knacks_val: list[str] = []
    if build_choice == "Base":
        school_ring_val = school_ring_choice
    elif build_choice == "Mirumoto Bushi":
        school_name = "Mirumoto Bushi"
        school_ring_val = RingName.VOID
        school_knacks_val = ["Counterattack", "Double Attack", "Iaijutsu"]
    elif build_choice == "Matsu Bushi":
        school_name = "Matsu Bushi"
        school_ring_val = RingName.FIRE
        school_knacks_val = ["Double Attack", "Iaijutsu", "Lunge"]
    elif build_choice == "Kakita Duelist":
        school_name = "Kakita Duelist"
        school_ring_val = RingName.FIRE
        school_knacks_val = ["Double Attack", "Iaijutsu", "Lunge"]
    elif build_choice == "Shinjo Bushi":
        school_name = "Shinjo Bushi"
        school_ring_val = RingName.AIR
        school_knacks_val = ["Double Attack", "Iaijutsu", "Lunge"]
    elif build_choice == "Otaku Bushi":
        school_name = "Otaku Bushi"
        school_ring_val = RingName.FIRE
        school_knacks_val = ["Double Attack", "Iaijutsu", "Lunge"]

    char = Character(
        name=label,
        rings=rings,
        skills=skills,
        school=school_name,
        school_ring=school_ring_val,
        school_knacks=school_knacks_val,
        profession_abilities=profession_abilities,
    )
    return char, weapon_type_choice, build_choice


_VALID_BUILD_MODES = {
    "Base", "Wave Man", "Mirumoto Bushi",
    "Matsu Bushi", "Kakita Duelist", "Shinjo Bushi",
    "Otaku Bushi",
}

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
char_a, wt_a, build_a = _build_character_sidebar("Fighter 1", "f1")
char_b, wt_b, build_b = _build_character_sidebar("Fighter 2", "f2")

# Compute display names from build choices
if build_a == build_b:
    char_a.name = f"{build_a} 1"
    char_b.name = f"{build_b} 2"
else:
    char_a.name = build_a
    char_b.name = build_b

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
