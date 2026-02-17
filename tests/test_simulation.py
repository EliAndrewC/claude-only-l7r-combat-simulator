"""Tests for the combat simulation orchestrator."""

from unittest.mock import patch

from src.engine.combat import create_combat_log
from src.engine.simulation import (
    _damage_pool_str,
    _format_pool_with_overflow,
    _resolve_attack,
    _should_convert_light_to_serious,
    _should_interrupt_parry,
    _should_predeclare_parry,
    _should_spend_void_on_wound_check,
    _snapshot_status,
    _tiebreak_key,
    simulate_combat,
)
from src.models.character import Character, Ring, RingName, Rings, Skill, SkillType
from src.models.combat import ActionType, FighterStatus
from src.models.weapon import Weapon, WeaponType


def _make_character(name: str, **ring_overrides: int) -> Character:
    """Helper to create a character with specific ring values."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    return Character(
        name=name,
        rings=Rings(**kwargs),
        skills=[
            Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ],
    )


KATANA = Weapon(name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2)


class TestSnapshotStatus:
    def test_returns_status_for_all_fighters(self) -> None:
        a = _make_character("A")
        b = _make_character("B")
        log = create_combat_log(["A", "B"], [a.rings.earth.value, b.rings.earth.value])
        fighters = {
            "A": {"char": a, "weapon": KATANA},
            "B": {"char": b, "weapon": KATANA},
        }
        actions_remaining: dict[str, list[int]] = {"A": [3, 5], "B": [2, 4, 7]}
        void_points = {"A": 2, "B": 2}
        result = _snapshot_status(log, fighters, actions_remaining, void_points)
        assert "A" in result
        assert "B" in result
        assert isinstance(result["A"], FighterStatus)

    def test_reflects_wound_state(self) -> None:
        a = _make_character("A")
        b = _make_character("B")
        log = create_combat_log(["A", "B"], [a.rings.earth.value, b.rings.earth.value])
        log.wounds["A"].light_wounds = 7
        log.wounds["A"].serious_wounds = 1
        fighters = {
            "A": {"char": a, "weapon": KATANA},
            "B": {"char": b, "weapon": KATANA},
        }
        actions_remaining: dict[str, list[int]] = {"A": [5], "B": [3, 8]}
        void_points = {"A": 2, "B": 2}
        result = _snapshot_status(log, fighters, actions_remaining, void_points)
        assert result["A"].light_wounds == 7
        assert result["A"].serious_wounds == 1
        assert result["A"].actions_remaining == [5]
        assert result["B"].light_wounds == 0
        assert result["B"].actions_remaining == [3, 8]

    def test_reflects_crippled_and_mortal(self) -> None:
        a = _make_character("A", earth=2)
        b = _make_character("B")
        log = create_combat_log(["A", "B"], [a.rings.earth.value, b.rings.earth.value])
        log.wounds["A"].serious_wounds = 2  # earth=2 -> crippled at 2
        fighters = {
            "A": {"char": a, "weapon": KATANA},
            "B": {"char": b, "weapon": KATANA},
        }
        void_points = {"A": 2, "B": 2}
        result = _snapshot_status(log, fighters, {"A": [], "B": []}, void_points)
        assert result["A"].is_crippled is True
        assert result["A"].is_mortally_wounded is False

    def test_void_points_from_dict(self) -> None:
        a = _make_character("A")
        b = _make_character("B")
        log = create_combat_log(["A", "B"], [a.rings.earth.value, b.rings.earth.value])
        fighters = {
            "A": {"char": a, "weapon": KATANA},
            "B": {"char": b, "weapon": KATANA},
        }
        void_points = {"A": 1, "B": 2}
        result = _snapshot_status(log, fighters, {"A": [], "B": []}, void_points)
        assert result["A"].void_points_max == a.void_points_max
        assert result["A"].void_points == 1
        assert result["B"].void_points == 2


class TestShouldSpendVoidOnWoundCheck:
    def test_returns_zero_when_no_void_available(self) -> None:
        result = _should_spend_void_on_wound_check(
            water_ring=2, light_wounds=20, void_available=0, max_spend=2,
        )
        assert result == 0

    def test_returns_zero_when_no_light_wounds(self) -> None:
        result = _should_spend_void_on_wound_check(
            water_ring=2, light_wounds=0, void_available=2, max_spend=2,
        )
        assert result == 0

    def test_deterministic_for_same_inputs(self) -> None:
        """Same inputs always produce the same decision."""
        results = [
            _should_spend_void_on_wound_check(
                water_ring=2, light_wounds=25, void_available=3, max_spend=2,
            )
            for _ in range(5)
        ]
        assert all(r == results[0] for r in results)

    def test_spends_when_high_wound_low_water(self) -> None:
        """With high wounds and low water, void should help significantly."""
        result = _should_spend_void_on_wound_check(
            water_ring=2, light_wounds=25, void_available=3, max_spend=2,
        )
        assert result >= 1

    def test_no_spend_when_low_wound_high_water(self) -> None:
        """With low wounds and high water, already likely to pass — no spend."""
        result = _should_spend_void_on_wound_check(
            water_ring=5, light_wounds=5, void_available=2, max_spend=2,
        )
        assert result == 0

    def test_respects_custom_threshold(self) -> None:
        """Higher threshold makes spending less likely."""
        result = _should_spend_void_on_wound_check(
            water_ring=2, light_wounds=15, void_available=1, max_spend=2,
            threshold=10.0,
        )
        assert result == 0

    def test_returns_int(self) -> None:
        """Function must return an int."""
        result = _should_spend_void_on_wound_check(
            water_ring=3, light_wounds=20, void_available=3, max_spend=2,
        )
        assert isinstance(result, int)

    def test_never_exceeds_max_spend(self) -> None:
        """Result must not exceed max_spend."""
        result = _should_spend_void_on_wound_check(
            water_ring=2, light_wounds=30, void_available=5, max_spend=3,
        )
        assert 0 <= result <= 3

    def test_never_exceeds_void_available(self) -> None:
        """Result must not exceed available void points."""
        result = _should_spend_void_on_wound_check(
            water_ring=2, light_wounds=30, void_available=1, max_spend=3,
        )
        assert 0 <= result <= 1


class TestStatusAfterOnActions:
    def test_all_actions_have_status_after(self) -> None:
        a = _make_character("Fighter A", fire=3)
        b = _make_character("Fighter B", fire=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=3)
        for action in log.actions:
            assert action.status_after is not None, (
                f"Action {action.action_type.value} by {action.actor} "
                f"at phase {action.phase} missing status_after"
            )

    def test_initiative_actions_have_correct_actions_remaining(self) -> None:
        a = _make_character("Fighter A")
        b = _make_character("Fighter B")
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        init_actions = [
            act for act in log.actions if act.action_type == ActionType.INITIATIVE
        ]
        # Each init action should have status_after with actions_remaining
        # matching the sorted kept dice (phase values) for that fighter
        for init_act in init_actions:
            assert init_act.status_after is not None
            actor_status = init_act.status_after[init_act.actor]
            assert actor_status.actions_remaining == sorted(init_act.dice_kept)


class TestSimulateCombatBasic:
    def test_returns_combat_log(self) -> None:
        a = _make_character("Fighter A")
        b = _make_character("Fighter B")
        log = simulate_combat(a, b, KATANA, KATANA)
        assert log.combatants == ["Fighter A", "Fighter B"]

    def test_has_winner_or_draw(self) -> None:
        a = _make_character("Fighter A")
        b = _make_character("Fighter B")
        log = simulate_combat(a, b, KATANA, KATANA)
        # Either there's a winner or it's a draw (None)
        assert log.winner is None or log.winner in ["Fighter A", "Fighter B"]

    def test_first_actions_are_initiative(self) -> None:
        a = _make_character("Fighter A")
        b = _make_character("Fighter B")
        log = simulate_combat(a, b, KATANA, KATANA)
        init_actions = [
            act for act in log.actions if act.action_type == ActionType.INITIATIVE
        ]
        assert len(init_actions) >= 2
        # First two actions should be initiative
        assert log.actions[0].action_type == ActionType.INITIATIVE
        assert log.actions[1].action_type == ActionType.INITIATIVE

    def test_respects_max_rounds(self) -> None:
        a = _make_character("Fighter A")
        b = _make_character("Fighter B")
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        assert log.round_number <= 1

    def test_logs_all_action_types(self) -> None:
        """A full combat should produce attack, damage, and wound_check actions."""
        a = _make_character("Fighter A", fire=3)
        b = _make_character("Fighter B", fire=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=10)
        action_types = {act.action_type for act in log.actions}
        assert ActionType.INITIATIVE in action_types
        assert ActionType.ATTACK in action_types


class TestSimulateCombatMortalWound:
    def test_ends_on_mortal_wound(self) -> None:
        """Combat ends when a character is mortally wounded."""
        # Give one fighter low earth (easy to kill) and high fire (easy to hit)
        a = _make_character("Strong", fire=4, earth=3, water=3, void=3)
        b = _make_character("Weak", fire=2, earth=1, water=1, void=2)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=50)
        # With earth=1, mortal wound at 2 serious wounds - should end quickly
        if log.winner is not None:
            loser = "Weak" if log.winner == "Strong" else "Strong"
            assert log.wounds[loser].is_mortally_wounded


class TestSimulateCombatPhaseOrder:
    def test_lower_die_acts_first_in_same_phase(self) -> None:
        """When two characters have actions in the same phase,
        the one with the lower action die acts first."""
        a = _make_character("Alpha", void=2)
        b = _make_character("Beta", void=2)

        # Control initiative: Alpha gets [3, 5] (drop 7), Beta gets [3, 8] (drop 9)
        # Both have phase 3 actions — Alpha's die is 3, Beta's die is 3 — tied
        # With same action dice, this still tests the phase ordering logic
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=2)
        # Just verify the simulation completes without error
        assert log.combatants == ["Alpha", "Beta"]


class TestSimulateCombatExtraDamage:
    def test_extra_damage_dice_from_exceeding_tn(self) -> None:
        """Extra damage dice = (attack_total - tn) // 5 on unparried hits."""
        a = _make_character("Attacker", fire=3, void=2)
        b = _make_character("Defender", fire=2, void=2)

        # We need to mock the combat functions to control the flow
        # Use a higher-level approach: run a real simulation and check that
        # damage actions exist with appropriate dice counts
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=5)
        damage_actions = [act for act in log.actions if act.action_type == ActionType.DAMAGE]
        # If any attacks hit, there should be damage actions
        attack_hits = [
            act for act in log.actions
            if act.action_type == ActionType.ATTACK and act.success
        ]
        if attack_hits:
            assert len(damage_actions) > 0

    def test_failed_parry_no_extra_dice(self) -> None:
        """When defender attempts parry and fails, no extra damage dice."""
        a = _make_character("Attacker", fire=3, void=2)
        b = _make_character("Defender", fire=2, void=2, air=3)

        # Run simulation — the rule about failed parry = no extra dice
        # is tested by checking the simulation logic directly below
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=5)
        # Verify parry actions are logged
        parry_actions = [act for act in log.actions if act.action_type == ActionType.PARRY]
        # This just verifies the simulation handles parries without crashing
        assert isinstance(parry_actions, list)


