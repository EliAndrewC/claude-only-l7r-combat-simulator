"""Tests for Wave Man profession builder."""

from src.engine.character_builders.waveman import (
    WAVE_MAN_ABILITY_ORDER,
    build_waveman_from_xp,
    compute_abilities,
    compute_waveman_stats_from_xp,
)


class TestComputeAbilities:
    def test_abilities_at_0xp(self) -> None:
        """0 earned XP → 1 ability: ability 1 rank 1."""
        abilities = compute_abilities(0)
        assert len(abilities) == 1
        assert abilities[0].number == 1
        assert abilities[0].rank == 1

    def test_abilities_at_15xp(self) -> None:
        """15 earned XP → 2 abilities: 1 and 4, both rank 1."""
        abilities = compute_abilities(15)
        assert len(abilities) == 2
        nums = {ab.number for ab in abilities}
        assert nums == {1, 4}
        assert all(ab.rank == 1 for ab in abilities)

    def test_abilities_at_14xp(self) -> None:
        """14 XP → still only 1 ability (1 + 14//15 = 1)."""
        abilities = compute_abilities(14)
        assert len(abilities) == 1

    def test_abilities_at_135xp(self) -> None:
        """135 XP → 10 abilities: all 10 at rank 1 (1 + 135//15 = 10)."""
        abilities = compute_abilities(135)
        assert len(abilities) == 10
        assert all(ab.rank == 1 for ab in abilities)
        nums = {ab.number for ab in abilities}
        assert nums == set(range(1, 11))

    def test_abilities_at_150xp(self) -> None:
        """150 XP → 11 abilities: all 10 at rank 1 + ability 1 at rank 2."""
        abilities = compute_abilities(150)
        assert len(abilities) == 10  # 10 unique ability numbers
        ab1 = next(ab for ab in abilities if ab.number == 1)
        assert ab1.rank == 2
        # Others still rank 1
        others = [ab for ab in abilities if ab.number != 1]
        assert all(ab.rank == 1 for ab in others)

    def test_abilities_max_rank_2(self) -> None:
        """High XP gives rank 2 on multiple abilities."""
        # 285 XP → 1 + 285//15 = 20 → all 10 at rank 2
        abilities = compute_abilities(285)
        assert len(abilities) == 10
        assert all(ab.rank == 2 for ab in abilities)

    def test_ability_order_matches_constant(self) -> None:
        """Abilities are granted in WAVE_MAN_ABILITY_ORDER."""
        for i in range(len(WAVE_MAN_ABILITY_ORDER)):
            count = i + 1  # 1-indexed
            xp = (count - 1) * 15
            abilities = compute_abilities(xp)
            expected_nums = sorted(WAVE_MAN_ABILITY_ORDER[:count])
            actual_nums = sorted(ab.number for ab in abilities)
            assert actual_nums == expected_nums, (
                f"At {xp} XP, expected {expected_nums},"
                f" got {actual_nums}"
            )


