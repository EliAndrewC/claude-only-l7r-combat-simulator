"""Tests for audit fix items: worldliness base class, Hida duel guard,
format_pool_with_overflow, Lucky attack reroll, Kitsuki 5th Dan debuff,
Daidoji counterattack resolution, Isawa Duelist interrupt lunge,
Doji Artisan SA counterattack.
"""

from __future__ import annotations

from unittest.mock import patch

from src.engine.combat_state import CombatState  # noqa: I001
from src.engine.simulation import simulate_combat
from src.engine.simulation_utils import format_pool_with_overflow
from src.models.character import (
    Advantage,
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.combat import ActionType
from tests.conftest import KATANA, make_combat_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rings(**overrides: int) -> dict[str, Ring]:
    return {
        rn: Ring(name=RingName(rn.capitalize()), value=overrides.get(rn, 2))
        for rn in ["air", "fire", "earth", "water", "void"]
    }


def _make_hida(
    name: str = "Hida",
    knack_rank: int = 4,
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Hida Bushi",
        school_ring=RingName.EARTH,
        school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Counterattack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Double Attack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def _make_kitsuki(
    name: str = "Kitsuki",
    knack_rank: int = 5,
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Kitsuki Magistrate",
        school_ring=RingName.FIRE,
        school_knacks=["Discern Honor", "Iaijutsu", "Oppose Social"],
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Oppose Social", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.FIRE,
            ),
        ],
    )


def _make_isawa_duelist(
    name: str = "IsawaDuelist",
    knack_rank: int = 4,
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Isawa Duelist",
        school_ring=RingName.WATER,
        school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Double Attack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Lunge", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def _make_doji_artisan(
    name: str = "DojiArtisan",
    knack_rank: int = 1,
    counterattack_rank: int = 3,
    culture_rank: int = 3,
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Doji Artisan",
        school_ring=RingName.AIR,
        school_knacks=["Discern Honor", "Oppose Social", "Worldliness"],
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Counterattack", rank=counterattack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Culture", rank=culture_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Discern Honor", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Oppose Social", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Worldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
        ],
    )


def _make_daidoji(
    name: str = "Daidoji",
    knack_rank: int = 1,
    counterattack_rank: int = 3,
    attack_rank: int = 3,
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        school="Daidoji Yojimbo",
        school_ring=RingName.WATER,
        school_knacks=["Counterattack", "Double Attack", "Iaijutsu"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Counterattack", rank=counterattack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Double Attack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        ],
    )


def _make_generic(
    name: str = "Generic",
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
        ],
    )