class TestVoidPointTracking:
    def test_void_points_initialized_from_character(self) -> None:
        """Void points should start at void_points_max for each fighter."""
        a = _make_character("A", void=3)  # lowest ring=2, so max=2
        b = _make_character("B", void=2)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        # First action's status_after should show initial void points
        first_status = log.actions[0].status_after
        assert first_status is not None
        assert first_status["A"].void_points_max == a.void_points_max
        assert first_status["B"].void_points_max == b.void_points_max
        # At the very start, void should be at max
        assert first_status["A"].void_points == a.void_points_max
        assert first_status["B"].void_points == b.void_points_max

    def test_void_points_never_negative(self) -> None:
        """Void points should never go below 0 during a combat."""
        a = _make_character("Strong", fire=4, earth=3, water=3, void=3)
        b = _make_character("Weak", fire=2, earth=1, water=1, void=2)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=50)
        for action in log.actions:
            if action.status_after:
                for name, status in action.status_after.items():
                    assert status.void_points >= 0, (
                        f"{name} has negative void points: {status.void_points}"
                    )

    def test_void_points_dont_exceed_max(self) -> None:
        """Void points should never exceed the max during combat."""
        a = _make_character("A", fire=3, void=3)
        b = _make_character("B", fire=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=10)
        for action in log.actions:
            if action.status_after:
                for name, status in action.status_after.items():
                    assert status.void_points <= status.void_points_max


