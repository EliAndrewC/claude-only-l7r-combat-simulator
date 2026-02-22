"""Tests for YogoFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.yogo import YogoFighter
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


def _make_yogo(
    name: str = "Yogo Warden",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    da_rank: int | None = None,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Yogo Warden character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    wl_rank = worldliness_rank if worldliness_rank is not None else knack_rank
    effective_da = da_rank if da_rank is not None else knack_rank
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Yogo Warden",
        school_ring=RingName.EARTH,
        school_knacks=["Double Attack", "Iaijutsu", "Feint"],
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
                name="Double Attack", rank=effective_da,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Iaijutsu", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Feint", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
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
    yogo_char: Character,
    opponent_char: Character,
    yogo_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [yogo_char.name, opponent_char.name],
        [yogo_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    y_void = (
        yogo_void if yogo_void is not None
        else yogo_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        yogo_char.name, state,
        char=yogo_char, weapon=KATANA, void_points=y_void,
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
    da_rank: int | None = None,
    void_points: int | None = None,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> YogoFighter:
    """Create a YogoFighter with a full CombatState."""
    char = _make_yogo(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        da_rank=da_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, yogo_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, YogoFighter)
    return fighter


class TestChooseAttack:
    """choose_attack: DA preference, attack default, crippled fallback."""

    def test_prefers_da_when_available(self) -> None:
        """Prefers double_attack when DA rank > 0."""
        fighter = _make_fighter(knack_rank=1, da_rank=1)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "double_attack"
        assert void_spend == 0

    def test_falls_back_to_attack_when_no_da(self) -> None:
        """Falls back to attack when DA rank is 0."""
        fighter = _make_fighter(knack_rank=1, da_rank=0)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0

    def test_falls_back_to_attack_when_crippled(self) -> None:
        """Falls back to attack when crippled, even with DA."""
        fighter = _make_fighter(knack_rank=3, da_rank=3, earth=2)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 2  # >= earth_ring=2 -> crippled
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on attack."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_no_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestWeaponRolledBoost:
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


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_wound_check_extra_rolled_at_dan_1(self) -> None:
        """1st Dan grants +1 rolled die on wound check."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_wound_check_extra_rolled_at_dan_0(self) -> None:
        """No extra die before 1st Dan."""
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestWoundCheckFlatBonus:
    """2nd Dan: +5 on WC. 4th Dan: +5 per void on WC."""

    def test_bonus_at_dan_2(self) -> None:
        """2nd Dan grants +5 flat bonus."""
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5
        assert "yogo 2nd Dan" in note

    def test_no_bonus_at_dan_1(self) -> None:
        """No bonus before 2nd Dan."""
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""

    def test_4th_dan_void_bonus(self) -> None:
        """4th Dan: +5 per void spent on WC."""
        fighter = _make_fighter(knack_rank=4)
        fighter._wc_void_spent = 2
        bonus, note = fighter.wound_check_flat_bonus()
        # 5 (2nd Dan) + 10 (4th Dan: 2 void * 5) = 15
        assert bonus == 15
        assert "yogo 4th Dan" in note

    def test_4th_dan_no_extra_without_void_spent(self) -> None:
        """4th Dan: No extra bonus when no void spent on WC."""
        fighter = _make_fighter(knack_rank=4)
        fighter._wc_void_spent = 0
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5  # Only the 2nd Dan bonus


class TestPostWoundCheck:
    """SA: Temp void on serious wound."""

    def test_temp_void_gained_on_sw(self) -> None:
        """Gain temp void for each serious wound taken."""
        fighter = _make_fighter(knack_rank=1, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 2
        sw_before = 0

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert fighter.temp_void == 2
        assert "yogo SA" in note

    def test_no_temp_void_when_no_sw_gained(self) -> None:
        """No temp void when no new serious wounds taken."""
        fighter = _make_fighter(knack_rank=1, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 2
        sw_before = 2

        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=20, attacker_name="Generic",
            sw_before_wc=sw_before,
        )
        assert fighter.temp_void == 0
        assert note == ""

    def test_resets_wc_void_spent(self) -> None:
        """post_wound_check resets _wc_void_spent to 0."""
        fighter = _make_fighter(knack_rank=4)
        fighter._wc_void_spent = 2
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.serious_wounds = 0
        fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
            sw_before_wc=0,
        )
        assert fighter._wc_void_spent == 0


