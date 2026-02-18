"""Tests for XP-based character builder."""


from src.engine.xp_builder import (
    DEFAULT_COMBAT_PROGRESSION,
    advanced_skill_raise_cost,
    build_character_from_xp,
    compute_stats_from_xp,
    ring_raise_cost,
)
from src.models.character import RingName


class TestXPCosts:
    """Tests for XP cost calculation functions."""

    def test_ring_raise_cost_to_3(self) -> None:
        assert ring_raise_cost(3) == 15

    def test_ring_raise_cost_to_4(self) -> None:
        assert ring_raise_cost(4) == 20

    def test_ring_raise_cost_to_5(self) -> None:
        assert ring_raise_cost(5) == 25

    def test_ring_raise_cost_to_6(self) -> None:
        assert ring_raise_cost(6) == 30

    def test_advanced_skill_raise_cost_rank_1(self) -> None:
        assert advanced_skill_raise_cost(1) == 4

    def test_advanced_skill_raise_cost_rank_2(self) -> None:
        assert advanced_skill_raise_cost(2) == 4

    def test_advanced_skill_raise_cost_rank_3(self) -> None:
        assert advanced_skill_raise_cost(3) == 6

    def test_advanced_skill_raise_cost_rank_4(self) -> None:
        assert advanced_skill_raise_cost(4) == 8

    def test_advanced_skill_raise_cost_rank_5(self) -> None:
        assert advanced_skill_raise_cost(5) == 10


class TestDefaultProgression:
    """Tests for the default combat progression constant."""

    def test_progression_is_list_of_strings(self) -> None:
        assert isinstance(DEFAULT_COMBAT_PROGRESSION, list)
        assert all(isinstance(s, str) for s in DEFAULT_COMBAT_PROGRESSION)

    def test_progression_starts_with_parry(self) -> None:
        assert DEFAULT_COMBAT_PROGRESSION[0] == "parry"

    def test_progression_contains_all_rings_and_skills(self) -> None:
        entries = set(DEFAULT_COMBAT_PROGRESSION)
        assert entries == {"void", "water", "earth", "fire", "air", "attack", "parry"}