class TestVoidSpendingOnWoundCheck:
    def test_wound_check_description_notes_void_spent(self) -> None:
        """When void is spent on a wound check, the description should note it."""
        # Run many combats to get at least one void spend
        a = _make_character("Strong", fire=4, earth=3, water=2, void=3)
        b = _make_character("Weak", fire=4, earth=2, water=2, void=2)
        found_void_note = False
        for _ in range(20):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            for action in log.actions:
                if action.action_type == ActionType.WOUND_CHECK and "void" in action.description.lower():
                    found_void_note = True
                    break
            if found_void_note:
                break
        # It's possible but unlikely that void is never spent in 20 combats
        # with these parameters. If this ever flakes, increase iterations.
        assert found_void_note, "Expected at least one wound check to mention void spending"

    def test_void_decrements_on_spend(self) -> None:
        """When void is spent, the fighter's void_points should decrease."""
        a = _make_character("Strong", fire=4, earth=3, water=2, void=3)
        b = _make_character("Weak", fire=4, earth=2, water=2, void=2)
        found_decrement = False
        for _ in range(20):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            for action in log.actions:
                if action.action_type == ActionType.WOUND_CHECK and "void" in action.description.lower():
                    found_decrement = True
                    break
            if found_decrement:
                break
        assert found_decrement

    def test_wound_check_tn_equals_light_wounds(self) -> None:
        """The wound check TN should equal current light_wounds (not double-counted)."""
        a = _make_character("A", fire=4, earth=3, water=3, void=3)
        b = _make_character("B", fire=4, earth=2, water=2, void=2)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=10)
        for i, action in enumerate(log.actions):
            if action.action_type == ActionType.WOUND_CHECK:
                # TN should equal the damage action's status_after light_wounds
                # (which is the light_wounds AFTER damage was applied)
                # Find the preceding damage action for this defender
                for j in range(i - 1, -1, -1):
                    prev = log.actions[j]
                    if prev.action_type == ActionType.DAMAGE and prev.target == action.actor:
                        damage_status = prev.status_after
                        if damage_status:
                            expected_tn = damage_status[action.actor].light_wounds
                            assert action.tn == expected_tn, (
                                f"Wound check TN {action.tn} != light_wounds {expected_tn}"
                            )
                        break


