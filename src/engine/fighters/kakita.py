"""KakitaFighter: Kakita Duelist school-specific overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState

from src.engine.combat import make_wound_check
from src.engine.dice import roll_and_keep
from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    format_pool_with_overflow,
    select_shinjo_wc_bonuses,
    should_convert_light_to_serious,
    should_spend_void_on_wound_check,
    void_spent_label,
)
from src.models.character import Character
from src.models.combat import ActionType, CombatAction
from src.models.weapon import Weapon


def _kakita_attack_choice(
    lunge_rank: int,
    double_attack_rank: int,
    fire_ring: int,
    defender_parry: int,
    dan: int,
    is_crippled: bool,
    known_bonus: int = 0,
) -> str:
    """Decide whether Kakita uses Lunge or Double Attack (never spends void).

    Returns:
        "lunge" or "double_attack".
    """
    if is_crippled or double_attack_rank <= 0:
        return "lunge"

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    first_dan_bonus = 1 if dan >= 1 else 0

    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = estimate_roll(da_rolled, da_kept) + known_bonus

    if da_expected >= da_tn * 0.85:
        return "double_attack"

    return "lunge"


def _kakita_should_phase0_attack(
    dan: int,
    attack_skill: int,
    phase0_count: int,
    total_dice: int,
    defender_next_phase: int,
) -> bool:
    """Decide whether to make a Phase 0 iaijutsu attack.

    If the Kakita has a phase 0 die (from rolling a 10 on initiative), the
    attack costs only 1 die — always worth it.  Without a phase 0 die, the
    Kakita can still interrupt-attack at phase 0 by spending 2 dice.

    The Kakita is a highly offensive school — phase 0 attacks are their
    signature ability and should be used aggressively.

    Args:
        dan: Kakita's dan level.
        attack_skill: Kakita's Attack skill rank.
        phase0_count: Number of phase 0 dice.
        total_dice: Total remaining action dice.
        defender_next_phase: Defender's next action phase (11 if none).

    Returns:
        True if the Kakita should make a phase 0 attack.
    """
    # With a phase 0 die: costs only 1 die — always attack
    if phase0_count > 0:
        return True

    # Interrupt (no phase 0 die): costs 2 highest dice
    if total_dice < 2:
        return False

    # Still always attack — striking before the opponent acts is the
    # Kakita's defining advantage, even at the cost of 2 dice.
    return True


def _resolve_kakita_phase0_attack(
    state: "CombatState",
    attacker_name: str,
    defender_name: str,
) -> None:
    """Execute a Phase 0 iaijutsu interrupt attack.

    Consumes 2 dice (the phase 0 die + lowest remaining die) and resolves
    an iaijutsu attack at phase 0.
    """
    log = state.log
    atk_ctx = state.fighters[attacker_name]
    def_ctx = state.fighters[defender_name]
    attacker: Character = atk_ctx.char
    defender: Character = def_ctx.char

    dan = attacker.dan

    # Consume dice: 1 die if using a phase 0 action, 2 highest dice if interrupting
    has_phase0 = 0 in atk_ctx.actions_remaining
    if has_phase0:
        atk_ctx.actions_remaining.remove(0)
    else:
        highest = sorted(atk_ctx.actions_remaining, reverse=True)[:2]
        for die in highest:
            atk_ctx.actions_remaining.remove(die)

    # Get skill ranks
    iaijutsu_skill = attacker.get_skill("Iaijutsu")
    iaijutsu_rank = iaijutsu_skill.rank if iaijutsu_skill else 0
    atk_skill = attacker.get_skill("Attack")
    atk_rank = atk_skill.rank if atk_skill else 0
    def_parry_skill = defender.get_skill("Parry")
    def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

    # Roll iaijutsu + Fire (keep Fire)
    fire_ring = attacker.rings.fire.value
    rolled = iaijutsu_rank + fire_ring
    kept = fire_ring

    # 1st Dan: +1 rolled die on iaijutsu
    if dan >= 1:
        rolled += 1

    attacker_crippled = log.wounds[attacker_name].is_crippled
    explode = not attacker_crippled

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=explode)

    # 2nd Dan: free raise (+5 to total)
    bonus_note = ""
    if dan >= 2:
        total += 5
        bonus_note += " (kakita 2nd Dan: free raise +5)"

    # 3rd Dan: + attack_skill * defender_next_phase
    defender_actions = sorted(def_ctx.actions_remaining)
    defender_future = [a for a in defender_actions if a > 0]
    defender_next = defender_future[0] if defender_future else 11
    if dan >= 3:
        gap = defender_next
        kakita_bonus = atk_rank * gap
        if kakita_bonus > 0:
            total += kakita_bonus
            phase_word = 'phase' if gap == 1 else 'phases'
            bonus_note += (
                f" (kakita 3rd Dan: +{kakita_bonus},"
                f" {gap} {phase_word})"
            )

    # TN = standard attack TN
    tn = 5 + 5 * def_parry_rank
    success = total >= tn

    attack_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.IAIJUTSU,
        target=defender_name,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=tn,
        success=success,
        description=(
            f"{attacker_name} phase 0 iaijutsu"
            f"{'' if has_phase0 else ' (interrupt)'}: "
            f"{format_pool_with_overflow(rolled, kept)}"
            f" vs TN {tn}{bonus_note}"
        ),
        dice_pool=format_pool_with_overflow(rolled, kept),
    )
    attack_action.status_after = state.snapshot_status()
    log.add_action(attack_action)

    if not success:
        return

    # Roll damage
    weapon: Weapon = atk_ctx.weapon
    extra_dice = max(0, (total - tn) // 5)
    damage_rolled = weapon.rolled + fire_ring + extra_dice
    damage_kept = weapon.kept

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(damage_rolled, damage_kept, explode=True)

    # 4th Dan: +5 on iaijutsu damage
    dmg_note = ""
    if dan >= 4:
        dmg_total += 5
        dmg_note = " (kakita 4th Dan: iaijutsu damage +5)"

    damage_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.DAMAGE,
        target=defender_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=f"{attacker_name} deals {dmg_total} damage{dmg_note}",
        dice_pool=format_pool_with_overflow(damage_rolled, damage_kept),
    )

    # Apply damage
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = state.snapshot_status()
    log.add_action(damage_action)

    # --- Wound check (reuse standard wound check logic) ---
    water_value = defender.rings.water.value

    # Compute wound check bonuses before void decision via Fighter hooks
    wc_extra_rolled = def_ctx.wound_check_extra_rolled()
    ab10_bonus = atk_ctx.wound_check_tn_bonus()

    # Decide how many void points to spend
    max_spend = defender.rings.lowest()
    void_spend = should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, def_ctx.total_void,
        max_spend=max_spend, extra_rolled=wc_extra_rolled, tn_bonus=ab10_bonus,
    )
    wc_from_temp, wc_from_reg = def_ctx.spend_void(void_spend)
    wc_void_label = void_spent_label(wc_from_temp, wc_from_reg)

    def_is_shinjo = defender.school == "Shinjo Bushi"
    def_dan_shinjo = defender.dan if def_is_shinjo else 0

    sw_before_wc = wound_tracker.serious_wounds

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=wc_extra_rolled, tn_bonus=ab10_bonus,
    )

    # Wound check flat bonus via Fighter hook (e.g. Otaku 2nd Dan +5)
    wc_flat_bonus, wc_flat_note = def_ctx.wound_check_flat_bonus()
    if wc_flat_bonus > 0:
        wc_total += wc_flat_bonus
        effective_tn = wound_tracker.light_wounds + ab10_bonus
        passed = wc_total >= effective_tn

    # Shinjo 5th Dan: apply stored bonuses after seeing the roll
    shinjo_bonus_note = ""
    if (def_is_shinjo and def_dan_shinjo >= 5
            and not passed
            and def_ctx.shinjo_bonuses):
        base_tn = wound_tracker.light_wounds
        raw_deficit = base_tn - wc_total
        used = select_shinjo_wc_bonuses(
            raw_deficit, def_ctx.shinjo_bonuses,
        )
        if used:
            bonus_applied = sum(used)
            wc_total += bonus_applied
            remaining = list(def_ctx.shinjo_bonuses)
            for b in used:
                remaining.remove(b)
            def_ctx.shinjo_bonuses[:] = remaining
            sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
            new_deficit = base_tn - wc_total
            if new_deficit <= 0:
                new_sw = 0
                passed = True
            else:
                new_sw = 1 + (new_deficit // 10)
            wound_tracker.serious_wounds += (new_sw - sw_added_by_wc)
            bonus_str = ", ".join(f"+{b}" for b in used)
            total_str = f" = +{bonus_applied}" if len(used) > 1 else ""
            if passed:
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" wound check passes)"
                )
            else:
                sw_saved = sw_added_by_wc - new_sw
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" {sw_saved} serious wound"
                    f"{'s' if sw_saved != 1 else ''}"
                    f" prevented)"
                )

    void_note = f" ({wc_void_label})" if wc_void_label else ""
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn + ab10_bonus

    # Feature 3: Wound check success choice
    convert_note = ""
    if passed:
        def_shinjo_pool = 0
        if def_is_shinjo and def_dan_shinjo >= 5:
            def_shinjo_pool = sum(def_ctx.shinjo_bonuses)
        should_convert = should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            shinjo_wc_bonus_pool=def_shinjo_pool,
        )
        if should_convert:
            wound_tracker.serious_wounds += 1
            wound_tracker.light_wounds = 0
            convert_note = " — converted light wounds to 1 serious wound"
        else:
            convert_note = f" — keeping {wound_tracker.light_wounds} light wounds"

    ab10_note = (
        f" (TN {wc_tn} from {wc_base_tn} LW due to wave man ability)"
        if ab10_bonus > 0 else ""
    )
    wc_rolled = water_value + 1 + wc_extra_rolled + void_spend
    wc_kept = water_value + void_spend
    wc_action = CombatAction(
        phase=0,
        actor=defender_name,
        action_type=ActionType.WOUND_CHECK,
        dice_rolled=wc_all_dice,
        dice_kept=wc_kept_dice,
        total=wc_total,
        tn=wc_tn,
        base_tn=wc_base_tn if ab10_bonus > 0 else None,
        success=passed,
        description=(
            f"{defender_name} wound check: {'passed' if passed else 'failed'} "
            f"(rolled {wc_total}){void_note}{wc_flat_note}"
            f"{shinjo_bonus_note}{convert_note}{ab10_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    if not passed:
        wound_tracker.light_wounds = 0

    wc_action.status_after = state.snapshot_status()


def _resolve_kakita_5th_dan(
    state: "CombatState",
    attacker_name: str,
    defender_name: str,
) -> None:
    """Resolve 5th Dan Kakita contested iaijutsu at phase 0.

    Automatic at the beginning of each round:
    1. Kakita rolls (iaijutsu + Fire)k(Fire), +1 if 1st Dan, +5 if 2nd Dan
    2. Opponent rolls (iaijutsu + Fire)k(Fire) or (Attack + Fire)k(Fire)
    3. Compare totals, roll damage with bonus/penalty dice
    """
    log = state.log
    atk_ctx = state.fighters[attacker_name]
    def_ctx = state.fighters[defender_name]
    attacker: Character = atk_ctx.char
    defender: Character = def_ctx.char
    dan = attacker.dan
    weapon: Weapon = atk_ctx.weapon

    # Kakita's iaijutsu roll
    iaijutsu_skill = attacker.get_skill("Iaijutsu")
    iaijutsu_rank = iaijutsu_skill.rank if iaijutsu_skill else 0
    fire_ring = attacker.rings.fire.value

    kakita_rolled = iaijutsu_rank + fire_ring
    kakita_kept = fire_ring
    if dan >= 1:
        kakita_rolled += 1

    attacker_crippled = log.wounds[attacker_name].is_crippled
    k_all, k_kept, kakita_total = roll_and_keep(
        kakita_rolled, kakita_kept, explode=not attacker_crippled,
    )

    # Accumulate bonuses with descriptions
    bonus_notes: list[str] = []

    # 2nd Dan: free raise on iaijutsu (+5)
    if dan >= 2:
        kakita_total += 5
        bonus_notes.append("2nd Dan free raise: +5")

    # Opponent's contested roll
    def_iaijutsu = defender.get_skill("Iaijutsu")
    def_atk_skill = defender.get_skill("Attack")
    no_iaijutsu = False
    if def_iaijutsu and def_iaijutsu.rank > 0:
        opp_skill_rank = def_iaijutsu.rank
        opp_skill_name = "iaijutsu"
    elif def_atk_skill:
        opp_skill_rank = def_atk_skill.rank
        opp_skill_name = "attack"
        no_iaijutsu = True
    else:
        opp_skill_rank = 0
        opp_skill_name = "attack"
        no_iaijutsu = True

    def_fire = defender.rings.fire.value
    opp_rolled = opp_skill_rank + def_fire
    opp_kept = def_fire
    defender_crippled = log.wounds[defender_name].is_crippled
    o_all, o_kept, opp_total = roll_and_keep(opp_rolled, opp_kept, explode=not defender_crippled)

    # Contested skill difference: +5 per point Kakita's skill exceeds opponent's
    skill_diff = iaijutsu_rank - opp_skill_rank
    if skill_diff > 0:
        skill_diff_bonus = skill_diff * 5
        kakita_total += skill_diff_bonus
        bonus_notes.append(f"skill {iaijutsu_rank} vs {opp_skill_rank}: +{skill_diff_bonus}")

    # Extra raise if opponent has no iaijutsu (uses attack instead)
    if no_iaijutsu:
        kakita_total += 5
        bonus_notes.append("no opponent iaijutsu: +5")

    # Log contested roll
    margin = kakita_total - opp_total
    won = margin >= 0
    contest_note = f"won by {margin}" if won else f"lost by {abs(margin)}"
    bonus_str = f" ({', '.join(bonus_notes)})" if bonus_notes else ""
    opp_pool = format_pool_with_overflow(opp_rolled, opp_kept)

    # Format opponent's dice: bold for kept, strikethrough for unkept
    opp_kept_remaining = list(o_kept)
    opp_dice_display: list[str] = []
    for d in o_all:
        if d in opp_kept_remaining:
            opp_dice_display.append(f"**{d}**")
            opp_kept_remaining.remove(d)
        else:
            opp_dice_display.append(f"~~{d}~~")
    opp_dice_str = f"[{', '.join(opp_dice_display)}]"

    opp_tn_desc = (
        f"vs TN {opp_total} ({defender_name}'s"
        f" {opp_pool} {opp_skill_name} {opp_dice_str})"
    )
    contest_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.IAIJUTSU,
        target=defender_name,
        dice_rolled=k_all,
        dice_kept=k_kept,
        total=kakita_total,
        tn=opp_total,
        success=won,
        description=(
            f"{attacker_name} 5th Dan iaijutsu: "
            f"{format_pool_with_overflow(kakita_rolled, kakita_kept)} = {kakita_total}{bonus_str}"
            f" vs {defender_name} {opp_pool} = {opp_total}"
            f" ({contest_note})"
        ),
        dice_pool=format_pool_with_overflow(kakita_rolled, kakita_kept),
        label="5th Dan iaijutsu",
        tn_description=opp_tn_desc,
    )
    contest_action.status_after = state.snapshot_status()
    log.add_action(contest_action)

    # Damage roll
    damage_rolled = weapon.rolled + fire_ring
    damage_kept = weapon.kept

    dmg_notes: list[str] = []
    if won:
        extra_damage_dice = max(0, margin // 5)
        damage_rolled += extra_damage_dice
        if extra_damage_dice > 0:
            dmg_notes.append(f"won by {margin}: +{extra_damage_dice} rolled")
    else:
        fewer_dice = min(weapon.rolled - 1, abs(margin) // 5)
        damage_rolled = max(1, damage_rolled - fewer_dice)
        if fewer_dice > 0:
            dmg_notes.append(f"lost by {abs(margin)}: -{fewer_dice} rolled")

    dmg_all, dmg_kept_dice, dmg_total = roll_and_keep(damage_rolled, damage_kept, explode=True)

    # 4th Dan: +5 on iaijutsu damage
    if dan >= 4:
        dmg_total += 5
        dmg_notes.append("4th Dan free raise: +5")

    dmg_note_str = f" ({', '.join(dmg_notes)})" if dmg_notes else ""

    damage_action = CombatAction(
        phase=0,
        actor=attacker_name,
        action_type=ActionType.DAMAGE,
        target=defender_name,
        dice_rolled=dmg_all,
        dice_kept=dmg_kept_dice,
        total=dmg_total,
        description=(
            f"{attacker_name} 5th Dan iaijutsu damage: "
            f"{format_pool_with_overflow(damage_rolled, damage_kept)}"
            f" = {dmg_total}{dmg_note_str}"
        ),
        dice_pool=format_pool_with_overflow(damage_rolled, damage_kept),
        label="5th Dan iaijutsu damage",
    )

    # Apply damage
    wound_tracker = log.wounds[defender_name]
    wound_tracker.light_wounds += dmg_total

    damage_action.status_after = state.snapshot_status()
    log.add_action(damage_action)

    # Wound check
    water_value = defender.rings.water.value

    # Compute wound check bonuses before void decision via Fighter hooks
    wc_extra_rolled = def_ctx.wound_check_extra_rolled()
    ab10_bonus = atk_ctx.wound_check_tn_bonus()

    max_spend = defender.rings.lowest()
    void_spend = should_spend_void_on_wound_check(
        water_value, wound_tracker.light_wounds, def_ctx.total_void,
        max_spend=max_spend, extra_rolled=wc_extra_rolled, tn_bonus=ab10_bonus,
    )
    wc_from_temp, wc_from_reg = def_ctx.spend_void(void_spend)
    wc_void_label = void_spent_label(wc_from_temp, wc_from_reg)

    def_is_shinjo = defender.school == "Shinjo Bushi"
    def_dan_shinjo = defender.dan if def_is_shinjo else 0

    sw_before_wc = wound_tracker.serious_wounds

    passed, wc_total, wc_all_dice, wc_kept_dice = make_wound_check(
        wound_tracker, water_value, void_spend=void_spend,
        extra_rolled=wc_extra_rolled, tn_bonus=ab10_bonus,
    )

    # Wound check flat bonus via Fighter hook (e.g. Otaku 2nd Dan +5)
    wc_flat_bonus, wc_flat_note = def_ctx.wound_check_flat_bonus()
    if wc_flat_bonus > 0:
        wc_total += wc_flat_bonus
        effective_tn = wound_tracker.light_wounds + ab10_bonus
        passed = wc_total >= effective_tn

    # Shinjo 5th Dan: apply stored bonuses after seeing the roll
    shinjo_bonus_note = ""
    if (def_is_shinjo and def_dan_shinjo >= 5
            and not passed
            and def_ctx.shinjo_bonuses):
        base_tn = wound_tracker.light_wounds
        raw_deficit = base_tn - wc_total
        used = select_shinjo_wc_bonuses(
            raw_deficit, def_ctx.shinjo_bonuses,
        )
        if used:
            bonus_applied = sum(used)
            wc_total += bonus_applied
            remaining = list(def_ctx.shinjo_bonuses)
            for b in used:
                remaining.remove(b)
            def_ctx.shinjo_bonuses[:] = remaining
            sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
            new_deficit = base_tn - wc_total
            if new_deficit <= 0:
                new_sw = 0
                passed = True
            else:
                new_sw = 1 + (new_deficit // 10)
            wound_tracker.serious_wounds += (new_sw - sw_added_by_wc)
            bonus_str = ", ".join(f"+{b}" for b in used)
            total_str = f" = +{bonus_applied}" if len(used) > 1 else ""
            if passed:
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" wound check passes)"
                )
            else:
                sw_saved = sw_added_by_wc - new_sw
                shinjo_bonus_note = (
                    f" (shinjo 5th Dan: applied"
                    f" {bonus_str}{total_str},"
                    f" {sw_saved} serious wound"
                    f"{'s' if sw_saved != 1 else ''}"
                    f" prevented)"
                )

    void_note = f" ({wc_void_label})" if wc_void_label else ""
    wc_base_tn = wound_tracker.light_wounds
    wc_tn = wc_base_tn + ab10_bonus

    convert_note = ""
    if passed:
        def_shinjo_pool = 0
        if def_is_shinjo and def_dan_shinjo >= 5:
            def_shinjo_pool = sum(def_ctx.shinjo_bonuses)
        should_convert = should_convert_light_to_serious(
            wound_tracker.light_wounds,
            wound_tracker.serious_wounds,
            wound_tracker.earth_ring,
            water_ring=water_value,
            shinjo_wc_bonus_pool=def_shinjo_pool,
        )
        if should_convert:
            wound_tracker.serious_wounds += 1
            wound_tracker.light_wounds = 0
            convert_note = " — converted light wounds to 1 serious wound"
        else:
            convert_note = f" — keeping {wound_tracker.light_wounds} light wounds"

    ab10_note = (
        f" (TN {wc_tn} from {wc_base_tn} LW due to wave man ability)"
        if ab10_bonus > 0 else ""
    )
    wc_rolled = water_value + 1 + wc_extra_rolled + void_spend
    wc_kept = water_value + void_spend
    wc_action = CombatAction(
        phase=0,
        actor=defender_name,
        action_type=ActionType.WOUND_CHECK,
        dice_rolled=wc_all_dice,
        dice_kept=wc_kept_dice,
        total=wc_total,
        tn=wc_tn,
        base_tn=wc_base_tn if ab10_bonus > 0 else None,
        success=passed,
        description=(
            f"{defender_name} wound check: {'passed' if passed else 'failed'} "
            f"(rolled {wc_total}){void_note}{wc_flat_note}"
            f"{shinjo_bonus_note}{convert_note}{ab10_note}"
        ),
        dice_pool=f"{wc_rolled}k{wc_kept}",
    )
    log.add_action(wc_action)

    if not passed:
        wound_tracker.light_wounds = 0

    wc_action.status_after = state.snapshot_status()


class KakitaFighter(Fighter):
    """Kakita Duelist fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 unkept die on initiative; +1 rolled die on attack/iaijutsu.
      2nd Dan: +5 free-raise on iaijutsu.
      3rd Dan: Post-roll attack bonus = Attack rank * phase gap to defender's
               next action.
      4th Dan: +5 damage on iaijutsu hits.
      5th Dan: Automatic contested iaijutsu at the start of each round.

    School Ability (SA): Initiative 10s become phase 0 actions (iaijutsu
    strikes before the opponent acts).

    Kakita NEVER spends void on attacks.
    """

    # -- Initiative hooks ---------------------------------------------------

    def initiative_extra_unkept(self) -> int:
        """1st Dan: +1 unkept die on initiative."""
        return 1 if self.dan >= 1 else 0

    def post_initiative(
        self, rolled_dice: list[int], kept_dice: list[int],
    ) -> list[int]:
        """SA: Convert 10s to phase 0 actions, re-pick from ALL rolled dice."""
        void_ring = self.char.rings.void.value
        converted = sorted(
            0 if d == 10 else d for d in rolled_dice
        )
        # Re-pick lowest Void-count dice from the full rolled set
        return converted[:void_ring] if len(converted) > void_ring else list(converted)

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int
    ) -> tuple[str, int]:
        """Kakita uses Lunge or DA (never void). Picks based on expected hit."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "lunge", 0

        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        lunge_skill = self.char.get_skill("Lunge")
        lunge_rank = lunge_skill.rank if lunge_skill else 0
        def_ctx = self.state.fighters[defender_name]
        def_parry_skill = def_ctx.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

        # 3rd Dan phase gap bonus informs the choice
        known_bonus = 0
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            def_actions = sorted(
                self.state.fighters[defender_name].actions_remaining,
            )
            def_future = [a for a in def_actions if a > phase]
            def_next = def_future[0] if def_future else 11
            known_bonus = atk_rank * (def_next - phase)

        choice = _kakita_attack_choice(
            lunge_rank,
            da_rank,
            self.char.rings.fire.value,
            def_parry_rank,
            self.dan,
            is_crippled,
            known_bonus=known_bonus,
        )
        # Kakita never spends void on attacks
        return choice, 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(
        self, rolled: int, kept: int, tn: int
    ) -> int:
        """Kakita never spends void on attacks."""
        return 0

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str
    ) -> tuple[int, str]:
        """3rd Dan: + Attack rank * (gap to defender's next action)."""
        if self.dan < 3:
            return 0, ""
        atk_skill = self.char.get_skill("Attack")
        atk_rank = atk_skill.rank if atk_skill else 0
        def_actions = sorted(
            self.state.fighters[defender_name].actions_remaining,
        )
        def_future = [a for a in def_actions if a > phase]
        def_next = def_future[0] if def_future else 11
        gap = def_next - phase
        bonus = atk_rank * gap
        if bonus > 0:
            phase_word = "phase" if gap == 1 else "phases"
            return bonus, (
                f" (kakita 3rd Dan: +{bonus},"
                f" {gap} {phase_word})"
            )
        return 0, ""

    # -- Parry hooks (as defender) ------------------------------------------

    def should_predeclare_parry(
        self, attack_tn: int, phase: int
    ) -> bool:
        """Kakita never pre-declares parries."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Kakita only parries when expected damage is very high."""
        from src.engine.simulation_utils import should_reactive_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
        return should_reactive_parry(
            def_parry_rank,
            self.char.rings.air.value,
            attack_total,
            attack_tn,
            weapon_rolled,
            attacker_fire,
            wound_info.serious_wounds,
            wound_info.earth_ring,
            wound_info.is_crippled,
            is_kakita=True,
        )

    # -- Special phase hooks ------------------------------------------------

    def has_phase0_action(self) -> bool:
        """Kakita always has a phase 0 capability (iaijutsu)."""
        return True

    def resolve_phase0(self, defender_name: str) -> None:
        """Execute phase 0 iaijutsu (delegates to module-level helpers)."""
        log = self.state.log
        name = self.name
        opp_name = defender_name

        if log.wounds[name].is_mortally_wounded:
            return
        if log.wounds[opp_name].is_mortally_wounded:
            return

        # 5th Dan: contested iaijutsu (automatic)
        if self.dan >= 5:
            _resolve_kakita_5th_dan(self.state, name, opp_name)

        # Phase 0 attack decision
        atk_skill = self.char.get_skill("Attack")
        atk_rank = atk_skill.rank if atk_skill else 0
        my_actions = self.actions_remaining
        phase0_count = my_actions.count(0)
        has_phase0 = phase0_count > 0
        can_attack = has_phase0 or len(my_actions) >= 2

        if can_attack:
            opp_actions = sorted(self.state.fighters[opp_name].actions_remaining)
            opp_future = [a for a in opp_actions if a > 0]
            defender_next = opp_future[0] if opp_future else 11
            if _kakita_should_phase0_attack(
                self.dan,
                atk_rank,
                phase0_count,
                len(my_actions),
                defender_next,
            ):
                _resolve_kakita_phase0_attack(self.state, name, opp_name)
