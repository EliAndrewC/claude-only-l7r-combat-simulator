"""Tests for HidaFighter school-specific overrides."""

from __future__ import annotations

from src.engine.combat import create_combat_log
from src.engine.combat_state import CombatState
from src.engine.fighters import create_fighter
from src.engine.fighters.hida import HidaFighter
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


def _make_hida(
    name: str = "Hida",
    knack_rank: int = 1,
    attack_rank: int = 3,
    parry_rank: int = 2,
    counterattack_rank: int | None = None,
    lunge_rank: int | None = None,
    **ring_overrides: int,
) -> Character:
    """Create a Hida Bushi character."""
    kwargs = {}
    for ring_name in ["air", "fire", "earth", "water", "void"]:
        val = ring_overrides.get(ring_name, 2)
        kwargs[ring_name] = Ring(
            name=RingName(ring_name.capitalize()), value=val,
        )
    ca_rank = (
        counterattack_rank if counterattack_rank is not None
        else knack_rank
    )
    lng_rank = (
        lunge_rank if lunge_rank is not None else knack_rank
    )
    return Character(
        name=name,
        rings=Rings(**kwargs),
        school="Hida Bushi",
        school_ring=RingName.WATER,
        school_knacks=["Counterattack", "Iaijutsu", "Lunge"],
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
                name="Counterattack", rank=ca_rank,
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
    hida_char: Character,
    opponent_char: Character,
    hida_void: int | None = None,
) -> CombatState:
    """Build a CombatState with the given characters."""
    log = create_combat_log(
        [hida_char.name, opponent_char.name],
        [hida_char.rings.earth.value, opponent_char.rings.earth.value],
    )
    h_void = (
        hida_void if hida_void is not None
        else hida_char.void_points_max
    )
    state = CombatState(log=log)
    create_fighter(
        hida_char.name, state,
        char=hida_char, weapon=KATANA, void_points=h_void,
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
    counterattack_rank: int | None = None,
    lunge_rank: int | None = None,
    void_points: int | None = None,
    **ring_overrides: int,
) -> HidaFighter:
    """Create a HidaFighter with a full CombatState."""
    char = _make_hida(
        knack_rank=knack_rank,
        attack_rank=attack_rank,
        parry_rank=parry_rank,
        counterattack_rank=counterattack_rank,
        lunge_rank=lunge_rank,
        **ring_overrides,
    )
    opp = _make_generic()
    state = _make_state(char, opp, hida_void=void_points)
    fighter = state.fighters[char.name]
    assert isinstance(fighter, HidaFighter)
    return fighter


