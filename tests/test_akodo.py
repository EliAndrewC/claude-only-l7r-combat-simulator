"""Tests for the Akodo Bushi character builder."""

from __future__ import annotations

from src.engine.character_builders.akodo import (
    AKODO_KNACK_NAMES,
    build_akodo_from_xp,
    compute_akodo_stats_from_xp,
)
from src.models.character import RingName


class TestStartingValues:
    """Starting values at 0 earned XP (100% non-combat)."""

    def test_rings_at_zero_xp(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert stats.ring_values["water"] == 3  # School ring
        assert stats.ring_values["air"] == 2
        assert stats.ring_values["fire"] == 2
        assert stats.ring_values["earth"] == 2
        assert stats.ring_values["void"] == 2

    def test_school_ring_is_water(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert stats.ring_values["water"] == 3

    def test_knacks_start_at_1(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        for k in AKODO_KNACK_NAMES:
            assert stats.knack_ranks[k] == 1, f"{k} should start at 1"

    def test_attack_parry_at_zero(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert stats.attack == 0
        assert stats.parry == 0


class TestProgression:
    """XP progression tests."""

    def test_water_raised_before_other_rings(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=100, non_combat_pct=0.0)
        # Water (school ring) should be raised first
        assert stats.ring_values["water"] >= stats.ring_values["air"]
        assert stats.ring_values["water"] >= stats.ring_values["fire"]
        assert stats.ring_values["water"] >= stats.ring_values["earth"]

    def test_knacks_advance_before_rings(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=50, non_combat_pct=0.0)
        # Knacks should get some ranks before rings get raised
        total_knack = sum(stats.knack_ranks.values())
        assert total_knack > 3  # more than starting 3

    def test_parry_constrained_by_attack(self) -> None:
        for xp in [50, 100, 150, 200]:
            stats = compute_akodo_stats_from_xp(earned_xp=xp, non_combat_pct=0.0)
            assert stats.parry <= stats.attack + 1, (
                f"parry ({stats.parry}) > attack + 1 ({stats.attack + 1}) at xp={xp}"
            )

    def test_4th_dan_water_boost(self) -> None:
        """When all knacks reach 4, Water gets a free +1."""
        # Find XP where all knacks reach 4
        for xp in range(0, 400, 10):
            stats = compute_akodo_stats_from_xp(earned_xp=xp, non_combat_pct=0.0)
            if all(stats.knack_ranks[k] >= 4 for k in AKODO_KNACK_NAMES):
                # Water should be boosted beyond base progression
                assert stats.ring_values["water"] >= 4
                break

    def test_water_max_is_6(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=500, non_combat_pct=0.0)
        assert stats.ring_values["water"] <= 6

    def test_other_rings_max_is_5(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=500, non_combat_pct=0.0)
        for ring in ["air", "fire", "earth", "void"]:
            assert stats.ring_values[ring] <= 5, f"{ring} exceeds max 5"

    def test_high_xp_progression(self) -> None:
        stats = compute_akodo_stats_from_xp(earned_xp=350, non_combat_pct=0.20)
        assert stats.attack >= 3
        assert stats.parry >= 2


class TestCharacterConstruction:
    """Tests for build_akodo_from_xp()."""

    def test_stats_match_builder(self) -> None:
        xp = 200
        stats = compute_akodo_stats_from_xp(earned_xp=xp, non_combat_pct=0.20)
        char = build_akodo_from_xp(earned_xp=xp, non_combat_pct=0.20)
        ring_map = {
            "air": RingName.AIR, "fire": RingName.FIRE, "earth": RingName.EARTH,
            "water": RingName.WATER, "void": RingName.VOID,
        }
        for ring, rn in ring_map.items():
            assert char.rings.get(rn).value == stats.ring_values[ring]
        atk = char.get_skill("Attack")
        assert atk and atk.rank == stats.attack
        par = char.get_skill("Parry")
        assert par and par.rank == stats.parry

    def test_school_name(self) -> None:
        char = build_akodo_from_xp(earned_xp=0)
        assert char.school == "Akodo Bushi"

    def test_school_knacks_on_char(self) -> None:
        char = build_akodo_from_xp(earned_xp=0)
        assert char.school_knacks == ["Double Attack", "Feint", "Iaijutsu"]

    def test_knack_skills_exist(self) -> None:
        char = build_akodo_from_xp(earned_xp=100)
        da = char.get_skill("Double Attack")
        fe = char.get_skill("Feint")
        ia = char.get_skill("Iaijutsu")
        assert da is not None
        assert fe is not None
        assert ia is not None