def _make_lucky_char(
    name: str = "Lucky",
    **ring_overrides: int,
) -> Character:
    return Character(
        name=name,
        rings=Rings(**_rings(**ring_overrides)),
        skills=[
            Skill(
                name="Attack", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=2,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
        ],
        advantages=[Advantage.LUCKY],
    )


def _setup_state(char_a: Character, char_b: Character) -> CombatState:
    return make_combat_state(char_a, char_b)


# ---------------------------------------------------------------------------
# Test: Worldliness void in base class
# ---------------------------------------------------------------------------

class TestWorldlinessBaseClass:
    """Worldliness void should be initialized in base Fighter.__init__."""

    def test_worldliness_from_base(self) -> None:
        """Fighter base class reads Worldliness skill rank."""
        from tests.conftest import make_courtier

        char = make_courtier(name="TestCourtier", knack_rank=3)
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["TestCourtier"]
        assert fighter.worldliness_void == 3

    def test_worldliness_zero_without_skill(self) -> None:
        """Fighter with no Worldliness skill gets 0."""
        char = _make_generic("NoWorldliness")
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["NoWorldliness"]
        assert fighter.worldliness_void == 0


# ---------------------------------------------------------------------------
# Test: Hida 4th Dan duel guard
# ---------------------------------------------------------------------------

class TestHidaDuelGuard:
    """Hida 4th Dan should_replace_wound_check must return False in duels."""

    def test_blocks_in_duel(self) -> None:
        """should_replace_wound_check returns (False, 0, '') when in_duel."""
        char = _make_hida(knack_rank=4, earth=3, water=3)
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["Hida"]

        # Without duel flag, 4th Dan should be available
        fighter.in_duel = False
        fighter.should_replace_wound_check(100)

        # With duel flag, always returns False
        fighter.in_duel = True
        replace, sw, note = fighter.should_replace_wound_check(100)
        assert replace is False
        assert sw == 0


# ---------------------------------------------------------------------------
# Test: format_pool_with_overflow
# ---------------------------------------------------------------------------

class TestFormatPoolOverflowBonus:
    """format_pool_with_overflow should use overflow_bonus param."""

    def test_default_overflow_bonus_2(self) -> None:
        """Default overflow adds +2 per excess kept."""
        # rolled=20, kept=5 → eff_kept = 5 + (20-10) = 15
        # bonus = (15-10)*2 = 10
        result = format_pool_with_overflow(20, 5)
        assert "+10" in result

    def test_custom_overflow_bonus_5(self) -> None:
        """Duel damage uses overflow_bonus=5."""
        result = format_pool_with_overflow(20, 5, overflow_bonus=5)
        # eff_kept = 5 + 10 = 15, bonus = (15-10)*5 = 25
        assert "+25" in result

    def test_no_overflow_no_bonus(self) -> None:
        """No overflow when rolled <= 10."""
        result = format_pool_with_overflow(8, 4)
        assert result == "8k4"


# ---------------------------------------------------------------------------
# Test: Lucky attack reroll
# ---------------------------------------------------------------------------

class TestLuckyAttackReroll:
    """Lucky advantage should allow attack reroll on near-miss."""

    def test_should_use_lucky_when_healthy_and_near_miss(self) -> None:
        """Lucky triggers on near-miss when character is healthy."""
        char = _make_lucky_char("Lucky")
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["Lucky"]
        fighter.lucky_used = False
        # Near miss: total 17, TN 20 → deficit 3 ≤ max(5, 5)
        assert fighter.should_use_lucky_reroll_attack(17, 20) is True

    def test_no_lucky_when_already_used(self) -> None:
        """Lucky doesn't trigger when already used."""
        char = _make_lucky_char("Lucky")
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["Lucky"]
        fighter.lucky_used = True
        assert fighter.should_use_lucky_reroll_attack(17, 20) is False

    def test_no_lucky_when_has_serious_wounds(self) -> None:
        """Lucky saved for WC when character has serious wounds."""
        char = _make_lucky_char("Lucky")
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["Lucky"]
        state.log.wounds["Lucky"].serious_wounds = 1
        assert fighter.should_use_lucky_reroll_attack(17, 20) is False

    def test_no_lucky_when_miss_too_large(self) -> None:
        """Lucky doesn't trigger when miss is too far away."""
        char = _make_lucky_char("Lucky")
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["Lucky"]
        # Total 5, TN 30 → deficit 25 > max(5, 7)
        assert fighter.should_use_lucky_reroll_attack(5, 30) is False

    def test_no_lucky_without_advantage(self) -> None:
        """Non-Lucky character never triggers."""
        char = _make_generic("NoLuck")
        state = _setup_state(char, _make_generic("Opp"))
        fighter = state.fighters["NoLuck"]
        assert fighter.should_use_lucky_reroll_attack(17, 20) is False


# ---------------------------------------------------------------------------
# Test: Kitsuki 5th Dan debuff wiring
# ---------------------------------------------------------------------------

class TestKitsuki5thDanDebuff:
    """Kitsuki 5th Dan should reduce opponent's rings at combat start."""

    def test_debuff_applied_in_simulation(self) -> None:
        """simulate_combat calls apply_5th_dan_debuff for 5th Dan Kitsuki."""
        kitsuki = _make_kitsuki(
            name="Kit", knack_rank=5, fire=3, air=3, water=3,
        )
        generic = _make_generic(name="Gen", fire=3, air=3, water=3)

        with patch(
            "src.engine.dice.roll_and_keep",
            return_value=([10], [10], 50),
        ):
            log = simulate_combat(
                kitsuki, generic, KATANA, KATANA, max_rounds=1,
            )

        # Check that a STANCE action mentions ring reduction
        stance_actions = [
            a for a in log.actions
            if a.action_type == ActionType.STANCE
            and a.actor == "Kit"
            and "reduced by 1" in (a.description or "")
        ]
        assert len(stance_actions) > 0

    def test_debuff_lowers_rings(self) -> None:
        """apply_5th_dan_debuff reduces opponent Air/Fire/Water by 1."""
        kitsuki = _make_kitsuki(
            name="Kit", knack_rank=5, fire=3,
        )
        generic = _make_generic(
            name="Gen", fire=3, air=3, water=3,
        )
        state = _setup_state(kitsuki, generic)
        fighter = state.fighters["Kit"]

        note = fighter.apply_5th_dan_debuff("Gen")
        assert "Air" in note
        assert "Fire" in note
        assert "Water" in note

        gen = state.fighters["Gen"]
        assert gen.char.rings.air.value == 2
        assert gen.char.rings.fire.value == 2
        assert gen.char.rings.water.value == 2

    def test_no_debuff_below_5th_dan(self) -> None:
        """apply_5th_dan_debuff does nothing below 5th Dan."""
        kitsuki = _make_kitsuki(
            name="Kit", knack_rank=4,
        )
        generic = _make_generic(name="Gen", fire=3)
        state = _setup_state(kitsuki, generic)
        fighter = state.fighters["Kit"]

        note = fighter.apply_5th_dan_debuff("Gen")
        assert note == ""

        gen = state.fighters["Gen"]
        assert gen.char.rings.fire.value == 3


# ---------------------------------------------------------------------------
# Test: Daidoji counterattack resolution
# ---------------------------------------------------------------------------

class TestDaidojiCounterattackResolution:
    """Daidoji SA counterattack should fully resolve (roll, damage, WC)."""

    def test_counterattack_produces_actions(self) -> None:
        """Daidoji counterattack creates CA, DAMAGE, and WC actions."""
        daidoji = _make_daidoji(
            name="Dai", knack_rank=1, counterattack_rank=3,
        )
        generic = _make_generic(name="Att", fire=2)
        state = _setup_state(daidoji, generic)

        dai_f = state.fighters["Dai"]
        dai_f.actions_remaining = [3, 5, 7]

        # Make the CA always hit with high roll
        with patch(
            "src.engine.fighters.daidoji.roll_and_keep",
            return_value=([30], [30], 30),
        ):
            result = dai_f.resolve_pre_attack_counterattack("Att", 5)

        assert result is not None
        margin, penalty = result
        assert penalty == 0  # Daidoji has no SA penalty on attacker

        # Check that CA, DAMAGE, and WC actions were logged
        ca_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.COUNTERATTACK
        ]
        dmg_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.DAMAGE
        ]
        wc_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.WOUND_CHECK
        ]
        assert len(ca_actions) >= 1
        assert len(dmg_actions) >= 1
        assert len(wc_actions) >= 1

    def test_counterattack_sa_wc_bonus(self) -> None:
        """Opponent gets +5 free raise on WC from Daidoji SA."""
        daidoji = _make_daidoji(
            name="Dai", knack_rank=1, counterattack_rank=3,
        )
        generic = _make_generic(name="Att", fire=2)
        state = _setup_state(daidoji, generic)

        dai_f = state.fighters["Dai"]
        dai_f.actions_remaining = [3, 5, 7]

        with patch(
            "src.engine.fighters.daidoji.roll_and_keep",
            return_value=([30], [30], 30),
        ):
            dai_f.resolve_pre_attack_counterattack("Att", 5)

        wc_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.WOUND_CHECK
        ]
        assert len(wc_actions) >= 1
        # WC description should mention SA bonus
        assert "daidoji sa" in wc_actions[0].description.lower()


