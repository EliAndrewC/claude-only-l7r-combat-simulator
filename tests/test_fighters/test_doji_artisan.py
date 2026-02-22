"""Tests for DojiArtisanFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.doji_artisan import DojiArtisanFighter
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


def _make_doji_artisan(
    name: str = "Doji Artisan",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    culture_rank: int = 5,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Doji Artisan character."""
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
        school="Doji Artisan",
        school_ring=RingName.WATER,
        school_knacks=["Counterattack", "Oppose Social", "Worldliness"],
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
                name="Culture", rank=culture_rank,
                skill_type=SkillType.BASIC, ring=RingName.AIR,
            ),
            Skill(
                name="Counterattack", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
            ),
            Skill(
                name="Oppose Social", rank=knack_rank,
                skill_type=SkillType.ADVANCED, ring=RingName.WATER,
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
    artisan_char: Character,
    opponent_char: Character,
    artisan_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [artisan_char.name, opponent_char.name],
        [artisan_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    a_void = (
        artisan_void if artisan_void is not None
        else artisan_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        artisan_char.name, state,
        char=artisan_char, weapon=KATANA, void_points=a_void,
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
    culture_rank: int = 5,
    void_points: int | None = None,
    worldliness_rank: int | None = None,
    **ring_overrides: int,
) -> DojiArtisanFighter:
    """Create a DojiArtisanFighter with a full CombatState."""
    char = _make_doji_artisan(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        culture_rank=culture_rank,
        worldliness_rank=worldliness_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, artisan_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, DojiArtisanFighter)
    return fighter


class TestChooseAttack:
    """choose_attack always returns ('attack', 0)."""

    def test_choose_attack_returns_attack(self) -> None:
        """choose_attack always returns ('attack', 0)."""
        fighter = _make_fighter(knack_rank=5)
        choice, void_spend = fighter.choose_attack("Generic", 3)
        assert choice == "attack"
        assert void_spend == 0


class TestAttackExtraRolled:
    """No extra rolled die on normal attacks."""

    def test_attack_extra_rolled_is_zero(self) -> None:
        """No extra rolled die on attacks at any dan."""
        for dan in range(6):
            fighter = _make_fighter(knack_rank=dan)
            assert fighter.attack_extra_rolled() == 0


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


class TestSAAttackBonus:
    """4th Dan: Phase bonus when target hasn't attacked this round."""

    def test_phase_bonus_at_dan_4(self) -> None:
        """4th Dan: +phase bonus when opponent hasn't attacked."""
        fighter = _make_fighter(knack_rank=4)
        fighter._opponent_attacked_this_round = False
        bonus, note = fighter.sa_attack_bonus(5)
        assert bonus == 5
        assert "doji 4th Dan" in note

    def test_no_bonus_when_opponent_attacked(self) -> None:
        """No bonus when opponent already attacked this round."""
        fighter = _make_fighter(knack_rank=4)
        fighter._opponent_attacked_this_round = True
        bonus, note = fighter.sa_attack_bonus(5)
        assert bonus == 0
        assert note == ""

    def test_no_bonus_before_dan_4(self) -> None:
        """No bonus before 4th Dan."""
        fighter = _make_fighter(knack_rank=3)
        fighter._opponent_attacked_this_round = False
        bonus, note = fighter.sa_attack_bonus(5)
        assert bonus == 0
        assert note == ""


class TestPostAttackRollBonus:
    """5th Dan: +TN bonus. 3rd Dan: free raises bridge deficit."""

    def test_5th_dan_tn_bonus(self) -> None:
        """5th Dan: +(TN - 10) / 5 bonus."""
        fighter = _make_fighter(knack_rank=5, culture_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        # (25 - 10) // 5 = 3
        assert bonus >= 3
        assert "doji 5th Dan" in note

    def test_5th_dan_no_bonus_at_tn_10(self) -> None:
        """No 5th Dan bonus when TN <= 10."""
        fighter = _make_fighter(knack_rank=5, culture_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 10, 3, "Generic")
        assert bonus == 0

    def test_3rd_dan_free_raises_bridge_deficit(self) -> None:
        """3rd Dan: free raises bridge attack deficit."""
        fighter = _make_fighter(knack_rank=3, culture_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(22, 25, 3, "Generic")
        assert bonus >= 5
        assert "doji 3rd Dan" in note
        assert fighter._free_raises < 10

    def test_3rd_dan_no_spend_when_hit(self) -> None:
        """Don't spend free raises if already hitting."""
        fighter = _make_fighter(knack_rank=3, culture_rank=5)
        bonus, note = fighter.post_attack_roll_bonus(30, 25, 3, "Generic")
        # 5th Dan not active (dan 3), already hitting -> no spend
        assert fighter._free_raises == 10

    def test_no_free_raises_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, culture_rank=5)
        assert fighter._free_raises == 0


class TestWCBonusPoolTotal:
    """3rd Dan: free raise pool for wound checks."""

    def test_wc_bonus_pool_at_dan_3(self) -> None:
        """wc_bonus_pool_total returns usable * 5."""
        fighter = _make_fighter(knack_rank=3, culture_rank=5)
        # min(10, 5) * 5 = 25
        assert fighter.wc_bonus_pool_total() == 25

    def test_wc_bonus_pool_before_dan_3(self) -> None:
        """No bonus pool before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, culture_rank=5)
        assert fighter.wc_bonus_pool_total() == 0


class TestPostWoundCheck:
    """3rd Dan: Spend free raises on failed WC. Track opponent attacked."""

    def test_tracks_opponent_attacked(self) -> None:
        """post_wound_check sets _opponent_attacked_this_round = True."""
        fighter = _make_fighter(knack_rank=1)
        assert fighter._opponent_attacked_this_round is False
        fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert fighter._opponent_attacked_this_round is True

    def test_spend_to_reduce_sw(self) -> None:
        """Spend raises to reduce serious wounds on failed WC."""
        fighter = _make_fighter(knack_rank=3, culture_rank=2, earth=3)
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
        fighter = _make_fighter(knack_rank=3, culture_rank=5, earth=2)
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
        fighter = _make_fighter(knack_rank=3, culture_rank=5)
        _, _, note = fighter.post_wound_check(
            passed=True, wc_total=50, attacker_name="Generic",
        )
        assert note == ""

    def test_no_spend_before_3rd_dan(self) -> None:
        """No free raise spending before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, culture_rank=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 45
        wound_tracker.serious_wounds = 3
        _, _, note = fighter.post_wound_check(
            passed=False, wc_total=24, attacker_name="Generic",
        )
        assert note == ""


class TestOnRoundStart:
    """on_round_start resets per-round state."""

    def test_resets_opponent_attacked(self) -> None:
        """Resets _opponent_attacked_this_round to False."""
        fighter = _make_fighter(knack_rank=1)
        fighter._opponent_attacked_this_round = True
        fighter.on_round_start()
        assert fighter._opponent_attacked_this_round is False


class TestFreeRaisePoolInit:
    """3rd Dan: Free raise pool initialization."""

    def test_free_raise_pool_at_3rd_dan(self) -> None:
        """Pool is 2 * culture_rank at 3rd Dan."""
        fighter = _make_fighter(knack_rank=3, culture_rank=5)
        assert fighter._free_raises == 10
        assert fighter._max_per_roll == 5

    def test_free_raise_pool_before_3rd_dan(self) -> None:
        """No free raises before 3rd Dan."""
        fighter = _make_fighter(knack_rank=2, culture_rank=5)
        assert fighter._free_raises == 0
        assert fighter._max_per_roll == 0


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


class TestFactoryRegistration:
    """Doji Artisan creates via fighter factory."""

    def test_creates_doji_artisan_fighter(self) -> None:
        """create_fighter returns DojiArtisanFighter for school='Doji Artisan'."""
        char = _make_doji_artisan()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, DojiArtisanFighter)
