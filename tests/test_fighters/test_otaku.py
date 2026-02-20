"""Tests for OtakuFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.otaku import OtakuFighter
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


def _make_otaku(
    name: str = "Otaku",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create an Otaku Bushi character."""
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
        school="Otaku Bushi",
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
    otaku_char: Character,
    opponent_char: Character,
    otaku_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [otaku_char.name, opponent_char.name],
        [otaku_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    o_void = (
        otaku_void if otaku_void is not None
        else otaku_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        otaku_char.name, state,
        char=otaku_char, weapon=KATANA, void_points=o_void,
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
    double_attack_rank: int | None = None,
    lunge_rank: int | None = None,
    void_points: int | None = None,
    **ring_overrides: int,
) -> OtakuFighter:
    """Create an OtakuFighter with a full CombatState."""
    char = _make_otaku(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        double_attack_rank=double_attack_rank,
        lunge_rank=lunge_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, otaku_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, OtakuFighter)
    return fighter


class TestLungeExtraRolled:
    """1st Dan: +1 rolled die on lunge attacks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.lunge_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.lunge_extra_rolled() == 0


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestWoundCheckFlatBonus:
    """2nd Dan: +5 flat bonus on wound checks."""

    def test_2nd_dan(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5
        assert "otaku 2nd Dan" in note

    def test_1st_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""

    def test_5th_dan(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 5


class TestPostDamageEffect:
    """3rd Dan: increase opponent's next X action dice."""

    def test_3rd_dan_increases_dice(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=3, fire=3)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [2, 4, 6]
        note = fighter.post_damage_effect("Generic")
        # increase = max(1, 6 - defender_fire(2)) = 4
        # X = attack_skill = 3, so increase all 3 dice by 4
        # [2+4, 4+4, 6+4] = [6, 8, 10]
        assert opp.actions_remaining == [6, 8, 10]
        assert "otaku 3rd Dan" in note

    def test_3rd_dan_caps_at_phase_10(self) -> None:
        fighter = _make_fighter(knack_rank=3, attack_rank=2, fire=3)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [7, 8, 9]
        fighter.post_damage_effect("Generic")
        # increase = max(1, 6-2) = 4, X = 2, so increase first 2
        # 7+4=11 -> capped to 10, 8+4=12 -> capped to 10
        assert opp.actions_remaining[0] == 10
        assert opp.actions_remaining[1] == 10
        assert opp.actions_remaining[2] == 9

    def test_2nd_dan_no_effect(self) -> None:
        fighter = _make_fighter(knack_rank=2)
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [2, 4, 6]
        note = fighter.post_damage_effect("Generic")
        assert opp.actions_remaining == [2, 4, 6]
        assert note == ""

    def test_3rd_dan_high_fire_opponent(self) -> None:
        """Opponent with Fire 5 only gets +1 increase."""
        opp_char = _make_generic(fire=5)
        state = _make_state(
            _make_otaku(knack_rank=3, attack_rank=2, fire=3), opp_char,
        )
        otaku_f = state.fighters["Otaku"]
        assert isinstance(otaku_f, OtakuFighter)
        opp_ctx = state.fighters["Generic"]
        opp_ctx.actions_remaining = [2, 4, 6]
        note = otaku_f.post_damage_effect("Generic")
        # increase = max(1, 6-5) = 1, X = 2
        assert opp_ctx.actions_remaining == [3, 5, 6]
        assert "otaku 3rd Dan" in note


class TestLungeDamageSurvivesParry:
    """4th Dan: lunge bonus die immune to parry reduction."""

    def test_4th_dan(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        assert fighter.lunge_damage_survives_parry() is True

    def test_3rd_dan(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        assert fighter.lunge_damage_survives_parry() is False


class TestShouldTradeDamageForWound:
    """5th Dan: ALWAYS trade 10 damage dice for 1 auto serious wound.

    The auto SW is not preventable by failed parry (unlike DA), so
    a 5th Dan Otaku always wants this on lunge/regular attacks.
    """

    def test_5th_dan_high_roll(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        should, dice, note = fighter.should_trade_damage_for_wound(14)
        assert should is True
        assert dice == 10
        assert "otaku 5th Dan" in note

    def test_5th_dan_exact_minimum(self) -> None:
        """Trade fires at exactly 10 dice (the minimum needed)."""
        fighter = _make_fighter(knack_rank=5)
        should, dice, note = fighter.should_trade_damage_for_wound(10)
        assert should is True
        assert dice == 10

    def test_5th_dan_below_minimum(self) -> None:
        """Cannot trade with fewer than 10 dice in pool."""
        fighter = _make_fighter(knack_rank=5)
        should, dice, note = fighter.should_trade_damage_for_wound(9)
        assert should is False
        assert dice == 0

    def test_4th_dan_no_trade(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        should, dice, note = fighter.should_trade_damage_for_wound(14)
        assert should is False

    def test_5th_dan_not_on_double_attack(self) -> None:
        """Trade should not be offered on double attacks."""
        fighter = _make_fighter(knack_rank=5)
        should, _, _ = fighter.should_trade_damage_for_wound(
            14, is_double_attack=True,
        )
        assert should is False, (
            "5th Dan trade must not fire on double attack"
        )


class TestResolvePostAttackInterrupt:
    """SA: counter-lunge after being attacked."""

    def test_has_dice_counter_lunges(self) -> None:
        fighter = _make_fighter(knack_rank=1, fire=3)
        fighter.actions_remaining = [3, 5, 7]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]
        initial_actions = len(fighter.actions_remaining)
        fighter.resolve_post_attack_interrupt("Generic", 5)
        # Should consume highest die (7) for counter-lunge
        assert len(fighter.actions_remaining) < initial_actions

    def test_counter_lunge_produces_attack_action(self) -> None:
        """The counter-lunge must resolve an attack even when the
        phase doesn't match any remaining die value."""
        fighter = _make_fighter(knack_rank=1, fire=3)
        # Otaku has dice at phases 3,4,5 but is attacked at phase 1
        fighter.actions_remaining = [3, 4, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [1, 2]
        fighter.resolve_post_attack_interrupt("Generic", 1)
        log = fighter.state.log
        lunge_actions = [
            a for a in log.actions
            if a.actor == "Otaku"
            and a.action_type.value == "lunge"
        ]
        assert len(lunge_actions) == 1, (
            f"Expected 1 counter-lunge action in log,"
            f" got {len(lunge_actions)}"
        )

    def test_counter_lunge_label_shows_sa(self) -> None:
        """Counter-lunge action label must indicate SA and consumed die."""
        fighter = _make_fighter(knack_rank=1, fire=3)
        fighter.actions_remaining = [3, 4, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [1, 2]
        fighter.resolve_post_attack_interrupt("Generic", 1)
        log = fighter.state.log
        lunge_actions = [
            a for a in log.actions
            if a.actor == "Otaku"
            and a.action_type.value == "lunge"
        ]
        assert len(lunge_actions) == 1
        action = lunge_actions[0]
        # Label should indicate SA counter-lunge and which die was used
        assert "SA" in action.label, (
            f"Counter-lunge label should mention SA, got: {action.label!r}"
        )
        assert "counter-lunge" in action.label, (
            f"Label should say counter-lunge, got: {action.label!r}"
        )
        assert "phase 5" in action.label, (
            f"Label should mention consumed die (phase 5),"
            f" got: {action.label!r}"
        )

    def test_counter_lunge_fires_after_miss(self) -> None:
        """Counter-lunge fires even when the triggering attack missed."""
        from src.engine.simulation import _resolve_attack

        fighter = _make_fighter(knack_rank=1, fire=3)
        fighter.actions_remaining = [3, 4, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [2]

        # Resolve an attack from opponent against Otaku
        # (low skill vs high parry → likely miss, but counter-lunge
        # should fire regardless of hit/miss)
        _resolve_attack(fighter.state, opp, fighter, 2)

        log = fighter.state.log
        lunge_actions = [
            a for a in log.actions
            if a.actor == "Otaku"
            and a.action_type.value == "lunge"
        ]
        assert len(lunge_actions) >= 1, (
            "Counter-lunge should fire after opponent's attack"
            " resolves, even if the attack missed"
        )

    def test_counter_lunge_fires_after_parry(self) -> None:
        """Counter-lunge fires even when the Otaku parried."""
        from src.engine.simulation import _resolve_attack

        fighter = _make_fighter(
            knack_rank=1, fire=3, attack_rank=3, parry_rank=3,
        )
        # Give Otaku dice: one to parry with, rest for counter-lunge
        fighter.actions_remaining = [2, 4, 6]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [2]

        _resolve_attack(fighter.state, opp, fighter, 2)

        log = fighter.state.log
        lunge_actions = [
            a for a in log.actions
            if a.actor == "Otaku"
            and a.action_type.value == "lunge"
        ]
        assert len(lunge_actions) >= 1, (
            "Counter-lunge should fire after opponent's attack"
            " resolves, even if the Otaku parried"
        )

    def test_no_dice_no_counter(self) -> None:
        fighter = _make_fighter(knack_rank=1, fire=3)
        fighter.actions_remaining = []
        # Should not error
        fighter.resolve_post_attack_interrupt("Generic", 5)

    def test_mortally_wounded_no_counter(self) -> None:
        fighter = _make_fighter(knack_rank=1, fire=3, earth=2)
        fighter.actions_remaining = [3, 5]
        # Make otaku mortally wounded
        fighter.state.log.wounds[fighter.name].serious_wounds = 4
        initial_actions = list(fighter.actions_remaining)
        fighter.resolve_post_attack_interrupt("Generic", 5)
        assert fighter.actions_remaining == initial_actions


class TestCounterLungeUsesLungeTN:
    """SA counter-lunge must use normal lunge TN, not DA TN."""

    def test_counter_lunge_tn_is_not_da_tn(self) -> None:
        """When choose_attack would pick DA, the forced counter-lunge
        must still use the normal attack TN (no +20)."""
        # High DA rank so choose_attack would return "double_attack"
        fighter = _make_fighter(
            knack_rank=5, attack_rank=5, double_attack_rank=5,
            fire=5, void=4,
        )
        opp = fighter.state.fighters["Generic"]
        # Give both sides dice so the attack resolves
        fighter.actions_remaining = [3, 5, 7]
        opp.actions_remaining = [4, 6]

        # Verify choose_attack would pick DA (the precondition for the bug)
        choice, _ = fighter.choose_attack("Generic", 5)
        assert choice == "double_attack", (
            "Precondition: choose_attack should pick DA for this fighter"
        )

        # Now trigger the counter-lunge SA
        fighter.resolve_post_attack_interrupt("Generic", 5)

        # Find the lunge action in the log
        log = fighter.state.log
        lunge_actions = [
            a for a in log.actions
            if a.actor == "Otaku"
            and a.action_type.value == "lunge"
        ]
        assert len(lunge_actions) == 1, (
            f"Expected 1 counter-lunge, got {len(lunge_actions)}"
        )
        lunge = lunge_actions[0]
        # Generic has Parry 2 -> base TN = 5 + 5*2 = 15
        # Bug: TN would be 15 + 20 = 35 (DA modifier leaked)
        assert lunge.tn == 15, (
            f"Counter-lunge TN should be 15 (normal lunge),"
            f" got {lunge.tn} (DA +20 leaked into forced lunge)"
        )


class TestChooseAttack:
    """choose_attack: prefers DA when viable, otherwise lunge. Never void."""

    def test_crippled_always_lunges(self) -> None:
        fighter = _make_fighter(knack_rank=3, fire=3, void=3)
        fighter.state.log.wounds[fighter.name].serious_wounds = 3
        result = fighter.choose_attack("Generic", 5)
        assert result[0] == "lunge"

    def test_returns_lunge_or_da(self) -> None:
        fighter = _make_fighter(knack_rank=2, fire=3, void=3)
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert choice in ("lunge", "double_attack")
        assert void_spend == 0  # Otaku never spends void on attacks

    def test_never_spends_void(self) -> None:
        fighter = _make_fighter(knack_rank=3, fire=4, void=4)
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert void_spend == 0


class TestOtakuParryReluctance:
    """Otaku should be reluctant to parry — save dice for counter-lunges."""

    def test_never_predeclares_parry(self) -> None:
        """Otaku never pre-declares parries (like Kakita)."""
        fighter = _make_fighter(
            knack_rank=3, parry_rank=4, fire=4, air=4,
        )
        # Even against a high attack TN, should not pre-declare
        assert fighter.should_predeclare_parry(40, 5) is False
        assert fighter.should_predeclare_parry(25, 3) is False

    def test_no_reactive_parry_on_low_damage(self) -> None:
        """Otaku skips reactive parry when expected damage is low (e.g. 9k2)."""
        fighter = _make_fighter(
            knack_rank=3, parry_rank=4, fire=4, air=4,
        )
        # 9k2 damage: weapon_rolled=4, attacker_fire=4, extra=1
        # attack_total=39, attack_tn=30 → extra_dice=1
        # damage_rolled = 4 + 4 + 1 = 9 → should NOT parry
        result = fighter.should_reactive_parry(
            attack_total=39, attack_tn=30,
            weapon_rolled=4, attacker_fire=4,
        )
        assert result is False, (
            "Otaku should not parry a 9k2 damage attack"
        )

    def test_reactive_parry_on_high_damage(self) -> None:
        """Otaku does parry when expected damage is very high."""
        fighter = _make_fighter(
            knack_rank=3, parry_rank=4, fire=4, air=4,
        )
        # 15k2 damage: weapon_rolled=4, attacker_fire=4, extra=7
        # attack_total=65, attack_tn=30 → extra_dice=7
        # damage_rolled = 4 + 4 + 7 = 15 → should parry
        result = fighter.should_reactive_parry(
            attack_total=65, attack_tn=30,
            weapon_rolled=4, attacker_fire=4,
        )
        assert result is True, (
            "Otaku should parry a very high damage attack"
        )


class TestFactoryCreatesOtaku:
    """create_fighter returns OtakuFighter for Otaku Bushi."""

    def test_factory_returns_otaku_fighter(self) -> None:
        char = _make_otaku()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, OtakuFighter)