class TestBuildCharacterFromXP:
    """Tests for the main builder function."""

    def test_zero_earned_xp_with_school_ring(self) -> None:
        """0 earned XP, 150 total, 120 combat, school ring Fire.

        Skills reach parry 4 / attack 3 before rings advance, then all
        rings reach 3 and the school ring reaches 4.
        """
        char = build_character_from_xp(
            name="Test", earned_xp=0, school_ring=RingName.FIRE
        )
        assert char.rings.void.value == 3
        assert char.rings.water.value == 3
        assert char.rings.earth.value == 3
        assert char.rings.fire.value == 4
        assert char.rings.air.value == 3
        assert char.get_skill("Attack").rank == 3
        assert char.get_skill("Parry").rank == 4

    def test_100_earned_xp_with_school_ring(self) -> None:
        """100 earned XP, 250 total, 200 combat, school ring Fire.

        Skills reach parry 5 / attack 4 first, then rings advance.
        Final: Void 4, Water 4, Earth 4, Fire 4, Air 3, Attack 4, Parry 5
        """
        char = build_character_from_xp(
            name="Test", earned_xp=100, school_ring=RingName.FIRE
        )
        assert char.rings.void.value == 4
        assert char.rings.water.value == 4
        assert char.rings.earth.value == 4
        assert char.rings.fire.value == 4
        assert char.rings.air.value == 3
        assert char.get_skill("Attack").rank == 4
        assert char.get_skill("Parry").rank == 5

    def test_350_earned_xp_maxes_stats(self) -> None:
        """350 earned XP, 500 total, 400 combat, school ring Fire."""
        char = build_character_from_xp(
            name="Test", earned_xp=350, school_ring=RingName.FIRE
        )
        assert char.rings.void.value == 5
        assert char.rings.water.value == 5
        assert char.rings.earth.value == 5
        assert char.rings.fire.value == 6  # School ring goes to 6
        assert char.rings.air.value == 5
        assert char.get_skill("Attack").rank == 5
        assert char.get_skill("Parry").rank == 5

    def test_xp_total_set_correctly(self) -> None:
        char = build_character_from_xp(earned_xp=100)
        assert char.xp_total == 250

    def test_xp_spent_set_correctly(self) -> None:
        """xp_spent = combat_spent + non_combat_allocated."""
        char = build_character_from_xp(
            earned_xp=0, school_ring=RingName.FIRE, non_combat_pct=0.20
        )
        # total=150, combat_xp=120, non_combat=30
        # Combat spent: skills 4+4+4+4+6+6+8 = 36 + rings 15+15+15+20+15 = 80 → 116
        # xp_spent = 116 + 30 = 146
        assert char.xp_spent == 146

    def test_non_combat_pct_zero_gives_more_stats(self) -> None:
        """0% non-combat means all XP goes to combat."""
        char_0pct = build_character_from_xp(
            earned_xp=0, school_ring=RingName.FIRE, non_combat_pct=0.0
        )
        char_20pct = build_character_from_xp(
            earned_xp=0, school_ring=RingName.FIRE, non_combat_pct=0.20
        )
        # With 0% non-combat (150 budget vs 120): higher skill ranks
        assert char_0pct.get_skill("Attack").rank > char_20pct.get_skill("Attack").rank

    def test_non_combat_pct_zero_stats(self) -> None:
        """0 earned, 0% non-combat: 150 combat budget, school ring Fire.

        Budget 150: parry1(4) atk1(4) parry2(4) atk2(4) parry3(6) atk3(6)
        parry4(8) = 36, budget=114. Rings: void3(15) water3(15) earth3(15)
        fire4(20) air3(15) = 80, budget=34. atk4(8) parry5(10) = 18,
        budget=16. void4(20)>16 skip ... atk5(10) budget=6.
        """
        char = build_character_from_xp(
            earned_xp=0, school_ring=RingName.FIRE, non_combat_pct=0.0
        )
        assert char.rings.void.value == 3
        assert char.rings.water.value == 3
        assert char.rings.earth.value == 3
        assert char.rings.fire.value == 4
        assert char.rings.air.value == 3
        assert char.get_skill("Attack").rank == 5
        assert char.get_skill("Parry").rank == 5

    def test_progression_order_respected(self) -> None:
        """Parry is raised before rings (first in progression)."""
        char = build_character_from_xp(
            name="Test", earned_xp=0, school_ring=RingName.FIRE
        )
        # Parry is prioritised over rings: parry 4 while rings only reach 3
        assert char.get_skill("Parry").rank > char.rings.void.value

    def test_custom_progression(self) -> None:
        """Custom progression only raises specified stats."""
        char = build_character_from_xp(
            earned_xp=0,
            non_combat_pct=0.0,
            progression=["fire", "fire", "attack", "attack"],
        )
        # No school ring: fire starts at 2
        # fire 2→3: 15, fire 3→4: 20, atk 0→1: 4, atk 1→2: 4
        # Total: 43 from 150 budget
        assert char.rings.fire.value == 4
        assert char.get_skill("Attack").rank == 2
        # Other rings unchanged
        assert char.rings.air.value == 2
        assert char.rings.void.value == 2
        assert char.get_skill("Parry").rank == 0

    def test_default_name(self) -> None:
        char = build_character_from_xp()
        assert char.name == "Fighter"

    def test_custom_name(self) -> None:
        char = build_character_from_xp(name="Akodo Taro")
        assert char.name == "Akodo Taro"

    def test_skills_are_advanced_type(self) -> None:
        char = build_character_from_xp()
        atk = char.get_skill("Attack")
        parry = char.get_skill("Parry")
        assert atk is not None
        assert parry is not None
        assert atk.skill_type.value == "advanced"
        assert parry.skill_type.value == "advanced"