class TestBuildWavemanFromXP:
    def test_rings_start_at_1(self) -> None:
        """0 earned XP, all rings should start from 1 (not 2)."""
        char = build_waveman_from_xp(earned_xp=0, non_combat_pct=1.0)
        # With 100% non-combat, no combat XP to raise rings
        assert char.rings.air.value == 1
        assert char.rings.fire.value == 1
        assert char.rings.earth.value == 1
        assert char.rings.water.value == 1
        assert char.rings.void.value == 1

    def test_no_school_ring(self) -> None:
        """Wave Man has no school ring."""
        char = build_waveman_from_xp(earned_xp=0)
        assert char.school_ring is None

    def test_rings_increase_with_xp(self) -> None:
        """Higher XP = higher ring values."""
        char_low = build_waveman_from_xp(earned_xp=0)
        char_high = build_waveman_from_xp(earned_xp=200)
        low_total = sum(
            r.value for r in [
                char_low.rings.air, char_low.rings.fire,
                char_low.rings.earth, char_low.rings.water,
                char_low.rings.void,
            ]
        )
        high_total = sum(
            r.value for r in [
                char_high.rings.air, char_high.rings.fire,
                char_high.rings.earth, char_high.rings.water,
                char_high.rings.void,
            ]
        )
        assert high_total > low_total

    def test_attack_parry_gain_ranks(self) -> None:
        """Combat skills increase with XP."""
        char = build_waveman_from_xp(earned_xp=200)
        atk = char.get_skill("Attack")
        assert atk is not None
        assert atk.rank >= 1
        parry = char.get_skill("Parry")
        assert parry is not None
        assert parry.rank >= 1

    def test_abilities_attached(self) -> None:
        """Character should have profession abilities."""
        char = build_waveman_from_xp(earned_xp=30)
        assert len(char.profession_abilities) >= 2

    def test_name_set(self) -> None:
        char = build_waveman_from_xp(name="Ronin")
        assert char.name == "Ronin"

    def test_xp_total(self) -> None:
        char = build_waveman_from_xp(earned_xp=100)
        assert char.xp_total == 250

    def test_zero_xp_progression(self) -> None:
        """0 earned XP, 0% non-combat → 150 budget, rings from 1.

        Skills to 2: parry1(4) atk1(4) parry2(4) = 12, budget=138.
        Rings 1→2: 5×10=50, budget=88.
        Skills: atk2(4) parry3(6) = 10, budget=78.
        Rings 2→3: 5×15=75, budget=3. No more budget.
        """
        char = build_waveman_from_xp(earned_xp=0, non_combat_pct=0.0)
        assert char.rings.void.value == 3
        assert char.rings.water.value == 3
        assert char.rings.earth.value == 3
        assert char.rings.fire.value == 3
        assert char.rings.air.value == 3
        assert char.get_skill("Attack").rank == 2
        assert char.get_skill("Parry").rank == 3

    def test_parry_never_exceeds_attack_plus_one(self) -> None:
        """Parry constraint holds for Wave Man."""
        char = build_waveman_from_xp(earned_xp=200)
        atk = char.get_skill("Attack").rank
        parry = char.get_skill("Parry").rank
        assert parry <= atk + 1

    def test_parry_never_exceeds_max_ring_plus_one(self) -> None:
        """Wave Man parry is no more than 1 higher than the highest ring."""
        for xp in (0, 50, 100, 150, 200, 250, 300, 350):
            for nc in (0.0, 0.10, 0.20, 0.30, 0.50):
                stats = compute_waveman_stats_from_xp(earned_xp=xp, non_combat_pct=nc)
                max_ring = max(stats.ring_values.values())
                assert stats.parry <= max_ring + 1, (
                    f"At {xp} XP, {nc*100}% NC: parry={stats.parry} > max_ring({max_ring})+1"
                )


class TestComputeWavemanStats:
    """Tests for compute_waveman_stats_from_xp helper."""

    def test_compute_waveman_stats_zero_xp(self) -> None:
        """0 earned XP with 100% non-combat: rings stay at 1."""
        stats = compute_waveman_stats_from_xp(earned_xp=0, non_combat_pct=1.0)
        assert stats.ring_values == {"air": 1, "fire": 1, "earth": 1, "water": 1, "void": 1}
        assert stats.attack == 0
        assert stats.parry == 0

    def test_compute_waveman_stats_consistency(self) -> None:
        """compute_waveman_stats_from_xp matches build_waveman_from_xp output."""
        for earned_xp in (0, 50, 100, 200, 350):
            stats = compute_waveman_stats_from_xp(
                earned_xp=earned_xp,
                non_combat_pct=0.20,
            )
            char = build_waveman_from_xp(
                earned_xp=earned_xp,
                non_combat_pct=0.20,
            )
            assert stats.ring_values["air"] == char.rings.air.value
            assert stats.ring_values["fire"] == char.rings.fire.value
            assert stats.ring_values["earth"] == char.rings.earth.value
            assert stats.ring_values["water"] == char.rings.water.value
            assert stats.ring_values["void"] == char.rings.void.value
            assert stats.attack == char.get_skill("Attack").rank
            assert stats.parry == char.get_skill("Parry").rank
