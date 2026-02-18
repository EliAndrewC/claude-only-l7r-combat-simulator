"""Streamlit AppTest integration tests for the combat dashboard."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.engine.kakita import compute_kakita_stats_from_xp
from src.engine.matsu import compute_matsu_stats_from_xp
from src.engine.mirumoto import compute_mirumoto_stats_from_xp
from src.engine.xp_builder import compute_stats_from_xp
from src.engine.waveman import compute_waveman_stats_from_xp
from src.models.combat import ActionType, CombatAction, CombatLog
from src.models.weapon import WeaponType
from src.models.combat import FighterStatus
from src.ui_helpers import _damage_icon, _format_fighter_status, _group_action_sequences, _parry_icon, _wound_check_icon, compute_combat_stats, extract_annotations


class TestAppLoads:
    def test_app_runs_without_error(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert not at.exception

    def test_app_has_title(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert any("L7R Combat Simulator" in t.value for t in at.title)

    def test_app_has_fight_button(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert len(at.button) > 0

    def test_fight_button_produces_results(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Click the Fight button
        at.button[0].click().run()
        assert not at.exception
        # After fighting, there should be success or warning (winner or draw)
        has_result = len(at.success) > 0 or len(at.warning) > 0
        assert has_result


class TestAppSidebar:
    def test_sidebar_has_build_selectors(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Should have selectboxes for build type (Base/Wave Man)
        assert len(at.selectbox) >= 2

    def test_waveman_option_loads(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        assert not at.exception

    def test_waveman_fight_works(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        at.selectbox(key="f2_preset").set_value("Wave Man").run()
        at.button[0].click().run()
        assert not at.exception
        has_result = len(at.success) > 0 or len(at.warning) > 0
        assert has_result


class TestXPPersistence:
    @staticmethod
    def _param_value(val: object) -> str:
        """Normalize query param value (AppTest may return a list)."""
        if isinstance(val, list):
            return val[0]
        return str(val)

    def test_xp_restored_from_query_params(self) -> None:
        """XP slider values are restored from URL query parameters on load."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_xp"] = "150"
        at.query_params["f2_xp"] = "200"
        at.run()
        assert not at.exception
        assert at.session_state["f1_earned_xp"] == 150
        assert at.session_state["f2_earned_xp"] == 200

    def test_noncombat_restored_from_query_params(self) -> None:
        """Non-combat XP % slider values are restored from query params."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_nc"] = "35"
        at.query_params["f2_nc"] = "10"
        at.run()
        assert not at.exception
        assert at.session_state["f1_noncombat"] == 35
        assert at.session_state["f2_noncombat"] == 10

    def test_xp_synced_to_query_params(self) -> None:
        """After changing XP slider, value is written to query params."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.slider(key="f1_earned_xp").set_value(100).run()
        assert self._param_value(at.query_params["f1_xp"]) == "100"

    def test_noncombat_synced_to_query_params(self) -> None:
        """After changing non-combat slider, value is written to query params."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.slider(key="f1_noncombat").set_value(40).run()
        assert self._param_value(at.query_params["f1_nc"]) == "40"

    def test_invalid_query_param_ignored(self) -> None:
        """Non-integer query param values are silently ignored."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_xp"] = "not_a_number"
        at.query_params["f1_nc"] = "bad"
        at.run()
        assert not at.exception
        assert at.session_state["f1_earned_xp"] == 0
        assert at.session_state["f1_noncombat"] == 20

    def test_build_mode_restored_from_query_params(self) -> None:
        """Build mode selectbox is restored from URL query params on load."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_build"] = "Wave Man"
        at.query_params["f2_build"] = "Wave Man"
        at.run()
        assert not at.exception
        assert at.session_state["f1_preset"] == "Wave Man"
        assert at.session_state["f2_preset"] == "Wave Man"

    def test_build_mode_synced_to_query_params(self) -> None:
        """After changing build mode, value is written to query params."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        assert self._param_value(at.query_params["f1_build"]) == "Wave Man"

    def test_invalid_build_mode_query_param_ignored(self) -> None:
        """Invalid build mode in query params defaults to Base."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_build"] = "Nonexistent"
        at.run()
        assert not at.exception
        assert at.session_state["f1_preset"] == "Base"


class TestExtractAnnotations:
    """Tests for extract_annotations helper used by _render_action."""

    def test_void_reroll_extracted(self) -> None:
        desc = "Akodo Taro attacks: 5k3 vs TN 15 (void: rerolled 10s)"
        assert extract_annotations(desc) == "*(void: rerolled 10s)*"

    def test_void_spent_on_wound_check(self) -> None:
        desc = "Kakita Yuri wound check: passed (rolled 22) (1 void point spent)"
        assert extract_annotations(desc) == "*(1 void point spent)*"

    def test_multiple_annotations(self) -> None:
        desc = (
            "Kakita Yuri parries: 5k2 vs TN 18"
            " (pre-declared, +5 bonus) (void: rerolled 10s)"
        )
        result = extract_annotations(desc)
        assert "(pre-declared, +5 bonus)" in result
        assert "(void: rerolled 10s)" in result

    def test_conversion_note_extracted(self) -> None:
        desc = (
            "Kakita Yuri wound check: passed (rolled 22)"
            " — converted light wounds to 1 serious wound"
        )
        result = extract_annotations(desc)
        assert "converted light wounds to 1 serious wound" in result

    def test_void_and_conversion_together(self) -> None:
        desc = (
            "Kakita wound check: passed (rolled 22) (2 void point spent)"
            " — converted light wounds to 1 serious wound"
        )
        result = extract_annotations(desc)
        assert "(2 void point spent)" in result
        assert "converted light wounds to 1 serious wound" in result

    def test_damage_will_be_annotation(self) -> None:
        desc = "Attacker attacks: 6k3 vs TN 15 — damage will be 10k2"
        result = extract_annotations(desc)
        assert "damage will be 10k2" in result

    def test_damage_reduced_annotation(self) -> None:
        desc = "Defender parries: 5k3 vs TN 25 — 9k2 is reduced to 7k2"
        result = extract_annotations(desc)
        assert "9k2 is reduced to 7k2" in result

    def test_damage_overflow_annotation(self) -> None:
        desc = "Attacker attacks: 6k3 vs TN 5 — damage will be 18k2, which becomes 10k10"
        result = extract_annotations(desc)
        assert "which becomes 10k10" in result

    def test_no_annotations_returns_empty(self) -> None:
        desc = "Akodo Taro attacks: 5k3 vs TN 15"
        assert extract_annotations(desc) == ""

    def test_rolled_parenthetical_excluded(self) -> None:
        """The '(rolled N)' note is redundant with total and should be skipped."""
        desc = "wound check: passed (rolled 22)"
        assert extract_annotations(desc) == ""

    def test_wasted_parry_not_annotated(self) -> None:
        desc = "Kakita pre-declared parry wasted (attack missed)"
        assert extract_annotations(desc) == ""


def _action(action_type: ActionType, phase: int = 0, actor: str = "A") -> CombatAction:
    """Helper to create a minimal CombatAction for grouping tests."""
    return CombatAction(phase=phase, actor=actor, action_type=action_type)


class TestGroupActionSequences:
    """Tests for _group_action_sequences helper."""

    def test_initiative_only_sequence(self) -> None:
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 1
        assert all(a.action_type == ActionType.INITIATIVE for a in seqs[0])

    def test_attack_starts_new_sequence(self) -> None:
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
            _action(ActionType.ATTACK, phase=3, actor="A"),
            _action(ActionType.PARRY, phase=3, actor="B"),
            _action(ActionType.DAMAGE, phase=3, actor="A"),
            _action(ActionType.WOUND_CHECK, phase=3, actor="B"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 2
        # First seq = initiative
        assert seqs[0][0].action_type == ActionType.INITIATIVE
        # Second seq = attack + parry + damage + wound_check
        assert seqs[1][0].action_type == ActionType.ATTACK
        assert len(seqs[1]) == 4

    def test_multiple_attack_sequences(self) -> None:
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
            _action(ActionType.ATTACK, phase=3, actor="A"),
            _action(ActionType.DAMAGE, phase=3, actor="A"),
            _action(ActionType.WOUND_CHECK, phase=3, actor="B"),
            _action(ActionType.ATTACK, phase=5, actor="B"),
            _action(ActionType.DAMAGE, phase=5, actor="B"),
            _action(ActionType.WOUND_CHECK, phase=5, actor="A"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 3
        assert seqs[1][0].action_type == ActionType.ATTACK
        assert seqs[1][0].phase == 3
        assert seqs[2][0].action_type == ActionType.ATTACK
        assert seqs[2][0].phase == 5

    def test_attack_miss_solo_sequence(self) -> None:
        """A missed attack (no follow-up actions) is its own sequence."""
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
            _action(ActionType.ATTACK, phase=3, actor="A"),
            _action(ActionType.ATTACK, phase=5, actor="B"),
            _action(ActionType.DAMAGE, phase=5, actor="B"),
            _action(ActionType.WOUND_CHECK, phase=5, actor="A"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 3
        # Missed attack sequence has just the attack
        assert len(seqs[1]) == 1
        assert seqs[1][0].action_type == ActionType.ATTACK

    def test_interrupt_included_in_attack_sequence(self) -> None:
        actions = [
            _action(ActionType.ATTACK, phase=3, actor="A"),
            _action(ActionType.INTERRUPT, phase=3, actor="B"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 1
        assert len(seqs[0]) == 2

    def test_double_attack_starts_new_sequence(self) -> None:
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
            _action(ActionType.DOUBLE_ATTACK, phase=1, actor="A"),
            _action(ActionType.INTERRUPT, phase=1, actor="B"),
            _action(ActionType.DAMAGE, phase=1, actor="A"),
            _action(ActionType.WOUND_CHECK, phase=1, actor="B"),
            _action(ActionType.DOUBLE_ATTACK, phase=2, actor="A"),
            _action(ActionType.DAMAGE, phase=2, actor="A"),
            _action(ActionType.WOUND_CHECK, phase=2, actor="B"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 3
        assert seqs[0][0].action_type == ActionType.INITIATIVE
        assert seqs[1][0].action_type == ActionType.DOUBLE_ATTACK
        assert seqs[1][0].phase == 1
        assert len(seqs[1]) == 4
        assert seqs[2][0].action_type == ActionType.DOUBLE_ATTACK
        assert seqs[2][0].phase == 2
        assert len(seqs[2]) == 3


class TestWoundCheckIcon:
    """Tests for dynamic wound check icons."""

    def test_passed_wound_check_black_heart(self) -> None:
        action = _action(ActionType.WOUND_CHECK, actor="A")
        action.success = True
        action.description = "A wound check: passed (rolled 25)"
        assert _wound_check_icon(action) == "🖤"

    def test_failed_wound_check_one_serious(self) -> None:
        action = _action(ActionType.WOUND_CHECK, actor="A")
        action.success = False
        action.tn = 20
        action.total = 15
        action.description = "A wound check: failed (rolled 15)"
        assert _wound_check_icon(action) == "💔"

    def test_failed_wound_check_multiple_serious(self) -> None:
        action = _action(ActionType.WOUND_CHECK, actor="A")
        action.success = False
        action.tn = 49
        action.total = 34
        action.description = "A wound check: failed (rolled 34)"
        # 1 + (49 - 34) // 10 = 1 + 1 = 2
        assert _wound_check_icon(action) == "💔💔"

    def test_converted_wound_check_broken_heart(self) -> None:
        action = _action(ActionType.WOUND_CHECK, actor="A")
        action.success = True
        action.description = "A wound check: passed (rolled 25) — converted light wounds to 1 serious wound"
        assert _wound_check_icon(action) == "💔"


class TestParryIcon:
    """Tests for dynamic parry icons."""

    def test_successful_parry(self) -> None:
        action = _action(ActionType.PARRY, actor="A")
        action.success = True
        assert _parry_icon(action) == "🛡️"

    def test_failed_parry(self) -> None:
        action = _action(ActionType.PARRY, actor="A")
        action.success = False
        assert _parry_icon(action) == "🛡️💢"

    def test_successful_interrupt(self) -> None:
        action = _action(ActionType.INTERRUPT, actor="A")
        action.success = True
        assert _parry_icon(action) == "🛡️"

    def test_failed_interrupt(self) -> None:
        action = _action(ActionType.INTERRUPT, actor="A")
        action.success = False
        assert _parry_icon(action) == "🛡️💢"


class TestDamageIcon:
    """Tests for dynamic damage icons."""

    def test_normal_damage(self) -> None:
        action = _action(ActionType.DAMAGE, actor="A")
        action.description = "damage: 25"
        assert _damage_icon(action) == "💥"

    def test_double_attack_damage(self) -> None:
        action = _action(ActionType.DAMAGE, actor="A")
        action.description = "damage: 25 (double attack: +1 serious wound)"
        assert _damage_icon(action) == "💔💥"


class TestComputeCombatStats:
    def _make_log(self) -> CombatLog:
        log = CombatLog(combatants=["A", "B"])
        log.add_action(CombatAction(
            phase=3, actor="A", action_type=ActionType.ATTACK,
            total=28, tn=15, success=True,
        ))
        log.add_action(CombatAction(
            phase=3, actor="A", action_type=ActionType.DAMAGE,
            total=22,
        ))
        log.add_action(CombatAction(
            phase=5, actor="B", action_type=ActionType.ATTACK,
            total=35, tn=20, success=True,
        ))
        log.add_action(CombatAction(
            phase=5, actor="B", action_type=ActionType.DAMAGE,
            total=18,
        ))
        log.add_action(CombatAction(
            phase=7, actor="A", action_type=ActionType.ATTACK,
            total=12, tn=20, success=False,
        ))
        return log

    def test_biggest_attack_roll(self) -> None:
        stats = compute_combat_stats(self._make_log())
        assert stats["biggest_attack"] == 35

    def test_biggest_damage_roll(self) -> None:
        stats = compute_combat_stats(self._make_log())
        assert stats["biggest_damage"] == 22

    def test_no_biggest_hit_key(self) -> None:
        """The old biggest_hit key should no longer exist."""
        stats = compute_combat_stats(self._make_log())
        assert "biggest_hit" not in stats

    def test_most_sw_one_hit_zero_without_snapshots(self) -> None:
        """Without status_after snapshots, most_sw_one_hit is 0."""
        stats = compute_combat_stats(self._make_log())
        assert stats["most_sw_one_hit"] == 0

    def test_most_sw_one_hit_tracks_delta(self) -> None:
        """Most SW From One Hit tracks the max serious wound increase in one hit."""
        log = CombatLog(combatants=["A", "B"])
        # First hit: B goes from 0 to 1 SW
        log.add_action(CombatAction(
            phase=3, actor="A", action_type=ActionType.DAMAGE, target="B", total=20,
            status_after={"A": FighterStatus(serious_wounds=0), "B": FighterStatus(serious_wounds=0)},
        ))
        log.add_action(CombatAction(
            phase=3, actor="B", action_type=ActionType.WOUND_CHECK, total=10, tn=20, success=False,
            status_after={"A": FighterStatus(serious_wounds=0), "B": FighterStatus(serious_wounds=1)},
        ))
        # Second hit: B goes from 1 to 3 SW (DA serious + failed WC)
        log.add_action(CombatAction(
            phase=5, actor="A", action_type=ActionType.DAMAGE, target="B", total=30,
            status_after={"A": FighterStatus(serious_wounds=0), "B": FighterStatus(serious_wounds=2)},
        ))
        log.add_action(CombatAction(
            phase=5, actor="B", action_type=ActionType.WOUND_CHECK, total=10, tn=30, success=False,
            status_after={"A": FighterStatus(serious_wounds=0), "B": FighterStatus(serious_wounds=3)},
        ))
        stats = compute_combat_stats(log)
        # Biggest single delta: 1→2 on damage (DA serious) + 2→3 on WC = 2 total from SW=1
        assert stats["most_sw_one_hit"] == 2

    def test_counts_lunges_and_double_attacks(self) -> None:
        """Total attacks and hits include lunges and double attacks."""
        log = CombatLog(combatants=["A", "B"])
        log.add_action(CombatAction(
            phase=3, actor="A", action_type=ActionType.ATTACK,
            total=25, tn=15, success=True,
        ))
        log.add_action(CombatAction(
            phase=5, actor="A", action_type=ActionType.DOUBLE_ATTACK,
            total=40, tn=35, success=True,
        ))
        log.add_action(CombatAction(
            phase=7, actor="B", action_type=ActionType.LUNGE,
            total=30, tn=20, success=True,
        ))
        log.add_action(CombatAction(
            phase=9, actor="B", action_type=ActionType.LUNGE,
            total=10, tn=20, success=False,
        ))
        stats = compute_combat_stats(log)
        assert stats["total_attacks"] == 4
        assert stats["hits"] == 3
        assert stats["biggest_attack"] == 40

    def test_wc_failed_by_10(self) -> None:
        """Count wound checks that failed by 10 or more."""
        log = CombatLog(combatants=["A", "B"])
        # Failed by 15 (tn=40, total=25) — counts
        log.add_action(CombatAction(
            phase=3, actor="B", action_type=ActionType.WOUND_CHECK,
            total=25, tn=40, success=False,
        ))
        # Failed by exactly 10 (tn=30, total=20) — counts
        log.add_action(CombatAction(
            phase=5, actor="B", action_type=ActionType.WOUND_CHECK,
            total=20, tn=30, success=False,
        ))
        # Failed by 5 (tn=25, total=20) — does not count
        log.add_action(CombatAction(
            phase=7, actor="A", action_type=ActionType.WOUND_CHECK,
            total=20, tn=25, success=False,
        ))
        # Passed — does not count
        log.add_action(CombatAction(
            phase=9, actor="A", action_type=ActionType.WOUND_CHECK,
            total=35, tn=30, success=True,
        ))
        stats = compute_combat_stats(log)
        assert stats["wc_failed_by_10"] == 2

    def test_empty_log(self) -> None:
        log = CombatLog(combatants=["A", "B"])
        stats = compute_combat_stats(log)
        assert stats["biggest_attack"] == 0
        assert stats["biggest_damage"] == 0
        assert stats["most_sw_one_hit"] == 0
        assert stats["wc_failed_by_10"] == 0


class TestMergedBuildMode:
    """Tests for the merged Base/Wave Man build modes with editable fields."""

    def test_base_shows_editable_rings(self) -> None:
        """Base mode renders ring number_input widgets."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        assert not at.exception
        # Ring inputs should exist for fighter 1
        assert at.number_input(key="f1_air") is not None
        assert at.number_input(key="f1_fire") is not None
        assert at.number_input(key="f1_earth") is not None
        assert at.number_input(key="f1_water") is not None
        assert at.number_input(key="f1_void") is not None

    def test_rings_populated_from_xp(self) -> None:
        """Ring values in session state match compute_stats_from_xp defaults."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        stats = compute_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == stats.ring_values[rn]
        assert at.session_state["f1_atk"] == stats.attack
        assert at.session_state["f1_parry"] == stats.parry

    def test_xp_change_repopulates(self) -> None:
        """Changing XP slider updates ring values to match new computation."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.slider(key="f1_earned_xp").set_value(100).run()
        assert not at.exception
        stats = compute_stats_from_xp(earned_xp=100, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == stats.ring_values[rn]
        assert at.session_state["f1_atk"] == stats.attack
        assert at.session_state["f1_parry"] == stats.parry

    def test_manual_edit_persists(self) -> None:
        """Editing a ring without changing XP keeps the manual value."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Manually change air ring to 5
        at.number_input(key="f1_air").set_value(5).run()
        assert not at.exception
        assert at.session_state["f1_air"] == 5

    def test_xp_overwrites_manual_edit(self) -> None:
        """Changing XP after a manual edit resets to computed values."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Manually set air to 5
        at.number_input(key="f1_air").set_value(5).run()
        assert at.session_state["f1_air"] == 5
        # Now change XP — should overwrite
        at.slider(key="f1_earned_xp").set_value(100).run()
        stats = compute_stats_from_xp(earned_xp=100, non_combat_pct=0.20)
        assert at.session_state["f1_air"] == stats.ring_values["air"]

    def test_waveman_shows_editable_rings(self) -> None:
        """Wave Man mode has ring number_input widgets."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        assert not at.exception
        assert at.number_input(key="f1_air") is not None
        stats = compute_waveman_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == stats.ring_values[rn]

    def test_switching_mode_repopulates(self) -> None:
        """Switching from Base to Wave Man recomputes ring values."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Start in Base mode (default)
        base_stats = compute_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        assert at.session_state["f1_air"] == base_stats.ring_values["air"]
        # Switch to Wave Man
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        wm_stats = compute_waveman_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == wm_stats.ring_values[rn]


class TestMirumotoUI:
    """Tests for Mirumoto Bushi build mode UI."""

    def test_mirumoto_option_loads(self) -> None:
        """Selecting 'Mirumoto Bushi' doesn't crash."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Mirumoto Bushi").run()
        assert not at.exception

    def test_mirumoto_fight_works(self) -> None:
        """Two Mirumoto Bushi can fight without errors."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Mirumoto Bushi").run()
        at.selectbox(key="f2_preset").set_value("Mirumoto Bushi").run()
        at.button[0].click().run()
        assert not at.exception
        has_result = len(at.success) > 0 or len(at.warning) > 0
        assert has_result

    def test_mirumoto_shows_knack_sliders(self) -> None:
        """Mirumoto mode has knack slider widgets."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Mirumoto Bushi").run()
        assert not at.exception
        # Knack sliders should exist
        assert at.slider(key="f1_knack_counterattack") is not None
        assert at.slider(key="f1_knack_double_attack") is not None
        assert at.slider(key="f1_knack_iaijutsu") is not None

    def test_mirumoto_build_mode_persists(self) -> None:
        """Build mode query param round-trip for Mirumoto."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_build"] = "Mirumoto Bushi"
        at.run()
        assert not at.exception
        assert at.session_state["f1_preset"] == "Mirumoto Bushi"

    def test_mirumoto_rings_from_xp(self) -> None:
        """Mirumoto ring values match compute_mirumoto_stats_from_xp."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Mirumoto Bushi").run()
        stats = compute_mirumoto_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        assert at.session_state["f1_void"] == stats.ring_values["void"]
        assert at.session_state["f1_air"] == stats.ring_values["air"]

    def test_switching_to_mirumoto_repopulates(self) -> None:
        """Switching from Base to Mirumoto recomputes ring values."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Mirumoto Bushi").run()
        stats = compute_mirumoto_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == stats.ring_values[rn]


