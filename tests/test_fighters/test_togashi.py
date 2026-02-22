"""Tests for TogashiFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.togashi import TogashiFighter
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


def _make_togashi(
    name: str = "Togashi",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    precepts_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Togashi Ise Zumi character."""
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
        school="Togashi Ise Zumi",
        school_ring=RingName.VOID,
        school_knacks=["Athletics", "Conviction", "Dragon Tattoo"],
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
                name="Athletics", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.WATER,
            ),
            Skill(
                name="Conviction", rank=knack_rank,
                skill_type=SkillType.BASIC, ring=RingName.EARTH,
            ),
            Skill(
                name="Dragon Tattoo", rank=knack_rank,
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
    togashi_char: Character,
    opponent_char: Character,
    togashi_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [togashi_char.name, opponent_char.name],
        [togashi_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    t_void = (
        togashi_void if togashi_void is not None
        else togashi_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        togashi_char.name, state,
        char=togashi_char, weapon=KATANA, void_points=t_void,
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
    **ring_overrides: int,
) -> TogashiFighter:
    """Create a TogashiFighter with a full CombatState."""
    char = _make_togashi(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        precepts_rank=precepts_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, togashi_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, TogashiFighter)
    return fighter


class TestInitiativeExtraUnkept:
    """SA: Roll 1 extra initiative die."""

    def test_initiative_extra_unkept_returns_1(self) -> None:
        """SA grants 1 extra unkept initiative die."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.initiative_extra_unkept() == 1

    def test_initiative_extra_unkept_at_all_dans(self) -> None:
        """Extra unkept die is always 1 regardless of dan."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan)
            assert fighter.initiative_extra_unkept() == 1


class TestChooseAttack:
    """choose_attack always returns ('attack', 0)."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_attack_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on attack."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_attack_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0

    def test_attack_extra_rolled_at_dan_5(self) -> None:
        """Higher dans still get +1."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.attack_extra_rolled() == 1


class TestParryExtraRolled:
    """1st Dan: +1 rolled die on parry."""

    def test_parry_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on parry."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.parry_extra_rolled() == 1

    def test_parry_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.parry_extra_rolled() == 0

    def test_parry_extra_rolled_at_dan_5(self) -> None:
        """Higher dans still get +1."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter.parry_extra_rolled() == 1


class TestWoundCheckExtraRolled:
    """No extra rolled die on wound checks."""

    def test_wound_check_extra_rolled_is_zero(self) -> None:
        """No extra rolled die on wound checks at any dan."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan)
            assert fighter.wound_check_extra_rolled() == 0


class TestOnRoundStart:
    """on_round_start resets per-round state."""

    def test_resets_5th_dan_healed_flag(self) -> None:
        """Resets _5th_dan_healed_this_round to False."""
        fighter = _make_fighter(knack_rank=5)
        fighter._5th_dan_healed_this_round = True
        fighter.on_round_start()
        assert fighter._5th_dan_healed_this_round is False

    def test_starts_with_healed_false(self) -> None:
        """_5th_dan_healed_this_round starts False."""
        fighter = _make_fighter(knack_rank=5)
        assert fighter._5th_dan_healed_this_round is False


class TestPostWoundCheck5thDan:
    """5th Dan: Spend void to heal 2 SW when in danger."""

    def test_heals_when_sw_ge_earth(self) -> None:
        """5th Dan: Spend 1 void to heal 2 SW when SW >= earth."""
        fighter = _make_fighter(knack_rank=5, void_points=5, earth=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 2
        sw_before = 1

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert wound_tracker.serious_wounds == 0
        assert "togashi 5th Dan" in note
        assert "healed 2 SW" in note
        assert fighter._5th_dan_healed_this_round is True

    def test_no_heal_before_5th_dan(self) -> None:
        """No healing before 5th Dan."""
        fighter = _make_fighter(knack_rank=4, void_points=5, earth=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
        )
        assert wound_tracker.serious_wounds == 3
        assert note == ""

    def test_no_heal_when_already_healed_this_round(self) -> None:
        """No healing when already healed this round."""
        fighter = _make_fighter(knack_rank=5, void_points=5, earth=2)
        fighter._5th_dan_healed_this_round = True
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
        )
        assert wound_tracker.serious_wounds == 3
        assert note == ""

    def test_no_heal_when_sw_below_earth(self) -> None:
        """No healing when SW < earth (not in danger)."""
        fighter = _make_fighter(knack_rank=5, void_points=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 2  # < earth=3

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
        )
        assert wound_tracker.serious_wounds == 2
        assert note == ""

    def test_no_heal_when_no_void(self) -> None:
        """No healing when no void available."""
        fighter = _make_fighter(knack_rank=5, void_points=0, earth=2)
        fighter.worldliness_void = 0
        fighter.temp_void = 0
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 3

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
        )
        assert wound_tracker.serious_wounds == 3
        assert note == ""

    def test_heals_only_1_sw_when_only_1(self) -> None:
        """Heals only 1 SW when fighter has exactly 1 SW left (>= earth)."""
        fighter = _make_fighter(knack_rank=5, void_points=5, earth=1)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 1  # >= earth=1

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
        )
        assert wound_tracker.serious_wounds == 0
        assert "healed 1 SW" in note


class TestWorldlinessVoid:
    """Worldliness void pool initialization."""

    def test_worldliness_void_initialized(self) -> None:
        """worldliness_void equals the Worldliness skill rank."""
        for rank in range(6):
            fighter = _make_fighter(knack_rank=rank)
            assert fighter.worldliness_void == rank

    def test_worldliness_void_custom_rank(self) -> None:
        """worldliness_void can differ from knack_rank."""
        fighter = _make_fighter(knack_rank=3, worldliness_rank=5)
        assert fighter.worldliness_void == 5


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Togashi does not spend void on attack."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_may_spend(self) -> None:
        """Non-crippled Togashi may spend void on attack."""
        fighter = _make_fighter(knack_rank=1, void_points=5, fire=3, void=3)
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestFactoryRegistration:
    """Togashi Ise Zumi creates via fighter factory."""

    def test_creates_togashi_fighter(self) -> None:
        """create_fighter returns TogashiFighter for school='Togashi Ise Zumi'."""
        char = _make_togashi()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, TogashiFighter)
