"""Tests for the combat engine."""

from unittest.mock import patch

from src.engine.combat import (
    calculate_attack_tn,
    create_combat_log,
    make_wound_check,
    roll_attack,
    roll_damage,
    roll_initiative,
)
from src.models.character import Character, Ring, RingName, Rings, Skill
from src.models.combat import ActionType, WoundTracker


def _make_character(name: str, **ring_overrides: int) -> Character:
    """Helper to create a character with specific ring values."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(name=RingName(ring_name.capitalize()), value=val)
    return Character(name=name, rings=Rings(**kwargs))


class TestInitiative:
    def test_initiative_uses_void_ring(self) -> None:
        c = _make_character("Akodo", void=3)
        # Void 3 → roll 4 dice, drop highest, keep 3
        with patch("src.engine.combat.roll_die", side_effect=[5, 3, 8, 2]):
            action = roll_initiative(c)
            assert action.action_type == ActionType.INITIATIVE
            assert action.actor == "Akodo"
            # Sorted ascending: [2, 3, 5, 8], drop 8, keep [2, 3, 5]
            assert action.dice_kept == [2, 3, 5]
            # Total is not meaningful for initiative (dice are action phases)
            assert action.total == 0

    def test_initiative_description_shows_phases(self) -> None:
        c = _make_character("Akodo", void=3)
        with patch("src.engine.combat.roll_die", side_effect=[5, 3, 8, 2]):
            action = roll_initiative(c)
            # Description should mention the phases, not a summed total
            assert "phases 2, 3, 5" in action.description

    def test_initiative_drops_highest(self) -> None:
        c = _make_character("Bayushi", void=2)
        # Void 2 → roll 3 dice, drop highest, keep 2
        with patch("src.engine.combat.roll_die", side_effect=[7, 4, 9]):
            action = roll_initiative(c)
            # Sorted ascending: [4, 7, 9], drop 9, keep [4, 7]
            assert action.dice_kept == [4, 7]
            assert action.total == 0

    def test_initiative_no_explode(self) -> None:
        c = _make_character("Matsu", void=2)
        with patch("src.engine.combat.roll_die") as mock_rd:
            mock_rd.side_effect = [10, 5, 3]
            roll_initiative(c)
            # All calls should pass explode=False
            for call in mock_rd.call_args_list:
                assert call == ((False,),) or call == ((), {"explode": False})


class TestAttackTN:
    def test_parry_0(self) -> None:
        assert calculate_attack_tn(0) == 5

    def test_parry_3(self) -> None:
        assert calculate_attack_tn(3) == 20

    def test_parry_5(self) -> None:
        assert calculate_attack_tn(5) == 30


class TestAttack:
    def test_attack_success(self) -> None:
        c = _make_character("Kakita", fire=3)
        c.skills = [Skill(name="Kenjutsu", rank=4, ring=RingName.FIRE)]
        mock_rv = ([9, 8, 7, 6, 5, 4, 3], [9, 8, 7], 24)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv):
            action = roll_attack(c, attack_skill=4, attack_ring=RingName.FIRE, tn=15)
            assert action.success is True
            assert action.total == 24

    def test_attack_failure(self) -> None:
        c = _make_character("Hida", fire=2)
        with patch("src.engine.combat.roll_and_keep", return_value=([3, 2], [3, 2], 5)):
            action = roll_attack(c, attack_skill=1, attack_ring=RingName.FIRE, tn=15)
            assert action.success is False


class TestAttackDicePool:
    def test_attack_dice_pool_set(self) -> None:
        """roll_attack sets dice_pool to 'rolled k kept'."""
        c = _make_character("Kakita", fire=3)
        c.skills = [Skill(name="Kenjutsu", rank=4, ring=RingName.FIRE)]
        mock_rv = ([9, 8, 7, 6, 5, 4, 3], [9, 8, 7], 24)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv):
            action = roll_attack(c, attack_skill=4, attack_ring=RingName.FIRE, tn=15)
            # 4 (skill) + 3 (fire) = 7 rolled, 3 kept
            assert action.dice_pool == "7k3"


class TestAttackExplode:
    def test_attack_passes_explode_true_by_default(self) -> None:
        """roll_attack defaults to explode=True."""
        c = _make_character("Kakita", fire=3)
        mock_rv = ([9, 8, 7, 6, 5], [9, 8, 7], 24)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv) as mock_rak:
            roll_attack(c, attack_skill=2, attack_ring=RingName.FIRE, tn=15)
            mock_rak.assert_called_once_with(5, 3, explode=True)

    def test_attack_passes_explode_false(self) -> None:
        """roll_attack can pass explode=False for crippled characters."""
        c = _make_character("Hida", fire=2)
        mock_rv = ([5, 3, 2], [5, 3], 8)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv) as mock_rak:
            roll_attack(c, attack_skill=1, attack_ring=RingName.FIRE, tn=15, explode=False)
            mock_rak.assert_called_once_with(3, 2, explode=False)


class TestDamage:
    def test_katana_damage(self) -> None:
        """Katana is 4k2, plus Fire ring added to rolled dice."""
        c = _make_character("Matsu", fire=3)
        mock_rv = ([10, 8, 7, 6, 5, 4, 3], [10, 8], 18)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv):
            action = roll_damage(c, weapon_rolled=4, weapon_kept=2)
            assert action.total == 18
            assert action.action_type == ActionType.DAMAGE

    def test_extra_damage_dice(self) -> None:
        c = _make_character("Matsu", fire=3)
        with patch("src.engine.combat.roll_and_keep") as mock_rak:
            mock_rak.return_value = ([9, 8, 7, 6, 5, 4, 3, 2], [9, 8], 17)
            roll_damage(c, weapon_rolled=4, weapon_kept=2, extra_dice=1)
            # 4 (weapon) + 3 (fire) + 1 (extra) = 8 rolled, 2 kept
            mock_rak.assert_called_once_with(8, 2, explode=True)


class TestDamageDicePool:
    def test_damage_dice_pool_set(self) -> None:
        """roll_damage sets dice_pool to 'rolled k kept'."""
        c = _make_character("Matsu", fire=3)
        mock_rv = ([10, 8, 7, 6, 5, 4, 3], [10, 8], 18)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv):
            action = roll_damage(c, weapon_rolled=4, weapon_kept=2)
            # 4 (weapon) + 3 (fire) = 7 rolled, 2 kept
            assert action.dice_pool == "7k2"

    def test_damage_dice_pool_with_extra(self) -> None:
        """roll_damage includes extra_dice in the pool string."""
        c = _make_character("Matsu", fire=3)
        mock_rv = ([9, 8, 7, 6, 5, 4, 3, 2], [9, 8], 17)
        with patch("src.engine.combat.roll_and_keep", return_value=mock_rv):
            action = roll_damage(c, weapon_rolled=4, weapon_kept=2, extra_dice=1)
            # 4 (weapon) + 3 (fire) + 1 (extra) = 8 rolled, 2 kept
            assert action.dice_pool == "8k2"


class TestWoundCheck:
    def test_wound_check_pass(self) -> None:
        wt = WoundTracker(light_wounds=10, earth_ring=3)
        with patch("src.engine.combat.roll_and_keep", return_value=([8, 7, 5], [8, 7], 15)):
            passed, total, all_dice, kept_dice = make_wound_check(wt, water_ring=2)
            assert passed is True
            assert wt.serious_wounds == 0
            assert all_dice == [8, 7, 5]
            assert kept_dice == [8, 7]

    def test_wound_check_fail_adds_serious(self) -> None:
        wt = WoundTracker(light_wounds=20, earth_ring=2)
        with patch("src.engine.combat.roll_and_keep", return_value=([5, 3, 2], [5, 3], 8)):
            passed, total, _, _ = make_wound_check(wt, water_ring=2)
            assert passed is False
            # Failed by 12: 1 base + 1 for the 10 = 2 serious wounds
            assert wt.serious_wounds == 2

    def test_wound_check_fail_by_exactly_10(self) -> None:
        wt = WoundTracker(light_wounds=20, earth_ring=2)
        with patch("src.engine.combat.roll_and_keep", return_value=([6, 4], [6, 4], 10)):
            passed, _, _, _ = make_wound_check(wt, water_ring=2)
            assert passed is False
            # Failed by 10: 1 base + 1 = 2 serious wounds
            assert wt.serious_wounds == 2


class TestWoundCheckVoid:
    def test_void_spend_adds_rolled_and_kept(self) -> None:
        """void_spend=1 adds +1k1: (water+1+1)k(water+1) = 4k3."""
        wt = WoundTracker(light_wounds=15, earth_ring=3)
        rv = ([9, 8, 7, 5], [9, 8, 7], 24)
        with patch("src.engine.combat.roll_and_keep", return_value=rv) as mock_rak:
            passed, total, _, _ = make_wound_check(
                wt, water_ring=2, void_spend=1,
            )
            # rolled = water+1+void = 4, kept = water+void = 3 → 4k3
            mock_rak.assert_called_once_with(4, 3, explode=True)
            assert passed is True

    def test_void_spend_default_zero_unchanged(self) -> None:
        """Default void_spend=0 keeps original behavior: (water+1)kwater."""
        wt = WoundTracker(light_wounds=10, earth_ring=3)
        rv = ([8, 7, 5], [8, 7], 15)
        with patch("src.engine.combat.roll_and_keep", return_value=rv) as mock_rak:
            make_wound_check(wt, water_ring=2)
            # rolled = 3, kept = 2 → 3k2 (unchanged)
            mock_rak.assert_called_once_with(3, 2, explode=True)

    def test_void_spend_multiple(self) -> None:
        """void_spend=3 adds +3k3: (water+1+3)k(water+3) = 6k5."""
        wt = WoundTracker(light_wounds=20, earth_ring=3)
        rv = ([9, 8, 7, 6, 5, 4], [9, 8, 7, 6, 5], 35)
        with patch("src.engine.combat.roll_and_keep", return_value=rv) as mock_rak:
            passed, total, _, _ = make_wound_check(wt, water_ring=2, void_spend=3)
            # rolled = water+1+void = 6, kept = water+void = 5 → 6k5
            mock_rak.assert_called_once_with(6, 5, explode=True)
            assert passed is True

    def test_void_spend_negative_raises(self) -> None:
        """void_spend < 0 raises ValueError."""
        wt = WoundTracker(light_wounds=10, earth_ring=3)
        import pytest
        with pytest.raises(ValueError, match="void_spend"):
            make_wound_check(wt, water_ring=2, void_spend=-1)


class TestCombatLog:
    def test_create_combat_log(self) -> None:
        log = create_combat_log(["A", "B"], [3, 2])
        assert log.combatants == ["A", "B"]
        assert log.wounds["A"].earth_ring == 3
        assert log.wounds["B"].earth_ring == 2
