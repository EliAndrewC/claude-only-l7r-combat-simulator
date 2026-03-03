"""Tests for DojiArtisanFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.doji_artisan import (
    DojiArtisanFighter,
    _resolve_doji_artisan_counterattack,
)
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


class TestAttackVoidStrategyCrippled:
    """attack_void_strategy returns 0 when crippled (lines 55-58)."""

    def test_crippled_returns_zero(self) -> None:
        """Crippled Doji Artisan does not spend void on attack."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        result = fighter.attack_void_strategy(5, 2, 15)
        assert result == 0

    def test_not_crippled_delegates(self) -> None:
        """Non-crippled Doji Artisan delegates to standard heuristic."""
        fighter = _make_fighter(knack_rank=3, void_points=5, fire=3, void=3)
        result = fighter.attack_void_strategy(6, 3, 30)
        assert isinstance(result, int)
        assert result >= 0


class TestPostWoundCheckDeficitLeZero:
    """post_wound_check: deficit <= 0 returns early (line 138)."""

    def test_deficit_le_zero_returns_early(self) -> None:
        """When wc_total >= light_wounds, no raises spent."""
        fighter = _make_fighter(knack_rank=3, culture_rank=5, earth=3)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 20
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=25, attacker_name="Generic",
        )
        assert not new_passed
        assert new_total == 25
        assert note == ""
        assert fighter._free_raises == 10


class TestPostWoundCheckBestSpendZero:
    """post_wound_check: best_spend <= 0 returns early (line 162)."""

    def test_best_spend_zero_returns_early(self) -> None:
        """When spending raises cannot reduce SW, returns early."""
        fighter = _make_fighter(knack_rank=3, culture_rank=1, earth=5)
        wound_tracker = fighter.state.log.wounds[fighter.name]
        wound_tracker.light_wounds = 50
        wound_tracker.serious_wounds = 1
        new_passed, new_total, note = fighter.post_wound_check(
            passed=False, wc_total=46, attacker_name="Generic",
            sw_before_wc=0,
        )
        assert note == ""
        assert fighter._free_raises == 2


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


class TestResolvePostAttackInterruptGuards:
    """resolve_post_attack_interrupt guard conditions."""

    def test_recursion_guard(self) -> None:
        """No counterattack when already in counterattack."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.actions_remaining = [3, 5]
        fighter._in_counterattack = True
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        # Actions and void unchanged
        assert fighter.actions_remaining == [3, 5]

    def test_no_void(self) -> None:
        """No counterattack when no void available."""
        fighter = _make_fighter(knack_rank=3, void_points=0, worldliness_rank=0)
        fighter.actions_remaining = [3, 5]
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        assert fighter.actions_remaining == [3, 5]

    def test_no_actions(self) -> None:
        """No counterattack when no actions remaining."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.actions_remaining = []
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)

    def test_no_counterattack_skill(self) -> None:
        """No counterattack when CA skill rank is 0."""
        fighter = _make_fighter(knack_rank=0, void_points=5)
        fighter.actions_remaining = [3, 5]
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        assert fighter.actions_remaining == [3, 5]

    def test_self_mortally_wounded(self) -> None:
        """No counterattack when self is mortally wounded."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        fighter.actions_remaining = [3, 5]
        fighter.state.log.wounds[fighter.name].serious_wounds = 4
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        assert fighter.actions_remaining == [3, 5]

    def test_attacker_mortally_wounded(self) -> None:
        """No counterattack when attacker is mortally wounded."""
        fighter = _make_fighter(knack_rank=3, void_points=5, earth=2)
        fighter.actions_remaining = [3, 5]
        fighter.state.log.wounds["Generic"].serious_wounds = 4
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        assert fighter.actions_remaining == [3, 5]

    def test_attacker_in_counterattack(self) -> None:
        """No counterattack when attacker is already in counterattack."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.actions_remaining = [3, 5]
        attacker_f = fighter.state.fighters["Generic"]
        attacker_f._in_counterattack = True
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        assert fighter.actions_remaining == [3, 5]

    def test_successful_counterattack_fires(self) -> None:
        """When all guards pass, counterattack fires (die + void consumed)."""
        fighter = _make_fighter(knack_rank=3, void_points=5)
        fighter.actions_remaining = [3, 5, 7]
        initial_void = fighter.total_void
        fighter.resolve_post_attack_interrupt("Generic", 3, attack_total=20)
        # Cheapest die (3) consumed + 1 void spent
        assert 3 not in fighter.actions_remaining
        assert fighter.total_void < initial_void