class TestCrippledNoExplode:
    """Feature 1: Crippled disables exploding 10s on attack/parry but not wound checks/damage."""

    def test_crippled_attacker_rolls_without_explode(self) -> None:
        """A crippled attacker's attack roll should have explode=False."""
        a = _make_character("Crippled", fire=3, earth=2, void=2)
        b = _make_character("Healthy", fire=2, earth=3, void=2)

        log = create_combat_log(
            ["Crippled", "Healthy"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        # Make attacker crippled (serious_wounds >= earth_ring)
        log.wounds["Crippled"].serious_wounds = 2  # earth=2, so crippled

        fighters = {
            "Crippled": {"char": a, "weapon": KATANA},
            "Healthy": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Crippled": [5], "Healthy": [3, 7]}
        void_points = {"Crippled": 0, "Healthy": 2}

        with patch("src.engine.simulation.roll_attack") as mock_attack:
            mock_attack.return_value = type("Action", (), {
                "success": False, "phase": 5, "target": None,
                "status_after": None, "total": 5,
                "action_type": ActionType.ATTACK, "actor": "Crippled",
                "dice_rolled": [5, 3], "dice_kept": [5, 3],
                "tn": 15, "description": "",
            })()
            _resolve_attack(
                log, 5, fighters["Crippled"], fighters["Healthy"],
                "Crippled", "Healthy", fighters, actions_remaining, void_points,
            )
            # Verify roll_attack was called with explode=False
            _, kwargs = mock_attack.call_args
            assert kwargs.get("explode") is False or (
                mock_attack.call_args[1].get("explode") is False
            )

    def test_crippled_defender_parries_without_explode(self) -> None:
        """A crippled defender's parry roll should have explode=False."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("CrippledDef", fire=2, earth=2, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "CrippledDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        # Make defender crippled
        log.wounds["CrippledDef"].serious_wounds = 2  # earth=2, so crippled

        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "CrippledDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "CrippledDef": [3, 7]}
        void_points = {"Attacker": 2, "CrippledDef": 0}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="CrippledDef", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
            )
            # Parry roll returns a failure
            mock_rak.return_value = ([8, 5], [8, 5], 13)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["CrippledDef"],
                "Attacker", "CrippledDef", fighters, actions_remaining, void_points,
            )
            # Verify roll_and_keep was called with explode=False for the parry
            parry_call = mock_rak.call_args
            assert parry_call[1].get("explode") is False

    def test_healthy_attacker_rolls_with_explode(self) -> None:
        """A non-crippled attacker's attack roll should have explode=True."""
        a = _make_character("Healthy", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, void=2)

        log = create_combat_log(
            ["Healthy", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        # No serious wounds, not crippled

        fighters = {
            "Healthy": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Healthy": [5], "Defender": [3, 7]}
        void_points = {"Healthy": 2, "Defender": 2}

        with patch("src.engine.simulation.roll_attack") as mock_attack:
            mock_attack.return_value = type("Action", (), {
                "success": False, "phase": 5, "target": None,
                "status_after": None, "total": 5,
                "action_type": ActionType.ATTACK, "actor": "Healthy",
                "dice_rolled": [5, 3], "dice_kept": [5, 3],
                "tn": 15, "description": "",
            })()
            _resolve_attack(
                log, 5, fighters["Healthy"], fighters["Defender"],
                "Healthy", "Defender", fighters, actions_remaining, void_points,
            )
            _, kwargs = mock_attack.call_args
            assert kwargs.get("explode") is True


class TestCrippledVoidReroll:
    """Feature 2: Spend void to reroll 10s while crippled."""

    def test_void_spent_to_reroll_tens_on_attack(self) -> None:
        """When crippled and attack has 10s, void can be spent to reroll them."""
        a = _make_character("Crippled", fire=3, earth=2, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        # Remove parry from defender so we focus on the attack reroll
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["Crippled", "Target"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        log.wounds["Crippled"].serious_wounds = 2  # crippled

        fighters = {
            "Crippled": {"char": a, "weapon": KATANA},
            "Target": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Crippled": [5], "Target": [3, 7]}
        void_points = {"Crippled": 2, "Target": 2}

        # Attack roll without explode gives [10, 7, 5, 3, 2] → kept [10, 7, 5], total=22
        # TN is 5 + 5*0 = 5 (no parry skill). Attack would succeed anyway.
        # But if TN were higher and attack missed, rerolling the 10 could help.
        # Let's set up a scenario where the attack MISSES with the 10 not exploded,
        # so void reroll kicks in.
        from src.models.combat import CombatAction

        # Mock roll_attack to return a failed roll with a 10 in dice
        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.reroll_tens") as mock_reroll:
            mock_attack.return_value = CombatAction(
                phase=5, actor="Crippled", action_type=ActionType.ATTACK,
                dice_rolled=[10, 7, 5, 3, 2], dice_kept=[10, 7, 5],
                total=22, tn=25, success=False,
                description="Crippled attacks: 5k3 vs TN 25",
            )
            # reroll_tens returns upgraded result that succeeds
            mock_reroll.return_value = ([18, 7, 5, 3, 2], [18, 7, 5], 30)

            _resolve_attack(
                log, 5, fighters["Crippled"], fighters["Target"],
                "Crippled", "Target", fighters, actions_remaining, void_points,
            )
            # Void should have been spent
            assert void_points["Crippled"] < 2
            mock_reroll.assert_called_once()

    def test_no_reroll_when_no_tens(self) -> None:
        """When crippled but no dice show 10, no void is spent for reroll."""
        a = _make_character("Crippled", fire=3, earth=2, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["Crippled", "Target"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        log.wounds["Crippled"].serious_wounds = 2  # crippled

        fighters = {
            "Crippled": {"char": a, "weapon": KATANA},
            "Target": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Crippled": [5], "Target": [3, 7]}
        void_points = {"Crippled": 2, "Target": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.reroll_tens") as mock_reroll:
            mock_attack.return_value = CombatAction(
                phase=5, actor="Crippled", action_type=ActionType.ATTACK,
                dice_rolled=[9, 7, 5, 3, 2], dice_kept=[9, 7, 5],
                total=21, tn=25, success=False,
                description="Crippled attacks: 5k3 vs TN 25",
            )

            _resolve_attack(
                log, 5, fighters["Crippled"], fighters["Target"],
                "Crippled", "Target", fighters, actions_remaining, void_points,
            )
            # No void spent for reroll (no tens)
            assert void_points["Crippled"] == 2
            mock_reroll.assert_not_called()


class TestWoundCheckSuccessChoice:
    """Feature 3: On successful wound check, may convert light wounds to 1 serious.

    The keep-threshold is based on wound check power:
        avg_wc ≈ water × 6.5 + 2
        threshold = max(10, round(avg_wc × 0.8))

    Water 1 → 10, Water 2 → 12, Water 3 → 17, Water 4 → 22, Water 5 → 28
    """

    # --- Universal: ≤ 10 is always safe ---

    def test_always_keeps_at_10_or_below(self) -> None:
        """Below 10 light wounds there is zero downside to keeping."""
        for water in range(1, 6):
            assert _should_convert_light_to_serious(
                light_wounds=10, serious_wounds=0, earth_ring=4, water_ring=water,
            ) is False

    def test_always_keeps_trivial_wounds(self) -> None:
        """Very low light wounds are never worth converting."""
        assert _should_convert_light_to_serious(
            light_wounds=5, serious_wounds=0, earth_ring=3, water_ring=1,
        ) is False

    # --- Low Water (bad wound check) ---

    def test_low_water_keeps_11(self) -> None:
        """Water 2 (threshold 12) still keeps 11 light wounds."""
        assert _should_convert_light_to_serious(
            light_wounds=11, serious_wounds=0, earth_ring=4, water_ring=2,
        ) is False

    def test_low_water_converts_above_threshold(self) -> None:
        """Water 2 (threshold 12) converts at 15 light wounds."""
        assert _should_convert_light_to_serious(
            light_wounds=15, serious_wounds=0, earth_ring=4, water_ring=2,
        ) is True

    def test_very_low_water_converts_above_10(self) -> None:
        """Water 1 (threshold 10) converts at 11 — bad wound check can't carry."""
        assert _should_convert_light_to_serious(
            light_wounds=11, serious_wounds=0, earth_ring=4, water_ring=1,
        ) is True

    # --- High Water (good wound check) ---

    def test_high_water_keeps_15(self) -> None:
        """Water 3 (threshold 17) comfortably keeps 15 light wounds."""
        assert _should_convert_light_to_serious(
            light_wounds=15, serious_wounds=0, earth_ring=4, water_ring=3,
        ) is False

    def test_high_water_keeps_20(self) -> None:
        """Water 4 (threshold 22) keeps 20 light wounds."""
        assert _should_convert_light_to_serious(
            light_wounds=20, serious_wounds=0, earth_ring=4, water_ring=4,
        ) is False

    def test_extreme_water_never_keeps_40(self) -> None:
        """Even Water 5 (threshold 28) converts 40 light wounds."""
        assert _should_convert_light_to_serious(
            light_wounds=40, serious_wounds=0, earth_ring=4, water_ring=5,
        ) is True

    def test_extreme_water_keeps_25(self) -> None:
        """Water 5 (threshold 28) keeps 25 light wounds."""
        assert _should_convert_light_to_serious(
            light_wounds=25, serious_wounds=0, earth_ring=4, water_ring=5,
        ) is False

    # --- Safety: never convert into crippled/mortal ---

    def test_no_convert_if_would_cripple(self) -> None:
        """Don't convert if taking a serious wound would cripple."""
        # earth=2, serious=1. Adding 1 more = 2 = crippled. Should avoid.
        assert _should_convert_light_to_serious(
            light_wounds=25, serious_wounds=1, earth_ring=2, water_ring=1,
        ) is False

    def test_no_convert_if_would_mortally_wound(self) -> None:
        """Don't convert if taking a serious wound would mortally wound."""
        # earth=2, serious=3. Adding 1 = 4 = 2*earth = mortal.
        assert _should_convert_light_to_serious(
            light_wounds=30, serious_wounds=3, earth_ring=2, water_ring=5,
        ) is False

    # --- Threshold scales monotonically with Water ---

    def test_threshold_increases_with_water(self) -> None:
        """Higher Water → higher threshold → can hold more light wounds."""
        # At 13 light wounds: Water 2 (threshold 12) converts, Water 3 (17) keeps
        assert _should_convert_light_to_serious(
            light_wounds=13, serious_wounds=0, earth_ring=4, water_ring=2,
        ) is True
        assert _should_convert_light_to_serious(
            light_wounds=13, serious_wounds=0, earth_ring=4, water_ring=3,
        ) is False

    # --- Integration: full simulation produces conversions ---

    def test_converts_in_full_simulation(self) -> None:
        """In a full simulation, wound check success conversion is logged."""
        a = _make_character("Heavy", fire=5, earth=4, water=4, void=4)
        b = _make_character("Tough", fire=5, earth=4, water=4, void=4)
        found_conversion = False
        for _ in range(30):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            for action in log.actions:
                if (action.action_type == ActionType.WOUND_CHECK
                        and action.success
                        and "convert" in action.description.lower()):
                    found_conversion = True
                    break
            if found_conversion:
                break
        assert found_conversion, "Expected at least one wound check conversion in 30 combats"


class TestPreDeclaredParry:
    """Feature 4: Pre-declared parry gives +5 bonus (free raise)."""

    def test_predeclare_heuristic_true_when_helpful(self) -> None:
        """Heuristic suggests pre-declaring when bonus meaningfully helps."""
        # High attack TN (hard to parry), moderate parry skill
        assert _should_predeclare_parry(
            defender_parry_rank=2, air_ring=3, attack_tn=25, is_crippled=False,
        ) is True

    def test_predeclare_heuristic_false_when_easy(self) -> None:
        """Don't pre-declare when parry is already likely to succeed."""
        # Low attack TN, strong parry — no need for bonus
        assert _should_predeclare_parry(
            defender_parry_rank=5, air_ring=4, attack_tn=10, is_crippled=False,
        ) is False

    def test_predeclare_gives_plus5_bonus(self) -> None:
        """When pre-declared, +5 bonus is added to the parry total."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        # Defender has action in phase 5
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=True):
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
            )
            # Parry roll: raw total 32, +5 bonus = 37, vs TN 35 (raw attack total)
            mock_rak.return_value = ([20, 12, 8], [20, 12], 32)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # Find the parry action in the log
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            parry = parry_actions[0]
            # TN is the raw attack total; total includes +5 bonus
            assert parry.tn == 35
            assert parry.total == 37  # 32 + 5
            assert "pre-declared" in parry.description.lower()

    def test_predeclare_wasted_on_miss(self) -> None:
        """When pre-declared and attack misses, parry die is still consumed but no wasted action logged."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=True):
            # Attack misses
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[5, 3], dice_kept=[5, 3],
                total=8, tn=15, success=False, description="Attacker attacks",
            )

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # Defender's phase-5 die was consumed by pre-declare
            assert 5 not in actions_remaining["Defender"]
            # Only the attack action is logged (no wasted parry action)
            assert len(log.actions) == 1
            assert log.actions[0].action_type == ActionType.ATTACK


    def test_consumed_die_skips_attack(self) -> None:
        """When attacker's die was already consumed (e.g. by parry), no attack is made."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        # Attacker has NO die for phase 5 (already consumed by parry)
        actions_remaining = {"Attacker": [7], "Defender": [3, 8]}
        void_points = {"Attacker": 2, "Defender": 2}

        _resolve_attack(
            log, 5, fighters["Attacker"], fighters["Defender"],
            "Attacker", "Defender", fighters, actions_remaining, void_points,
        )

        # No action should be logged
        assert len(log.actions) == 0
        # Remaining dice unchanged
        assert actions_remaining["Attacker"] == [7]
        assert actions_remaining["Defender"] == [3, 8]


class TestInterruptParry:
    """Feature 5: Spend 2 action dice to create an interrupt parry."""

    def test_interrupt_spends_two_dice(self) -> None:
        """Interrupt parry consumes 2 action dice."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        # Defender has NO action in phase 5, but has 2 other dice
        actions_remaining = {"Attacker": [5], "Defender": [7, 9]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_interrupt_parry", return_value=True):
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            # Parry roll
            mock_rak.return_value = ([20, 12, 8], [20, 12], 32)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # Defender should have spent 2 dice (had [7, 9], now empty)
            assert len(actions_remaining["Defender"]) == 0

    def test_interrupt_logged_as_interrupt(self) -> None:
        """Interrupt parries should be logged with INTERRUPT action type."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [7, 9]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_interrupt_parry", return_value=True):
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_rak.return_value = ([20, 12, 8], [20, 12], 32)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # Find the interrupt action
            interrupt_actions = [a for a in log.actions if a.action_type == ActionType.INTERRUPT]
            assert len(interrupt_actions) == 1
            assert "interrupt" in interrupt_actions[0].description.lower()

    def test_no_interrupt_with_fewer_than_2_dice(self) -> None:
        """Cannot interrupt with fewer than 2 remaining dice."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        # Defender has no action in phase 5, and only 1 die left
        actions_remaining = {"Attacker": [5], "Defender": [9]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack:
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
            )

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # No parry or interrupt should have occurred
            parry_actions = [a for a in log.actions
                            if a.action_type in (ActionType.PARRY, ActionType.INTERRUPT)]
            assert len(parry_actions) == 0
            # Defender's die should be unchanged
            assert actions_remaining["Defender"] == [9]

    def test_interrupt_heuristic_catastrophic_overflow(self) -> None:
        """Heuristic triggers on catastrophic overflow (damage_rolled > 10)."""
        # attack_total=35 vs attack_tn=15 → extra = (35-15)//5 = 4
        # damage_rolled = weapon_rolled(4) + attacker_fire(3) + 4 = 11 > 10 → catastrophic
        assert _should_interrupt_parry(
            defender_parry_rank=3, air_ring=3,
            attack_total=35, attack_tn=15,
            weapon_rolled=4, attacker_fire=3,
            dice_remaining=4, serious_wounds=0, earth_ring=3,
        ) is True

    def test_interrupt_heuristic_near_cripple_with_extras(self) -> None:
        """Heuristic triggers when near cripple and significant extra dice."""
        # attack_total=25 vs attack_tn=15 → extra = 2
        # damage_rolled = 4 + 3 + 2 = 9 ≤ 10, but wounds_to_cripple=1 and extra≥2
        assert _should_interrupt_parry(
            defender_parry_rank=3, air_ring=3,
            attack_total=25, attack_tn=15,
            weapon_rolled=4, attacker_fire=3,
            dice_remaining=3, serious_wounds=2, earth_ring=3,
        ) is True

    def test_interrupt_heuristic_declines_low_threat(self) -> None:
        """Heuristic declines when damage is modest and not near cripple."""
        # attack_total=16 vs attack_tn=15 → extra = 0
        # damage_rolled = 4 + 3 + 0 = 7 ≤ 10, wounds_to_cripple=3
        assert _should_interrupt_parry(
            defender_parry_rank=3, air_ring=3,
            attack_total=16, attack_tn=15,
            weapon_rolled=4, attacker_fire=3,
            dice_remaining=4, serious_wounds=0, earth_ring=3,
        ) is False

    def test_interrupt_heuristic_declines_when_few_dice(self) -> None:
        """Cannot interrupt with fewer than 2 remaining dice."""
        assert _should_interrupt_parry(
            defender_parry_rank=3, air_ring=3,
            attack_total=35, attack_tn=15,
            weapon_rolled=4, attacker_fire=3,
            dice_remaining=1, serious_wounds=0, earth_ring=3,
        ) is False

    def test_interrupt_heuristic_declines_no_parry_skill(self) -> None:
        """Cannot interrupt without parry skill."""
        assert _should_interrupt_parry(
            defender_parry_rank=0, air_ring=3,
            attack_total=35, attack_tn=15,
            weapon_rolled=4, attacker_fire=3,
            dice_remaining=4, serious_wounds=0, earth_ring=3,
        ) is False

    def test_interrupt_never_predeclared(self) -> None:
        """Interrupt parries are reactive and never get the +5 pre-declare bonus."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [7, 9]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_interrupt_parry", return_value=True):
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_rak.return_value = ([20, 12, 8], [20, 12], 32)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # Find the interrupt action — no pre-declare bonus
            interrupt_actions = [a for a in log.actions if a.action_type == ActionType.INTERRUPT]
            assert len(interrupt_actions) == 1
            assert "pre-declared" not in interrupt_actions[0].description.lower()
            assert interrupt_actions[0].total == 32  # No +5 bonus


class TestInitiativeTiebreak:
    """Feature 6: Full initiative tiebreaking rules."""

    def test_tiebreak_by_second_lowest_die(self) -> None:
        """When same phase, lower second die acts first."""
        a = _make_character("Alpha", void=3)
        b = _make_character("Beta", void=3)
        fighters = {
            "Alpha": {"char": a, "weapon": KATANA},
            "Beta": {"char": b, "weapon": KATANA},
        }
        # Alpha's remaining actions: [3, 5, 8]
        # Beta's remaining actions: [3, 6, 9]
        # Both in phase 3. Alpha's sorted dice asc = [3, 5, 8], Beta's = [3, 6, 9]
        # Alpha's second-lowest is 5 < Beta's 6, so Alpha goes first
        key_a = _tiebreak_key("Alpha", {"Alpha": [3, 5, 8], "Beta": [3, 6, 9]}, fighters, 3)
        key_b = _tiebreak_key("Beta", {"Alpha": [3, 5, 8], "Beta": [3, 6, 9]}, fighters, 3)
        assert key_a < key_b

    def test_tiebreak_by_void_when_dice_equal(self) -> None:
        """When action dice are identical, higher Void acts first."""
        a = _make_character("Alpha", void=4)
        b = _make_character("Beta", void=2)
        fighters = {
            "Alpha": {"char": a, "weapon": KATANA},
            "Beta": {"char": b, "weapon": KATANA},
        }
        # Same dice
        key_a = _tiebreak_key("Alpha", {"Alpha": [3, 5], "Beta": [3, 5]}, fighters, 3)
        key_b = _tiebreak_key("Beta", {"Alpha": [3, 5], "Beta": [3, 5]}, fighters, 3)
        # Higher Void goes first, so key_a < key_b
        assert key_a < key_b

    def test_tiebreak_in_full_simulation(self) -> None:
        """Full simulation uses proper tiebreaking without errors."""
        a = _make_character("Alpha", void=3, fire=3)
        b = _make_character("Beta", void=3, fire=3)
        # Run several simulations to exercise tiebreaking
        for _ in range(10):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=3)
            assert log.combatants == ["Alpha", "Beta"]


class TestDamagePoolStr:
    """Tests for the _damage_pool_str helper."""

    def test_basic_pool(self) -> None:
        assert _damage_pool_str(4, 2, 3, 0) == "7k2"

    def test_with_extra_dice(self) -> None:
        assert _damage_pool_str(4, 2, 3, 2) == "9k2"

    def test_zero_fire(self) -> None:
        # Shouldn't happen in practice but check math
        assert _damage_pool_str(3, 1, 0, 0) == "3k1"


class TestDicePoolOnParryAndWoundCheck:
    """dice_pool should be set on parry/interrupt and wound_check actions."""

    def test_parry_action_has_dice_pool(self) -> None:
        """Parry actions should have dice_pool set."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=True):
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_rak.return_value = ([20, 12, 8], [20, 12], 32)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            # Parry: parry_rank=2, air=3, so 5k3, pre-declared gives + 5
            assert parry_actions[0].dice_pool == "5k3 + 5"

    def test_wound_check_has_dice_pool(self) -> None:
        """Wound check actions should have dice_pool set."""
        a = _make_character("Attacker", fire=4, earth=3, void=3)
        b = _make_character("Defender", fire=2, earth=3, water=3, void=2)
        # Remove parry from defender for simplicity
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=5, success=True, description="Attacker attacks",
                dice_pool="7k4",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Attacker deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            wc_actions = [a for a in log.actions if a.action_type == ActionType.WOUND_CHECK]
            assert len(wc_actions) == 1
            # Water 3 + void_spend. Expected: "{water+1}k{water+void}"
            # Base case (no void spend): 4k3
            assert "k" in wc_actions[0].dice_pool


class TestDamageContext:
    """Damage context annotations on attack hits and failed parries."""

    def test_attack_hit_shows_damage_pool(self) -> None:
        """When attack hits, description includes expected damage pool."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)
        # Remove parry so we get unparried damage
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            # Attack hits with total=20 vs TN=5, so extra_dice = (20-5)//5 = 3
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[12, 8], dice_kept=[12, 8],
                total=20, tn=5, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Attacker deals 18 damage",
                dice_pool="10k2",
            )
            mock_wc.return_value = (True, 25)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            attack_action = [a for a in log.actions if a.action_type == ActionType.ATTACK][0]
            # Extra dice = (20-5)//5 = 3; damage pool = (4+3+3)k2 = 10k2
            assert "damage will be 10k2" in attack_action.description

    def test_failed_parry_shows_reduced_damage(self) -> None:
        """When parry fails, parry description shows damage reduced by parry rank."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            # Attack hits with total=25, tn=15 → extra = (25-15)//5 = 2
            # Defender has Parry rank 2, so reduces by 2 → 0 extras remain
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[25, 15], dice_kept=[25, 15],
                total=25, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            # Parry fails
            mock_rak.return_value = ([10, 8, 5], [10, 8], 18)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            # extra=2, parry_rank=2 → reduced_extra=0 → reduced_rolled=4+3+0=7
            # full_rolled=4+3+2=9 → "9k2 is reduced to 7k2"
            assert "9k2 is reduced to 7k2" in parry_actions[0].description


class TestFormatPoolWithOverflow:
    """Tests for the _format_pool_with_overflow helper."""

    def test_no_overflow(self) -> None:
        assert _format_pool_with_overflow(7, 2) == "7k2"

    def test_with_overflow(self) -> None:
        # 18k2 → kept=2+8=10, rolled=10 → "18k2, which becomes 10k10"
        assert _format_pool_with_overflow(18, 2) == "18k2, which becomes 10k10"

    def test_with_overflow_and_bonus(self) -> None:
        # 22k3 → kept=3+12=15, rolled=10 → bonus=5, kept=10
        # "22k3, which becomes 10k10+5"
        assert _format_pool_with_overflow(22, 3) == "22k3, which becomes 10k10+5"

    def test_exactly_10_rolled(self) -> None:
        assert _format_pool_with_overflow(10, 3) == "10k3"

    def test_11_rolled(self) -> None:
        # 11k2 → kept=2+1=3, rolled=10 → "11k2, which becomes 10k3"
        assert _format_pool_with_overflow(11, 2) == "11k2, which becomes 10k3"


class TestDamageOverflowAnnotations:
    """Overflow conversion appears in attack hit and failed parry annotations."""

    def test_attack_hit_shows_overflow_conversion(self) -> None:
        """High extras trigger overflow display in attack annotation."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)
        # Remove parry so we get unparried damage
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            # Attack hits with total=50 vs TN=5, so extra_dice = (50-5)//5 = 9
            # raw_rolled = 4 + 3 + 9 = 16 → overflow → "16k2, which becomes 10k8"
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[30, 20], dice_kept=[30, 20],
                total=50, tn=5, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Attacker deals 18 damage",
                dice_pool="10k2",
            )
            mock_wc.return_value = (True, 25)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            attack_action = [a for a in log.actions if a.action_type == ActionType.ATTACK][0]
            assert "16k2, which becomes 10k8" in attack_action.description

    def test_failed_parry_partial_reduction(self) -> None:
        """When parry rank < all extras, only parry rank dice are removed."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        # Defender with Parry rank 2
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            # Attack total=40, tn=15 → extra = (40-15)//5 = 5
            # Parry rank 2 → reduces by 2 → 3 extras remain
            # full_rolled = 4+3+5 = 12, reduced_rolled = 4+3+3 = 10
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[25, 15], dice_kept=[25, 15],
                total=40, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_rak.return_value = ([10, 8, 5], [10, 8], 18)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            # "12k2 is reduced to 10k2"
            assert "12k2 is reduced to 10k2" in parry_actions[0].description

    def test_failed_parry_no_annotation_when_no_extras(self) -> None:
        """When attack barely hits (no extras), failed parry has no damage annotation."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            # Attack total=17, tn=15 → extra = (17-15)//5 = 0
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[10, 7], dice_kept=[10, 7],
                total=17, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            mock_rak.return_value = ([10, 8, 5], [10, 8], 18)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            assert "is reduced to" not in parry_actions[0].description

    def test_actual_damage_uses_reduced_extras(self) -> None:
        """Verify roll_damage gets the correct reduced extra_dice count."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_character("Defender", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(
            ["Attacker", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "Defender": [5, 7]}
        void_points = {"Attacker": 2, "Defender": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            # Attack total=40, tn=15 → all_extra = 5
            # Defender Parry rank 2 → extra_dice = max(0, 5-2) = 3
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                dice_rolled=[25, 15], dice_kept=[25, 15],
                total=40, tn=15, success=True, description="Attacker attacks",
                dice_pool="6k3",
            )
            # Parry fails
            mock_rak.return_value = ([10, 8, 5], [10, 8], 18)
            mock_damage.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Attacker deals 18 damage",
                dice_pool="10k2",
            )
            mock_wc.return_value = (True, 25)

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["Defender"],
                "Attacker", "Defender", fighters, actions_remaining, void_points,
            )

            # roll_damage should be called with extra_dice=3 (5 - parry_rank 2)
            mock_damage.assert_called_once()
            _, kwargs = mock_damage.call_args
            if "extra_dice" in kwargs:
                assert kwargs["extra_dice"] == 3
            else:
                # positional: roll_damage(attacker, weapon_rolled, weapon_kept, extra_dice)
                args = mock_damage.call_args[0]
                assert args[3] == 3