class TestDefaultWeapon:
    """Tests for default weapon selection based on build mode."""

    def test_waveman_defaults_to_spear(self) -> None:
        """Selecting Wave Man sets weapon to Spear."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        assert at.session_state["f1_weapon"] == WeaponType.SPEAR

    def test_mirumoto_defaults_to_katana(self) -> None:
        """Selecting Mirumoto Bushi sets weapon to Katana."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Mirumoto Bushi").run()
        assert at.session_state["f1_weapon"] == WeaponType.KATANA

    def test_base_defaults_to_katana(self) -> None:
        """Switching back to Base sets weapon to Katana."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Wave Man").run()
        assert at.session_state["f1_weapon"] == WeaponType.SPEAR
        at.selectbox(key="f1_preset").set_value("Base").run()
        assert at.session_state["f1_weapon"] == WeaponType.KATANA


class TestDanPointsUI:
    """Tests for 3rd Dan and temp void display in UI."""

    def test_temp_void_displayed_in_status(self) -> None:
        """Temp void shown as separate 'Temp Void N' entry."""
        status = FighterStatus(
            void_points=3, void_points_max=3, temp_void_points=1, actions_remaining=[5],
        )
        result = _format_fighter_status("Mirumoto", status)
        assert "Temp Void 1" in result

    def test_dan_points_displayed_in_status(self) -> None:
        """Dan points shown as '3rd Dan points: 6' when > 0."""
        status = FighterStatus(
            void_points=3, void_points_max=3, dan_points=6,
            actions_remaining=[3, 7],
        )
        result = _format_fighter_status("Mirumoto", status)
        assert "3rd Dan points: 6" in result

    def test_dan_points_hidden_when_zero(self) -> None:
        """Dan points not shown when 0."""
        status = FighterStatus(
            void_points=3, void_points_max=3, dan_points=0,
            actions_remaining=[3, 7],
        )
        result = _format_fighter_status("Mirumoto", status)
        assert "3rd Dan points" not in result

    def test_mirumoto_sa_annotation_extracted(self) -> None:
        """extract_annotations picks up SA temp void text."""
        desc = "Mirumoto parries: 5k3 vs TN 20 (mirumoto SA: +1 temp void)"
        result = extract_annotations(desc)
        assert "(mirumoto SA: +1 temp void)" in result

    def test_3rd_dan_annotation_extracted(self) -> None:
        """extract_annotations picks up 3rd Dan bonus text."""
        desc = "Mirumoto attacks: 6k3 vs TN 15 (3rd dan: +4 bonus, 2 pts)"
        result = extract_annotations(desc)
        assert "(3rd dan: +4 bonus, 2 pts)" in result


class TestLungeActionSequence:
    """Tests for Lunge action type in grouping and display."""

    def test_lunge_starts_new_sequence(self) -> None:
        """LUNGE starts a new action sequence like ATTACK does."""
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
            _action(ActionType.LUNGE, phase=3, actor="A"),
            _action(ActionType.DAMAGE, phase=3, actor="A"),
            _action(ActionType.WOUND_CHECK, phase=3, actor="B"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 2
        assert seqs[0][0].action_type == ActionType.INITIATIVE
        assert seqs[1][0].action_type == ActionType.LUNGE
        assert len(seqs[1]) == 3


class TestMatsuUI:
    """Tests for Matsu Bushi build mode UI."""

    def test_matsu_option_loads(self) -> None:
        """Selecting 'Matsu Bushi' doesn't crash."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Matsu Bushi").run()
        assert not at.exception

    def test_matsu_fight_works(self) -> None:
        """Two Matsu Bushi can fight without errors."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Matsu Bushi").run()
        at.selectbox(key="f2_preset").set_value("Matsu Bushi").run()
        at.button[0].click().run()
        assert not at.exception
        has_result = len(at.success) > 0 or len(at.warning) > 0
        assert has_result

    def test_matsu_shows_knack_sliders(self) -> None:
        """Matsu mode has knack slider widgets."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Matsu Bushi").run()
        assert not at.exception
        assert at.slider(key="f1_knack_double_attack") is not None
        assert at.slider(key="f1_knack_iaijutsu") is not None
        assert at.slider(key="f1_knack_lunge") is not None

    def test_matsu_build_mode_persists(self) -> None:
        """Build mode query param round-trip for Matsu."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_build"] = "Matsu Bushi"
        at.run()
        assert not at.exception
        assert at.session_state["f1_preset"] == "Matsu Bushi"

    def test_matsu_rings_from_xp(self) -> None:
        """Matsu ring values match compute_matsu_stats_from_xp."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Matsu Bushi").run()
        stats = compute_matsu_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        assert at.session_state["f1_fire"] == stats.ring_values["fire"]
        assert at.session_state["f1_air"] == stats.ring_values["air"]

    def test_switching_to_matsu_repopulates(self) -> None:
        """Switching from Base to Matsu recomputes ring values."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Matsu Bushi").run()
        stats = compute_matsu_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == stats.ring_values[rn]

    def test_matsu_defaults_to_katana(self) -> None:
        """Selecting Matsu Bushi sets weapon to Katana."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Matsu Bushi").run()
        assert at.session_state["f1_weapon"] == WeaponType.KATANA

    def test_matsu_bonuses_displayed_in_status(self) -> None:
        """Status display shows 3rd Dan bonuses when non-empty."""
        status = FighterStatus(
            void_points=3, void_points_max=3, matsu_bonuses=[9, 9],
            actions_remaining=[3, 7],
        )
        result = _format_fighter_status("Matsu", status)
        assert "3rd Dan bonuses: +9, +9" in result

    def test_matsu_bonuses_hidden_when_empty(self) -> None:
        """No bonuses text when matsu_bonuses is empty."""
        status = FighterStatus(
            void_points=3, void_points_max=3, matsu_bonuses=[],
            actions_remaining=[3, 7],
        )
        result = _format_fighter_status("Matsu", status)
        assert "3rd Dan bonuses" not in result

    def test_matsu_annotation_extracted(self) -> None:
        """extract_annotations picks up matsu bonus text."""
        desc = "Matsu lunges: 6k3 vs TN 15 (matsu 3rd Dan: +12 wound check bonus stored)"
        result = extract_annotations(desc)
        assert "(matsu 3rd Dan: +12 wound check bonus stored)" in result


