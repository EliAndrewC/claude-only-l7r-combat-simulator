"""Streamlit AppTest integration tests for the combat dashboard."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.models.combat import ActionType, CombatAction, CombatLog
from src.ui_helpers import _group_action_sequences, compute_combat_stats, extract_annotations


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
    def test_sidebar_has_preset_selectors(self) -> None:
        at = AppTest.from_file("src/app.py", default_timeout=10)
        at.run()
        # Should have selectboxes for presets
        assert len(at.selectbox) >= 2


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

    def test_empty_log(self) -> None:
        log = CombatLog(combatants=["A", "B"])
        stats = compute_combat_stats(log)
        assert stats["biggest_attack"] == 0
        assert stats["biggest_damage"] == 0
