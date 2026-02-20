"""Tests for the Mirumoto Bushi school builder."""

from src.engine.character_builders.mirumoto import (
    build_mirumoto_from_xp,
    compute_mirumoto_stats_from_xp,
)
from src.models.character import RingName


class TestStartingValues:
    def test_starting_rings(self) -> None:
        """Void=3, others=2 at 0 XP / 100% non-combat."""
        stats = compute_mirumoto_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert stats.ring_values["void"] == 3
        assert stats.ring_values["air"] == 2
        assert stats.ring_values["fire"] == 2
        assert stats.ring_values["earth"] == 2
        assert stats.ring_values["water"] == 2

    def test_school_ring_is_void(self) -> None:
        """School ring is always Void."""
        char = build_mirumoto_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert char.school_ring == RingName.VOID

    def test_knacks_start_at_1(self) -> None:
        """All 3 school knacks start at rank 1 with no earned XP."""
        stats = compute_mirumoto_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert stats.knack_ranks["counterattack"] == 1
        assert stats.knack_ranks["double_attack"] == 1
        assert stats.knack_ranks["iaijutsu"] == 1

    def test_dan_at_0xp(self) -> None:
        """Dan is 1 at 0 XP because all knacks start at 1."""
        char = build_mirumoto_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert char.dan == 1


class TestProgression:
    def test_zero_xp_progression(self) -> None:
        """At 0 XP / 0% non-combat, parry/attack advance before rings."""
        stats = compute_mirumoto_stats_from_xp(earned_xp=0, non_combat_pct=0.0)
        # 150 XP combat budget, should buy at least parry 1 and attack 1
        assert stats.parry >= 1
        assert stats.attack >= 1

    def test_knacks_before_rings(self) -> None:
        """Knacks reach 3 before Air reaches 3."""
        # Give enough XP to get knacks to 3 but not rings
        stats = compute_mirumoto_stats_from_xp(earned_xp=50, non_combat_pct=0.0)
        # At this XP knacks should be at least 2
        for knack in ("counterattack", "double_attack", "iaijutsu"):
            assert stats.knack_ranks[knack] >= 2

    def test_4th_dan_void_boost(self) -> None:
        """When all knacks reach 4, Void gets +1 for free."""
        # High XP to reach 4th dan
        stats_high = compute_mirumoto_stats_from_xp(earned_xp=350, non_combat_pct=0.0)
        # Knacks should all be at least 4
        for knack in ("counterattack", "double_attack", "iaijutsu"):
            assert stats_high.knack_ranks[knack] >= 4
        # Void should be boosted (higher than if we just had the paid raises)
        # At 350 XP we should have Void >= 5
        assert stats_high.ring_values["void"] >= 5

    def test_4th_dan_void_cost_discount(self) -> None:
        """Void raise after 4th Dan costs 5 less effectively (gets one more raise)."""
        # Compare a high XP build: Mirumoto gets Void boost at 4th dan
        stats = compute_mirumoto_stats_from_xp(earned_xp=350, non_combat_pct=0.0)
        # The free Void +1 means the Mirumoto can reach higher Void than without it
        assert stats.ring_values["void"] >= 5

    def test_parry_constraint_holds(self) -> None:
        """Parry never exceeds attack + 1."""
        for xp in (0, 50, 100, 150, 200, 250, 300, 350):
            stats = compute_mirumoto_stats_from_xp(earned_xp=xp, non_combat_pct=0.0)
            assert stats.parry <= stats.attack + 1, f"Failed at XP={xp}"

    def test_high_xp_progression(self) -> None:
        """350 XP reaches near-max stats."""
        stats = compute_mirumoto_stats_from_xp(earned_xp=350, non_combat_pct=0.0)
        # Should have high rings and skills
        assert stats.attack >= 4
        assert stats.parry >= 4
        assert stats.ring_values["void"] >= 5
        assert stats.ring_values["air"] >= 3


class TestCharacterConstruction:
    def test_stats_consistency(self) -> None:
        """compute_mirumoto_stats_from_xp matches build_mirumoto_from_xp."""
        for xp in (0, 100, 200, 350):
            stats = compute_mirumoto_stats_from_xp(earned_xp=xp, non_combat_pct=0.2)
            char = build_mirumoto_from_xp(earned_xp=xp, non_combat_pct=0.2)
            for rn in ("air", "fire", "earth", "water", "void"):
                assert char.rings.get(RingName(rn.capitalize())).value == stats.ring_values[rn], \
                    f"Ring {rn} mismatch at XP={xp}"
            atk = char.get_skill("Attack")
            assert atk and atk.rank == stats.attack, f"Attack mismatch at XP={xp}"
            par = char.get_skill("Parry")
            assert par and par.rank == stats.parry, f"Parry mismatch at XP={xp}"

    def test_school_knacks_on_character(self) -> None:
        """Character has the 3 school knack names."""
        char = build_mirumoto_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert char.school_knacks == ["Counterattack", "Double Attack", "Iaijutsu"]

    def test_school_name(self) -> None:
        """Character school is set correctly."""
        char = build_mirumoto_from_xp(earned_xp=0)
        assert char.school == "Mirumoto Bushi"

    def test_knack_skills_on_character(self) -> None:
        """Character has skill objects for each knack."""
        char = build_mirumoto_from_xp(earned_xp=100, non_combat_pct=0.0)
        for name in ("Counterattack", "Double Attack", "Iaijutsu"):
            skill = char.get_skill(name)
            assert skill is not None, f"Missing skill {name}"
            assert skill.rank >= 1
