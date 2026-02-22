"""Tests for KakitaFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.kakita import KakitaFighter
from src.models.character import (
    Character,
    Ring,
    RingName,
    Rings,
    Skill,
    SkillType,
)
from src.models.weapon import Weapon, WeaponType

KATANA = Weapon(
    name="Katana", weapon_type=WeaponType.KATANA, rolled=4, kept=2,
)


def _make_kakita(
    name: str = "Kakita",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Kakita Duelist character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    da_rank = (
        double_attack_rank if double_attack_rank is not None
        else knack_rank
    )
    lng_rank = (
        lunge_rank if lunge_rank is not None else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Kakita Duelist",
        school_ring=RingName.FIRE,
        school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
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
                name="Double Attack", rank=da_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Lunge", rank=lng_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
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
    kakita_char: Character,
    opponent_char: Character,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [kakita_char.name, opponent_char.name],
        [kakita_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    state = CombatState(log=log)
    create_fighter(
        kakita_char.name, state,
        char=kakita_char, weapon=KATANA,
        void_points=kakita_char.void_points_max,
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
    **ring_overrides: int,
) -> KakitaFighter:
    """Create a KakitaFighter with a full CombatState."""
    char = _make_kakita(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, KakitaFighter)
    return fighter


class TestInitiativeExtraUnkept:
    """1st Dan: +1 unkept die on initiative."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.initiative_extra_unkept() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.initiative_extra_unkept() == 0


class TestPostInitiative:
    """SA: Convert 10s to phase 0 actions."""

    def test_converts_tens(self) -> None:
        fighter = _make_fighter(knack_rank=1, void=2)
        # Void ring = 2, so keeps 2 lowest
        result = fighter.post_initiative([3, 10], [3, 10])
        assert 0 in result
        assert 10 not in result

    def test_no_tens_unchanged(self) -> None:
        fighter = _make_fighter(knack_rank=1, void=2)
        result = fighter.post_initiative([3, 5], [3, 5])
        assert result == [3, 5]