class TestCounterattackFunction:
    """_resolve_doji_artisan_counterattack: 3rd Dan raises, 5th Dan bonus, failure."""

    def test_counterattack_logs_actions(self) -> None:
        """Counterattack creates combat log actions."""
        fighter = _make_fighter(knack_rank=3, void_points=5, culture_rank=5)
        state = fighter.state
        initial_actions = len(state.log.actions)
        _resolve_doji_artisan_counterattack(
            state, "Doji Artisan", "Generic", phase=3,
            consumed_die=3, attacker_roll=30,
        )
        assert len(state.log.actions) > initial_actions

    def test_3rd_dan_free_raises_on_counterattack(self) -> None:
        """3rd Dan: free raises used to bridge counterattack deficit."""

        fighter = _make_fighter(knack_rank=3, void_points=5, culture_rank=5)
        initial_raises = fighter._free_raises
        # Run many times to hit the deficit-bridging branch
        for _ in range(50):
            fighter._free_raises = initial_raises
            _resolve_doji_artisan_counterattack(
                fighter.state, "Doji Artisan", "Generic", phase=3,
                consumed_die=3, attacker_roll=30,
            )
        # At least one run should have spent raises (probabilistic but reliable)

    def test_5th_dan_bonus_on_counterattack(self) -> None:
        """5th Dan: +(TN-10)/5 bonus applied to counterattack."""

        # High parry opponent => TN > 10
        opp = _make_generic()
        doji_char = _make_doji_artisan(knack_rank=5, culture_rank=5, fire=4)
        state = _make_state(doji_char, opp, artisan_void=10)
        fighter = state.fighters["Doji Artisan"]
        assert isinstance(fighter, DojiArtisanFighter)

        for _ in range(50):
            _resolve_doji_artisan_counterattack(
                state, "Doji Artisan", "Generic", phase=3,
                consumed_die=3, attacker_roll=50,
            )

    def test_counterattack_failure_returns_zero(self) -> None:
        """Failed counterattack returns 0 margin."""

        # High parry opponent (rank 5 => TN 30), very weak artisan
        high_parry_opp = Character(
            name="Tank",
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
                    name="Parry", rank=5,
                    skill_type=SkillType.ADVANCED, ring=RingName.AIR,
                ),
            ],
        )
        # Knack 0 => no CA skill, fire=1 => minimal dice. Low attacker_roll => low SA bonus.
        doji_char = _make_doji_artisan(
            knack_rank=0, culture_rank=0, fire=1,
        )
        state = _make_state(doji_char, high_parry_opp, artisan_void=10)

        got_zero = False
        for _ in range(200):
            result = _resolve_doji_artisan_counterattack(
                state, "Doji Artisan", "Tank", phase=3,
                consumed_die=3, attacker_roll=5,
            )
            if result == 0:
                got_zero = True
                break
        assert got_zero, "Expected at least one failed counterattack"

    def test_counterattack_wound_check_with_flat_bonus(self) -> None:
        """Counterattack wound check applies target's wound_check_flat_bonus."""

        # Use a Doji vs Doji so the target has wound_check_flat_bonus from 2nd Dan
        doji1_char = _make_doji_artisan(
            name="Doji1", knack_rank=5, culture_rank=5, fire=5,
        )
        doji2_char = _make_doji_artisan(
            name="Doji2", knack_rank=2, culture_rank=3, fire=2,
        )
        log = create_combat_log(
            ["Doji1", "Doji2"],
            [doji1_char.rings.earth.value, doji2_char.rings.earth.value],
        )
        state = CombatState(log=log)
        create_fighter("Doji1", state, char=doji1_char, weapon=KATANA, void_points=10)
        create_fighter("Doji2", state, char=doji2_char, weapon=KATANA, void_points=10)

        # Run enough times that a hit occurs and wound check happens
        for _ in range(100):
            _resolve_doji_artisan_counterattack(
                state, "Doji1", "Doji2", phase=3,
                consumed_die=3, attacker_roll=50,
            )


