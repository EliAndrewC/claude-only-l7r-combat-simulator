"""Combat simulation engine.

Handles initiative, attacking, parrying, damage, and wound checks
according to L7R rules.
"""

from __future__ import annotations

from src.engine.dice import roll_and_keep, roll_die
from src.models.character import Character, RingName
from src.models.combat import (
    ActionType,
    CombatAction,
    CombatLog,
    WoundTracker,
)


def roll_initiative(character: Character) -> CombatAction:
    """Roll initiative: (Void + 1) dice, drop the single highest, keep the rest.

    No exploding 10s. Each kept die = a phase the character acts in.

    Args:
        character: The character rolling initiative.

    Returns:
        A CombatAction recording the initiative roll.
    """
    void_ring = character.rings.void.value
    num_dice = void_ring + 1

    all_dice = sorted([roll_die(explode=False) for _ in range(num_dice)])
    # Drop the single highest die (last after ascending sort), keep the rest
    kept_dice = all_dice[:-1]
    phases_str = ", ".join(str(d) for d in kept_dice)

    return CombatAction(
        phase=0,
        actor=character.name,
        action_type=ActionType.INITIATIVE,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=0,
        description=(
            f"{character.name} acts in phases {phases_str}"
        ),
    )


def calculate_attack_tn(defender_parry: int) -> int:
    """Calculate the TN to hit a defender.

    Attack TN = 5 + (5 * defender's parry skill).

    Args:
        defender_parry: The defender's parry skill rank.

    Returns:
        The target number for the attack roll.
    """
    return 5 + (5 * defender_parry)


def roll_attack(
    attacker: Character,
    attack_skill: int,
    attack_ring: RingName,
    tn: int,
    explode: bool = True,
) -> CombatAction:
    """Roll an attack against a target number.

    Dice = attack_skill + ring value, keep ring value.

    Args:
        attacker: The attacking character.
        attack_skill: The attacker's attack skill rank.
        attack_ring: The ring used for the attack roll.
        tn: The target number to meet or exceed.
        explode: Whether 10s explode (False when crippled).

    Returns:
        A CombatAction recording the attack roll.
    """
    ring_value = attacker.rings.get(attack_ring).value
    rolled = attack_skill + ring_value
    kept = ring_value

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=explode)
    success = total >= tn

    return CombatAction(
        phase=0,
        actor=attacker.name,
        action_type=ActionType.ATTACK,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        tn=tn,
        success=success,
        description=f"{attacker.name} attacks: {rolled}k{kept} vs TN {tn}",
        dice_pool=f"{rolled}k{kept}",
    )


def roll_damage(
    attacker: Character,
    weapon_rolled: int,
    weapon_kept: int,
    extra_dice: int = 0,
) -> CombatAction:
    """Roll damage for a successful attack.

    Damage dice = weapon_rolled + Fire ring + extra_dice, keep weapon_kept.

    Args:
        attacker: The attacking character.
        weapon_rolled: Base rolled dice from weapon.
        weapon_kept: Base kept dice from weapon.
        extra_dice: Bonus rolled dice (e.g., from raises).

    Returns:
        A CombatAction recording the damage roll.
    """
    fire = attacker.rings.fire.value
    rolled = weapon_rolled + fire + extra_dice
    kept = weapon_kept

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=True)

    return CombatAction(
        phase=0,
        actor=attacker.name,
        action_type=ActionType.DAMAGE,
        dice_rolled=all_dice,
        dice_kept=kept_dice,
        total=total,
        description=f"{attacker.name} deals {total} damage ({rolled}k{kept})",
        dice_pool=f"{rolled}k{kept}",
    )


def make_wound_check(
    wound_tracker: WoundTracker,
    water_ring: int,
    void_spend: int = 0,
) -> tuple[bool, int, list[int], list[int]]:
    """Make a wound check against the current light wound total.

    Roll (Water + 1)k(Water + void_spend) vs TN = light_wounds.
    Failure: 1 serious wound + 1 per 10 failed by.

    Args:
        wound_tracker: The character's current wound state.
        water_ring: The character's Water ring value.
        void_spend: Void points spent. Each adds one kept die.

    Returns:
        Tuple of (passed, roll_total, all_dice, kept_dice).

    Raises:
        ValueError: If void_spend is negative.
    """
    if void_spend < 0:
        raise ValueError(f"void_spend must be >= 0, got {void_spend}")
    rolled = water_ring + 1
    kept = water_ring + void_spend
    tn = wound_tracker.light_wounds

    all_dice, kept_dice, total = roll_and_keep(rolled, kept, explode=True)
    passed = total >= tn

    if not passed:
        deficit = tn - total
        serious = 1 + (deficit // 10)
        wound_tracker.serious_wounds += serious

    return passed, total, all_dice, kept_dice


def create_combat_log(combatant_names: list[str], earth_values: list[int]) -> CombatLog:
    """Initialize a combat log for an encounter.

    Args:
        combatant_names: Names of all combatants.
        earth_values: Earth ring values for wound tracking.

    Returns:
        A fresh CombatLog ready for combat.
    """
    wounds = {
        name: WoundTracker(earth_ring=earth)
        for name, earth in zip(combatant_names, earth_values)
    }
    return CombatLog(combatants=combatant_names, wounds=wounds)
