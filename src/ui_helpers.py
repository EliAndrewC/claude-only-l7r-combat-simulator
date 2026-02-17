"""Rendering helpers for the Streamlit combat dashboard."""

from __future__ import annotations

import re

import streamlit as st

from src.engine.waveman import WAVE_MAN_ABILITY_NAMES
from src.models.character import Character
from src.models.combat import ActionType, CombatAction, CombatLog, FighterStatus
from src.models.weapon import Weapon

# Annotations worth surfacing from action descriptions.
_ANNOTATION_KEYWORDS = ("void", "pre-declared", "converted", "wave man")


def _md_to_html(text: str) -> str:
    """Convert basic markdown bold, strikethrough, and italic to HTML.

    Used when embedding markdown-formatted text inside an HTML block element
    (e.g. ``<div style="text-align: right">``), where Streamlit's markdown
    processor won't handle ``**bold**`` / ``~~strike~~`` / ``*italic*``.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


def extract_annotations(description: str) -> str:
    """Extract notable annotations from an action description.

    Pulls out parenthetical notes that mention void spending,
    pre-declared parry bonuses, or wound conversion, and any
    em-dash conversion note.  Redundant notes like ``(rolled N)``
    and ``(attack missed)`` are excluded.

    Returns:
        Italic markdown string with annotations, or empty string.
    """
    parts: list[str] = []

    for match in re.finditer(r"\([^)]+\)", description):
        text = match.group(0)
        if any(kw in text.lower() for kw in _ANNOTATION_KEYWORDS):
            parts.append(text)

    em_dash = re.search(r"—\s*(.+)$", description)
    if em_dash:
        parts.append(em_dash.group(1).strip())

    if not parts:
        return ""
    return f"*{' '.join(parts)}*"


def _group_action_sequences(
    actions: list[CombatAction],
) -> list[list[CombatAction]]:
    """Group a round's actions into display sequences.

    Initiative actions (1-2) form one sequence.  Each ATTACK starts a new
    sequence; subsequent PARRY/INTERRUPT/DAMAGE/WOUND_CHECK actions belong
    to the most recent attack sequence.
    """
    sequences: list[list[CombatAction]] = []
    current: list[CombatAction] = []

    for action in actions:
        if action.action_type == ActionType.ATTACK:
            if current:
                sequences.append(current)
            current = [action]
        else:
            current.append(action)

    if current:
        sequences.append(current)

    return sequences


def render_character_card(
    char: Character, weapon: Weapon, col: st.delta_generator.DeltaGenerator
) -> None:
    """Render a character summary card in the given Streamlit column."""
    col.subheader(char.name)
    if char.school:
        col.caption(char.school)

    ring_text = " | ".join(
        f"**{r.name.value}** {r.value}" for r in [
            char.rings.air, char.rings.fire, char.rings.earth,
            char.rings.water, char.rings.void,
        ]
    )
    col.markdown(ring_text)

    if char.skills:
        skills_text = ", ".join(f"{s.name} {s.rank}" for s in char.skills)
        col.markdown(f"**Skills:** {skills_text}")

    if char.profession_abilities:
        parts = []
        for ab in char.profession_abilities:
            name = WAVE_MAN_ABILITY_NAMES.get(ab.number, f"#{ab.number}")
            suffix = f" (x{ab.rank})" if ab.rank > 1 else ""
            parts.append(f"{name}{suffix}")
        col.markdown(f"**Abilities:** {', '.join(parts)}")

    col.markdown(f"**Weapon:** {weapon.name} ({weapon.dice_str})")


def render_winner_banner(log: CombatLog) -> None:
    """Show the winner or draw banner."""
    if log.winner:
        st.success(f"Winner: {log.winner}!")
    else:
        st.warning("Draw! No winner after max rounds.")


def compute_combat_stats(log: CombatLog) -> dict:
    """Compute summary statistics from a combat log."""
    attacks = [a for a in log.actions if a.action_type == ActionType.ATTACK]
    hits = [a for a in attacks if a.success]
    parries = [a for a in log.actions if a.action_type == ActionType.PARRY]
    successful_parries = [a for a in parries if a.success]
    damages = [a for a in log.actions if a.action_type == ActionType.DAMAGE]
    biggest_attack = max((a.total for a in hits), default=0)
    biggest_damage = max((d.total for d in damages), default=0)

    return {
        "rounds": log.round_number,
        "total_attacks": len(attacks),
        "hits": len(hits),
        "parry_attempts": len(parries),
        "successful_parries": len(successful_parries),
        "biggest_attack": biggest_attack,
        "biggest_damage": biggest_damage,
    }


def render_combat_stats(stats: dict) -> None:
    """Render combat summary stats."""
    cols = st.columns(3)
    cols[0].metric("Rounds", stats["rounds"])
    cols[0].metric("Total Attacks", stats["total_attacks"])
    cols[1].metric("Hits", stats["hits"])
    cols[1].metric("Biggest Attack Roll", stats["biggest_attack"])
    cols[1].metric("Biggest Damage Roll", stats["biggest_damage"])
    cols[2].metric("Parry Attempts", stats["parry_attempts"])
    cols[2].metric("Successful Parries", stats["successful_parries"])


def render_round_log(log: CombatLog) -> None:
    """Render round-by-round combat actions in expanders.

    Fighter 1 actions are left-aligned, Fighter 2 right-aligned.
    Inline status is shown between action sequences.
    """
    combatants = log.combatants

    # Group actions by round — initiative actions mark round starts
    rounds: list[list[CombatAction]] = []
    current_round: list[CombatAction] = []
    init_count = 0

    for action in log.actions:
        if action.action_type == ActionType.INITIATIVE:
            init_count += 1
            if init_count > 2 and init_count % 2 == 1:
                rounds.append(current_round)
                current_round = []
        current_round.append(action)
    if current_round:
        rounds.append(current_round)

    for i, round_actions in enumerate(rounds, 1):
        with st.expander(f"Round {i}", expanded=(i == len(rounds))):
            sequences = _group_action_sequences(round_actions)
            for seq in sequences:
                for action in seq:
                    is_fighter_1 = (action.actor == combatants[0])
                    _render_action_aligned(action, is_fighter_1)
                # Show status from last action in sequence that has status_after
                last_status = None
                for action in reversed(seq):
                    if action.status_after:
                        last_status = action.status_after
                        break
                if last_status:
                    _render_status_between(last_status)


_ACTION_ICONS = {
    ActionType.INITIATIVE: "🎲",
    ActionType.ATTACK: "⚔️",
    ActionType.PARRY: "🛡️",
    ActionType.INTERRUPT: "🛡️",
    ActionType.DAMAGE: "💥",
    ActionType.WOUND_CHECK: "❤️",
}


def _render_action_aligned(action: CombatAction, is_fighter_1: bool) -> None:
    """Render a single combat action, left-aligned for Fighter 1, right for Fighter 2."""
    icon = _ACTION_ICONS.get(action.action_type, "▪️")

    phase_str = f"Phase {action.phase}" if action.phase > 0 else "Initiative"

    if action.success is not None:
        result = "**HIT**" if action.success else "miss"
        if action.action_type in (ActionType.PARRY, ActionType.INTERRUPT):
            result = "**PARRIED**" if action.success else "failed"
        if action.action_type == ActionType.WOUND_CHECK:
            if action.success:
                result = "passed"
            else:
                serious = 1 + ((action.tn - action.total) // 10)
                if serious > 1:
                    result = f"**FAILED, takes {serious} serious wounds**"
                else:
                    result = "**FAILED**"
    else:
        result = ""

    # Dice display
    dice_str = ""
    if action.dice_rolled:
        kept_remaining = list(action.dice_kept)
        rolled_display = []
        for d in action.dice_rolled:
            if d in kept_remaining:
                rolled_display.append(f"**{d}**")
                kept_remaining.remove(d)
            else:
                rolled_display.append(f"~~{d}~~")
        dice_str = f" [{', '.join(rolled_display)}]"

    if action.action_type == ActionType.INITIATIVE:
        phases = ", ".join(str(d) for d in action.dice_kept)
        text = (
            f"{icon} **{phase_str}** | {action.actor} | "
            f"Action dice: phases {phases}{dice_str}"
        )
    else:
        pool_prefix = f"{action.dice_pool} " if action.dice_pool else ""
        tn_str = f" vs TN {action.tn}" if action.tn is not None else ""
        total_str = f" = {action.total}" if action.total else ""
        notes = extract_annotations(action.description)
        notes_str = f" {notes}" if notes else ""
        text = (
            f"{icon} **{phase_str}** | {action.actor} | "
            f"{pool_prefix}{action.action_type.value}{tn_str}{total_str} {result}{dice_str}{notes_str}"
        )

    if is_fighter_1:
        content_col, _spacer = st.columns([5, 1])
        content_col.markdown(text)
    else:
        _spacer, content_col = st.columns([1, 5])
        content_col.markdown(
            f"<div style='text-align: right'>{_md_to_html(text)}</div>",
            unsafe_allow_html=True,
        )


def _format_fighter_status(name: str, status: FighterStatus) -> str:
    """Format a single fighter's status as a compact string."""
    if len(status.actions_remaining) == 1:
        actions_display = f"Actions: phase {status.actions_remaining[0]}"
    elif status.actions_remaining:
        phases_str = ", ".join(str(p) for p in status.actions_remaining)
        actions_display = f"Actions: phases {phases_str}"
    else:
        actions_display = "Actions: none"
    parts = [
        f"Light {status.light_wounds}",
        f"Serious {status.serious_wounds}",
        f"Void {status.void_points}/{status.void_points_max}",
        actions_display,
    ]
    if status.is_mortally_wounded:
        parts.append("**MORTAL**")
    elif status.is_crippled:
        parts.append("*Crippled*")
    return f"**{name}**: {' | '.join(parts)}"


def _render_status_between(status_after: dict[str, FighterStatus]) -> None:
    """Render fighter status centered between action sequences."""
    names = list(status_after.keys())
    lines = [
        _md_to_html(_format_fighter_status(n, status_after[n]))
        for n in names
    ]
    _pad_l, center, _pad_r = st.columns([1, 4, 1])
    center.caption(
        f"<div style='text-align: center'>{'<br>'.join(lines)}</div>",
        unsafe_allow_html=True,
    )


def render_wound_status(log: CombatLog) -> None:
    """Render final wound status for each combatant."""
    st.subheader("Final Wound Status")
    for name in log.combatants:
        wt = log.wounds[name]
        status_parts = [f"Light: {wt.light_wounds}", f"Serious: {wt.serious_wounds}"]
        if wt.is_mortally_wounded:
            status_parts.append("**MORTALLY WOUNDED**")
        elif wt.is_crippled:
            status_parts.append("*Crippled*")
        st.markdown(f"**{name}**: {' | '.join(status_parts)} (Earth: {wt.earth_ring})")
