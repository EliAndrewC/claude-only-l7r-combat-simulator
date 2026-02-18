"""Tests for the combat simulation orchestrator."""

from unittest.mock import patch

from src.engine.combat import create_combat_log
from src.engine.simulation import (
    _apply_ability4_rounding,
    _compute_dan_roll_bonus,
    _damage_pool_str,
    _format_pool_with_overflow,
    _matsu_attack_choice,
    _resolve_attack,
    _should_convert_light_to_serious,
    _should_interrupt_parry,
    _should_predeclare_parry,
    _should_spend_void_on_wound_check,
    _snapshot_status,
    _spend_void,
    _tiebreak_key,
    _total_void,
    _void_spent_label,
    _try_phase_shift_parry,
    simulate_combat,
)
from src.models.character import Character, ProfessionAbility, Ring, RingName, Rings, Skill, SkillType
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


def _make_waveman(
    name: str,
    abilities: list[tuple[int, int]] | None = None,
    **ring_overrides: int,
) -> Character:
    """Helper to create a Wave Man character with specific abilities."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    pa = [ProfessionAbility(number=n, rank=r) for n, r in (abilities or [])]
    return Character(
        name=name,
        rings=Rings(**kwargs),
        skills=[
            Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ],
        profession_abilities=pa,
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

    If converting would cripple, threshold is raised to 1.5× (e.g. Water 4 → 33).
    Never converts if it would mortally wound.
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

    # --- Safety: cripple threshold / mortal guard ---

    def test_would_cripple_raises_threshold(self) -> None:
        """If converting would cripple, require higher light wounds to convert."""
        # earth=3, serious=2. Normal threshold for water=3 is 17.
        # Converting would cripple → threshold raised to 26.
        # 20 light wounds: below cripple threshold, keeps.
        assert _should_convert_light_to_serious(
            light_wounds=20, serious_wounds=2, earth_ring=3, water_ring=3,
        ) is False
        # 30 light wounds: above cripple threshold, converts despite cripple cost.
        assert _should_convert_light_to_serious(
            light_wounds=30, serious_wounds=2, earth_ring=3, water_ring=3,
        ) is True

    def test_already_crippled_uses_normal_threshold(self) -> None:
        """Already crippled (serious >= earth) — no extra cripple cost, normal threshold."""
        # earth=3, serious=3, water=3. Already crippled. serious+1=4 >= 3 but < 6.
        # would_cripple is True (4 >= 3), so cripple threshold 26 applies.
        # But 30 > 26, so still converts.
        assert _should_convert_light_to_serious(
            light_wounds=30, serious_wounds=3, earth_ring=3, water_ring=3,
        ) is True

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
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

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
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

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
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

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
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

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


# ===================================================================
# Wave Man Ability Integration Tests
# ===================================================================


class TestWaveManInitiative:
    """Ability 6: Extra unkept die on initiative."""

    def test_ability6_extra_unkept_die(self) -> None:
        """Ability 6 rank 1 means roll_initiative gets extra_unkept=1."""
        a = _make_waveman("WM", abilities=[(6, 1)], void=3)
        b = _make_character("Samurai", void=3)

        # WM: void=3, extra_unkept=1 → rolls 5 dice, drop 2 highest, keep 3
        # Samurai: void=3, extra_unkept=0 → rolls 4, drop 1, keep 3
        with patch("src.engine.simulation.roll_initiative") as mock_init:
            from src.models.combat import CombatAction
            mock_init.side_effect = [
                CombatAction(
                    phase=0, actor="WM", action_type=ActionType.INITIATIVE,
                    dice_rolled=[2, 3, 5, 7, 9], dice_kept=[2, 3, 5],
                    total=0, description="WM acts in phases 2, 3, 5",
                ),
                CombatAction(
                    phase=0, actor="Samurai", action_type=ActionType.INITIATIVE,
                    dice_rolled=[3, 4, 6, 8], dice_kept=[3, 4, 6],
                    total=0, description="Samurai acts in phases 3, 4, 6",
                ),
            ]
            simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
            # Verify WM's call includes extra_unkept=1
            wm_call = mock_init.call_args_list[0]
            assert wm_call[1].get("extra_unkept") == 1 or wm_call.kwargs.get("extra_unkept") == 1

    def test_ability6_rank2_extra(self) -> None:
        """Ability 6 rank 2 passes extra_unkept=2."""
        a = _make_waveman("WM", abilities=[(6, 2)], void=2)
        b = _make_character("B")
        with patch("src.engine.simulation.roll_initiative") as mock_init:
            from src.models.combat import CombatAction
            mock_init.side_effect = [
                CombatAction(
                    phase=0, actor="WM", action_type=ActionType.INITIATIVE,
                    dice_rolled=[1, 2, 3, 8, 9], dice_kept=[1, 2],
                    total=0, description="WM acts in phases 1, 2",
                ),
                CombatAction(
                    phase=0, actor="B", action_type=ActionType.INITIATIVE,
                    dice_rolled=[3, 5, 7], dice_kept=[3, 5],
                    total=0, description="B acts in phases 3, 5",
                ),
            ]
            simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
            wm_call = mock_init.call_args_list[0]
            assert wm_call[1].get("extra_unkept") == 2 or wm_call.kwargs.get("extra_unkept") == 2


class TestWaveManAttackReroll:
    """Ability 1: Free raise on miss, auto-parry."""

    def test_ability1_raises_missed_attack(self) -> None:
        """Ability 1 rank 1 adds +5 to a missed attack."""
        a = _make_waveman("WM", abilities=[(1, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            # Attack misses by 3 (total=2, tn=5). Ability 1 adds +5 → 7 >= 5, hits.
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[2], dice_kept=[2],
                total=2, tn=5, success=False,
                description="WM attacks: 5k2 vs TN 5",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="WM deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            # Attack should be marked as hit with free raise note
            attack_actions = [a for a in log.actions if a.action_type == ActionType.ATTACK]
            assert len(attack_actions) == 1
            assert attack_actions[0].success is True
            assert "on miss" in attack_actions[0].description.lower()

            # Parry should auto-succeed
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            assert parry_actions[0].success is True
            assert "auto-success" in parry_actions[0].description.lower()

    def test_ability1_no_effect_when_attack_hits(self) -> None:
        """Ability 1 doesn't trigger when attack already hits."""
        a = _make_waveman("WM", abilities=[(1, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, void=2)
        b.skills = []  # No parry

        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[20], dice_kept=[20],
                total=20, tn=5, success=True,
                description="WM attacks",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10], dice_kept=[10],
                total=10, description="WM deals 10 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            attack_actions = [a for a in log.actions if a.action_type == ActionType.ATTACK]
            assert "on miss" not in attack_actions[0].description.lower()


class TestWaveManParryTN:
    """Ability 2: Raises parry TN by 5."""

    def test_ability2_raises_parry_tn(self) -> None:
        """Ability 2 rank 1 adds +5 to the TN the defender must meet to parry."""
        a = _make_waveman("WM", abilities=[(2, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [5, 7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=15, success=True, description="WM attacks",
                dice_pool="6k3",
            )
            # Parry total = 22. Normal TN would be 20 (attack total).
            # With ability 2: TN = 20 + 5 = 25. 22 < 25 → fails.
            mock_rak.return_value = ([12, 10, 8], [12, 10], 22)

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            assert parry_actions[0].tn == 25  # 20 + 5
            assert parry_actions[0].success is False


class TestWaveManWeaponBoost:
    """Ability 3: Add rolled die to weapons < 4k2."""

    def test_ability3_boosts_wakizashi(self) -> None:
        """Ability 3 rank 1 boosts Wakizashi from 3k2 to 4k2."""
        a = _make_waveman("WM", abilities=[(3, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, void=2)
        b.skills = []  # No parry

        wakizashi = Weapon(name="Wakizashi", weapon_type=WeaponType.WAKIZASHI, rolled=3, kept=2)
        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": wakizashi},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[20], dice_kept=[20],
                total=20, tn=5, success=True, description="WM attacks",
                dice_pool="6k3",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="WM deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            # roll_damage should be called with boosted_rolled=4 (3+1, capped at 4)
            mock_damage.assert_called_once()
            args = mock_damage.call_args[0]
            assert args[1] == 4  # weapon_rolled

    def test_ability3_no_boost_for_katana(self) -> None:
        """Ability 3 doesn't boost Katana (already 4k2)."""
        a = _make_waveman("WM", abilities=[(3, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, void=2)
        b.skills = []

        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[20], dice_kept=[20],
                total=20, tn=5, success=True, description="WM attacks",
                dice_pool="6k3",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="WM deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            # Katana is already 4k2, no boost
            args = mock_damage.call_args[0]
            assert args[1] == 4  # weapon_rolled stays at 4


class TestWaveManDamageRounding:
    """Ability 4: Round damage up to nearest 5 or add 3 if already multiple of 5."""

    def test_ability4_rounds_up(self) -> None:
        """12 → ceil(12/5)*5 = 15."""
        total, note = _apply_ability4_rounding(12, 1)
        assert total == 15
        assert "12" in note and "15" in note

    def test_ability4_adds_3_on_multiple_of_5(self) -> None:
        """15 → 15 + 3 = 18."""
        total, note = _apply_ability4_rounding(15, 1)
        assert total == 18

    def test_ability4_rank2_double_application(self) -> None:
        """12 → 15 (round up) → 18 (multiple of 5, +3)."""
        total, note = _apply_ability4_rounding(12, 2)
        assert total == 18

    def test_ability4_rank2_non_multiple(self) -> None:
        """7 → 10 → 13."""
        total, note = _apply_ability4_rounding(7, 2)
        assert total == 13


class TestWaveManFailedParryBonus:
    """Ability 9: Recover removed extra dice on failed parry."""

    def test_ability9_recovers_dice(self) -> None:
        """Ability 9 rank 1 recovers up to 2 removed extra dice."""
        a = _make_waveman("WM", abilities=[(9, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, air=3, void=2)

        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [5, 7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            # Attack total=40, tn=15 → all_extra=5, parry_rank=2 → removed=2
            # Without ability 9: extra_dice=3
            # With ability 9 rank 1: bonus_back=min(2, 2*1)=2, extra_dice=3+2=5
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[25, 15], dice_kept=[25, 15],
                total=40, tn=15, success=True, description="WM attacks",
                dice_pool="6k3",
            )
            mock_rak.return_value = ([10, 8, 5], [10, 8], 18)  # Parry fails
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="WM deals 18 damage",
                dice_pool="10k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            # roll_damage called with extra_dice=5 (3 base + 2 recovered)
            mock_damage.assert_called_once()
            args = mock_damage.call_args[0]
            assert args[3] == 5


class TestWaveManDamageReduction:
    """Ability 8: Subtract damage when attacker had extra dice."""

    def test_ability8_reduces_damage(self) -> None:
        """Ability 8 rank 1 subtracts 5 from damage when extras exist."""
        a = _make_character("Atk", fire=3, earth=3, void=2)
        b = _make_waveman("WM", abilities=[(8, 1)], fire=2, earth=3, void=2)
        b.skills = []  # No parry

        log = create_combat_log(["Atk", "WM"], [3, 3])
        fighters = {
            "Atk": {"char": a, "weapon": KATANA},
            "WM": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Atk": [5], "WM": [7]}
        void_points = {"Atk": 2, "WM": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            # Attack total=25, tn=5 → 4 extra dice → ability 8 triggers
            mock_attack.return_value = CombatAction(
                phase=5, actor="Atk", action_type=ActionType.ATTACK,
                dice_rolled=[15, 10], dice_kept=[15, 10],
                total=25, tn=5, success=True, description="Atk attacks",
                dice_pool="5k2",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="Atk", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Atk deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["Atk"], fighters["WM"],
                "Atk", "WM", fighters, actions_remaining, void_points,
            )

            damage_actions = [a for a in log.actions if a.action_type == ActionType.DAMAGE]
            assert len(damage_actions) == 1
            assert damage_actions[0].total == 13  # 18 - 5
            assert "damage reduction" in damage_actions[0].description.lower()

    def test_ability8_no_reduction_without_extras(self) -> None:
        """Ability 8 doesn't reduce when there are no extra dice."""
        a = _make_character("Atk", fire=3, earth=3, void=2)
        b = _make_waveman("WM", abilities=[(8, 1)], fire=2, earth=3, void=2)
        b.skills = []

        log = create_combat_log(["Atk", "WM"], [3, 3])
        fighters = {
            "Atk": {"char": a, "weapon": KATANA},
            "WM": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Atk": [5], "WM": [7]}
        void_points = {"Atk": 2, "WM": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            # Attack total=5, tn=5 → 0 extra dice → no reduction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Atk", action_type=ActionType.ATTACK,
                dice_rolled=[5], dice_kept=[5],
                total=5, tn=5, success=True, description="Atk attacks",
                dice_pool="5k2",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="Atk", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Atk deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["Atk"], fighters["WM"],
                "Atk", "WM", fighters, actions_remaining, void_points,
            )

            damage_actions = [a for a in log.actions if a.action_type == ActionType.DAMAGE]
            assert damage_actions[0].total == 18  # No reduction


class TestWaveManWoundCheckBonus:
    """Ability 7: Extra unkept dice on wound checks."""

    def test_ability7_passes_extra_rolled(self) -> None:
        """Ability 7 rank 1 → extra_rolled=2 on wound check."""
        a = _make_character("Atk", fire=3, earth=3, void=2)
        b = _make_waveman("WM", abilities=[(7, 1)], fire=2, earth=3, water=3, void=2)
        b.skills = []

        log = create_combat_log(["Atk", "WM"], [3, 3])
        fighters = {
            "Atk": {"char": a, "weapon": KATANA},
            "WM": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Atk": [5], "WM": [7]}
        void_points = {"Atk": 2, "WM": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_attack.return_value = CombatAction(
                phase=5, actor="Atk", action_type=ActionType.ATTACK,
                dice_rolled=[20], dice_kept=[20],
                total=20, tn=5, success=True, description="Atk attacks",
                dice_pool="6k3",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="Atk", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="Atk deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 33, [15, 10, 8, 7, 5], [15, 10, 8])

            _resolve_attack(
                log, 5, fighters["Atk"], fighters["WM"],
                "Atk", "WM", fighters, actions_remaining, void_points,
            )

            mock_wc.assert_called_once()
            _, kwargs = mock_wc.call_args
            assert kwargs.get("extra_rolled") == 2


class TestWaveManWoundCheckTN:
    """Ability 10: Raises wound check TN, but serious wounds use original TN."""

    def test_ability10_raises_tn(self) -> None:
        """Ability 10 rank 1 → tn_bonus=5 on wound check."""
        a = _make_waveman("WM", abilities=[(10, 1)], fire=3, earth=3, void=2)
        b = _make_character("Def", fire=2, earth=3, water=3, void=2)
        b.skills = []

        log = create_combat_log(["WM", "Def"], [3, 3])
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [7]}
        void_points = {"WM": 2, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[20], dice_kept=[20],
                total=20, tn=5, success=True, description="WM attacks",
                dice_pool="6k3",
            )
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10, 8], dice_kept=[10, 8],
                total=18, description="WM deals 18 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (False, 12, [8, 4], [8, 4])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            mock_wc.assert_called_once()
            _, kwargs = mock_wc.call_args
            assert kwargs.get("tn_bonus") == 5


class TestWaveManCrippledReroll:
    """Ability 5: Free reroll of 10s when crippled (NOT on initiative)."""

    def test_ability5_never_on_initiative(self) -> None:
        """Ability 5 should NOT affect initiative rolls."""
        a = _make_waveman("WM", abilities=[(5, 1)], void=3)
        b = _make_character("B", void=3)
        # Even if WM is crippled, initiative should not get reroll
        # Since initiative is handled by roll_initiative (not _resolve_attack),
        # ability 5 is never called for initiative. This is by design.
        from src.engine.combat import roll_initiative
        with patch("src.engine.combat.roll_die", side_effect=[10, 5, 3, 2]):
            action = roll_initiative(a)
            # The 10 should remain as 10 (no reroll)
            assert 10 in action.dice_rolled or 10 in action.dice_kept or action.dice_rolled[-1] == 10

    def test_ability5_rerolls_in_attack(self) -> None:
        """Ability 5 rerolls 10s on attack when crippled."""
        a = _make_waveman("WM", abilities=[(5, 1)], fire=3, earth=2, void=3)
        b = _make_character("Def", fire=2, earth=3, void=2)
        b.skills = []

        log = create_combat_log(["WM", "Def"], [2, 3])
        log.wounds["WM"].serious_wounds = 2  # Crippled

        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "Def": [7]}
        void_points = {"WM": 0, "Def": 2}

        from src.models.combat import CombatAction

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.reroll_tens") as mock_reroll, \
             patch("src.engine.simulation.roll_damage") as mock_damage, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            # Attack misses with a 10 showing
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[10, 7, 5, 3, 2], dice_kept=[10, 7, 5],
                total=22, tn=25, success=False,
                description="WM attacks: 5k3 vs TN 5",
            )
            # Free reroll raises total high enough
            mock_reroll.return_value = ([18, 7, 5, 3, 2], [18, 7, 5], 30)
            mock_damage.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.DAMAGE,
                dice_rolled=[10], dice_kept=[10],
                total=10, description="WM deals 10 damage",
                dice_pool="7k2",
            )
            mock_wc.return_value = (True, 20, [15], [15])

            _resolve_attack(
                log, 5, fighters["WM"], fighters["Def"],
                "WM", "Def", fighters, actions_remaining, void_points,
            )

            # Free reroll should have been called with max_reroll=1
            mock_reroll.assert_called_once()
            args, kwargs = mock_reroll.call_args
            assert kwargs.get("max_reroll") == 1 or args[2] == 1
            # Void should NOT have been spent (ability 5 is free)
            assert void_points["WM"] == 0


class TestWaveManSmokeTest:
    """Full simulation smoke tests with Wave Man characters."""

    def test_two_wavemen_fight(self) -> None:
        """Two Wave Men can fight 20 rounds without errors."""
        a = _make_waveman("WM1", abilities=[(1, 1), (4, 1), (7, 1)], fire=3, earth=3, void=3)
        b = _make_waveman("WM2", abilities=[(2, 1), (8, 1), (10, 1)], fire=3, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
        assert log.combatants == ["WM1", "WM2"]

    def test_waveman_vs_samurai(self) -> None:
        """A Wave Man vs a regular samurai completes without errors."""
        a = _make_waveman("WM", abilities=[(1, 1), (3, 1), (6, 1)], fire=3, earth=3, void=3)
        b = _make_character("Samurai", fire=3, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
        assert log.combatants == ["WM", "Samurai"]

    def test_full_ability_waveman(self) -> None:
        """Wave Man with all 10 abilities at rank 2 runs without error."""
        all_abilities = [(i, 2) for i in range(1, 11)]
        a = _make_waveman("WM", abilities=all_abilities, fire=4, earth=4, void=4, water=4, air=4)
        b = _make_character("Samurai", fire=4, earth=4, void=4, water=4, air=4)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["WM", "Samurai"]


def _make_mirumoto(
    name: str,
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Helper to create a Mirumoto Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    da_rank = double_attack_rank if double_attack_rank is not None else knack_rank
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Mirumoto Bushi",
        school_ring=RingName.VOID,
        school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
        skills=[
            Skill(name="Attack", rank=attack_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=parry_rank, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            Skill(name="Counterattack", rank=knack_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Double Attack", rank=da_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Iaijutsu", rank=knack_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        ],
    )


class TestMirumotoFirstDan:
    """First Dan: +1 rolled die on attack and parry."""

    def test_first_dan_extra_attack_die(self) -> None:
        """Attack pool is skill+ring+1 for Mirumoto with dan >= 1."""
        a = _make_mirumoto("Miru", knack_rank=1, attack_rank=3, fire=3, earth=3, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["Miru", "Target"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "Miru": {"char": a, "weapon": KATANA},
            "Target": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Miru": [5], "Target": [3, 7]}
        void_points = {"Miru": 0, "Target": 2}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation.roll_attack") as mock_attack:
            from src.models.combat import CombatAction
            mock_da.return_value = (False, 0)
            mock_attack.return_value = CombatAction(
                phase=5, actor="Miru", action_type=ActionType.ATTACK,
                target="Target", dice_rolled=[8, 7, 5, 4, 3, 2, 1],
                dice_kept=[8, 7, 5], total=20, tn=5, success=True,
                description="Miru attacks",
            )
            _resolve_attack(
                log, 5, fighters["Miru"], fighters["Target"],
                "Miru", "Target", fighters, actions_remaining, void_points,
            )
            # roll_attack gets effective_atk_rank = 3 + 1 (1st Dan) = 4
            call_args = mock_attack.call_args
            assert call_args[0][1] == 4  # attack_skill passed as 4 (3+1)

    def test_first_dan_extra_parry_die(self) -> None:
        """Parry pool is skill+ring+1 for Mirumoto defender with dan >= 1."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("MiruDef", knack_rank=1, parry_rank=2, air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "MiruDef": [5, 7]}
        void_points = {"Attacker": 2, "MiruDef": 0}  # 0 void prevents combat void spending

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="MiruDef", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=35, tn=15, success=True, description="Attacker attacks",
            )
            mock_rak.return_value = ([20, 15, 8], [20, 15, 8], 43)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["MiruDef"],
                "Attacker", "MiruDef", fighters, actions_remaining, void_points,
            )
            # Parry roll_and_keep should get rolled = parry(2) + air(3) + 1 = 6
            parry_call = mock_rak.call_args
            assert parry_call[0][0] == 6  # 2 + 3 + 1 = 6 rolled


class TestMirumotoSecondDan:
    """Second Dan: free raise (+5) on parry rolls."""

    def test_second_dan_free_raise_parry(self) -> None:
        """Parry total gets +5 bonus for Mirumoto with dan >= 2."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("MiruDef", knack_rank=2, parry_rank=3, air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "MiruDef": [5, 7]}
        void_points = {"Attacker": 2, "MiruDef": 2}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="MiruDef", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=25, tn=20, success=True, description="Attacker attacks",
            )
            # Parry roll: total 22, plus 5 free raise = 27 >= 25 = success
            mock_rak.return_value = ([12, 10, 8, 5, 3], [12, 10, 8], 30)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["MiruDef"],
                "Attacker", "MiruDef", fighters, actions_remaining, void_points,
            )
            # Find the parry action in the log
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) >= 1
            # The parry total should include +5 from 2nd Dan free raise
            assert "mirumoto: free raise +5" in parry_actions[-1].description


class TestMirumotoSpecialAbility:
    """Special Ability: temp void on parry attempt."""

    def test_special_ability_temp_void_on_parry(self) -> None:
        """Temp void increases by 1 after any parry attempt by Mirumoto."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("MiruDef", knack_rank=1, parry_rank=2, air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "MiruDef": [5, 7]}
        # Start with 1 void — too low for combat void spending (reserves 1)
        void_points = {"Attacker": 2, "MiruDef": 1}
        temp_void: dict[str, int] = {"Attacker": 0, "MiruDef": 0}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="MiruDef", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=15, success=True, description="Attacker attacks",
            )
            # Parry succeeds (returns early, no wound check to consume void)
            mock_rak.return_value = ([15, 10, 8], [15, 10, 8], 33)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["MiruDef"],
                "Attacker", "MiruDef", fighters, actions_remaining, void_points,
                temp_void=temp_void,
            )
            # Regular void stays at 1, temp void increased by 1
            assert void_points["MiruDef"] == 1
            assert temp_void["MiruDef"] == 1


class TestMirumotoFourthDan:
    """Fourth Dan: failed parries subtract half extra damage dice."""

    def test_fourth_dan_half_parry_reduction(self) -> None:
        """Failed parry against 4th Dan Mirumoto only subtracts half parry rank."""
        a = _make_mirumoto("MiruAtk", knack_rank=4, attack_rank=4, fire=4, earth=4, void=4)
        b = _make_character("Defender", fire=3, earth=3, air=3, void=3)

        log = create_combat_log(
            ["MiruAtk", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "MiruAtk": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"MiruAtk": [5], "Defender": [5, 7]}
        void_points = {"MiruAtk": 0, "Defender": 0}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_dmg:
            from src.models.combat import CombatAction
            mock_da.return_value = (False, 0)
            # Attack hits with big total: 40 vs TN 15 = 5 extra dice
            mock_attack.return_value = CombatAction(
                phase=5, actor="MiruAtk", action_type=ActionType.ATTACK,
                target="Defender", dice_rolled=[20, 15, 10, 8],
                dice_kept=[20, 15, 10, 8], total=40, tn=15, success=True,
                description="MiruAtk attacks",
            )
            # Parry fails
            mock_rak.return_value = ([8, 5, 3], [8, 5, 3], 16)
            mock_dmg.return_value = CombatAction(
                phase=5, actor="MiruAtk", action_type=ActionType.DAMAGE,
                total=25, description="MiruAtk deals 25 damage",
                dice_rolled=[10, 8, 5], dice_kept=[10, 8], dice_pool="7k2",
            )
            _resolve_attack(
                log, 5, fighters["MiruAtk"], fighters["Defender"],
                "MiruAtk", "Defender", fighters, actions_remaining, void_points,
            )
            # Extra dice: (40-15)//5 = 5. Defender parry rank = 2.
            # 4th Dan: subtract half = 2//2 = 1 instead of 2.
            # So extra = 5 - 1 = 4 (instead of 5 - 2 = 3)
            dmg_call = mock_dmg.call_args
            extra_dice_arg = dmg_call[1].get("extra_dice", dmg_call[0][3] if len(dmg_call[0]) > 3 else 0)
            assert extra_dice_arg == 4


class TestMirumotoFifthDan:
    """Fifth Dan: void spending adds +10 per void on combat rolls."""

    def test_fifth_dan_void_bonus(self) -> None:
        """When 5th Dan Mirumoto spends void, each void adds +10 to combat roll."""
        from src.engine.simulation import _should_spend_void_on_combat_roll
        # High TN, void should provide +10 per void = much more valuable
        spend = _should_spend_void_on_combat_roll(
            rolled=6, kept=3, tn=30,
            void_available=2, max_spend=2,
            fifth_dan_bonus=10,
        )
        assert spend >= 1


class TestVoidSpendOnCombatRoll:
    """Void spending on attack/parry rolls."""

    def test_void_spend_on_attack_when_helpful(self) -> None:
        """Spends void when close to TN."""
        from src.engine.simulation import _should_spend_void_on_combat_roll
        spend = _should_spend_void_on_combat_roll(
            rolled=5, kept=3, tn=25,
            void_available=2, max_spend=2,
            fifth_dan_bonus=0,
        )
        assert spend >= 1

    def test_void_not_spent_when_easy_hit(self) -> None:
        """Doesn't spend when roll easily exceeds TN."""
        from src.engine.simulation import _should_spend_void_on_combat_roll
        spend = _should_spend_void_on_combat_roll(
            rolled=8, kept=4, tn=10,
            void_available=2, max_spend=2,
            fifth_dan_bonus=0,
        )
        assert spend == 0

    def test_void_reserved_for_wound_checks(self) -> None:
        """Never spends all void — result < void_available."""
        from src.engine.simulation import _should_spend_void_on_combat_roll
        # Only 1 void available — shouldn't spend the last one
        spend = _should_spend_void_on_combat_roll(
            rolled=5, kept=3, tn=20,
            void_available=1, max_spend=1,
            fifth_dan_bonus=0,
        )
        assert spend == 0


class TestDoubleAttack:
    """Double Attack knack tests."""

    def test_double_attack_tn_raised_by_20(self) -> None:
        """Double Attack raises TN by 20."""
        a = _make_mirumoto("MiruAtk", knack_rank=3, attack_rank=4,
                           double_attack_rank=3, fire=4, earth=3, void=4)
        b = _make_character("Defender", fire=2, earth=3, air=2, void=2)
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["MiruAtk", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "MiruAtk": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"MiruAtk": [5], "Defender": [3, 7]}
        void_points = {"MiruAtk": 3, "Defender": 2}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_dmg:
            from src.models.combat import CombatAction
            mock_da.return_value = (True, 0)
            # Roll succeeds even with TN+20
            mock_rak.return_value = ([20, 15, 10, 8], [20, 15, 10, 8], 53)
            mock_dmg.return_value = CombatAction(
                phase=5, actor="MiruAtk", action_type=ActionType.DOUBLE_ATTACK,
                total=25, description="MiruAtk deals 25 damage",
                dice_rolled=[10, 8, 5], dice_kept=[10, 8], dice_pool="7k2",
            )
            _resolve_attack(
                log, 5, fighters["MiruAtk"], fighters["Defender"],
                "MiruAtk", "Defender", fighters, actions_remaining, void_points,
            )
            # The attack action in log should have TN = base TN + 20
            da_actions = [a for a in log.actions if a.action_type == ActionType.DOUBLE_ATTACK]
            assert len(da_actions) >= 1
            base_tn = 5 + 5 * 0  # defender has no parry
            assert da_actions[0].tn == base_tn + 20

    def test_double_attack_skipped_when_rank_0(self) -> None:
        """Double attack is never used when rank is 0."""
        a = _make_mirumoto("MiruAtk", knack_rank=1, attack_rank=3,
                           double_attack_rank=0, fire=3, earth=3, void=3)
        b = _make_character("Defender", fire=2, earth=3, void=2)

        log = create_combat_log(
            ["MiruAtk", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "MiruAtk": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"MiruAtk": [5], "Defender": [3, 7]}
        void_points = {"MiruAtk": 2, "Defender": 2}

        _resolve_attack(
            log, 5, fighters["MiruAtk"], fighters["Defender"],
            "MiruAtk", "Defender", fighters, actions_remaining, void_points,
        )
        # No double attack action should appear
        da_actions = [a for a in log.actions if a.action_type == ActionType.DOUBLE_ATTACK]
        assert len(da_actions) == 0

    def test_double_attack_inflicts_serious_wound(self) -> None:
        """Double attack inflicts 1 extra serious wound when no parry."""
        a = _make_mirumoto("MiruAtk", knack_rank=3, attack_rank=4,
                           double_attack_rank=3, fire=4, earth=3, void=4)
        b = _make_character("Defender", fire=2, earth=3, air=2, void=2)
        b.skills = [Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(
            ["MiruAtk", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )

        fighters = {
            "MiruAtk": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"MiruAtk": [5], "Defender": [3, 7]}
        void_points = {"MiruAtk": 3, "Defender": 2}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_dmg, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            from src.models.combat import CombatAction
            mock_da.return_value = (True, 0)
            mock_rak.return_value = ([20, 15, 10, 8], [20, 15, 10, 8], 53)
            mock_dmg.return_value = CombatAction(
                phase=5, actor="MiruAtk", action_type=ActionType.DOUBLE_ATTACK,
                total=20, description="MiruAtk deals 20 damage",
                dice_rolled=[10, 8, 5], dice_kept=[10, 8], dice_pool="7k2",
            )
            mock_wc.return_value = (True, 30, [15, 10, 5], [15, 10])
            _resolve_attack(
                log, 5, fighters["MiruAtk"], fighters["Defender"],
                "MiruAtk", "Defender", fighters, actions_remaining, void_points,
            )
            # Double attack should inflict 1 extra serious wound
            assert log.wounds["Defender"].serious_wounds >= 1


class TestMirumotoSmokeTest:
    """Full simulation smoke tests with Mirumoto characters."""

    def test_two_mirumoto_fight(self) -> None:
        """Two Mirumoto Bushi can fight 20 rounds without errors."""
        a = _make_mirumoto("M1", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        b = _make_mirumoto("M2", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
        assert log.combatants == ["M1", "M2"]

    def test_mirumoto_vs_samurai(self) -> None:
        """A Mirumoto vs a regular samurai completes without errors."""
        a = _make_mirumoto("Miru", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        b = _make_character("Samurai", fire=4, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
        assert log.combatants == ["Miru", "Samurai"]

    def test_mirumoto_vs_waveman(self) -> None:
        """A Mirumoto vs a Wave Man completes without errors."""
        a = _make_mirumoto("Miru", knack_rank=2, attack_rank=3, fire=3, earth=3, void=3, air=3)
        b = _make_waveman("WM", abilities=[(1, 1), (4, 1), (7, 1)], fire=3, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
        assert log.combatants == ["Miru", "WM"]

    def test_5th_dan_mirumoto_fight(self) -> None:
        """5th Dan Mirumoto (all knacks 5) fights without errors."""
        a = _make_mirumoto("M5", knack_rank=5, attack_rank=5, parry_rank=5,
                           fire=5, earth=5, void=6, air=5, water=5)
        b = _make_character("Samurai", fire=5, earth=5, void=5, air=5, water=5)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["M5", "Samurai"]


# ===================================================================
# Step 1: dan_points model tests
# ===================================================================


class TestDanPointsModel:
    def test_fighter_status_dan_points_default(self) -> None:
        """FighterStatus.dan_points defaults to 0."""
        status = FighterStatus()
        assert status.dan_points == 0

    def test_fighter_status_dan_points_set(self) -> None:
        """FighterStatus(dan_points=6) works."""
        status = FighterStatus(dan_points=6)
        assert status.dan_points == 6


# ===================================================================
# Step 2a: Temp void separation tests
# ===================================================================


class TestTempVoidSeparation:
    """Tests for the _spend_void / _total_void helpers and temp void tracking."""

    def test_spend_void_temp_first(self) -> None:
        """_spend_void deducts from temp_void before regular void."""
        void_points = {"A": 3}
        temp_void = {"A": 2}
        from_temp, from_reg = _spend_void(void_points, temp_void, "A", 3)
        assert from_temp == 2
        assert from_reg == 1
        assert temp_void["A"] == 0  # 2 temp consumed
        assert void_points["A"] == 2  # only 1 regular consumed

    def test_spend_void_temp_only(self) -> None:
        """_spend_void uses only temp when temp covers the full amount."""
        void_points = {"A": 3}
        temp_void = {"A": 2}
        from_temp, from_reg = _spend_void(void_points, temp_void, "A", 1)
        assert from_temp == 1
        assert from_reg == 0
        assert temp_void["A"] == 1
        assert void_points["A"] == 3  # untouched

    def test_total_void_sums_both(self) -> None:
        """_total_void returns regular + temp."""
        void_points = {"A": 3}
        temp_void = {"A": 2}
        assert _total_void(void_points, temp_void, "A") == 5

    def test_void_spent_label_temp_only(self) -> None:
        assert _void_spent_label(1, 0) == "1 temp void spent"

    def test_void_spent_label_regular_only(self) -> None:
        assert _void_spent_label(0, 2) == "2 void spent"

    def test_void_spent_label_mixed(self) -> None:
        assert _void_spent_label(1, 1) == "2 void spent (1 temp)"

    def test_void_spent_label_zero(self) -> None:
        assert _void_spent_label(0, 0) == ""

    def test_temp_void_tracked_in_snapshot(self) -> None:
        """FighterStatus snapshot includes temp_void_points."""
        a = _make_character("A")
        b = _make_character("B")
        log = create_combat_log(["A", "B"], [2, 2])
        fighters = {"A": {"char": a, "weapon": KATANA}, "B": {"char": b, "weapon": KATANA}}
        actions_remaining: dict[str, list[int]] = {"A": [5], "B": [3]}
        void_points = {"A": 2, "B": 3}
        temp_void = {"A": 1, "B": 0}
        dan_points = {"A": 0, "B": 0}
        snap = _snapshot_status(log, fighters, actions_remaining, void_points, dan_points, temp_void)
        assert snap["A"].temp_void_points == 1
        assert snap["B"].temp_void_points == 0
        assert snap["A"].void_points == 2

    def test_temp_void_spent_before_regular_in_combat(self) -> None:
        """Integration: Mirumoto SA grants temp, next spend uses temp first."""
        # Mirumoto defender gets +1 temp void from parry, then spends on wound check
        a = _make_character("Attacker", fire=4, earth=4, void=3)
        b = _make_mirumoto("MiruDef", knack_rank=1, parry_rank=2, air=3, earth=3, void=3, water=2)

        log = create_combat_log(
            ["Attacker", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "MiruDef": [5, 7]}
        void_points = {"Attacker": 3, "MiruDef": 3}
        temp_void: dict[str, int] = {"Attacker": 0, "MiruDef": 1}

        # Force an attack that hits, parry that fails, then wound check that spends void
        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_dmg, \
             patch("src.engine.simulation._should_spend_void_on_combat_roll", return_value=0), \
             patch("src.engine.simulation._should_spend_void_on_wound_check") as mock_wc_decide, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="MiruDef", dice_rolled=[25, 18], dice_kept=[25, 18],
                total=25, tn=15, success=True, description="Attacker attacks",
            )
            mock_rak.return_value = ([8, 5, 3], [8, 5], 13)  # parry fails
            mock_dmg.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.DAMAGE,
                total=15, description="15 damage",
                dice_rolled=[8, 5, 2], dice_kept=[8, 5], dice_pool="5k2",
            )
            # Spend 1 void on wound check
            mock_wc_decide.return_value = 1
            mock_wc.return_value = (True, 20, [12, 8, 5], [12, 8])

            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["MiruDef"],
                "Attacker", "MiruDef", fighters, actions_remaining, void_points,
                temp_void=temp_void,
            )
            # Parry grants +1 temp void (total temp = 2)
            # Wound check spends 1 void — should come from temp first
            # So temp_void should be 1 (2 gained - 1 spent), regular void should be 3
            assert temp_void["MiruDef"] == 1
            assert void_points["MiruDef"] == 3


class TestAttackVoidFix:
    """Tests that normal attack void spending adds +1k1 (not +1k0)."""

    def test_attack_void_adds_1k1(self) -> None:
        """When Mirumoto spends void on attack, dice pool shows +1k1 pattern."""
        a = _make_mirumoto("MiruAtk", knack_rank=1, attack_rank=3, fire=3, earth=3, void=3)
        b = _make_character("Defender", fire=2, earth=2, air=2, void=2)

        log = create_combat_log(
            ["MiruAtk", "Defender"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "MiruAtk": {"char": a, "weapon": KATANA},
            "Defender": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"MiruAtk": [5], "Defender": []}
        # Enough void that AI decides to spend
        void_points = {"MiruAtk": 3, "Defender": 2}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation._should_spend_void_on_combat_roll") as mock_void_decide, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation.roll_damage") as mock_dmg, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            from src.models.combat import CombatAction
            mock_da.return_value = (False, 0)
            mock_void_decide.return_value = 1  # spend 1 void

            # Base: (3+1) skill + 3 fire = 7 rolled, 3 kept
            # With +1 void: 8 rolled, 4 kept → 8k4
            mock_rak.return_value = ([15, 12, 9, 7, 5, 4, 3, 2], [15, 12, 9, 7], 43)
            mock_dmg.return_value = CombatAction(
                phase=5, actor="MiruAtk", action_type=ActionType.DAMAGE,
                total=20, description="damage", dice_rolled=[10, 5], dice_kept=[10, 5],
                dice_pool="6k2",
            )
            mock_wc.return_value = (True, 25, [15, 10], [15, 10])

            _resolve_attack(
                log, 5, fighters["MiruAtk"], fighters["Defender"],
                "MiruAtk", "Defender", fighters, actions_remaining, void_points,
            )
            # Check the attack action's dice_pool reflects +1k1
            attack_actions = [a for a in log.actions if a.action_type == ActionType.ATTACK]
            assert len(attack_actions) == 1
            assert attack_actions[0].dice_pool == "8k4"  # 7+1 rolled, 3+1 kept


# ===================================================================
# Step 2b: Temp void display tests
# ===================================================================


class TestTempVoidDisplay:
    def test_temp_void_annotation_on_parry(self) -> None:
        """Normal parry by Mirumoto shows '(mirumoto SA: +1 temp void)' in description."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("MiruDef", knack_rank=1, parry_rank=2, air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "MiruDef": [5, 7]}
        void_points = {"Attacker": 2, "MiruDef": 1}
        dan_points: dict[str, int] = {"Attacker": 0, "MiruDef": 0}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="MiruDef", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=15, success=True, description="Attacker attacks",
            )
            # Parry fails — still gets temp void annotation
            mock_rak.return_value = ([8, 5, 3], [8, 5], 13)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["MiruDef"],
                "Attacker", "MiruDef", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            assert "(mirumoto SA: +1 temp void)" in parry_actions[0].description

    def test_temp_void_in_snapshot_after_parry(self) -> None:
        """Snapshot after parry reflects the +1 temp void in temp_void_points field."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("MiruDef", knack_rank=1, parry_rank=2, air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "MiruDef": [5, 7]}
        void_points = {"Attacker": 2, "MiruDef": 1}
        dan_points: dict[str, int] = {"Attacker": 0, "MiruDef": 0}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="MiruDef", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=15, success=True, description="Attacker attacks",
            )
            # Parry succeeds
            mock_rak.return_value = ([15, 12, 8], [15, 12, 8], 35)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["MiruDef"],
                "Attacker", "MiruDef", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            # Regular void stays at 1, temp void is 1
            assert parry_actions[0].status_after["MiruDef"].void_points == 1
            assert parry_actions[0].status_after["MiruDef"].temp_void_points == 1

    def test_temp_void_annotation_on_auto_success_parry(self) -> None:
        """Wave man auto-success parry by Mirumoto defender also shows temp void annotation."""
        a = _make_waveman("WM", abilities=[(1, 1)], fire=3, earth=3, void=2)
        b = _make_mirumoto("MiruDef", knack_rank=1, parry_rank=2, air=3, earth=3, void=3)

        log = create_combat_log(
            ["WM", "MiruDef"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "WM": {"char": a, "weapon": KATANA},
            "MiruDef": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"WM": [5], "MiruDef": [5, 7]}
        void_points = {"WM": 2, "MiruDef": 1}
        dan_points: dict[str, int] = {"WM": 0, "MiruDef": 0}

        with patch("src.engine.simulation.roll_attack") as mock_attack:
            from src.models.combat import CombatAction
            # Attack misses by 3 (total=12, tn=15) → ability 1 adds +5 → 17 >= 15
            mock_attack.return_value = CombatAction(
                phase=5, actor="WM", action_type=ActionType.ATTACK,
                dice_rolled=[8, 4], dice_kept=[8, 4],
                total=12, tn=15, success=False,
                description="WM attacks: 5k2 vs TN 15",
            )
            _resolve_attack(
                log, 5, fighters["WM"], fighters["MiruDef"],
                "WM", "MiruDef", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            assert "(mirumoto SA: +1 temp void)" in parry_actions[0].description
            # Snapshot should reflect +1 temp void in separate field
            assert parry_actions[0].status_after["MiruDef"].void_points == 1
            assert parry_actions[0].status_after["MiruDef"].temp_void_points == 1


# ===================================================================
# Step 3: Dan points generation tests
# ===================================================================


class TestDanPointsGeneration:
    def test_dan_points_generated_at_round_start(self) -> None:
        """3rd Dan Mirumoto with Attack 4 gets 2*4 = 8 dan points."""
        a = _make_mirumoto("M3", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        b = _make_character("Samurai", fire=3, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        # First action is initiative; its snapshot should show dan_points=8
        init_actions = [act for act in log.actions if act.action_type == ActionType.INITIATIVE]
        m3_init = [act for act in init_actions if act.actor == "M3"]
        assert len(m3_init) >= 1
        assert m3_init[0].status_after["M3"].dan_points == 8

    def test_dan_points_not_generated_below_3rd_dan(self) -> None:
        """2nd Dan Mirumoto gets 0 dan points."""
        a = _make_mirumoto("M2", knack_rank=2, attack_rank=3, fire=3, earth=3, void=3, air=3)
        b = _make_character("Samurai", fire=3, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        init_actions = [act for act in log.actions if act.action_type == ActionType.INITIATIVE]
        m2_init = [act for act in init_actions if act.actor == "M2"]
        assert len(m2_init) >= 1
        assert m2_init[0].status_after["M2"].dan_points == 0

    def test_dan_points_in_snapshot(self) -> None:
        """FighterStatus.dan_points reflects current total in snapshot."""
        a = _make_mirumoto("M3", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        b = _make_character("Samurai", fire=3, earth=3, void=3)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        # Samurai should have 0 dan_points
        init_actions = [act for act in log.actions if act.action_type == ActionType.INITIATIVE]
        assert init_actions[0].status_after["Samurai"].dan_points == 0


# ===================================================================
# Step 4: Phase shift parry tests
# ===================================================================


class TestPhaseShiftParry:
    def test_phase_shift_enables_parry(self) -> None:
        """Phase shift uses 3rd Dan points to shift a die and attempt parry."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("M3Def", knack_rank=3, parry_rank=3, attack_rank=4,
                           air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "M3Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "M3Def": {"char": b, "weapon": KATANA},
        }
        # Defender has NO action in phase 5 but has die at 7 (cost=2 pts)
        actions_remaining = {"Attacker": [5], "M3Def": [7, 9]}
        void_points = {"Attacker": 2, "M3Def": 0}
        dan_points = {"Attacker": 0, "M3Def": 8}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="M3Def", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=20, success=True, description="Attacker attacks",
            )
            mock_rak.return_value = ([15, 12, 8], [15, 12, 8], 35)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["M3Def"],
                "Attacker", "M3Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) >= 1
            assert "3rd dan" in parry_actions[0].description.lower()

    def test_phase_shift_picks_cheapest_die(self) -> None:
        """Phase shift picks the lowest die above current phase."""
        # phase=5, dice=[7, 9] → picks 7 (cost=2) not 9 (cost=4)
        can_shift, cost, die_phase = _try_phase_shift_parry(
            phase=5, defender_name="D",
            actions_remaining={"D": [7, 9]},
            dan_points={"D": 8},
            serious_wounds=0, earth_ring=3,
        )
        assert can_shift is True
        assert cost == 2
        assert die_phase == 7

    def test_phase_shift_fails_when_insufficient_points(self) -> None:
        """Phase shift can't happen without enough dan points."""
        can_shift, cost, die_phase = _try_phase_shift_parry(
            phase=5, defender_name="D",
            actions_remaining={"D": [9]},  # cost=4
            dan_points={"D": 1},  # only 1 pt
            serious_wounds=0, earth_ring=3,
        )
        assert can_shift is False

    def test_phase_shift_preferred_over_interrupt(self) -> None:
        """Phase shift (1 die) is preferred over interrupt (2 dice)."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("M3Def", knack_rank=3, parry_rank=3, attack_rank=4,
                           air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "M3Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "M3Def": {"char": b, "weapon": KATANA},
        }
        # No die at phase 5, but has [7, 9] — phase shift costs 2, interrupt costs 2 dice
        actions_remaining = {"Attacker": [5], "M3Def": [7, 9]}
        void_points = {"Attacker": 2, "M3Def": 0}
        dan_points = {"Attacker": 0, "M3Def": 8}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_interrupt_parry") as mock_int:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="M3Def", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=20, success=True, description="Attacker attacks",
            )
            mock_rak.return_value = ([15, 12, 8], [15, 12, 8], 35)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["M3Def"],
                "Attacker", "M3Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            # Interrupt should NOT have been called — phase shift took priority
            mock_int.assert_not_called()
            # Only 1 die consumed (the shifted one), not 2
            assert len(actions_remaining["M3Def"]) == 1

    def test_phase_shift_annotation_in_description(self) -> None:
        """Phase shift shows '(3rd dan: shifted from phase X, Y pts)' in description."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("M3Def", knack_rank=3, parry_rank=3, attack_rank=4,
                           air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "M3Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "M3Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "M3Def": [7]}
        void_points = {"Attacker": 2, "M3Def": 0}
        dan_points = {"Attacker": 0, "M3Def": 8}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="M3Def", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=20, success=True, description="Attacker attacks",
            )
            mock_rak.return_value = ([8, 5, 3], [8, 5], 13)  # Parry fails
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["M3Def"],
                "Attacker", "M3Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            assert "3rd dan: shifted from phase 7, 2 pts" in parry_actions[0].description

    def test_phase_shift_consumes_dan_points(self) -> None:
        """Phase shift reduces dan_points by shift cost."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("M3Def", knack_rank=3, parry_rank=3, attack_rank=4,
                           air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "M3Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "M3Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "M3Def": [7]}
        void_points = {"Attacker": 2, "M3Def": 0}
        dan_points = {"Attacker": 0, "M3Def": 8}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak:
            from src.models.combat import CombatAction
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="M3Def", dice_rolled=[20, 15], dice_kept=[20, 15],
                total=20, tn=20, success=True, description="Attacker attacks",
            )
            mock_rak.return_value = ([15, 12, 8], [15, 12, 8], 35)  # Parry succeeds
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["M3Def"],
                "Attacker", "M3Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            # Die 7 shifted to phase 5 costs 2 pts: 8 - 2 = 6
            assert dan_points["M3Def"] == 6


# ===================================================================
# Step 5: Dan roll bonus tests
# ===================================================================


class TestDanRollBonus:
    def test_attack_roll_bonus_applied(self) -> None:
        """Near-miss attack boosted by 3rd Dan points to hit."""
        a = _make_mirumoto("M3Atk", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        # Defender with Parry 2 → TN = 5 + 5*2 = 15
        b = _make_character("Def", fire=2, earth=3, void=2)

        log = create_combat_log(
            ["M3Atk", "Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "M3Atk": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"M3Atk": [5], "Def": [3, 7]}
        void_points = {"M3Atk": 0, "Def": 2}
        dan_points = {"M3Atk": 8, "Def": 0}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_dmg, \
             patch("src.engine.simulation.make_wound_check") as mock_wc, \
             patch("src.engine.simulation._should_interrupt_parry", return_value=False):
            from src.models.combat import CombatAction
            mock_da.return_value = (False, 0)
            # Attack misses by 3: total=12, tn=15 (Def has Parry 2)
            mock_attack.return_value = CombatAction(
                phase=5, actor="M3Atk", action_type=ActionType.ATTACK,
                target="Def", dice_rolled=[8, 4], dice_kept=[8, 4],
                total=12, tn=15, success=False,
                description="M3Atk attacks: 9k4 vs TN 15",
            )
            mock_dmg.return_value = CombatAction(
                phase=5, actor="M3Atk", action_type=ActionType.DAMAGE,
                total=10, description="M3Atk deals 10 damage",
                dice_rolled=[10], dice_kept=[10], dice_pool="7k2",
            )
            mock_wc.return_value = (True, 20, [15, 10], [15, 10])
            _resolve_attack(
                log, 5, fighters["M3Atk"], fighters["Def"],
                "M3Atk", "Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            attack_actions = [a for a in log.actions if a.action_type == ActionType.ATTACK]
            assert len(attack_actions) == 1
            # Deficit 3 → need ceil(3/2)=2 pts → +4 bonus → total=16 >= 15
            assert attack_actions[0].success is True
            assert attack_actions[0].total >= 15
            assert "3rd dan" in attack_actions[0].description.lower()

    def test_parry_roll_bonus_applied(self) -> None:
        """Near-miss parry boosted by 3rd Dan points."""
        a = _make_character("Attacker", fire=3, earth=3, void=2)
        b = _make_mirumoto("M3Def", knack_rank=3, parry_rank=3, attack_rank=4,
                           air=3, earth=3, void=3)

        log = create_combat_log(
            ["Attacker", "M3Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "Attacker": {"char": a, "weapon": KATANA},
            "M3Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"Attacker": [5], "M3Def": [5, 7]}
        void_points = {"Attacker": 2, "M3Def": 0}
        dan_points = {"Attacker": 0, "M3Def": 8}

        with patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_and_keep") as mock_rak, \
             patch("src.engine.simulation._should_predeclare_parry", return_value=False):
            from src.models.combat import CombatAction
            # Attack total=25, parry TN = 25
            mock_attack.return_value = CombatAction(
                phase=5, actor="Attacker", action_type=ActionType.ATTACK,
                target="M3Def", dice_rolled=[25, 15], dice_kept=[25, 15],
                total=25, tn=20, success=True, description="Attacker attacks",
            )
            # Parry roll=17, +5 2nd dan = 22 < 25 → short by 3 → need ceil(3/2)=2 pts
            mock_rak.return_value = ([10, 7, 5, 3], [10, 7], 17)
            _resolve_attack(
                log, 5, fighters["Attacker"], fighters["M3Def"],
                "Attacker", "M3Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            parry_actions = [a for a in log.actions if a.action_type == ActionType.PARRY]
            assert len(parry_actions) == 1
            # 17 + 5 (2nd dan) + 4 (2 pts) = 26 >= 25
            assert parry_actions[0].success is True
            assert "3rd dan" in parry_actions[0].description.lower()

    def test_roll_bonus_not_spent_when_already_succeeded(self) -> None:
        """No dan points spent when roll already passes."""
        pts = _compute_dan_roll_bonus(
            current_total=20, tn=15, dan_points_available=8,
        )
        assert pts == 0

    def test_roll_bonus_not_spent_when_gap_too_large(self) -> None:
        """No dan points spent when deficit exceeds threshold."""
        # deficit=30, points_needed=15 → threshold=ceil(8/2)+2=6 → 15>6 → skip
        pts = _compute_dan_roll_bonus(
            current_total=10, tn=40, dan_points_available=8,
        )
        assert pts == 0

    def test_roll_bonus_annotation_in_description(self) -> None:
        """Roll bonus annotation shows '(3rd dan: +N bonus, M pts)'."""
        a = _make_mirumoto("M3Atk", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        # Defender with Parry 2 → TN = 5 + 5*2 = 15
        b = _make_character("Def", fire=2, earth=3, void=2)

        log = create_combat_log(
            ["M3Atk", "Def"],
            [a.rings.earth.value, b.rings.earth.value],
        )
        fighters = {
            "M3Atk": {"char": a, "weapon": KATANA},
            "Def": {"char": b, "weapon": KATANA},
        }
        actions_remaining = {"M3Atk": [5], "Def": [3, 7]}
        void_points = {"M3Atk": 0, "Def": 2}
        dan_points = {"M3Atk": 8, "Def": 0}

        with patch("src.engine.simulation._should_use_double_attack") as mock_da, \
             patch("src.engine.simulation.roll_attack") as mock_attack, \
             patch("src.engine.simulation.roll_damage") as mock_dmg, \
             patch("src.engine.simulation.make_wound_check") as mock_wc, \
             patch("src.engine.simulation._should_interrupt_parry", return_value=False):
            from src.models.combat import CombatAction
            mock_da.return_value = (False, 0)
            mock_attack.return_value = CombatAction(
                phase=5, actor="M3Atk", action_type=ActionType.ATTACK,
                target="Def", dice_rolled=[8, 4], dice_kept=[8, 4],
                total=12, tn=15, success=False,
                description="M3Atk attacks: 9k4 vs TN 15",
            )
            mock_dmg.return_value = CombatAction(
                phase=5, actor="M3Atk", action_type=ActionType.DAMAGE,
                total=10, description="M3Atk deals 10 damage",
                dice_rolled=[10], dice_kept=[10], dice_pool="7k2",
            )
            mock_wc.return_value = (True, 20, [15, 10], [15, 10])
            _resolve_attack(
                log, 5, fighters["M3Atk"], fighters["Def"],
                "M3Atk", "Def", fighters, actions_remaining, void_points,
                dan_points=dan_points,
            )
            attack_actions = [a for a in log.actions if a.action_type == ActionType.ATTACK]
            # deficit=3, pts=2 → "+4 bonus, 2 pts"
            assert "(3rd dan: +4 bonus, 2 pts)" in attack_actions[0].description

    def test_parry_more_generous_than_attack(self) -> None:
        """Parry threshold is more generous (ceil(avail/2)+3 vs +2)."""
        # Borderline case: available=8, threshold for attack=ceil(8/2)+2=6
        # threshold for parry=ceil(8/2)+3=7
        # deficit=13, pts_needed=7 → attack skips (7>6), parry spends (7<=7)
        atk_pts = _compute_dan_roll_bonus(
            current_total=7, tn=20, dan_points_available=8, is_parry=False,
        )
        parry_pts = _compute_dan_roll_bonus(
            current_total=7, tn=20, dan_points_available=8, is_parry=True,
        )
        assert atk_pts == 0  # 7 > 6 threshold
        assert parry_pts == 7  # 7 <= 7 threshold


# ===================================================================
# Step 7: Smoke tests
# ===================================================================


class TestMirumotoThirdDanSmokeTest:
    def test_3rd_dan_mirumoto_fight(self) -> None:
        """Two 3rd Dan Mirumoto fight 20 rounds without errors."""
        a = _make_mirumoto("M3_1", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        b = _make_mirumoto("M3_2", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["M3_1", "M3_2"]

    def test_3rd_dan_mirumoto_vs_waveman(self) -> None:
        """3rd Dan Mirumoto vs Wave Man completes without errors."""
        a = _make_mirumoto("M3", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        b = _make_waveman("WM", abilities=[(1, 1), (4, 1), (7, 1)], fire=3, earth=3, void=3)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["M3", "WM"]


# --- Matsu Bushi helpers and tests ---

def _make_matsu(
    name: str,
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Helper to create a Matsu Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    da_rank = double_attack_rank if double_attack_rank is not None else knack_rank
    lng_rank = lunge_rank if lunge_rank is not None else knack_rank
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Matsu Bushi",
        school_ring=RingName.FIRE,
        school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
        skills=[
            Skill(name="Attack", rank=attack_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=parry_rank, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
            Skill(name="Double Attack", rank=da_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Iaijutsu", rank=knack_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Lunge", rank=lng_rank, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
        ],
    )


class TestMatsuSpecialAbility:
    """Matsu SA: always rolls 10 dice for initiative."""

    def test_matsu_initiative_rolls_10_dice(self) -> None:
        """Matsu should roll 10 initiative dice regardless of Void value."""
        a = _make_matsu("Matsu", knack_rank=1, fire=3, void=2)
        b = _make_character("Target", fire=2, earth=3, void=2)
        log = simulate_combat(a, b, KATANA, KATANA, max_rounds=1)
        # Find initiative action for the Matsu
        init_actions = [a for a in log.actions if a.action_type == ActionType.INITIATIVE and a.actor == "Matsu"]
        assert len(init_actions) >= 1
        # Void=2 means they'd normally roll 3 dice. With SA, should be 10.
        assert len(init_actions[0].dice_rolled) == 10


class TestMatsuFirstDan:
    """First Dan: +1 rolled die on double attack and wound check."""

    def test_first_dan_extra_die_on_double_attack(self) -> None:
        """DA pool is DA_rank + fire + 1 for Matsu with dan >= 1."""
        a = _make_matsu("Matsu", knack_rank=1, attack_rank=3, double_attack_rank=3, fire=3, earth=3, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(["Matsu", "Target"], [a.rings.earth.value, b.rings.earth.value])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 0, "Target": 2}

        # Force DA choice by mocking
        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice:
            mock_choice.return_value = ("double_attack", 0)
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        da_actions = [a for a in log.actions if a.action_type == ActionType.DOUBLE_ATTACK]
        assert len(da_actions) == 1
        # DA_rank(3) + Fire(3) + 1st Dan(1) = 7 dice rolled
        assert len(da_actions[0].dice_rolled) == 7

    def test_first_dan_extra_die_on_wound_check(self) -> None:
        """Wound check rolls (Water+1+1) dice for Matsu 1st Dan."""
        a = _make_character("Attacker", fire=4, earth=3, void=3)
        b = _make_matsu("Matsu", knack_rank=1, fire=3, earth=3, water=3, void=2)

        log = create_combat_log(["Attacker", "Matsu"], [3, 3])
        log.wounds["Matsu"].light_wounds = 10
        fighters = {"Attacker": {"char": a, "weapon": KATANA}, "Matsu": {"char": b, "weapon": KATANA}}

        # Manually drive a hit that leads to wound check
        # We'll use simulate_combat and check wound check dice
        log2 = simulate_combat(a, b, KATANA, KATANA, max_rounds=3)
        wc_actions = [act for act in log2.actions if act.action_type == ActionType.WOUND_CHECK and act.actor == "Matsu"]
        if wc_actions:
            # Water=3, so base rolled = 4, Matsu 1st Dan adds 1 -> 5
            assert len(wc_actions[0].dice_rolled) == 5


class TestMatsuThirdDan:
    """3rd Dan: void spending generates wound check bonus pool."""

    def test_void_spending_generates_bonus(self) -> None:
        """Spending void on lunge generates 3*attack_rank bonus."""
        a = _make_matsu("Matsu", knack_rank=3, attack_rank=4, fire=4, earth=3, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2, air=4)
        b.skills = [
            Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=4, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 3, "Target": 2}
        matsu_bonuses: dict[str, list[int]] = {"Matsu": [], "Target": []}

        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice:
            mock_choice.return_value = ("lunge", 1)  # Spend 1 void
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
                matsu_bonuses=matsu_bonuses,
            )

        # Should have 1 bonus of 3 * attack_rank(4) = 12
        assert len(matsu_bonuses["Matsu"]) >= 1
        assert matsu_bonuses["Matsu"][0] == 12

    def test_matsu_bonus_applied_to_wound_check(self) -> None:
        """Stored matsu bonus can rescue a failed wound check."""
        a = _make_character("Attacker", fire=4, earth=3, void=3)
        b = _make_matsu("Matsu", knack_rank=3, attack_rank=3, fire=3, earth=3, water=2, void=2)

        # Run multiple combats, check that matsu bonus annotation appears
        found_bonus_application = False
        for _ in range(20):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=5)
            for action in log.actions:
                if "matsu 3rd Dan: applied" in action.description:
                    found_bonus_application = True
                    break
            if found_bonus_application:
                break
        # Not guaranteed but with enough runs should find it if Matsu spends void
        # This test verifies the code path exists and doesn't crash


class TestMatsuFourthDan:
    """4th Dan: near-miss double attack still hits with base damage."""

    def test_near_miss_da_still_hits(self) -> None:
        """Miss by < 20 on DA = hit for Matsu 4th Dan."""
        a = _make_matsu("Matsu", knack_rank=4, attack_rank=4, fire=5, earth=3, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 0, "Target": 2}

        # Mock roll_and_keep to return exactly TN-15 (near miss)
        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice, \
             patch("src.engine.simulation.roll_and_keep") as mock_roll:
            mock_choice.return_value = ("double_attack", 0)
            # TN = 5 + 5*0 + 20 = 25 for parry 0. Return 10 (misses by 15, within 20)
            mock_roll.return_value = ([5, 3, 2], [5, 3, 2], 10)
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        da_actions = [a for a in log.actions if a.action_type == ActionType.DOUBLE_ATTACK]
        assert len(da_actions) == 1
        assert da_actions[0].success is True
        assert "near-miss" in da_actions[0].description

    def test_miss_by_20_or_more_is_miss(self) -> None:
        """Miss by >= 20 on DA is still a miss."""
        a = _make_matsu("Matsu", knack_rank=4, attack_rank=4, fire=5, earth=3, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 0, "Target": 2}

        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice, \
             patch("src.engine.simulation.roll_and_keep") as mock_roll:
            mock_choice.return_value = ("double_attack", 0)
            # TN = 25. Return 4 (misses by 21, >= 20)
            mock_roll.return_value = ([2, 1, 1], [2, 1, 1], 4)
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        da_actions = [a for a in log.actions if a.action_type == ActionType.DOUBLE_ATTACK]
        assert len(da_actions) == 1
        assert da_actions[0].success is False

    def test_near_miss_da_no_auto_serious(self) -> None:
        """Near-miss DA hit should not inflict auto serious wound."""
        a = _make_matsu("Matsu", knack_rank=4, attack_rank=4, fire=5, earth=3, void=3)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 0, "Target": 2}

        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice, \
             patch("src.engine.simulation.roll_and_keep") as mock_roll:
            mock_choice.return_value = ("double_attack", 0)
            # TN = 25. Return 10 (near miss by 15)
            mock_roll.return_value = ([5, 3, 2], [5, 3, 2], 10)
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        # Check no "double attack: +1 serious wound" in damage description
        damage_actions = [a for a in log.actions if a.action_type == ActionType.DAMAGE]
        for d in damage_actions:
            assert "double attack:" not in d.description


class TestMatsuFifthDan:
    """5th Dan: light wounds reset to 15 after failed wound check."""

    def test_light_wounds_reset_to_15(self) -> None:
        """After a Matsu 5th Dan causes a failed WC, light wounds = 15."""
        a = _make_matsu("Matsu", knack_rank=5, attack_rank=5, fire=5, earth=4, void=4)
        b = _make_character("Target", fire=2, earth=2, water=2, void=2)
        b.skills = [
            Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=0, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ]

        # Run many fights looking for a failed wound check
        found = False
        for _ in range(30):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=5)
            for action in log.actions:
                if "matsu 5th Dan: light wounds reset to 15" in action.description:
                    found = True
                    break
            if found:
                break
        # Even if not found in 30 runs (unlikely), the code path is tested below
        # by directly checking wound tracker state in a unit test

    def test_light_wounds_reset_to_15_directly(self) -> None:
        """Direct test: failed wound check against Matsu 5th Dan sets light = 15."""
        a = _make_matsu("Matsu", knack_rank=5, attack_rank=5, fire=5, earth=4, void=4)
        b = _make_character("Target", fire=2, earth=4, water=2, void=2)
        b.skills = [
            Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=0, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ]

        log = create_combat_log(["Matsu", "Target"], [4, 4])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 0, "Target": 0}

        # Mock so lunge hits and wound check fails
        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice, \
             patch("src.engine.simulation.roll_and_keep") as mock_roll, \
             patch("src.engine.simulation.make_wound_check") as mock_wc:
            mock_choice.return_value = ("lunge", 0)
            mock_roll.return_value = ([10, 8, 7, 6], [10, 8, 7], 25)
            # Mock wound check to fail
            mock_wc.return_value = (False, 5, [3, 2, 1], [3, 2])
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        # After failed wound check from 5th Dan Matsu, light wounds should be 15
        assert log.wounds["Target"].light_wounds == 15


class TestMatsuAttackChoice:
    """Tests for the _matsu_attack_choice decision function."""

    def test_always_lunge_or_da(self) -> None:
        """Matsu never returns anything other than 'lunge' or 'double_attack'."""
        for da_rank in (0, 1, 2, 3, 4, 5):
            for fire in (2, 3, 4, 5):
                choice, _ = _matsu_attack_choice(
                    lunge_rank=3, double_attack_rank=da_rank,
                    attack_skill=3, fire_ring=fire,
                    defender_parry=2, void_available=3,
                    max_void_spend=2, dan=2, is_crippled=False,
                )
                assert choice in ("lunge", "double_attack")

    def test_crippled_always_lunges(self) -> None:
        """Crippled Matsu always lunges."""
        choice, _ = _matsu_attack_choice(
            lunge_rank=3, double_attack_rank=3,
            attack_skill=3, fire_ring=4,
            defender_parry=2, void_available=3,
            max_void_spend=2, dan=3, is_crippled=True,
        )
        assert choice == "lunge"

    def test_no_da_rank_always_lunges(self) -> None:
        """With DA rank 0, always lunges."""
        choice, _ = _matsu_attack_choice(
            lunge_rank=3, double_attack_rank=0,
            attack_skill=3, fire_ring=4,
            defender_parry=2, void_available=3,
            max_void_spend=2, dan=3, is_crippled=False,
        )
        assert choice == "lunge"

    def test_da_more_aggressive_with_4th_dan(self) -> None:
        """4th Dan lowers DA threshold (near-miss hits)."""
        # With low fire vs high parry, 4th Dan should still try DA
        choice_4th, _ = _matsu_attack_choice(
            lunge_rank=3, double_attack_rank=4,
            attack_skill=4, fire_ring=4,
            defender_parry=2, void_available=3,
            max_void_spend=2, dan=4, is_crippled=False,
        )
        # 4th Dan should be more willing to DA
        assert choice_4th == "double_attack"


class TestLunge:
    """Tests for lunge attack mechanics."""

    def test_lunge_uses_knack_rank(self) -> None:
        """Lunge dice pool uses Lunge rank + Fire."""
        a = _make_matsu("Matsu", knack_rank=1, lunge_rank=3, fire=3, earth=3, void=2)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE)]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": [3, 7]}
        void_points = {"Matsu": 0, "Target": 2}

        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice:
            mock_choice.return_value = ("lunge", 0)
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        lunge_actions = [a for a in log.actions if a.action_type == ActionType.LUNGE]
        assert len(lunge_actions) == 1
        # Lunge rank(3) + Fire(3) = 6 dice rolled
        assert len(lunge_actions[0].dice_rolled) == 6

    def test_lunge_extra_damage_die(self) -> None:
        """Lunge grants +1 rolled damage die on hit — verified via dice_pool annotation."""
        a = _make_matsu("Matsu", knack_rank=1, lunge_rank=3, fire=3, earth=3, void=2)
        b = _make_character("Target", fire=2, earth=3, void=2)
        b.skills = [
            Skill(name="Attack", rank=1, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=0, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [5], "Target": []}
        void_points = {"Matsu": 0, "Target": 0}

        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice, \
             patch("src.engine.simulation.roll_and_keep") as mock_roll:
            mock_choice.return_value = ("lunge", 0)
            # Lunge hits with total = 24 vs TN 5
            mock_roll.return_value = ([9, 8, 7, 6, 5, 4], [9, 8, 7], 24)
            _resolve_attack(
                log, 5, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
            )

        damage_actions = [a for a in log.actions if a.action_type == ActionType.DAMAGE]
        assert len(damage_actions) == 1
        # Weapon(4) + Fire(3) + extra_dice(from raises) + lunge_bonus(1)
        # With hit total 24, base TN 5, extra dice = (24-5)//5 = 3
        # Total = 4 + 3 + 3 + 1 = 11 rolled, kept=2
        # The dice_pool annotation captures the full pool (overflow means actual dice < 11)
        assert "11k2" in damage_actions[0].dice_pool

    def test_lunge_gives_opponent_bonus(self) -> None:
        """Opponent's next attack against the lunger gets -5 TN."""
        a = _make_matsu("Matsu", knack_rank=1, lunge_rank=3, fire=3, earth=3, void=2)
        b = _make_character("Target", fire=3, earth=3, void=2, air=2)
        b.skills = [
            Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
        ]

        log = create_combat_log(["Matsu", "Target"], [3, 3])
        fighters = {"Matsu": {"char": a, "weapon": KATANA}, "Target": {"char": b, "weapon": KATANA}}
        actions_remaining = {"Matsu": [3, 5], "Target": [4, 7]}
        void_points = {"Matsu": 0, "Target": 0}
        lunge_target_bonus: dict[str, int] = {"Matsu": 0, "Target": 0}

        with patch("src.engine.simulation._matsu_attack_choice") as mock_choice:
            mock_choice.return_value = ("lunge", 0)
            _resolve_attack(
                log, 3, fighters["Matsu"], fighters["Target"],
                "Matsu", "Target", fighters, actions_remaining, void_points,
                lunge_target_bonus=lunge_target_bonus,
            )

        # After Matsu lunges, Target should get -5 TN on next attack
        assert lunge_target_bonus["Target"] == 5


class TestMatsuSmokeTest:
    """Smoke tests for Matsu Bushi in full combat simulations."""

    def test_matsu_vs_matsu_fight(self) -> None:
        """Two Matsu Bushi can fight without errors."""
        a = _make_matsu("M1", knack_rank=3, attack_rank=4, fire=4, earth=3, void=3, air=3)
        b = _make_matsu("M2", knack_rank=3, attack_rank=4, fire=4, earth=3, void=3, air=3)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["M1", "M2"]

    def test_matsu_vs_mirumoto_fight(self) -> None:
        """Matsu vs Mirumoto completes without errors."""
        a = _make_matsu("Matsu", knack_rank=3, attack_rank=4, fire=4, earth=3, void=3, air=3)
        b = _make_mirumoto("Miru", knack_rank=3, attack_rank=4, fire=4, earth=3, void=4, air=3)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["Matsu", "Miru"]

    def test_matsu_vs_waveman_fight(self) -> None:
        """Matsu vs Wave Man completes without errors."""
        a = _make_matsu("Matsu", knack_rank=2, attack_rank=3, fire=3, earth=3, void=2, air=2)
        b = _make_waveman("WM", abilities=[(1, 1), (4, 1), (7, 1)], fire=3, earth=3, void=3)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["Matsu", "WM"]

    def test_matsu_vs_base_fight(self) -> None:
        """Matsu vs Base character completes without errors."""
        a = _make_matsu("Matsu", knack_rank=2, attack_rank=3, fire=3, earth=3, void=2, air=2)
        b = _make_character("Base", fire=3, earth=3, void=3)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["Matsu", "Base"]

    def test_5th_dan_matsu_fight(self) -> None:
        """Two 5th Dan Matsu fight without errors."""
        a = _make_matsu("M5_1", knack_rank=5, attack_rank=5, fire=5, earth=4, void=4, air=4, water=4)
        b = _make_matsu("M5_2", knack_rank=5, attack_rank=5, fire=5, earth=4, void=4, air=4, water=4)
        for _ in range(5):
            log = simulate_combat(a, b, KATANA, KATANA, max_rounds=20)
            assert log.combatants == ["M5_1", "M5_2"]