class TestOnVoidSpent:
    """3rd Dan: Void spending reduces LW."""

    def test_reduces_lw_at_dan_3(self) -> None:
        """3rd Dan: Reduce LW by 2*atk_rank per void."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 30
        note = fighter.on_void_spent(1, "attack")
        # Reduction = 2 * 3 * 1 = 6
        assert wound_tracker.light_wounds == 24
        assert "yogo 3rd Dan" in note
        assert "-6 LW" in note

    def test_no_reduction_before_dan_3(self) -> None:
        """No LW reduction before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 30
        note = fighter.on_void_spent(1, "attack")
        assert wound_tracker.light_wounds == 30
        assert note == ""

    def test_multiple_void_spent(self) -> None:
        """Multiple void spent increases reduction proportionally."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 30
        note = fighter.on_void_spent(2, "attack")
        # Reduction = 2 * 3 * 2 = 12
        assert wound_tracker.light_wounds == 18
        assert "-12 LW" in note

    def test_reduction_capped_at_current_lw(self) -> None:
        """Reduction cannot go below 0 LW."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 3
        note = fighter.on_void_spent(1, "attack")
        # Reduction = 2 * 3 * 1 = 6, but only 3 LW to reduce
        assert wound_tracker.light_wounds == 0
        assert "-3 LW" in note

    def test_no_reduction_when_no_lw(self) -> None:
        """No reduction when LW is 0."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 0
        note = fighter.on_void_spent(1, "attack")
        assert wound_tracker.light_wounds == 0
        assert note == ""


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


class TestAttackVoidStrategy:
    """attack_void_strategy: crippled returns 0, normal delegates."""

    def test_crippled_returns_zero(self) -> None:
        """When crippled, attack_void_strategy returns 0."""
        fighter = _make_fighter(knack_rank=3, da_rank=3, void_points=5, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(rolled=5, kept=3, tn=15)
        assert result == 0

    def test_not_crippled_delegates_to_utility(self) -> None:
        """When not crippled, delegates to should_spend_void_on_combat_roll."""
        fighter = _make_fighter(knack_rank=3, da_rank=3, void_points=5, earth=2)
        result = fighter.attack_void_strategy(rolled=5, kept=3, tn=15)
        assert isinstance(result, int)
        assert result >= 0


class TestWoundCheckVoidStrategy:
    """wound_check_void_strategy stores void spent for 4th Dan."""

    def test_stores_result_in_wc_void_spent(self) -> None:
        """wound_check_void_strategy stores result in _wc_void_spent."""
        fighter = _make_fighter(knack_rank=4, void_points=5, water=3)
        fighter.state.log.wounds[fighter.name].light_wounds = 40
        result = fighter.wound_check_void_strategy(
            water_ring=3, light_wounds=40,
        )
        assert isinstance(result, int)
        assert result >= 0
        assert fighter._wc_void_spent == result

    def test_low_dan_still_works(self) -> None:
        """wound_check_void_strategy works at lower dans (no tn_bonus)."""
        fighter = _make_fighter(knack_rank=1, void_points=3, water=2)
        fighter.state.log.wounds[fighter.name].light_wounds = 20
        result = fighter.wound_check_void_strategy(
            water_ring=2, light_wounds=20,
        )
        assert isinstance(result, int)
        assert fighter._wc_void_spent == result


class TestOnVoidSpentEdgeCases:
    """Edge cases for on_void_spent at 3rd Dan."""

    def test_attack_rank_zero_returns_empty(self) -> None:
        """3rd Dan with attack rank 0: reduction=0, returns ''."""
        fighter = _make_fighter(knack_rank=3, attack_rank=0)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 30
        note = fighter.on_void_spent(1, "attack")
        assert wound_tracker.light_wounds == 30
        assert note == ""

    def test_no_lw_actual_zero_returns_empty(self) -> None:
        """3rd Dan with positive reduction but 0 LW: actual=0, returns ''."""
        fighter = _make_fighter(knack_rank=3, attack_rank=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 0
        note = fighter.on_void_spent(1, "attack")
        assert wound_tracker.light_wounds == 0
        assert note == ""


class TestFactoryRegistration:
    """Yogo Warden creates via fighter factory."""

    def test_creates_yogo_fighter(self) -> None:
        """create_fighter returns YogoFighter for school='Yogo Warden'."""
        char = _make_yogo()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, YogoFighter)