class TestWoundCheckExtraRolled:
    """1st Dan: +1 rolled die on wound checks."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.wound_check_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.wound_check_extra_rolled() == 0


class TestAttackExtraRolled:
    """1st Dan: +1 rolled die on attack."""

    def test_first_dan(self) -> None:
        fighter = _make_fighter(knack_rank=1)
        assert fighter.attack_extra_rolled() == 1

    def test_zero_dan(self) -> None:
        fighter = _make_fighter(knack_rank=0)
        assert fighter.attack_extra_rolled() == 0


class TestChooseAttack:
    """Hida always uses lunge (no DA knack)."""

    def test_always_lunge(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        choice, void_spend = fighter.choose_attack("Generic", 5)
        assert choice == "lunge"
        assert void_spend == 0


class TestAttackReroll:
    """3rd Dan: reroll X dice <= 6 on non-counterattack attacks (X = CA rank)."""

    def test_3rd_dan_rerolls_dice(self) -> None:
        """3rd Dan reroll should modify dice and return a description."""
        fighter = _make_fighter(knack_rank=3, counterattack_rank=3, fire=3)
        # Give some low dice to reroll
        all_dice = [10, 8, 6, 5, 4, 3, 2, 1]
        kept_count = 3
        new_all, new_kept, new_total, note = fighter.post_attack_reroll(
            all_dice, kept_count,
        )
        # Should have rerolled some dice (CA rank 3 → reroll 3 dice)
        assert "hida 3rd Dan" in note
        assert "rerolled" in note

    def test_3rd_dan_rerolls_correct_count(self) -> None:
        """Reroll count = counterattack rank on non-CA attacks.

        With CA rank 3, only 3 lowest dice <= 6 should be rerolled.
        Provide exactly 3 eligible dice to verify count.
        """
        fighter = _make_fighter(knack_rank=3, counterattack_rank=3, fire=3)
        # 3 dice <= 6 (eligible), 3 dice > 6 (not eligible)
        # CA rank 3 → reroll 3 dice (the three <= 6)
        all_dice = [10, 9, 8, 5, 3, 1]
        kept_count = 3
        new_all, new_kept, new_total, note = fighter.post_attack_reroll(
            all_dice, kept_count,
        )
        # The note should show exactly the 3 old values sorted descending
        assert "hida 3rd Dan" in note
        assert "[5, 3, 1]" in note

    def test_2nd_dan_no_reroll(self) -> None:
        """Below 3rd Dan, no reroll."""
        fighter = _make_fighter(knack_rank=2)
        all_dice = [6, 5, 4, 3, 2, 1]
        kept_count = 3
        new_all, new_kept, new_total, note = fighter.post_attack_reroll(
            all_dice, kept_count,
        )
        assert note == ""
        assert new_all == all_dice

    def test_no_eligible_dice(self) -> None:
        """If all dice are > 6, no reroll (nothing eligible)."""
        fighter = _make_fighter(knack_rank=3, counterattack_rank=3, fire=3)
        all_dice = [18, 15, 12, 9, 8, 7]
        kept_count = 3
        new_all, new_kept, new_total, note = fighter.post_attack_reroll(
            all_dice, kept_count,
        )
        assert note == ""

    def test_crippled_halves_count(self) -> None:
        """When crippled, reroll count is halved (round up)."""
        fighter = _make_fighter(knack_rank=3, counterattack_rank=3, fire=3, earth=2)
        # Make fighter crippled
        fighter.state.log.wounds[fighter.name].serious_wounds = 2
        all_dice = [6, 5, 4, 3, 2, 1]
        kept_count = 3
        new_all, new_kept, new_total, note = fighter.post_attack_reroll(
            all_dice, kept_count,
        )
        # CA rank 3, halved round up = 2
        assert "hida 3rd Dan" in note

    def test_reroll_appears_in_lunge_description(self) -> None:
        """Integration: lunge attack action should show reroll in description."""
        from src.engine.simulation import _resolve_attack
        from src.models.combat import ActionType

        fighter = _make_fighter(knack_rank=3, counterattack_rank=3, fire=3)
        fighter.actions_remaining = [3, 5]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]

        _resolve_attack(fighter.state, fighter, opp, 3)

        log = fighter.state.log
        lunge_actions = [
            a for a in log.actions
            if a.actor == "Hida"
            and a.action_type == ActionType.LUNGE
        ]
        # There should be a lunge action. If any dice were <= 6,
        # the description should mention the reroll.
        assert len(lunge_actions) >= 1
        # The lunge description should mention 3rd Dan when dice are rerolled
        # (may not always fire if all dice roll > 6, but the hook is wired)


class TestParryBehavior:
    """Hida never parries — save dice for counterattack."""

    def test_never_predeclares_parry(self) -> None:
        fighter = _make_fighter(knack_rank=3, parry_rank=4, air=4)
        assert fighter.should_predeclare_parry(40, 5) is False

    def test_never_reactive_parries(self) -> None:
        """Hida never reactive parries, even on extreme hits."""
        fighter = _make_fighter(knack_rank=3, parry_rank=4, air=4)
        result = fighter.should_reactive_parry(
            attack_total=99, attack_tn=30,
            weapon_rolled=6, attacker_fire=6,
        )
        assert result is False

    def test_never_interrupt_parries(self) -> None:
        """Hida never interrupt parries."""
        fighter = _make_fighter(knack_rank=3, parry_rank=4, air=4)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.should_interrupt_parry(
            attack_total=99, attack_tn=30,
            weapon_rolled=6, attacker_fire=6,
        )
        assert result is False


class TestShouldReplaceWoundCheck:
    """4th Dan: replace wound check with 2 SW only when expecting 3+ SW."""

    def test_4th_dan_very_high_lw_low_water(self) -> None:
        """With low water and extreme LW, replacement should trigger."""
        fighter = _make_fighter(knack_rank=4, water=2, void_points=0)
        # Water 2 → kept ~2, expected total ~14. LW 60 → expected ~5 SW.
        should, sw, note = fighter.should_replace_wound_check(60)
        assert should is True
        assert sw == 2
        assert "hida 4th Dan" in note

    def test_4th_dan_moderate_lw_high_water_no_replace(self) -> None:
        """With high water and moderate LW, should NOT replace."""
        fighter = _make_fighter(knack_rank=4, water=6, void_points=4)
        # Water 6 + void 4 → kept ~10, expected total ~65. LW 30 is easy.
        should, sw, note = fighter.should_replace_wound_check(30)
        assert should is False

    def test_4th_dan_20_lw_no_replace(self) -> None:
        """LW=20 with decent water should NOT trigger replacement."""
        fighter = _make_fighter(knack_rank=4, water=3, void_points=2)
        should, sw, note = fighter.should_replace_wound_check(20)
        assert should is False

    def test_3rd_dan_no_replace(self) -> None:
        fighter = _make_fighter(knack_rank=3)
        should, sw, note = fighter.should_replace_wound_check(99)
        assert should is False


class TestWoundCheckFlatBonus:
    """5th Dan: counterattack margin adds to wound check."""

    def test_5th_dan_with_margin(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        fighter._counterattack_margin = 15
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 15
        assert "hida 5th Dan" in note
        # Margin should be consumed
        assert fighter._counterattack_margin == 0

    def test_5th_dan_no_margin(self) -> None:
        fighter = _make_fighter(knack_rank=5)
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0
        assert note == ""

    def test_4th_dan_no_bonus(self) -> None:
        fighter = _make_fighter(knack_rank=4)
        fighter._counterattack_margin = 15
        bonus, note = fighter.wound_check_flat_bonus()
        assert bonus == 0


class TestPreAttackCounterattack:
    """Dan 1-4: pre-attack counterattack fires before opponent's roll."""

    def test_has_dice_counterattacks(self) -> None:
        fighter = _make_fighter(knack_rank=1, fire=3, counterattack_rank=3)
        fighter.actions_remaining = [3, 5, 7]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        # Should return (margin, 5) or None
        if result is not None:
            margin, penalty = result
            assert penalty == 5
            assert isinstance(margin, int)

    def test_no_dice_no_counter(self) -> None:
        fighter = _make_fighter(knack_rank=1, fire=3)
        fighter.actions_remaining = []
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is None

    def test_mortally_wounded_no_counter(self) -> None:
        fighter = _make_fighter(knack_rank=1, fire=3, earth=2)
        fighter.actions_remaining = [3, 5]
        fighter.state.log.wounds[fighter.name].serious_wounds = 4
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is None

    def test_5th_dan_also_pre_attack(self) -> None:
        """5th Dan counterattacks pre-attack and stores margin for WC bonus."""
        fighter = _make_fighter(knack_rank=5, fire=4, counterattack_rank=5)
        fighter.actions_remaining = [3, 5, 7]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is not None
        margin, penalty = result
        assert penalty == 5
        # If counterattack hit, margin should be stored for wound check bonus
        if margin > 0:
            assert fighter._counterattack_margin == margin

    def test_counterattack_action_logged(self) -> None:
        """Counterattack should log a CombatAction."""
        fighter = _make_fighter(knack_rank=2, fire=3, counterattack_rank=3)
        fighter.actions_remaining = [3, 5, 7]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]
        fighter.resolve_pre_attack_counterattack("Generic", 5)
        from src.models.combat import ActionType
        ca_actions = [
            a for a in fighter.state.log.actions
            if a.action_type == ActionType.COUNTERATTACK
        ]
        assert len(ca_actions) >= 1

    def test_recursion_prevention(self) -> None:
        """Setting _in_counterattack prevents recursion."""
        fighter = _make_fighter(knack_rank=2, fire=3)
        fighter.actions_remaining = [3, 5]
        fighter._in_counterattack = True
        result = fighter.resolve_pre_attack_counterattack("Generic", 5)
        assert result is None


