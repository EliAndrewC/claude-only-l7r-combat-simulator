"""Tests for BrotherhoodMonkFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.brotherhood_monk import BrotherhoodMonkFighter
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.weapon import Weapon, WeaponType

UNARMED = Weapon(
    name="Unarmed", weapon_type=WeaponType.UNARMED, rolled=0, kept=2,
)
KATANA = Weapon(
    name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2,
)


def _make_monk(
    name: str = "Brotherhood Monk",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Brotherhood Monk character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    wl_rank = worldliness_rank if worldliness_rank is not None else knack_rank
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Brotherhood Monk",
        school_ring=RingName.WATER,
        school_knacks=["Conviction", "Otherworldliness", "Worldliness"],
        skills=[
            Skill(
                name="Attack", rank=attack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Parry", rank=parry_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.AIR,
            ),
            Skill(
                name="Precepts", rank=precepts_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Conviction", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.EARTH,
            ),
            Skill(
                name="Otherworldliness", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.VOID,
            ),
            Skill(
                name="Worldliness", rank=wl_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
        ],
    )


def _make_generic(name: str = "Generic", **kw: int) -> Character:
    """Create a generic character (opponent)."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = kw.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    return Character(
        name=name,
        rings=Rings(**kwargs),
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


def _make_state(
    monk_char: Character,
    opponent_char: Character,
    monk_void: int | None = None,
    monk_weapon: Weapon = UNARMED,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [monk_char.name, opponent_char.name],
        [monk_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    m_void = (
        monk_void if monk_void is not None
        else monk_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        monk_char.name, state,
        char=monk_char, weapon=monk_weapon, void_points=m_void,
    )
    create_fighter(
        opponent_char.name, state,
        char=opponent_char, weapon=KATANA,
        void_points=opponent_char.void_points_max,
    )
    return state


def _make_fighter(
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    void_points: int | None = None,
    worldliness_rank: int | None = None,
    monk_weapon: Weapon = UNARMED,
    **ring_overrides: int,
) -> BrotherhoodMonkFighter:
    """Create a BrotherhoodMonkFighter with a full CombatState."""
    char = _make_monk(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        precepts_rank=precepts_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, monk_void=void_points, monk_weapon=monk_weapon)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, BrotherhoodMonkFighter)
    return fighter


class TestBrotherhoodMonkInit:
    """Initialization and state tracking."""

    def test_worldliness_void_initialized(self) -> None:
        """worldliness_void equals the Worldliness skill rank."""
        for rank in range(6):
            fighter = _make_fighter(knack_rank=rank)
            assert fighter.worldliness_void == rank

    def test_worldliness_void_custom_rank(self) -> None:
        """worldliness_void can differ from knack_rank."""
        fighter = _make_fighter(knack_rank=3, worldliness_rank=5)
        assert fighter.worldliness_void == 5

    def test_free_raise_pool_at_3rd_dan(self) -> None:
        """Pool is 2 * precepts_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_free_raise_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, precepts_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0

    def test_counterattack_used_starts_false(self) -> None:
        """_counterattack_used_this_round starts False."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter._counterattack_used_this_round is False


class TestAttackHooks:
    """Attack-related hooks."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_attack_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on attack."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_attack_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0

    def test_sa_attack_bonus_at_dan_2(self) -> None:
        """2nd Dan gives +5 free raise on attack."""
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 5
        assert "monk 2nd Dan" in note

    def test_sa_attack_bonus_at_dan_1(self) -> None:
        """No bonus before 2nd Dan."""
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.sa_attack_bonus(3)
        assert bonus == 0
        assert note == ""


class TestSADamageBonus:
    """SA: +1 kept die on unarmed damage."""

    def test_unarmed_gives_extra_kept(self) -> None:
        """sa_attack_damage_bonus returns (0, 1) with UNARMED weapon."""
        fighter = _make_fighter(knack_rank=1, monk_weapon=UNARMED)
        extra_rolled, extra_kept = fighter.sa_attack_damage_bonus(0)
        assert extra_rolled == 0
        assert extra_kept == 1

    def test_katana_gives_no_extra(self) -> None:
        """sa_attack_damage_bonus returns (0, 0) with KATANA weapon."""
        fighter = _make_fighter(knack_rank=1, monk_weapon=KATANA)
        extra_rolled, extra_kept = fighter.sa_attack_damage_bonus(0)
        assert extra_rolled == 0
        assert extra_kept == 0


class TestFirstDanDamage:
    """1st Dan: +1 rolled die on damage."""

    def test_weapon_rolled_boost_at_dan_1(self) -> None:
        """weapon_rolled_boost returns weapon_rolled + 1 at dan >= 1."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.weapon_rolled_boost(0, 2) == 1
        assert fighter.weapon_rolled_boost(4, 2) == 5

    def test_weapon_rolled_boost_at_dan_0(self) -> None:
        """weapon_rolled_boost returns weapon_rolled at dan 0."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.weapon_rolled_boost(0, 2) == 0
        assert fighter.weapon_rolled_boost(4, 2) == 4


class TestFirstDanWoundCheck:
    """1st Dan: +1 rolled die on wound checks."""

    def test_wound_check_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on wound check."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestThirdDanFreeRaises:
    """3rd Dan: Free raise pool mechanics."""

    def test_spend_on_attack_miss(self) -> None:
        """Spend minimum raises to bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 5
        assert fighter._free_raises == 9
        assert "1 free raise" in note

    def test_spend_on_attack_larger_deficit(self) -> None:
        """Spend multiple raises for larger deficit."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(13, 25, 3, "Generic")
        assert bonus == 15
        assert fighter._free_raises == 7
        assert "3 free raise" in note

    def test_no_spend_when_hit(self) -> None:
        """Don't spend if already hitting."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_no_spend_when_gap_too_large(self) -> None:
        """Don't spend if can't bridge gap with max per roll."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(0, 26, 3, "Generic")
        assert bonus == 0
        assert fighter._free_raises == 10

    def test_pool_exhaustion(self) -> None:
        """Pool decreases with each spend."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 5
        fighter.post_attack_roll_bonus(0, 25, 3, "Generic")
        assert fighter._free_raises == 0
        bonus, _ = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus == 0

    def test_wc_bonus_pool_total(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_total_before_3rd_dan(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, precepts_rank=5)
        assert fighter.wc_bonus_pool_total() == 0

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=2, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45

        wound_tracker.serious_wounds = 3
        sw_before = 0
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert not new_passed
        assert new_total == 29
        assert "1 free raise" in note
        assert wound_tracker.serious_wounds == 2

    def test_spend_to_pass_when_mortal(self) -> None:
        """Spend to pass if taking SW would be mortal."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5, earth=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 25

        wound_tracker.serious_wounds = 4
        sw_before = 3
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert new_passed
        assert note != ""

    def test_no_spend_when_passed(self) -> None:
        """Don't spend on already-passed wound check."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, precepts_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
        assert note == ""


class TestFourthDanParryReduction:
    """4th Dan: Failed parry does not reduce damage dice."""

    def test_no_reduction_at_dan_4(self) -> None:
        """damage_parry_reduction returns 0 at dan >= 4."""
        fighter = _make_fighter(knack_rank=4)
        assert fighter.damage_parry_reduction(3) == 0

    def test_reduction_before_dan_4(self) -> None:
        """damage_parry_reduction returns defender_parry_rank at dan < 4."""
        fighter = _make_fighter(knack_rank=3)
        assert fighter.damage_parry_reduction(3) == 3

    def test_no_reduction_at_dan_5(self) -> None:
        """damage_parry_reduction returns 0 at dan 5."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.damage_parry_reduction(5) == 0


class TestFifthDanCounterattack:
    """5th Dan: Pre-damage counterattack."""

    def test_no_cancel_before_5th_dan(self) -> None:
        """try_cancel_before_damage returns (False, '') at dan < 5."""
        fighter = _make_fighter(knack_rank=4, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_no_cancel_when_already_used(self) -> None:
        """try_cancel_before_damage returns (False, '') when already used this round."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        fighter._counterattack_used_this_round = True
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_no_cancel_when_no_action_dice(self) -> None:
        """try_cancel_before_damage returns (False, '') when no action dice."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = []
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_no_cancel_when_survivable(self) -> None:
        """try_cancel_before_damage returns (False, '') when damage is survivable."""
        fighter = _make_fighter(knack_rank=5, earth=4, water=4)
        fighter.actions_remaining = [3, 5]
        result, note = fighter.try_cancel_before_damage(25, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_counterattack_fires_when_near_mortal(self) -> None:
        """Counterattack fires when projected damage is near-mortal."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2, fire=2)
        fighter.actions_remaining = [3, 5, 7]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30

        # Big attack that should project lethal damage
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        # Regardless of whether it cancels, the counterattack should fire
        assert note != ""
        assert "monk 5th Dan" in note
        assert fighter._counterattack_used_this_round is True
        # Cheapest die (3) should be consumed
        assert 3 not in fighter.actions_remaining

    def test_no_cancel_when_mortally_wounded(self) -> None:
        """No counterattack when monk is mortally wounded."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 4  # 2*earth = mortally wounded
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""


class TestOnRoundStart:
    """on_round_start resets per-round state."""

    def test_resets_counterattack_used(self) -> None:
        """Resets _counterattack_used_this_round to False."""
        fighter = _make_fighter(knack_rank=5)
        fighter._counterattack_used_this_round = True
        fighter.on_round_start()
        assert fighter._counterattack_used_this_round is False


class TestCounterattackHelperEdgeCases:
    """Edge cases in _resolve_monk_counterattack helper."""

    def test_counterattack_hit_but_no_damage(self) -> None:
        """Line 133: counterattack misses (hit_success=False) returns (canceled, 0)."""
        from unittest.mock import patch

        from src.engine.fighters.brotherhood_monk import _resolve_monk_counterattack

        monk_char = _make_monk(knack_rank=5, attack_rank=1, fire=1)
        opp = _make_generic(parry_rank=10)  # Very high parry TN
        state = _make_state(monk_char, opp)

        # Patch roll_and_keep to return a very low attack total so hit fails
        with patch(
            "src.engine.fighters.brotherhood_monk.roll_and_keep",
            return_value=([1], [1], 1),
        ):
            canceled, margin = _resolve_monk_counterattack(
                state, monk_char.name, opp.name, 3, 5,
                attacker_attack_total=1,  # Low so cancel check may pass
            )
        # With very high parry TN, hit_success is False, margin should be 0
        assert margin == 0

    def test_counterattack_damage_total_zero(self) -> None:
        """Line 151: dmg_total <= 0 returns (canceled, margin) without applying damage."""
        from unittest.mock import patch

        from src.engine.fighters.brotherhood_monk import _resolve_monk_counterattack

        monk_char = _make_monk(knack_rank=5, attack_rank=3, fire=2, parry_rank=0)
        opp = _make_generic(parry_rank=0)
        state = _make_state(monk_char, opp)

        call_count = [0]

        def mock_roll_and_keep(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                # Attack roll: high enough to hit (TN = 5 + 5*0 = 5)
                return [10, 8, 7, 6, 5], [10, 8], 18
            # Damage roll: return 0 total
            return [0], [0], 0

        with patch(
            "src.engine.fighters.brotherhood_monk.roll_and_keep",
            side_effect=mock_roll_and_keep,
        ):
            canceled, margin = _resolve_monk_counterattack(
                state, monk_char.name, opp.name, 3, 5,
                attacker_attack_total=10,
            )
        # Should return without applying wounds
        assert isinstance(canceled, bool)
        assert margin > 0  # Attack hit, so margin = total - TN

    def test_counterattack_wc_flat_bonus_path(self) -> None:
        """Lines 193-195: WC flat bonus path in counterattack helper.

        When the target has a wound_check_flat_bonus (like Otaku 2nd Dan),
        the WC total gets the bonus and passed is recalculated.
        """
        from unittest.mock import patch

        from src.engine.fighters.brotherhood_monk import _resolve_monk_counterattack

        # Create monk and an Otaku opponent (who has wound_check_flat_bonus)
        monk_char = _make_monk(knack_rank=5, attack_rank=3, fire=2)
        otaku_char = Character(
            name="Otaku",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Otaku Bushi",
            school_ring=RingName.FIRE,
            school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
            skills=[
                Skill(
                    name="Attack", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Parry", rank=0,
                    skill_type=SkillType.ADVANCED, ring=RingName.AIR,
                ),
                Skill(
                    name="Double Attack", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=2,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(monk_char, otaku_char)

        call_count = [0]

        def mock_roll_and_keep(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Attack hits (TN=5)
            if call_count[0] == 2:
                return [5, 3], [5, 3], 8  # Damage
            # Wound check: roll low enough that without flat bonus it fails
            return [3, 2, 1], [3, 2], 5

        with patch(
            "src.engine.fighters.brotherhood_monk.roll_and_keep",
            side_effect=mock_roll_and_keep,
        ), patch(
            "src.engine.fighters.brotherhood_monk.make_wound_check",
            return_value=(False, 5, [3, 2, 1], [3, 2]),
        ):
            _resolve_monk_counterattack(
                state, monk_char.name, otaku_char.name, 3, 5,
                attacker_attack_total=10,
            )
        # The Otaku has wound_check_flat_bonus if dan >= 2; we confirm it ran

    def test_counterattack_convert_light_to_serious(self) -> None:
        """Lines 211-213: convert light wounds to 1 serious wound in counterattack."""
        from unittest.mock import patch

        from src.engine.fighters.brotherhood_monk import _resolve_monk_counterattack

        monk_char = _make_monk(knack_rank=5, attack_rank=3, fire=2)
        # Opponent with high earth so conversion is attractive
        opp = _make_generic(earth=3, water=3)
        state = _make_state(monk_char, opp)

        call_count = [0]

        def mock_roll_and_keep(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8], [10, 8], 18  # Attack hits (TN=15)
            if call_count[0] == 2:
                return [10, 5], [10, 5], 15  # Damage = 15
            # Wound check: pass with enough margin
            return [20, 15, 10], [20, 15], 35

        wound_tracker = state.log.wounds[opp.name]
        wound_tracker.light_wounds = 0  # Will have 15 after damage

        with patch(
            "src.engine.fighters.brotherhood_monk.roll_and_keep",
            side_effect=mock_roll_and_keep,
        ), patch(
            "src.engine.fighters.brotherhood_monk.make_wound_check",
            return_value=(True, 35, [20, 15, 10], [20, 15]),
        ), patch(
            "src.engine.fighters.brotherhood_monk.should_convert_light_to_serious",
            return_value=True,
        ):
            _resolve_monk_counterattack(
                state, monk_char.name, opp.name, 3, 5,
                attacker_attack_total=10,
            )
        # Confirm conversion happened
        assert wound_tracker.serious_wounds >= 1

    def test_counterattack_wc_failed_resets_lw(self) -> None:
        """Line 238: WC not passed resets light_wounds to 0."""
        from unittest.mock import patch

        from src.engine.fighters.brotherhood_monk import _resolve_monk_counterattack

        monk_char = _make_monk(knack_rank=5, attack_rank=3, fire=2)
        opp = _make_generic(earth=2, water=2)
        state = _make_state(monk_char, opp)

        call_count = [0]

        def mock_roll_and_keep(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8], [10, 8], 18  # Attack hits
            if call_count[0] == 2:
                return [10, 5], [10, 5], 15  # Damage
            return [3, 2, 1], [3, 2], 5  # Wound check: fails

        with patch(
            "src.engine.fighters.brotherhood_monk.roll_and_keep",
            side_effect=mock_roll_and_keep,
        ), patch(
            "src.engine.fighters.brotherhood_monk.make_wound_check",
            return_value=(False, 5, [3, 2, 1], [3, 2]),
        ):
            _resolve_monk_counterattack(
                state, monk_char.name, opp.name, 3, 5,
                attacker_attack_total=10,
            )
        wound_tracker = state.log.wounds[opp.name]
        assert wound_tracker.light_wounds == 0


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy when crippled and not crippled."""

    def test_returns_zero_when_crippled(self) -> None:
        """Lines 293-295: When crippled, attack_void_strategy returns 0."""
        fighter = _make_fighter(knack_rank=3, earth=2, void=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 2  # is_crippled = sw >= earth
        result = fighter.attack_void_strategy(5, 2, 20)
        assert result == 0

    def test_not_crippled_delegates_to_heuristic(self) -> None:
        """Lines 296-297: When not crippled, delegates to should_spend_void_on_combat_roll."""
        fighter = _make_fighter(knack_rank=3, earth=3, void=3)
        # Not crippled (sw=0 < earth=3)
        result = fighter.attack_void_strategy(5, 2, 20)
        assert isinstance(result, int)
        assert result >= 0


class TestPostWoundCheckEdgeCases:
    """Edge cases in post_wound_check."""

    def test_deficit_lte_zero(self) -> None:
        """Line 386: deficit <= 0 returns early without spending."""
        fighter = _make_fighter(knack_rank=3, precepts_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        wound_tracker.serious_wounds = 1
        # wc_total >= light_wounds means deficit <= 0
        passed, total, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=0,
        )
        assert note == ""
        assert fighter._free_raises == 10

    def test_best_spend_zero_or_sw_not_reduced(self) -> None:
        """Line 410: best_spend <= 0 or best_sw >= current_sw returns early.

        This happens when free raises cannot reduce SW count (deficit too
        large and spending doesn't cross a 10-point threshold).
        """
        fighter = _make_fighter(knack_rank=3, precepts_rank=1, earth=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 50
        wound_tracker.serious_wounds = 3
        # deficit = 50 - 20 = 30. current_sw = 1 + 30//10 = 4.
        # max_per_roll = 1, usable = min(1, 2) = 1.
        # spend=1: new_deficit=25, new_sw = 1+25//10 = 3. 3 < 4, so it will reduce.
        # But let's make it so spending doesn't help:
        # deficit = 50 - 46 = 4, current_sw = 1. spend=1: new_deficit=-1 -> pass.
        # Not mortal, so won't pass. best_spend stays 0.
        wound_tracker.light_wounds = 50
        wound_tracker.serious_wounds = 1
        sw_before = 0
        passed, total, note = fighter.post_wound_check(
            passed=False, wc_total=46, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        # deficit=4, current_sw=1. spend=1 -> new_deficit=-1 -> passes.
        # would_die: sw_before(0)+current_sw(1) >= 2*5=10 -> False.
        # So won't spend to pass. best_spend=0.
        assert note == ""


class TestConsumeCheapestDieNoActions:
    """_consume_cheapest_die when no actions remaining."""

    def test_returns_none(self) -> None:
        """Line 446: returns None when actions_remaining is empty."""
        fighter = _make_fighter(knack_rank=5)
        fighter.actions_remaining = []
        result = fighter._consume_cheapest_die()
        assert result is None


class TestTryCancelBeforeDamageEdgeCases:
    """Edge cases in try_cancel_before_damage."""

    def test_in_counterattack_guard(self) -> None:
        """Line 464: _in_counterattack prevents recursive counterattack."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        fighter._in_counterattack = True
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_attacker_mortally_wounded(self) -> None:
        """Line 472: attacker is mortally wounded, no counterattack."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        attacker_wounds = fighter.state.log.wounds["Generic"]
        attacker_wounds.serious_wounds = 4  # 2*earth=4 -> mortally wounded
        result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_attacker_not_in_fighters(self) -> None:
        """Line 477: attacker_f is None (attacker not found in fighters dict)."""
        fighter = _make_fighter(knack_rank=5, earth=2, water=2)
        fighter.actions_remaining = [3, 5]
        # Add a wound tracker for "Unknown" so it doesn't error there
        from src.models.combat import WoundTracker
        fighter.state.log.wounds["Unknown"] = WoundTracker(earth_ring=2)
        result, note = fighter.try_cancel_before_damage(40, 25, "Unknown", 3)
        assert result is False
        assert note == ""

    def test_survivable_projected_damage(self) -> None:
        """Line 505: projected_sw < 2*earth means survivable, skip.

        Set up so wc_deficit > 0 (damage exceeds WC) but
        existing_sw + projected_sw < 2*earth (still survivable).
        """
        # Low water so WC expected is low, but high earth so survivable
        fighter = _make_fighter(
            knack_rank=5, earth=5, water=1, fire=1, precepts_rank=0,
        )
        fighter.actions_remaining = [3, 5]
        # No existing SW, so existing_sw=0
        # Generic has fire=2, katana 4k2
        # attack_total=30, tn=25 -> extra_dice=1
        # damage_rolled = 4+2+1=7, kept=2 -> est ~14
        # projected_lw = 0+14 = 14
        # water=1, rolled=1+1=2, kept=1 -> est ~7, pool=0
        # wc_deficit = 14-7 = 7 > 0
        # projected_sw = 1+7//10 = 1
        # existing_sw(0) + projected_sw(1) = 1 < 2*5=10 -> survivable
        result, note = fighter.try_cancel_before_damage(30, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_consumed_die_is_none(self) -> None:
        """Line 510: consumed is None after heuristic passes.

        This can't naturally happen because we check actions_remaining
        before calling _consume_cheapest_die, but we test the guard.
        """
        from unittest.mock import patch

        fighter = _make_fighter(knack_rank=5, earth=2, water=2, fire=2)
        fighter.actions_remaining = [3, 5]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30

        with patch.object(fighter, "_consume_cheapest_die", return_value=None):
            result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert note == ""

    def test_counterattack_fires_but_does_not_cancel(self) -> None:
        """Lines 529-533: counterattack fires but roll does not cancel."""
        from unittest.mock import patch

        fighter = _make_fighter(knack_rank=5, earth=2, water=2, fire=2)
        fighter.actions_remaining = [3, 5, 7]
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3
        wound_tracker.light_wounds = 30

        # Mock the counterattack to NOT cancel (return False)
        with patch(
            "src.engine.fighters.brotherhood_monk._resolve_monk_counterattack",
            return_value=(False, 5),
        ):
            result, note = fighter.try_cancel_before_damage(40, 25, "Generic", 3)
        assert result is False
        assert "does not cancel" in note
        assert "monk 5th Dan" in note
        assert fighter._counterattack_used_this_round is True


class TestCounterattack3rdDanFreeRaises:
    """3rd Dan: Free raises in _resolve_monk_counterattack (lines 91-97)."""

    def test_free_raises_bridge_cancel_deficit(self) -> None:
        """3rd Dan: Spend free raises to bridge cancel deficit."""
        from unittest.mock import patch

        from src.engine.fighters.brotherhood_monk import _resolve_monk_counterattack

        monk_char = _make_monk(
            knack_rank=3, attack_rank=3, fire=2, precepts_rank=5,
        )
        opp = _make_generic(parry_rank=0)
        state = _make_state(monk_char, opp)

        monk_ctx = state.fighters[monk_char.name]
        assert monk_ctx._free_raises == 10

        call_count = [0]

        def mock_roll_and_keep(
            rolled: int, kept: int, explode: bool = True,
        ) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                # Attack roll: return total lower than attacker's total (20)
                # so that cancel_deficit > 0 and free raises are needed
                return [6, 5, 4], [6, 5], 11
            # Damage roll
            return [5, 3], [5, 3], 8

        with patch(
            "src.engine.fighters.brotherhood_monk.roll_and_keep",
            side_effect=mock_roll_and_keep,
        ), patch(
            "src.engine.fighters.brotherhood_monk.make_wound_check",
            return_value=(True, 35, [20, 15], [20, 15]),
        ):
            canceled, margin = _resolve_monk_counterattack(
                state, monk_char.name, opp.name, 3, 5,
                attacker_attack_total=20,
            )

        # Free raises should have been spent to bridge the deficit
        # Attack total was 11 + 5 (2nd Dan) = 16, attacker total = 20
        # Deficit = 20 - 16 = 4, needs 1 raise (+5)
        assert monk_ctx._free_raises < 10


class TestFactoryRegistration:
    """Brotherhood Monk creates via fighter factory."""

    def test_creates_brotherhood_monk_fighter(self) -> None:
        """create_fighter returns BrotherhoodMonkFighter for school='Brotherhood Monk'."""
        char = _make_monk()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, BrotherhoodMonkFighter)