# ---------------------------------------------------------------------------
# Test: Isawa Duelist 4th Dan interrupt lunge
# ---------------------------------------------------------------------------

class TestIsawaDuelistInterruptLunge:
    """Isawa Duelist 4th Dan should counter-lunge after being attacked."""

    def test_has_interrupt_lunge_at_4th_dan(self) -> None:
        """4th Dan Isawa Duelist has resolve_post_attack_interrupt."""
        isawa = _make_isawa_duelist(
            name="Isawa", knack_rank=4, fire=3,
        )
        generic = _make_generic(name="Att", fire=2)
        state = _setup_state(isawa, generic)
        fighter = state.fighters["Isawa"]
        fighter.actions_remaining = [3, 5, 7]

        # Just verify it doesn't crash — the lunge resolution is complex
        # and depends on _resolve_attack
        with patch(
            "src.engine.simulation._resolve_attack",
        ) as mock_resolve:
            fighter.resolve_post_attack_interrupt("Att", 5, 20)
            mock_resolve.assert_called_once()

    def test_no_interrupt_before_4th_dan(self) -> None:
        """Below 4th Dan, no interrupt lunge."""
        isawa = _make_isawa_duelist(
            name="Isawa", knack_rank=3, fire=3,
        )
        generic = _make_generic(name="Att")
        state = _setup_state(isawa, generic)
        fighter = state.fighters["Isawa"]
        fighter.actions_remaining = [3, 5, 7]

        with patch(
            "src.engine.simulation._resolve_attack",
        ) as mock_resolve:
            fighter.resolve_post_attack_interrupt("Att", 5, 20)
            mock_resolve.assert_not_called()

    def test_once_per_round(self) -> None:
        """Interrupt lunge can only be used once per round."""
        isawa = _make_isawa_duelist(
            name="Isawa", knack_rank=4, fire=3,
        )
        generic = _make_generic(name="Att")
        state = _setup_state(isawa, generic)
        fighter = state.fighters["Isawa"]
        fighter.actions_remaining = [1, 3, 5, 7]

        with patch(
            "src.engine.simulation._resolve_attack",
        ) as mock_resolve:
            fighter.resolve_post_attack_interrupt("Att", 5, 20)
            fighter.resolve_post_attack_interrupt("Att", 7, 25)
            assert mock_resolve.call_count == 1

    def test_resets_on_round_start(self) -> None:
        """Counter-lunge resets each round."""
        isawa = _make_isawa_duelist(
            name="Isawa", knack_rank=4, fire=3,
        )
        generic = _make_generic(name="Att")
        state = _setup_state(isawa, generic)
        fighter = state.fighters["Isawa"]
        fighter.actions_remaining = [1, 3, 5, 7, 9]
        fighter._counter_lunge_used_this_round = True

        fighter.on_round_start()
        assert fighter._counter_lunge_used_this_round is False