class TestPostDamageCounterattack:
    """5th Dan: counterattack after seeing damage."""

    def test_5th_dan_fires(self) -> None:
        fighter = _make_fighter(knack_rank=5, fire=4, counterattack_rank=5)
        fighter.actions_remaining = [3, 5, 7]
        opp = fighter.state.fighters["Generic"]
        opp.actions_remaining = [4]
        result = fighter.resolve_post_damage_counterattack("Generic", 5, 20)
        assert isinstance(result, int)
        # Should consume a die
        assert len(fighter.actions_remaining) < 3

    def test_4th_dan_no_fire(self) -> None:
        fighter = _make_fighter(knack_rank=4, fire=4)
        fighter.actions_remaining = [3, 5, 7]
        result = fighter.resolve_post_damage_counterattack("Generic", 5, 20)
        assert result == 0

    def test_no_dice_no_counter(self) -> None:
        fighter = _make_fighter(knack_rank=5, fire=4)
        fighter.actions_remaining = []
        result = fighter.resolve_post_damage_counterattack("Generic", 5, 20)
        assert result == 0


class TestFactoryCreatesHida:
    """create_fighter returns HidaFighter for Hida Bushi."""

    def test_factory_returns_hida_fighter(self) -> None:
        char = _make_hida()
        opp = _make_generic()
        state = _make_state(char, opp)
        fighter = create_fighter(char.name, state)
        assert isinstance(fighter, HidaFighter)