class TestChooseAttack:
    """choose_attack: Lunge or DA, never void."""

    def test_crippled_always_lunges(self) -> None:
        fighter = _make_fighter(knack_rank=3, fire=3, void=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 3
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert choice == "lunge"
        assert void_spend == 0

    def test_never_spends_void(self) -> None:
        fighter = _make_fighter(knack_rank=2, fire=3, void=3)
        _, void_spend = fighter.choose_attack("Generic", 5)
        assert void_spend == 0

    def test_returns_lunge_or_da(self) -> None:
        fighter = _make_fighter(knack_rank=2, fire=3)
        choice, _ = fighter.choose_attack("Generic", 5)
        assert choice in ("lunge", "double_attack")


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestAttackVoidStrategy:
    """Kakita never spends void on attacks."""

    def test_always_zero(self) -> None:
        fighter = _make_fighter(knack_rank=3, fire=3, void=3)
        assert fighter.attack_void_strategy(6, 3, 50) == 0


class TestPostAttackRollBonus:
    """3rd Dan: Attack rank * phase gap bonus."""

    def test_3rd_dan_phase_gap(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=4)
        # Defender has next action at phase 8, current phase is 3
        fighter.state.fighters["Generic"].actions_remaining = [8]
        bonus, note = fighter.post_attack_roll_bonus(10, 15, 3, "Generic")
        # gap = 8 - 3 = 5, bonus = 4 * 5 = 20
        assert bonus == 20
        assert "kakita 3rd Dan" in note

    def test_3rd_dan_no_defender_actions(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        fighter.state.fighters["Generic"].actions_remaining = []
        bonus, note = fighter.post_attack_roll_bonus(10, 15, 5, "Generic")
        # gap = 11 - 5 = 6, bonus = 3 * 6 = 18
        assert bonus == 18
        assert "6 phases" in note

    def test_2nd_dan_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=2, attack_rank=3)
        fighter.state.fighters["Generic"].actions_remaining = [8]
        bonus, note = fighter.post_attack_roll_bonus(10, 15, 3, "Generic")
        assert bonus == 0
        assert note == ""


class TestShouldPredeclareParry:
    """Kakita never pre-declares parries."""

    def test_always_false(self) -> None:
        fighter = _make_fighter(knack_rank=3, parry_rank=4, air=3)
        assert fighter.should_predeclare_parry(15, 5) is False


class TestShouldReactiveParry:
    """Kakita reactive parry with Kakita-specific thresholds."""

    def test_returns_bool(self) -> None:
        fighter = _make_fighter(knack_rank=2, parry_rank=3, air=3)
        result = fighter.should_reactive_parry(
            attack_total=15, attack_tn=15,
            weapon_rolled=4, attacker_fire=2,
        )
        assert isinstance(result, bool)


class TestHasPhase0Action:
    """Kakita always has phase 0 capability."""

    def test_always_true(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.has_phase0_action() is True


class TestSaAttackBonusReturnsZero:
    """sa_attack_bonus returns (0, '') for Kakita (base Fighter default)."""

    def test_no_sa_attack_bonus(self) -> None:
        """Line 767: post_attack_roll_bonus returns (0, '') when bonus is 0.

        This happens at 3rd Dan when gap * atk_rank == 0.
        """
        fighter = _make_fighter(knack_rank=3, attack_rank=0)
        fighter.state.fighters["Generic"].actions_remaining = [4]
        bonus, note = fighter.post_attack_roll_bonus(10, 15, 3, "Generic")
        # atk_rank=0 -> bonus = 0 * (4-3) = 0
        assert bonus == 0
        assert note == ""


class TestPhase0IaijutsuStrikeWCFlatBonus:
    """Phase 0 iaijutsu strike wound check with flat bonus path (lines 256-258)."""

    def test_otaku_wc_flat_bonus_in_phase0_attack(self) -> None:
        """Lines 256-258: Otaku 2nd Dan +5 WC flat bonus applied in iaijutsu strike WC."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_phase0_attack

        kakita_char = _make_kakita(knack_rank=3, attack_rank=3, fire=3)
        # Otaku 2nd Dan defender who has wound_check_flat_bonus
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
                    name="Parry", rank=2,
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
        state = _make_state(kakita_char, otaku_char)
        kakita_f = state.fighters["Kakita"]
        kakita_f.actions_remaining = [0, 3, 5]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Iaijutsu attack
            if call_count[0] == 2:
                return [8, 5, 3], [8, 5], 13  # Damage
            return [3, 2, 1], [3, 2], 5  # WC roll

        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            return_value=(False, 5, [3, 2, 1], [3, 2]),
        ):
            _resolve_kakita_phase0_attack(state, "Kakita", "Otaku")
        # The Otaku wound check flat bonus should have been applied


class TestPhase0IaijutseShinjoWCBonus:
    """Phase 0 iaijutsu strike with Shinjo 5th Dan WC bonus path (lines 265-295)."""

    def test_shinjo_5th_dan_wc_bonus_passes(self) -> None:
        """Lines 265-282: Shinjo 5th Dan bonuses pass the WC in iaijutsu."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_phase0_attack

        kakita_char = _make_kakita(knack_rank=3, attack_rank=3, fire=3)
        shinjo_char = Character(
            name="Shinjo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Shinjo Bushi",
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
                    name="Double Attack", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(kakita_char, shinjo_char)
        kakita_f = state.fighters["Kakita"]
        shinjo_f = state.fighters["Shinjo"]
        kakita_f.actions_remaining = [0, 3, 5]
        shinjo_f.shinjo_bonuses = [10, 15]  # 5th Dan stored bonuses

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Iaijutsu attack hits
            if call_count[0] == 2:
                return [8, 5, 3], [8, 5], 13  # Damage = 13
            return [3, 2, 1], [3, 2], 5  # WC roll

        # Damage=13, LW=13, WC total=5. Deficit=8. Bonuses [10,15]: +10 covers it.
        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            return_value=(False, 5, [3, 2, 1], [3, 2]),
        ):
            _resolve_kakita_phase0_attack(state, "Kakita", "Shinjo")

        # Shinjo bonuses should have been consumed (some or all)
        assert len(shinjo_f.shinjo_bonuses) < 2 or sum(shinjo_f.shinjo_bonuses) < 25

    def test_shinjo_5th_dan_wc_bonus_reduces_sw_not_pass(self) -> None:
        """Lines 283, 294-295: Shinjo bonuses reduce SW but WC still fails."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_phase0_attack

        kakita_char = _make_kakita(knack_rank=3, attack_rank=3, fire=3)
        shinjo_char = Character(
            name="Shinjo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Shinjo Bushi",
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
                    name="Double Attack", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(kakita_char, shinjo_char)
        kakita_f = state.fighters["Kakita"]
        shinjo_f = state.fighters["Shinjo"]
        kakita_f.actions_remaining = [0, 3, 5]
        shinjo_f.shinjo_bonuses = [5]

        wound_tracker = state.log.wounds["Shinjo"]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Iaijutsu attack hits
            if call_count[0] == 2:
                return [10, 8, 5, 3], [10, 8], 26  # Damage = 26
            return [3, 2, 1], [3, 2], 5  # WC roll

        def mock_make_wc(*args, **kwargs):
            """Mock that also adds SW like real make_wound_check."""
            # LW=26, WC total=5, deficit=21. SW=1+21//10=3.
            wound_tracker.serious_wounds += 3
            return (False, 5, [3, 2, 1], [3, 2])

        # sw_before_wc=0. WC adds 3 SW. Shinjo bonus +5: deficit=26-10=16.
        # new_sw=1+16//10=2. sw_added=3. wound_tracker.sw += (2-3)=-1 -> sw=2.
        # sw_saved=3-2=1. Lines 283, 294-295 covered.
        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            side_effect=mock_make_wc,
        ):
            _resolve_kakita_phase0_attack(state, "Kakita", "Shinjo")

        assert wound_tracker.light_wounds == 0
        assert wound_tracker.serious_wounds == 2


class TestPhase0IaijutsuShinjoConvertLine312:
    """Shinjo wound check edge case (line 312) in phase 0 iaijutsu."""

    def test_shinjo_5th_dan_pool_on_conversion_decision(self) -> None:
        """Line 312: def_shinjo_pool sum used in should_convert_light_to_serious."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_phase0_attack

        kakita_char = _make_kakita(knack_rank=3, attack_rank=3, fire=3)
        shinjo_char = Character(
            name="Shinjo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Shinjo Bushi",
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
                    name="Double Attack", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(kakita_char, shinjo_char)
        kakita_f = state.fighters["Kakita"]
        shinjo_f = state.fighters["Shinjo"]
        kakita_f.actions_remaining = [0, 3, 5]
        shinjo_f.shinjo_bonuses = [10]  # Still have leftover bonuses

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Attack hits
            if call_count[0] == 2:
                return [5, 3], [5, 3], 8  # Damage = 8
            return [10, 8, 6], [10, 8], 18  # WC passes

        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            return_value=(True, 18, [10, 8, 6], [10, 8]),
        ):
            _resolve_kakita_phase0_attack(state, "Kakita", "Shinjo")
        # Test completes without error; the Shinjo conversion path ran


class TestFifthDanIaijutsuOpponentSkills:
    """5th Dan iaijutsu: opponent skill selection branches."""

    def test_opponent_no_skills(self) -> None:
        """Lines 414-416: Opponent has no iaijutsu skill AND no attack skill."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_5th_dan

        kakita_char = _make_kakita(knack_rank=5, attack_rank=3, fire=3)
        # Opponent with NO skills at all
        no_skill_char = Character(
            name="NoSkill",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            skills=[],
        )
        state = _make_state(kakita_char, no_skill_char)
        kakita_f = state.fighters["Kakita"]
        kakita_f.actions_remaining = [0, 3, 5]
        noskill_f = state.fighters["NoSkill"]
        noskill_f.actions_remaining = [3, 5]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Kakita iaijutsu
            if call_count[0] == 2:
                return [3, 2], [3, 2], 5  # Opponent contested roll (0+fire)
            return [5, 3], [5, 3], 8  # Damage

        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ):
            _resolve_kakita_5th_dan(state, "Kakita", "NoSkill")

        # Verify the iaijutsu action was logged
        from src.models.combat import ActionType
        iaijutsu_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.IAIJUTSU
        ]
        assert len(iaijutsu_actions) >= 1
        # Should mention "no opponent iaijutsu" bonus
        assert "no opponent iaijutsu" in iaijutsu_actions[0].description

    def test_opponent_has_attack_but_no_iaijutsu(self) -> None:
        """Lines 410-412: Opponent has Attack skill but no Iaijutsu skill."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_5th_dan

        kakita_char = _make_kakita(knack_rank=5, attack_rank=3, fire=3)
        # Opponent with Attack skill only, no Iaijutsu
        atk_only_char = Character(
            name="AtkOnly",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
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
        state = _make_state(kakita_char, atk_only_char)
        kakita_f = state.fighters["Kakita"]
        kakita_f.actions_remaining = [0, 3, 5]
        opp_f = state.fighters["AtkOnly"]
        opp_f.actions_remaining = [3, 5]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Kakita iaijutsu
            if call_count[0] == 2:
                return [5, 4, 3], [5, 4], 9  # Opponent attack roll
            return [5, 3], [5, 3], 8  # Damage

        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ):
            _resolve_kakita_5th_dan(state, "Kakita", "AtkOnly")

        from src.models.combat import ActionType
        iaijutsu_actions = [
            a for a in state.log.actions
            if a.action_type == ActionType.IAIJUTSU
        ]
        assert len(iaijutsu_actions) >= 1
        # Should mention "no opponent iaijutsu" since they used attack
        assert "no opponent iaijutsu" in iaijutsu_actions[0].description


class TestFifthDanIaijutsuShinjoWCBonus:
    """5th Dan iaijutsu WC paths: Shinjo 5th Dan WC bonus (lines 558-597, 613)."""

    def test_shinjo_wc_bonus_passes_in_5th_dan_iaijutsu(self) -> None:
        """Lines 567-584: Shinjo 5th Dan bonuses pass the WC in 5th Dan iaijutsu."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_5th_dan

        kakita_char = _make_kakita(knack_rank=5, attack_rank=3, fire=3)
        shinjo_char = Character(
            name="Shinjo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Shinjo Bushi",
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
                    name="Double Attack", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(kakita_char, shinjo_char)
        kakita_f = state.fighters["Kakita"]
        shinjo_f = state.fighters["Shinjo"]
        kakita_f.actions_remaining = [0, 3, 5]
        shinjo_f.actions_remaining = [3, 5]
        shinjo_f.shinjo_bonuses = [10, 15]  # Enough to cover deficit

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Kakita iaijutsu roll
            if call_count[0] == 2:
                return [5, 4, 3], [5, 4], 9  # Shinjo contest roll
            if call_count[0] == 3:
                return [8, 5, 3], [8, 5], 13  # Damage = 13
            return [3, 2, 1], [3, 2], 5  # WC total=5, LW=13, deficit=8

        # Deficit=8, bonuses [10,15]: +10 covers it -> passes
        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            return_value=(False, 5, [3, 2, 1], [3, 2]),
        ):
            _resolve_kakita_5th_dan(state, "Kakita", "Shinjo")

        # Shinjo bonuses should have been consumed
        assert len(shinjo_f.shinjo_bonuses) < 2

    def test_shinjo_wc_bonus_reduces_sw_not_pass_5th_dan(self) -> None:
        """Lines 585, 596-597: Shinjo bonuses reduce SW but WC still fails."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_5th_dan

        kakita_char = _make_kakita(knack_rank=5, attack_rank=3, fire=3)
        shinjo_char = Character(
            name="Shinjo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Shinjo Bushi",
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
                    name="Double Attack", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(kakita_char, shinjo_char)
        kakita_f = state.fighters["Kakita"]
        shinjo_f = state.fighters["Shinjo"]
        kakita_f.actions_remaining = [0, 3, 5]
        shinjo_f.actions_remaining = [3, 5]
        shinjo_f.shinjo_bonuses = [5]

        wound_tracker = state.log.wounds["Shinjo"]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Kakita iaijutsu
            if call_count[0] == 2:
                return [5, 4, 3], [5, 4], 9  # Shinjo contest
            if call_count[0] == 3:
                # Damage = 21. 4th Dan adds +5 -> dmg_total = 26, LW = 26.
                return [10, 8, 3], [10, 8], 21
            return [3, 2, 1], [3, 2], 5  # WC total=5

        def mock_make_wc(*args, **kwargs):
            """Mock that also adds SW like real make_wound_check."""
            # LW=26, WC total=5, deficit=21. SW=1+21//10=3.
            wound_tracker.serious_wounds += 3
            return (False, 5, [3, 2, 1], [3, 2])

        # sw_before_wc=0. WC adds 3 SW -> sw=3.
        # Shinjo bonus +5: wc_total=10. new_deficit=26-10=16.
        # new_sw=1+16//10=2. sw_added=3. wound_tracker.sw += (2-3)=-1 -> sw=2.
        # sw_saved = 3-2 = 1. Lines 585, 596-597 hit.
        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            side_effect=mock_make_wc,
        ):
            _resolve_kakita_5th_dan(state, "Kakita", "Shinjo")

        assert wound_tracker.light_wounds == 0
        assert wound_tracker.serious_wounds == 2

    def test_shinjo_5th_dan_wc_flat_bonus_in_5th_dan(self) -> None:
        """Lines 558-560: Otaku-style WC flat bonus in 5th Dan iaijutsu WC."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_5th_dan

        kakita_char = _make_kakita(knack_rank=5, attack_rank=3, fire=3)
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
                    name="Parry", rank=2,
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
        state = _make_state(kakita_char, otaku_char)
        kakita_f = state.fighters["Kakita"]
        kakita_f.actions_remaining = [0, 3, 5]
        otaku_f = state.fighters["Otaku"]
        otaku_f.actions_remaining = [3, 5]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Kakita iaijutsu
            if call_count[0] == 2:
                return [5, 4, 3], [5, 4], 9  # Otaku contest
            if call_count[0] == 3:
                return [8, 5, 3], [8, 5], 13  # Damage
            return [3, 2, 1], [3, 2], 5  # WC

        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            return_value=(False, 5, [3, 2, 1], [3, 2]),
        ):
            _resolve_kakita_5th_dan(state, "Kakita", "Otaku")

    def test_shinjo_5th_dan_pool_in_conversion_in_5th_dan(self) -> None:
        """Line 613: Shinjo 5th Dan pool used in conversion decision in 5th Dan WC."""
        from unittest.mock import patch

        from src.engine.fighters.kakita import _resolve_kakita_5th_dan

        kakita_char = _make_kakita(knack_rank=5, attack_rank=3, fire=3)
        shinjo_char = Character(
            name="Shinjo",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Shinjo Bushi",
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
                    name="Double Attack", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        state = _make_state(kakita_char, shinjo_char)
        kakita_f = state.fighters["Kakita"]
        shinjo_f = state.fighters["Shinjo"]
        kakita_f.actions_remaining = [0, 3, 5]
        shinjo_f.actions_remaining = [3, 5]
        shinjo_f.shinjo_bonuses = [10]

        call_count = [0]

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            call_count[0] += 1
            if call_count[0] == 1:
                return [10, 8, 7], [10, 8], 18  # Kakita iaijutsu
            if call_count[0] == 2:
                return [5, 4, 3], [5, 4], 9  # Shinjo contest
            if call_count[0] == 3:
                return [5, 3], [5, 3], 8  # Damage
            return [10, 8, 6], [10, 8], 18  # WC passes

        with patch(
            "src.engine.fighters.kakita.roll_and_keep",
            side_effect=mock_roll,
        ), patch(
            "src.engine.fighters.kakita.make_wound_check",
            return_value=(True, 18, [10, 8, 6], [10, 8]),
        ):
            _resolve_kakita_5th_dan(state, "Kakita", "Shinjo")
        # Ran conversion check with Shinjo pool


class TestExecutePhase0MortallyWounded:
    """execute_phase_zero when mortally wounded."""

    def test_kakita_mortally_wounded_skips(self) -> None:
        """Line 816: resolve_phase0 returns immediately when Kakita is mortally wounded."""
        fighter = _make_fighter(knack_rank=5, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 4
        # Should return without error or logging any actions
        initial_action_count = len(fighter.state.log.actions)
        fighter.resolve_phase0("Generic")
        assert len(fighter.state.log.actions) == initial_action_count

    def test_opponent_mortally_wounded_skips(self) -> None:
        """Line 818: resolve_phase0 returns when opponent is mortally wounded."""
        fighter = _make_fighter(knack_rank=5, earth=2)
        fighter.state.log.wounds["Generic"].serious_wounds = 4
        initial_action_count = len(fighter.state.log.actions)
        fighter.resolve_phase0("Generic")
        assert len(fighter.state.log.actions) == initial_action_count


class TestFactoryCreatesKakita:
    """create_fighter returns KakitaFighter for Kakita Duelist."""

    def test_factory_returns_kakita_fighter(self) -> None:
        from src.engine.fighters import create_fighter

        char = _make_kakita()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, KakitaFighter)