class TestKakitaUI:
    """Tests for Kakita Duelist build mode UI."""

    def test_kakita_option_loads(self) -> None:
        """Selecting 'Kakita Duelist' doesn't crash."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Kakita Duelist").run()
        assert not at.exception

    def test_kakita_fight_works(self) -> None:
        """Two Kakita Duelists can fight without errors."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Kakita Duelist").run()
        at.selectbox(key="f2_preset").set_value("Kakita Duelist").run()
        at.button[0].click().run()
        assert not at.exception
        has_result = len(at.success) > 0 or len(at.warning) > 0
        assert has_result

    def test_kakita_shows_knack_sliders(self) -> None:
        """Kakita mode has knack slider widgets."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Kakita Duelist").run()
        assert not at.exception
        assert at.slider(key="f1_knack_double_attack") is not None
        assert at.slider(key="f1_knack_iaijutsu") is not None
        assert at.slider(key="f1_knack_lunge") is not None

    def test_kakita_build_mode_persists(self) -> None:
        """Build mode query param round-trip for Kakita."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.query_params["f1_build"] = "Kakita Duelist"
        at.run()
        assert not at.exception
        assert at.session_state["f1_preset"] == "Kakita Duelist"

    def test_kakita_rings_from_xp(self) -> None:
        """Kakita ring values match compute_kakita_stats_from_xp."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Kakita Duelist").run()
        stats = compute_kakita_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        assert at.session_state["f1_fire"] == stats.ring_values["fire"]
        assert at.session_state["f1_air"] == stats.ring_values["air"]

    def test_switching_to_kakita_repopulates(self) -> None:
        """Switching from Base to Kakita recomputes ring values."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Kakita Duelist").run()
        stats = compute_kakita_stats_from_xp(earned_xp=0, non_combat_pct=0.20)
        for rn in ("air", "fire", "earth", "water", "void"):
            assert at.session_state[f"f1_{rn}"] == stats.ring_values[rn]

    def test_kakita_defaults_to_katana(self) -> None:
        """Selecting Kakita Duelist sets weapon to Katana."""
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        at.selectbox(key="f1_preset").set_value("Kakita Duelist").run()
        assert at.session_state["f1_weapon"] == WeaponType.KATANA

    def test_kakita_annotation_extracted(self) -> None:
        """extract_annotations picks up kakita bonus text."""
        desc = "Kakita lunges: 6k3 vs TN 15 (kakita 3rd Dan: +20, 5 phases)"
        result = extract_annotations(desc)
        assert "(kakita 3rd Dan: +20, 5 phases)" in result

    def test_kakita_4th_dan_annotation_extracted(self) -> None:
        """extract_annotations picks up 4th Dan bonus text."""
        desc = "Kakita 5th Dan iaijutsu damage: 10k5 = 86 (4th Dan free raise: +5)"
        result = extract_annotations(desc)
        assert "(4th Dan free raise: +5)" in result

    def test_kakita_5th_dan_damage_notes_extracted(self) -> None:
        """extract_annotations picks up won/lost margin notes with Dan."""
        desc = "Kakita 5th Dan iaijutsu damage: 14k2 = 23 (won by 16: +3 rolled, 4th Dan free raise: +5)"
        result = extract_annotations(desc)
        assert "4th Dan free raise: +5" in result


class TestIaijutsuActionSequence:
    """Tests for Iaijutsu action type in grouping."""

    def test_iaijutsu_starts_new_sequence(self) -> None:
        """IAIJUTSU starts a new action sequence like ATTACK does."""
        actions = [
            _action(ActionType.INITIATIVE, actor="A"),
            _action(ActionType.INITIATIVE, actor="B"),
            _action(ActionType.IAIJUTSU, phase=0, actor="A"),
            _action(ActionType.DAMAGE, phase=0, actor="A"),
            _action(ActionType.WOUND_CHECK, phase=0, actor="B"),
        ]
        seqs = _group_action_sequences(actions)
        assert len(seqs) == 2
        assert seqs[0][0].action_type == ActionType.INITIATIVE
        assert seqs[1][0].action_type == ActionType.IAIJUTSU
        assert len(seqs[1]) == 3