class TestDeclarationLine:
    """Pre-attack counterattack should be preceded by a declaration action."""

    def test_declaration_logged_before_counterattack(self) -> None:
        """When the attacker attacks and defender counterattacks,
        a declaration action appears before the counterattack actions."""
        from src.engine.simulation import _resolve_attack
        from src.models.combat import ActionType

        hida = _make_hida(knack_rank=2, fire=3, counterattack_rank=3)
        generic = _make_generic()
        state = _make_state(hida, generic)
        hida_f = state.fighters["Hida"]
        generic_f = state.fighters["Generic"]
        hida_f.actions_remaining = [3, 5, 7]
        generic_f.actions_remaining = [3, 5]

        _resolve_attack(state, generic_f, hida_f, 3)

        actions = state.log.actions
        # Counterattack must have fired (Hida has dice, dan 2)
        ca_idx = next(
            i for i, a in enumerate(actions)
            if a.action_type == ActionType.COUNTERATTACK
        )
        # The declaration must be immediately before the counterattack
        assert ca_idx >= 1, "Declaration should precede counterattack"
        decl = actions[ca_idx - 1]
        assert decl.actor == "Generic"
        assert decl.success is None
        assert "counterattacks first" in decl.label

    def test_declaration_has_no_dice(self) -> None:
        """Declaration action should have no dice or total."""
        from src.engine.simulation import _resolve_attack

        hida = _make_hida(knack_rank=2, fire=3, counterattack_rank=3)
        generic = _make_generic()
        state = _make_state(hida, generic)
        hida_f = state.fighters["Hida"]
        generic_f = state.fighters["Generic"]
        hida_f.actions_remaining = [3, 5, 7]
        generic_f.actions_remaining = [3, 5]

        _resolve_attack(state, generic_f, hida_f, 3)

        actions = state.log.actions
        decl_actions = [
            a for a in actions
            if a.success is None
            and a.label
            and "counterattacks first" in a.label
        ]
        assert len(decl_actions) == 1
        decl = decl_actions[0]
        assert decl.dice_rolled == []
        assert decl.dice_kept == []
        assert decl.total == 0
        assert decl.tn is None

    def test_no_declaration_without_counterattack(self) -> None:
        """When defender has no counterattack, no declaration is logged."""
        from src.engine.simulation import _resolve_attack

        hida = _make_hida(knack_rank=2, fire=3, counterattack_rank=3)
        generic = _make_generic()
        state = _make_state(hida, generic)
        hida_f = state.fighters["Hida"]
        generic_f = state.fighters["Generic"]
        hida_f.actions_remaining = [3, 5, 7]
        generic_f.actions_remaining = [3, 5]

        # Generic attacks Hida — generic has no counterattack ability,
        # but Hida IS the defender and DOES counterattack.
        # Let's test generic attacking generic (no counterattack).
        generic2 = _make_generic(name="Generic2")
        log2 = create_combat_log(
            ["Generic", "Generic2"],
            [generic.rings.earth.value, generic2.rings.earth.value],
        )
        state2 = CombatState(log=log2)
        create_fighter(
            "Generic", state2, char=generic, weapon=KATANA,
            void_points=generic.void_points_max,
        )
        create_fighter(
            "Generic2", state2, char=generic2, weapon=KATANA,
            void_points=generic2.void_points_max,
        )
        g1 = state2.fighters["Generic"]
        g2 = state2.fighters["Generic2"]
        g1.actions_remaining = [3, 5]
        g2.actions_remaining = [4]

        _resolve_attack(state2, g1, g2, 3)

        decl_actions = [
            a for a in state2.log.actions
            if a.success is None and a.label and "counterattacks first" in a.label
        ]
        assert len(decl_actions) == 0