class TestParryAttackConstraint:
    """Tests that parry rank never exceeds attack rank + 1."""

    def test_parry_never_exceeds_attack_plus_one(self) -> None:
        """With default progression, parry <= attack + 1 always holds."""
        char = build_character_from_xp(earned_xp=200, school_ring=RingName.FIRE)
        atk = char.get_skill("Attack").rank
        parry = char.get_skill("Parry").rank
        assert parry <= atk + 1

    def test_parry_skipped_when_would_violate_constraint(self) -> None:
        """Progression with double parry: second parry skipped."""
        char = build_character_from_xp(
            earned_xp=0,
            non_combat_pct=0.0,
            progression=["parry", "parry", "attack"],
        )
        # parry 0→1: new_parry=1, attack=0. 1 <= 0+1 ✓. Allowed.
        # parry 1→2: new_parry=2, attack=0. 2 <= 0+1 ✗. Skipped.
        # attack 0→1: Allowed.
        assert char.get_skill("Parry").rank == 1
        assert char.get_skill("Attack").rank == 1

    def test_constraint_with_parry_only_progression(self) -> None:
        """Parry-only progression: only reaches rank 1."""
        char = build_character_from_xp(
            earned_xp=0,
            non_combat_pct=0.0,
            progression=["parry", "parry", "parry", "parry", "parry"],
        )
        # parry 0→1: 1 <= 0+1 ✓.
        # parry 1→2: 2 <= 0+1 ✗. Skipped. (and all subsequent)
        assert char.get_skill("Parry").rank == 1
        assert char.get_skill("Attack").rank == 0

    def test_constraint_holds_at_high_levels(self) -> None:
        """Even with max XP, constraint holds."""
        char = build_character_from_xp(earned_xp=350, school_ring=RingName.FIRE)
        atk = char.get_skill("Attack").rank
        parry = char.get_skill("Parry").rank
        assert parry <= atk + 1


class TestSchoolRing:
    """Tests for school ring behavior."""

    def test_school_ring_starts_at_3(self) -> None:
        char = build_character_from_xp(
            earned_xp=0,
            school_ring=RingName.WATER,
            progression=[],  # No raises
        )
        assert char.rings.water.value == 3
        assert char.school_ring == RingName.WATER

    def test_non_school_rings_start_at_2(self) -> None:
        char = build_character_from_xp(
            earned_xp=0,
            school_ring=RingName.WATER,
            progression=[],
        )
        assert char.rings.air.value == 2
        assert char.rings.fire.value == 2
        assert char.rings.earth.value == 2
        assert char.rings.void.value == 2

    def test_school_ring_can_reach_6(self) -> None:
        char = build_character_from_xp(
            earned_xp=350, school_ring=RingName.FIRE
        )
        assert char.rings.fire.value == 6

    def test_non_school_ring_capped_at_5(self) -> None:
        """Non-school rings cannot exceed 5."""
        char = build_character_from_xp(
            earned_xp=0,
            non_combat_pct=0.0,
            school_ring=RingName.FIRE,
            progression=["void", "void", "void", "void", "void"],
        )
        # void: 2→3(15), 3→4(20), 4→5(25) = 60. Then 5 is max, skip remaining.
        assert char.rings.void.value == 5

    def test_no_school_ring_all_start_at_2(self) -> None:
        char = build_character_from_xp(
            earned_xp=0,
            school_ring=None,
            progression=[],
        )
        assert char.rings.air.value == 2
        assert char.rings.fire.value == 2
        assert char.rings.earth.value == 2
        assert char.rings.water.value == 2
        assert char.rings.void.value == 2
        assert char.school_ring is None

    def test_no_school_ring_max_5(self) -> None:
        """Without school ring, all rings max at 5."""
        char = build_character_from_xp(
            earned_xp=350,
            school_ring=None,
        )
        assert char.rings.fire.value == 5
        assert char.rings.void.value == 5


class TestComputeStatsFromXP:
    """Tests for the compute_stats_from_xp helper."""

    def test_compute_stats_zero_xp(self) -> None:
        """0 earned XP with no school ring: all rings 2, skills 0-ish."""
        stats = compute_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        # With 100% non-combat, no budget to raise anything
        assert stats.ring_values == {"air": 2, "fire": 2, "earth": 2, "water": 2, "void": 2}
        assert stats.attack == 0
        assert stats.parry == 0

    def test_compute_stats_consistency(self) -> None:
        """compute_stats_from_xp output matches build_character_from_xp."""
        for earned_xp in (0, 50, 100, 200, 350):
            stats = compute_stats_from_xp(
                earned_xp=earned_xp,
                school_ring=RingName.FIRE,
                non_combat_pct=0.20,
            )
            char = build_character_from_xp(
                earned_xp=earned_xp,
                school_ring=RingName.FIRE,
                non_combat_pct=0.20,
            )
            assert stats.ring_values["air"] == char.rings.air.value
            assert stats.ring_values["fire"] == char.rings.fire.value
            assert stats.ring_values["earth"] == char.rings.earth.value
            assert stats.ring_values["water"] == char.rings.water.value
            assert stats.ring_values["void"] == char.rings.void.value
            assert stats.attack == char.get_skill("Attack").rank
            assert stats.parry == char.get_skill("Parry").rank