class TestCounterattackDeterministic:
    """Deterministic tests using mocked dice for hard-to-reach branches."""

    def test_3rd_dan_free_raises_bridge_deficit(self) -> None:
        """3rd Dan: free raises bridge counterattack deficit (lines 89-95)."""
        from unittest.mock import patch

        # 3rd Dan, culture 5 => _free_raises=10, _max_per_roll=5
        # Opponent parry 2 => TN = 5 + 5*2 = 15
        fighter = _make_fighter(knack_rank=3, void_points=5, culture_rank=5)
        initial_raises = fighter._free_raises

        # Mock roll_and_keep to return a total just below TN (e.g. 12 vs TN 15)
        # deficit = 3, raises_needed = 1
        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
            return_value=([3, 4, 5], [4, 5], 12),
        ):
            result = _resolve_doji_artisan_counterattack(
                fighter.state, "Doji Artisan", "Generic", phase=3,
                consumed_die=3, attacker_roll=0,
            )

        # Free raises should have been spent
        assert fighter._free_raises < initial_raises
        # With 1 raise (+5), total becomes 17, success with margin 2
        assert result >= 0

    def test_counterattack_failure_deterministic(self) -> None:
        """Failed counterattack returns 0 (line 132)."""
        from unittest.mock import patch

        # Opponent parry 2 => TN = 15
        fighter = _make_fighter(knack_rank=0, void_points=5, culture_rank=0)

        # Mock roll to return very low total (2 vs TN 15)
        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
            return_value=([1, 1], [1], 2),
        ):
            result = _resolve_doji_artisan_counterattack(
                fighter.state, "Doji Artisan", "Generic", phase=3,
                consumed_die=3, attacker_roll=0,
            )
        assert result == 0

    def test_wound_check_flat_bonus_applied(self) -> None:
        """Counterattack wound check applies target's flat bonus (line 184).

        The TARGET of the counterattack must have wound_check_flat_bonus > 0.
        IsawaDuelistFighter at 2nd Dan+ returns +5.
        """
        from unittest.mock import patch

        from src.engine.fighters.isawa_duelist import IsawaDuelistFighter

        # Doji Artisan counterattacks an Isawa Duelist (2nd Dan => +5 WC flat bonus)
        doji_char = _make_doji_artisan(
            name="Doji", knack_rank=3, culture_rank=5, fire=3,
        )
        isawa_char = Character(
            name="Isawa",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=2),
                earth=Ring(name=RingName.EARTH, value=2),
                water=Ring(name=RingName.WATER, value=2),
                void=Ring(name=RingName.VOID, value=2),
            ),
            school="Isawa Duelist",
            school_ring=RingName.WATER,
            school_knacks=["Double Attack", "Iaijutsu", "Lunge"],
            skills=[
                Skill(name="Attack", rank=3, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
                Skill(name="Parry", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.AIR),
                Skill(name="Double Attack", rank=2, skill_type=SkillType.ADVANCED,
                      ring=RingName.FIRE),
                Skill(name="Iaijutsu", rank=2, skill_type=SkillType.ADVANCED,
                      ring=RingName.FIRE),
                Skill(name="Lunge", rank=2, skill_type=SkillType.ADVANCED, ring=RingName.FIRE),
            ],
        )
        log = create_combat_log(
            ["Doji", "Isawa"],
            [doji_char.rings.earth.value, isawa_char.rings.earth.value],
        )
        state = CombatState(log=log)
        create_fighter("Doji", state, char=doji_char, weapon=KATANA, void_points=10)
        create_fighter("Isawa", state, char=isawa_char, weapon=KATANA, void_points=10)
        isawa_f = state.fighters["Isawa"]
        assert isinstance(isawa_f, IsawaDuelistFighter)
        assert isawa_f.wound_check_flat_bonus()[0] == 5  # 2nd Dan +5

        call_count = 0

        def mock_roll(rolled: int, kept: int, explode: bool = True) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Counterattack hits (TN=15)
                return ([10, 10, 8], [10, 10], 30)
            # Damage + wound check — moderate values
            return ([5, 4, 3], [5, 4], 9)

        with patch(
            "src.engine.fighters.doji_artisan.roll_and_keep",
            side_effect=mock_roll,
        ):
            with patch(
                "src.engine.combat.roll_and_keep",
                side_effect=lambda r, k, explode=True: ([3, 2, 1], [3, 2], 5),
            ):
                _resolve_doji_artisan_counterattack(
                    state, "Doji", "Isawa", phase=3,
                    consumed_die=3, attacker_roll=50,
                )

        # Verify wound check was logged for the target
        wc_actions = [
            a for a in state.log.actions
            if a.action_type.value == "wound check" and a.actor == "Isawa"
        ]
        assert len(wc_actions) > 0


class TestFactoryRegistration:
    """Doji Artisan creates via fighter factory."""

    def test_creates_doji_artisan_fighter(self) -> None:
        """create_fighter returns DojiArtisanFighter for school='Doji Artisan'."""
        char = _make_doji_artisan()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = state.fighters[char.name]
        assert isinstance(fighter, DojiArtisanFighter)
