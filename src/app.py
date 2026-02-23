"""Streamlit dashboard for the L7R Combat Simulator."""

from __future__ import annotations

import streamlit as st

from src.engine.character_builders.akodo import compute_akodo_stats_from_xp
from src.engine.character_builders.bayushi import compute_bayushi_stats_from_xp
from src.engine.character_builders.brotherhood_monk import compute_brotherhood_monk_stats_from_xp
from src.engine.character_builders.courtier import compute_courtier_stats_from_xp
from src.engine.character_builders.daidoji import compute_daidoji_stats_from_xp
from src.engine.character_builders.doji_artisan import compute_doji_artisan_stats_from_xp
from src.engine.character_builders.hida import compute_hida_stats_from_xp
from src.engine.character_builders.hiruma import compute_hiruma_stats_from_xp
from src.engine.character_builders.ide_diplomat import compute_ide_diplomat_stats_from_xp
from src.engine.character_builders.ikoma_bard import compute_ikoma_bard_stats_from_xp
from src.engine.character_builders.isawa_duelist import compute_isawa_duelist_stats_from_xp
from src.engine.character_builders.isawa_ishi import compute_isawa_ishi_stats_from_xp
from src.engine.character_builders.kakita import compute_kakita_stats_from_xp
from src.engine.character_builders.kitsuki import compute_kitsuki_stats_from_xp
from src.engine.character_builders.kuni import compute_kuni_stats_from_xp
from src.engine.character_builders.matsu import compute_matsu_stats_from_xp
from src.engine.character_builders.merchant import compute_merchant_stats_from_xp
from src.engine.character_builders.mirumoto import compute_mirumoto_stats_from_xp
from src.engine.character_builders.otaku import compute_otaku_stats_from_xp
from src.engine.character_builders.priest import compute_priest_stats_from_xp
from src.engine.character_builders.shiba import compute_shiba_stats_from_xp
from src.engine.character_builders.shinjo import compute_shinjo_stats_from_xp
from src.engine.character_builders.shosuro import compute_shosuro_stats_from_xp
from src.engine.character_builders.togashi import compute_togashi_stats_from_xp
from src.engine.character_builders.waveman import (
    WAVE_MAN_ABILITY_NAMES,
    compute_abilities,
    compute_waveman_stats_from_xp,
)
from src.engine.character_builders.xp_builder import compute_stats_from_xp
from src.engine.character_builders.yogo import compute_yogo_stats_from_xp
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
        elif build_choice == "Brotherhood Monk":
            st.session_state[f"{prefix}_weapon"] = WeaponType.UNARMED
        else:
            st.session_state[f"{prefix}_weapon"] = WeaponType.KATANA

    if build_choice == "Akodo Bushi":
        stats = compute_akodo_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Mirumoto Bushi":
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
    elif build_choice == "Daidoji Yojimbo":
        stats = compute_daidoji_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Doji Artisan":
        stats = compute_doji_artisan_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Hida Bushi":
        stats = compute_hida_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Hiruma Scout":
        stats = compute_hiruma_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Ide Diplomat":
        stats = compute_ide_diplomat_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Ikoma Bard":
        stats = compute_ikoma_bard_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Isawa Duelist":
        stats = compute_isawa_duelist_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Isawa Ishi":
        stats = compute_isawa_ishi_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Kitsuki Magistrate":
        stats = compute_kitsuki_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Kuni Witch Hunter":
        stats = compute_kuni_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Priest":
        stats = compute_priest_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Shosuro Actor":
        stats = compute_shosuro_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Shiba Bushi":
        stats = compute_shiba_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Bayushi Bushi":
        stats = compute_bayushi_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Brotherhood Monk":
        stats = compute_brotherhood_monk_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Togashi Ise Zumi":
        stats = compute_togashi_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Courtier":
        stats = compute_courtier_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Merchant":
        stats = compute_merchant_stats_from_xp(
            earned_xp=earned_xp,
            non_combat_pct=non_combat / 100.0,
        )
    elif build_choice == "Yogo Warden":
        stats = compute_yogo_stats_from_xp(
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
        "Akodo Bushi", "Mirumoto Bushi", "Matsu Bushi", "Kakita Duelist",
        "Shinjo Bushi", "Otaku Bushi", "Daidoji Yojimbo", "Doji Artisan",
        "Hida Bushi", "Hiruma Scout", "Ide Diplomat",
        "Ikoma Bard", "Isawa Duelist", "Isawa Ishi",
        "Kitsuki Magistrate", "Kuni Witch Hunter", "Shosuro Actor",
        "Shiba Bushi", "Bayushi Bushi", "Brotherhood Monk",
        "Courtier", "Merchant", "Priest",
        "Togashi Ise Zumi", "Yogo Warden",
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
        "Base", "Wave Man",
        "Courtier", "Merchant", "Priest",
        "Akodo Bushi", "Bayushi Bushi", "Brotherhood Monk",
        "Daidoji Yojimbo", "Doji Artisan", "Hida Bushi",
        "Hiruma Scout", "Ide Diplomat", "Ikoma Bard",
        "Isawa Duelist", "Isawa Ishi", "Kakita Duelist",
        "Kitsuki Magistrate", "Kuni Witch Hunter",
        "Matsu Bushi", "Mirumoto Bushi", "Otaku Bushi",
        "Shiba Bushi", "Shinjo Bushi", "Shosuro Actor",
        "Togashi Ise Zumi", "Yogo Warden",
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
    if build_choice == "Akodo Bushi":
        knack_display = {
            "double_attack": "Double Attack",
            "feint": "Feint",
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
            techniques.append("1st: +1 die atk/DA/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise WC")
        if dan_level >= 3:
            techniques.append("3rd: WC excess -> atk pool")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / void WC free raises")
        if dan_level >= 5:
            techniques.append("5th: damage reflection")
        if dan_level >= 1:
            techniques.append("SA: temp void on feint")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Mirumoto Bushi":
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

    elif build_choice == "Daidoji Yojimbo":
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
            techniques.append("1st: +1 die atk/CA/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise CA")
        if dan_level >= 3:
            techniques.append("3rd: CA -> WC bonus")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / bodyguard")
        if dan_level >= 5:
            techniques.append("5th: WC excess -> TN reduction")
        if dan_level >= 1:
            techniques.append("SA: CA interrupt for 1 die")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Doji Artisan":
        knack_display = {
            "counterattack": "Counterattack",
            "oppose_social": "Oppose Social",
            "worldliness": "Worldliness",
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
            techniques.append("1st: +1 die CA/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise manipulation")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / phase bonus")
        if dan_level >= 5:
            techniques.append("5th: TN bonus on rolls")
        if dan_level >= 1:
            techniques.append("SA: void CA interrupt")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Hida Bushi":
        knack_display = {"counterattack": "Counterattack", "iaijutsu": "Iaijutsu", "lunge": "Lunge"}
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
            techniques.append("1st: +1 die atk/CA/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise CA")
        if dan_level >= 3:
            techniques.append("3rd: reroll low dice on CA")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / 2 SW replace WC")
        if dan_level >= 5:
            techniques.append("5th: CA margin → WC bonus")
        if dan_level >= 1:
            techniques.append("SA: counterattack for 1 die")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Hiruma Scout":
        knack_display = {
            "double_attack": "Double Attack",
            "feint": "Feint",
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
            techniques.append("1st: +1 die init/parry/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise parry")
        if dan_level >= 3:
            techniques.append("3rd: parry -> atk/dmg bonus")
        if dan_level >= 4:
            techniques.append("4th: Air +1 / dice lowering")
        if dan_level >= 5:
            techniques.append("5th: parry -> damage reduction")
        if dan_level >= 1:
            techniques.append("SA: ally TN +5 (no-op)")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Ide Diplomat":
        knack_display = {
            "double_attack": "Double Attack",
            "feint": "Feint",
            "worldliness": "Worldliness",
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
            techniques.append("1st: +1 die atk/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise WC")
        if dan_level >= 3:
            techniques.append("3rd: void → penalty opponent roll")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / extra void")
        if dan_level >= 5:
            techniques.append("5th: void regen")
        if dan_level >= 1:
            techniques.append("SA: feint → -10 TN")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Ikoma Bard":
        knack_display = {
            "discern_honor": "Discern Honor",
            "oppose_knowledge": "Oppose Knowledge",
            "oppose_social": "Oppose Social",
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
            techniques.append("1st: +1 die atk/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise atk")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / 10 dice unparried dmg")
        if dan_level >= 5:
            techniques.append("5th: double SA / defensive cancel")
        if dan_level >= 1:
            techniques.append("SA: force parry")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Isawa Duelist":
        knack_display = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu",
            "lunge": "Lunge",
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
            techniques.append("1st: +1 die DA/lunge/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise WC")
        if dan_level >= 3:
            techniques.append("3rd: +3X atk / -5 TN")
        if dan_level >= 4:
            techniques.append("4th: Water +1")
        if dan_level >= 5:
            techniques.append("5th: WC excess -> WC pool")
        if dan_level >= 1:
            techniques.append("SA: Water for damage")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Isawa Ishi":
        knack_display = {
            "absorb_void": "Absorb Void",
            "kharmic_spin": "Kharmic Spin",
            "otherworldliness": "Otherworldliness",
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
            techniques.append("1st: +1 die precepts")
        if dan_level >= 2:
            techniques.append("2nd: free raise chosen")
        if dan_level >= 3:
            techniques.append("3rd: void to ally")
        if dan_level >= 4:
            techniques.append("4th: Void +1 / void block")
        if dan_level >= 5:
            techniques.append("5th: negate school")
        if dan_level >= 1:
            techniques.append("SA: modified void pool")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Kitsuki Magistrate":
        knack_display = {
            "discern_honor": "Discern Honor",
            "iaijutsu": "Iaijutsu",
            "presence": "Presence",
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
            techniques.append("1st: +1 die WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise interrogation")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / know stats")
        if dan_level >= 5:
            techniques.append("5th: ring debuff opponent")
        if dan_level >= 1:
            techniques.append("SA: +2x Water atk")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Kuni Witch Hunter":
        knack_display = {
            "detect_taint": "Detect Taint",
            "iaijutsu": "Iaijutsu",
            "presence": "Presence",
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
            techniques.append("1st: +1 die dmg/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise interrogation")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Earth +1 / parry-only die")
        if dan_level >= 5:
            techniques.append("5th: damage reflection")
        if dan_level >= 1:
            techniques.append("SA: +1k1 WC")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Shosuro Actor":
        knack_display = {
            "athletics": "Athletics",
            "discern_honor": "Discern Honor",
            "pontificate": "Pontificate",
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
            techniques.append("1st: +1 die atk/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise sincerity")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Air +1")
        if dan_level >= 5:
            techniques.append("5th: +lowest 3 dice")
        if dan_level >= 1:
            techniques.append("SA: +Acting dice atk/parry/WC")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Priest":
        knack_display = {
            "conviction": "Conviction",
            "otherworldliness": "Otherworldliness",
            "pontificate": "Pontificate",
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
            techniques.append("1st: +1 die WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise honor")
        if dan_level >= 3:
            techniques.append("3rd: dice swap")
        if dan_level >= 4:
            techniques.append("4th: Water +1")
        if dan_level >= 5:
            techniques.append("5th: conviction pool")
        if dan_level >= 1:
            techniques.append("SA: all 10 rituals")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Shiba Bushi":
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
            techniques.append("1st: +1 die DA/parry/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise parry")
        if dan_level >= 3:
            techniques.append("3rd: parry deals damage")
        if dan_level >= 4:
            techniques.append("4th: Air +1 / +3k1 WC")
        if dan_level >= 5:
            techniques.append("5th: parry margin → TN reduction")
        if dan_level >= 1:
            techniques.append("SA: interrupt for 1 die")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Bayushi Bushi":
        knack_display = {
            "double_attack": "Double Attack",
            "feint": "Feint",
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
            techniques.append("1st: +1 die DA/iaijutsu/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise DA")
        if dan_level >= 3:
            techniques.append("3rd: feint deals damage")
        if dan_level >= 4:
            techniques.append("4th: Fire +1 / feint free raise")
        if dan_level >= 5:
            techniques.append("5th: half LW for serious calc")
        if dan_level >= 1:
            techniques.append("SA: void on atk → +1k1 dmg")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Yogo Warden":
        knack_display = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu",
            "feint": "Feint",
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
            techniques.append("1st: +1 die atk/dmg/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise WC")
        if dan_level >= 3:
            techniques.append("3rd: void -> LW reduction")
        if dan_level >= 4:
            techniques.append("4th: Earth +1 / void WC free raises")
        if dan_level >= 5:
            techniques.append("5th: TBD")
        if dan_level >= 1:
            techniques.append("SA: temp void on SW")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Brotherhood Monk":
        knack_display = {
            "conviction": "Conviction",
            "otherworldliness": "Otherworldliness",
            "worldliness": "Worldliness",
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
            techniques.append("1st: +1 die atk/dmg/WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise atk")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Water +1 / no parry reduction")
        if dan_level >= 5:
            techniques.append("5th: pre-damage counterattack")
        if dan_level >= 1:
            techniques.append("SA: +1 kept dmg (unarmed)")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Togashi Ise Zumi":
        knack_display = {
            "athletics": "Athletics",
            "conviction": "Conviction",
            "dragon_tattoo": "Dragon Tattoo",
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
            techniques.append("1st: +1 die atk/parry")
        if dan_level >= 2:
            techniques.append("2nd: free raise athletics")
        if dan_level >= 3:
            techniques.append("3rd: athletics free raises")
        if dan_level >= 4:
            techniques.append("4th: Void +1 / reroll contested")
        if dan_level >= 5:
            techniques.append("5th: spend void heal 2 SW")
        if dan_level >= 1:
            techniques.append("SA: +1 initiative die")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Courtier":
        knack_display = {
            "discern_honor": "Discern Honor",
            "oppose_social": "Oppose Social",
            "worldliness": "Worldliness",
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
            techniques.append("1st: +1 die WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise manipulation")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Air +1 / temp void on hit")
        if dan_level >= 5:
            techniques.append("5th: +Air contested/TN rolls")
        if dan_level >= 1:
            techniques.append("SA: +Air atk/dmg")
        if techniques:
            st.sidebar.text("Techniques: " + ", ".join(techniques))

    elif build_choice == "Merchant":
        knack_display = {
            "discern_honor": "Discern Honor",
            "oppose_knowledge": "Oppose Knowledge",
            "worldliness": "Worldliness",
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
            techniques.append("1st: +1 die WC")
        if dan_level >= 2:
            techniques.append("2nd: free raise interrogation")
        if dan_level >= 3:
            techniques.append("3rd: free raise pool")
        if dan_level >= 4:
            techniques.append("4th: Water +1")
        if dan_level >= 5:
            techniques.append("5th: selective reroll")
        if dan_level >= 1:
            techniques.append("SA: post-roll void")
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
    if build_choice == "Akodo Bushi":
        knack_display_names = {
            "double_attack": "Double Attack",
            "feint": "Feint",
            "iaijutsu": "Iaijutsu",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Mirumoto Bushi":
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
    elif build_choice == "Daidoji Yojimbo":
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
    elif build_choice == "Doji Artisan":
        knack_display_names = {
            "counterattack": "Counterattack",
            "oppose_social": "Oppose Social",
            "worldliness": "Worldliness",
        }
        skills.append(Skill(
            name="Culture", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.AIR,
        ))
        knack_rings: dict[str, RingName] = {
            "counterattack": RingName.FIRE,
            "oppose_social": RingName.WATER,
            "worldliness": RingName.WATER,
        }
        knack_skill_types: dict[str, SkillType] = {
            "counterattack": SkillType.ADVANCED,
            "oppose_social": SkillType.BASIC,
            "worldliness": SkillType.BASIC,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=knack_skill_types[knack_key],
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Hida Bushi":
        knack_display_names = {
            "counterattack": "Counterattack",
            "iaijutsu": "Iaijutsu", "lunge": "Lunge",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Hiruma Scout":
        knack_display_names = {
            "double_attack": "Double Attack",
            "feint": "Feint",
            "iaijutsu": "Iaijutsu",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Ide Diplomat":
        knack_display_names = {
            "double_attack": "Double Attack",
            "feint": "Feint",
            "worldliness": "Worldliness",
        }
        skills.append(Skill(
            name="Tact", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings: dict[str, RingName] = {
            "double_attack": RingName.FIRE,
            "feint": RingName.FIRE,
            "worldliness": RingName.WATER,
        }
        knack_skill_types: dict[str, SkillType] = {
            "double_attack": SkillType.ADVANCED,
            "feint": SkillType.ADVANCED,
            "worldliness": SkillType.BASIC,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=knack_skill_types[knack_key],
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Ikoma Bard":
        knack_display_names = {
            "discern_honor": "Discern Honor",
            "oppose_knowledge": "Oppose Knowledge",
            "oppose_social": "Oppose Social",
        }
        skills.append(Skill(
            name="Bragging", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings = {
            "discern_honor": RingName.WATER,
            "oppose_knowledge": RingName.AIR,
            "oppose_social": RingName.WATER,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Isawa Duelist":
        knack_display_names = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu",
            "lunge": "Lunge",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Isawa Ishi":
        knack_display_names = {
            "absorb_void": "Absorb Void",
            "kharmic_spin": "Kharmic Spin",
            "otherworldliness": "Otherworldliness",
        }
        skills.append(Skill(
            name="Precepts", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings = {
            "absorb_void": RingName.VOID,
            "kharmic_spin": RingName.VOID,
            "otherworldliness": RingName.VOID,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Kitsuki Magistrate":
        knack_display_names = {
            "discern_honor": "Discern Honor",
            "iaijutsu": "Iaijutsu",
            "presence": "Presence",
        }
        skills.append(Skill(
            name="Investigation", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings = {
            "discern_honor": RingName.WATER,
            "iaijutsu": RingName.FIRE,
            "presence": RingName.EARTH,
        }
        knack_skill_types = {
            "discern_honor": SkillType.ADVANCED,
            "iaijutsu": SkillType.ADVANCED,
            "presence": SkillType.ADVANCED,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=knack_skill_types[knack_key],
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Kuni Witch Hunter":
        knack_display_names = {
            "detect_taint": "Detect Taint",
            "iaijutsu": "Iaijutsu",
            "presence": "Presence",
        }
        skills.append(Skill(
            name="Investigation", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.EARTH,
        ))
        knack_rings = {
            "detect_taint": RingName.EARTH,
            "iaijutsu": RingName.FIRE,
            "presence": RingName.EARTH,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Shosuro Actor":
        knack_display_names = {
            "athletics": "Athletics",
            "discern_honor": "Discern Honor",
            "pontificate": "Pontificate",
        }
        skills.append(Skill(
            name="Acting", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.AIR,
        ))
        skills.append(Skill(
            name="Sincerity", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.AIR,
        ))
        knack_rings = {
            "athletics": RingName.WATER,
            "discern_honor": RingName.AIR,
            "pontificate": RingName.AIR,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Priest":
        knack_display_names = {
            "conviction": "Conviction",
            "otherworldliness": "Otherworldliness",
            "pontificate": "Pontificate",
        }
        skills.append(Skill(
            name="Precepts", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings = {
            "conviction": RingName.EARTH,
            "otherworldliness": RingName.VOID,
            "pontificate": RingName.AIR,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Shiba Bushi":
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
    elif build_choice == "Bayushi Bushi":
        knack_display_names = {
            "double_attack": "Double Attack",
            "feint": "Feint",
            "iaijutsu": "Iaijutsu",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Yogo Warden":
        knack_display_names = {
            "double_attack": "Double Attack",
            "iaijutsu": "Iaijutsu",
            "feint": "Feint",
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.ADVANCED,
                ring=RingName.FIRE,
            ))
    elif build_choice == "Brotherhood Monk":
        knack_display_names = {
            "conviction": "Conviction",
            "otherworldliness": "Otherworldliness",
            "worldliness": "Worldliness",
        }
        skills.append(Skill(
            name="Precepts", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings = {
            "conviction": RingName.EARTH,
            "otherworldliness": RingName.VOID,
            "worldliness": RingName.WATER,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Togashi Ise Zumi":
        knack_display_names = {
            "athletics": "Athletics",
            "conviction": "Conviction",
            "dragon_tattoo": "Dragon Tattoo",
        }
        skills.append(Skill(
            name="Precepts", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        knack_rings = {
            "athletics": RingName.WATER,
            "conviction": RingName.EARTH,
            "dragon_tattoo": RingName.VOID,
        }
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=knack_rings[knack_key],
            ))
    elif build_choice == "Courtier":
        knack_display_names = {
            "discern_honor": "Discern Honor",
            "oppose_social": "Oppose Social",
            "worldliness": "Worldliness",
        }
        skills.append(Skill(
            name="Tact", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.AIR,
        ))
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=RingName.AIR,
            ))
    elif build_choice == "Merchant":
        knack_display_names = {
            "discern_honor": "Discern Honor",
            "oppose_knowledge": "Oppose Knowledge",
            "worldliness": "Worldliness",
        }
        skills.append(Skill(
            name="Sincerity", rank=5,
            skill_type=SkillType.BASIC, ring=RingName.WATER,
        ))
        for knack_key, knack_name in knack_display_names.items():
            skills.append(Skill(
                name=knack_name,
                rank=knack_ranks.get(knack_key, 1),
                skill_type=SkillType.BASIC,
                ring=RingName.WATER,
            ))

    profession_abilities = compute_abilities(earned_xp) if build_choice == "Wave Man" else []

    school_name = None
    school_ring_val = None
    school_knacks_val: list[str] = []
    if build_choice == "Base":
        school_ring_val = school_ring_choice
    elif build_choice == "Akodo Bushi":
        school_name = "Akodo Bushi"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Double Attack", "Feint", "Iaijutsu"]
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
    elif build_choice == "Daidoji Yojimbo":
        school_name = "Daidoji Yojimbo"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Counterattack", "Double Attack", "Iaijutsu"]
    elif build_choice == "Doji Artisan":
        school_name = "Doji Artisan"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Counterattack", "Oppose Social", "Worldliness"]
    elif build_choice == "Hida Bushi":
        school_name = "Hida Bushi"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Counterattack", "Iaijutsu", "Lunge"]
    elif build_choice == "Hiruma Scout":
        school_name = "Hiruma Scout"
        school_ring_val = RingName.AIR
        school_knacks_val = ["Double Attack", "Feint", "Iaijutsu"]
    elif build_choice == "Ide Diplomat":
        school_name = "Ide Diplomat"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Double Attack", "Feint", "Worldliness"]
    elif build_choice == "Ikoma Bard":
        school_name = "Ikoma Bard"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Discern Honor", "Oppose Knowledge", "Oppose Social"]
    elif build_choice == "Isawa Duelist":
        school_name = "Isawa Duelist"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Double Attack", "Iaijutsu", "Lunge"]
    elif build_choice == "Isawa Ishi":
        school_name = "Isawa Ishi"
        school_ring_val = RingName.VOID
        school_knacks_val = ["Absorb Void", "Kharmic Spin", "Otherworldliness"]
    elif build_choice == "Kitsuki Magistrate":
        school_name = "Kitsuki Magistrate"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Discern Honor", "Iaijutsu", "Presence"]
    elif build_choice == "Kuni Witch Hunter":
        school_name = "Kuni Witch Hunter"
        school_ring_val = RingName.EARTH
        school_knacks_val = ["Detect Taint", "Iaijutsu", "Presence"]
    elif build_choice == "Shosuro Actor":
        school_name = "Shosuro Actor"
        school_ring_val = RingName.AIR
        school_knacks_val = ["Athletics", "Discern Honor", "Pontificate"]
    elif build_choice == "Priest":
        school_name = "Priest"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Conviction", "Otherworldliness", "Pontificate"]
    elif build_choice == "Shiba Bushi":
        school_name = "Shiba Bushi"
        school_ring_val = RingName.AIR
        school_knacks_val = ["Counterattack", "Double Attack", "Iaijutsu"]
    elif build_choice == "Bayushi Bushi":
        school_name = "Bayushi Bushi"
        school_ring_val = RingName.FIRE
        school_knacks_val = ["Double Attack", "Feint", "Iaijutsu"]
    elif build_choice == "Yogo Warden":
        school_name = "Yogo Warden"
        school_ring_val = RingName.EARTH
        school_knacks_val = ["Double Attack", "Iaijutsu", "Feint"]
    elif build_choice == "Brotherhood Monk":
        school_name = "Brotherhood Monk"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Conviction", "Otherworldliness", "Worldliness"]
    elif build_choice == "Togashi Ise Zumi":
        school_name = "Togashi Ise Zumi"
        school_ring_val = RingName.VOID
        school_knacks_val = ["Athletics", "Conviction", "Dragon Tattoo"]
    elif build_choice == "Courtier":
        school_name = "Courtier"
        school_ring_val = RingName.AIR
        school_knacks_val = ["Discern Honor", "Oppose Social", "Worldliness"]
    elif build_choice == "Merchant":
        school_name = "Merchant"
        school_ring_val = RingName.WATER
        school_knacks_val = ["Discern Honor", "Oppose Knowledge", "Worldliness"]

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
    "Base", "Wave Man", "Akodo Bushi", "Mirumoto Bushi",
    "Matsu Bushi", "Kakita Duelist", "Shinjo Bushi",
    "Otaku Bushi", "Daidoji Yojimbo", "Doji Artisan",
    "Hida Bushi", "Hiruma Scout", "Ide Diplomat", "Ikoma Bard",
    "Isawa Duelist", "Isawa Ishi", "Kitsuki Magistrate",
    "Kuni Witch Hunter", "Shosuro Actor",
    "Shiba Bushi", "Bayushi Bushi", "Brotherhood Monk",
    "Courtier", "Merchant", "Priest",
    "Togashi Ise Zumi", "Yogo Warden",
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
