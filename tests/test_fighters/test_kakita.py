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


class TestFactoryCreatesKakita:
    """create_fighter returns KakitaFighter for Kakita Duelist."""

    def test_factory_returns_kakita_fighter(self) -> None:
        from src.engine.fighters import create_fighter

        char = _make_kakita()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, KakitaFighter)