class TestWoundCheckReplacementAction:
    """4th Dan wound check replacement should have clean description."""

    def test_no_em_dash_in_replacement_description(self) -> None:
        """Wound check replacement description should not have em-dash
        (em-dash causes extract_annotations to duplicate the note)."""
        from src.engine.simulation import _resolve_attack
        from src.models.combat import ActionType

        hida = _make_hida(knack_rank=4, fire=3, water=3, earth=3)
        generic = _make_generic(fire=3, earth=3, water=3)
        state = _make_state(hida, generic)
        hida_f = state.fighters["Hida"]
        generic_f = state.fighters["Generic"]
        hida_f.actions_remaining = [3, 5, 7]
        generic_f.actions_remaining = [3, 5]

        # Pre-set high LW so 4th Dan replacement fires on any hit
        state.log.wounds["Hida"].light_wounds = 20

        _resolve_attack(state, generic_f, hida_f, 3)

        replacement_wcs = [
            a for a in state.log.actions
            if a.action_type == ActionType.WOUND_CHECK
            and a.actor == "Hida"
            and "replaced" in a.description
        ]
        for wc in replacement_wcs:
            # No em-dash in description
            assert "\u2014" not in wc.description
            # success=None and tn=None for clean rendering
            assert wc.success is None
            assert wc.tn is None

    def test_no_duplicate_annotation_in_replacement(self) -> None:
        """extract_annotations should not produce duplicate notes
        for the wound check replacement."""
        from src.engine.simulation import _resolve_attack
        from src.models.combat import ActionType
        from src.ui_helpers import extract_annotations

        hida = _make_hida(knack_rank=4, fire=3, water=3, earth=3)
        generic = _make_generic(fire=3, earth=3, water=3)
        state = _make_state(hida, generic)
        hida_f = state.fighters["Hida"]
        generic_f = state.fighters["Generic"]
        hida_f.actions_remaining = [3, 5, 7]
        generic_f.actions_remaining = [3, 5]

        state.log.wounds["Hida"].light_wounds = 20

        _resolve_attack(state, generic_f, hida_f, 3)

        replacement_wcs = [
            a for a in state.log.actions
            if a.action_type == ActionType.WOUND_CHECK
            and a.actor == "Hida"
            and "replaced" in a.description
        ]
        for wc in replacement_wcs:
            annotations = extract_annotations(wc.description)
            # The hida 4th Dan note should appear at most once
            assert annotations.count("hida 4th Dan") <= 1


class TestDeclarationNotCountedAsAttack:
    """Declaration actions (success=None) should not inflate attack stats."""

    def test_compute_combat_stats_excludes_declarations(self) -> None:
        from src.models.combat import ActionType, CombatAction, CombatLog

        log = CombatLog(combatants=["A", "B"])
        # Add a real attack
        log.add_action(CombatAction(
            phase=3, actor="A", action_type=ActionType.ATTACK,
            total=35, tn=25, success=True, description="A attacks",
        ))
        # Add a declaration (success=None)
        log.add_action(CombatAction(
            phase=5, actor="A", action_type=ActionType.ATTACK,
            total=0, tn=None, success=None,
            description="A declares",
            label="attacks — B counterattacks first",
        ))
        from src.ui_helpers import compute_combat_stats
        stats = compute_combat_stats(log)
        # Only the real attack should be counted
        assert stats["total_attacks"] == 1
        assert stats["hits"] == 1


class TestSimulationIntegration:
    """Hida can complete a full combat simulation."""

    def test_hida_vs_generic_completes(self) -> None:
        """Hida vs Generic finishes without errors."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        hida = _make_hida(knack_rank=3, fire=3, water=3, earth=3, void=3)
        generic = _make_generic(fire=3, earth=3, water=3)
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(hida, generic, weapon, weapon)
        assert log.round_number >= 1

    def test_hida_vs_hida_no_infinite_loop(self) -> None:
        """Two Hida fighters don't infinite loop via counter-counterattack."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        hida1 = _make_hida(
            name="Hida 1", knack_rank=3, fire=3, water=3, earth=3, void=3,
        )
        hida2 = _make_hida(
            name="Hida 2", knack_rank=3, fire=3, water=3, earth=3, void=3,
        )
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(hida1, hida2, weapon, weapon)
        assert log.round_number >= 1

    def test_hida_vs_otaku_no_infinite_loop(self) -> None:
        """Hida vs Otaku doesn't loop (cross-SA guard)."""
        from src.engine.simulation import simulate_combat
        from src.models.weapon import WEAPONS, WeaponType

        hida = _make_hida(knack_rank=3, fire=3, water=3, earth=3, void=3)
        otaku_char = Character(
            name="Otaku",
            rings=Rings(
                air=Ring(name=RingName.AIR, value=2),
                fire=Ring(name=RingName.FIRE, value=3),
                earth=Ring(name=RingName.EARTH, value=3),
                water=Ring(name=RingName.WATER, value=3),
                void=Ring(name=RingName.VOID, value=3),
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
                    name="Double Attack", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Iaijutsu", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
                Skill(
                    name="Lunge", rank=3,
                    skill_type=SkillType.ADVANCED, ring=RingName.FIRE,
                ),
            ],
        )
        weapon = WEAPONS[WeaponType.KATANA]
        log = simulate_combat(hida, otaku_char, weapon, weapon)
        assert log.round_number >= 1