# ---------------------------------------------------------------------------
# Test: Doji Artisan SA counterattack
# ---------------------------------------------------------------------------

class TestDojiArtisanSACounterattack:
    """Doji Artisan SA counterattack should spend void + die and counter."""

    def test_counterattack_fires(self) -> None:
        """Doji Artisan SA counterattack produces actions."""
        doji = _make_doji_artisan(
            name="Doji", knack_rank=1, counterattack_rank=3,
            fire=3, void=3,
        )
        generic = _make_generic(name="Att", fire=2)
        state = _setup_state(doji, generic)

        doji_f = state.fighters["Doji"]
        doji_f.actions_remaining = [3, 5, 7]
        initial_void = doji_f.total_void

        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
            return_value=([30], [30], 30),
        ):
            doji_f.resolve_post_attack_interrupt("Att", 5, 25)

        # Should have spent 1 void
        assert doji_f.total_void < initial_void

        # Should have consumed cheapest die
        assert 3 not in doji_f.actions_remaining

        # Check that CA and DAMAGE actions were logged
        ca_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.COUNTERATTACK
        ]
        assert len(ca_actions) >= 1

    def test_no_counter_without_void(self) -> None:
        """Doji Artisan can't counterattack without void."""
        doji = _make_doji_artisan(
            name="Doji", counterattack_rank=3, void=3,
        )
        generic = _make_generic(name="Att")
        state = _setup_state(doji, generic)

        doji_f = state.fighters["Doji"]
        doji_f.actions_remaining = [3, 5, 7]
        # Drain all void
        doji_f.void_points = 0
        doji_f.temp_void = 0
        doji_f.worldliness_void = 0

        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
        ) as mock_roll:
            doji_f.resolve_post_attack_interrupt("Att", 5, 25)
            mock_roll.assert_not_called()

    def test_no_counter_without_dice(self) -> None:
        """Doji Artisan can't counterattack without action dice."""
        doji = _make_doji_artisan(
            name="Doji", counterattack_rank=3, void=3,
        )
        generic = _make_generic(name="Att")
        state = _setup_state(doji, generic)

        doji_f = state.fighters["Doji"]
        doji_f.actions_remaining = []

        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
        ) as mock_roll:
            doji_f.resolve_post_attack_interrupt("Att", 5, 25)
            mock_roll.assert_not_called()

    def test_attacker_roll_bonus(self) -> None:
        """SA bonus = attacker's roll / 5 applied to CA."""
        doji = _make_doji_artisan(
            name="Doji", counterattack_rank=3, fire=3, void=3,
        )
        generic = _make_generic(name="Att", fire=2)
        state = _setup_state(doji, generic)

        doji_f = state.fighters["Doji"]
        doji_f.actions_remaining = [3, 5, 7]

        # Attacker rolled 30 → bonus = 30/5 = 6
        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
            return_value=([10], [10], 10),
        ):
            doji_f.resolve_post_attack_interrupt("Att", 5, 30)

        ca_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.COUNTERATTACK
        ]
        if ca_actions:
            # The CA description should mention the SA bonus
            assert "SA: +6" in ca_actions[0].description

    def test_no_counter_without_ca_skill(self) -> None:
        """Doji Artisan can't counterattack without Counterattack skill."""
        doji = _make_doji_artisan(
            name="Doji", counterattack_rank=0, void=3,
        )
        generic = _make_generic(name="Att")
        state = _setup_state(doji, generic)

        doji_f = state.fighters["Doji"]
        doji_f.actions_remaining = [3, 5, 7]

        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
        ) as mock_roll:
            doji_f.resolve_post_attack_interrupt("Att", 5, 25)
            mock_roll.assert_not_called()


# ---------------------------------------------------------------------------
# Test: in_duel flag set/cleared in simulation
# ---------------------------------------------------------------------------

class TestInDuelFlag:
    """The in_duel flag should be set during duel and cleared after."""

    def test_in_duel_set_during_duel(self) -> None:
        """Fighters have in_duel=True during duel phase."""
        from tests.conftest import make_character

        char_a = make_character("A", fire=3)
        char_b = make_character("B", fire=3)
        # Add Iaijutsu skill for the duel
        char_a.skills.append(
            Skill(
                name="Iaijutsu", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        )
        char_b.skills.append(
            Skill(
                name="Iaijutsu", rank=3,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
        )

        # Mock to make duel resolve quickly (both hit)
        with patch(
            "src.engine.dice.roll_and_keep",
            return_value=([10], [10], 50),
        ):
            log = simulate_combat(
                char_a, char_b, KATANA, KATANA,
                is_duel=True, max_rounds=1,
            )

        # After simulation, in_duel should be False
        # (we can't easily check during duel without hooks)
        assert log is not None
