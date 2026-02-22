"""HirumaFighter: Hiruma Scout school-specific overrides.

SA: Allies' TN raised by 5 (no-op in 1v1).
1st Dan: +1 rolled die on initiative, parry, and wound check rolls.
2nd Dan: Free raise on parry (+5 flat).
3rd Dan: After parry (success or fail), +2X to next attack and damage
         (X = attack skill), as flat bonus.
4th Dan: Air +1 (builder). After initiative, lower all dice by 2 (min 1).
5th Dan: After parry (success or fail), attacker deals 10 fewer LW on next 2
         damage rolls.
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class HirumaFighter(Fighter):
    """Hiruma Scout fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._parry_attack_bonus: int = 0
        self._parry_damage_bonus: int = 0
        self._damage_reduction_charges: int = 0
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Initiative hooks ---------------------------------------------------

    def initiative_extra_unkept(self) -> int:
        """1st Dan: +1 rolled die on initiative."""
        return 1 if self.dan >= 1 else 0

    def post_initiative(
        self, dice_rolled: list[int], dice_kept: list[int],
    ) -> list[int]:
        """4th Dan: Lower all initiative dice by 2 (min 1)."""
        if self.dan >= 4:
            return [max(1, d - 2) for d in dice_kept]
        return dice_kept

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Hiruma prefers DA when available."""
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "attack", 0
        if da_rank > 0:
            return "double_attack", 0
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attacks (counts for DA too)."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Void spending considers parry bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        known_bonus = self._parry_attack_bonus
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=known_bonus,
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """3rd Dan: Consume stored parry attack bonus."""
        if self._parry_attack_bonus > 0:
            bonus = self._parry_attack_bonus
            self._parry_attack_bonus = 0
            return bonus, f" (hiruma 3rd Dan: +{bonus} from parry)"
        return 0, ""

    def sa_damage_flat_bonus(self) -> tuple[int, str]:
        """3rd Dan: Consume stored parry damage bonus."""
        if self._parry_damage_bonus > 0:
            bonus = self._parry_damage_bonus
            self._parry_damage_bonus = 0
            return bonus, f" (hiruma 3rd Dan: +{bonus} damage from parry)"
        return 0, ""

    # -- Parry hooks --------------------------------------------------------

    def parry_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on parry."""
        return 1 if self.dan >= 1 else 0

    def parry_bonus(self) -> tuple[int, str]:
        """2nd Dan: Free raise on parry (+5)."""
        if self.dan >= 2:
            return 5, " (hiruma 2nd Dan: free raise +5)"
        return 0, ""

    def on_parry_attempt(
        self, parry_succeeded: bool, margin: int,
        attacker_name: str, phase: int,
    ) -> None:
        """3rd Dan: Store 2X bonus after parry. 5th Dan: damage reduction."""
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            bonus = 2 * atk_rank
            self._parry_attack_bonus = bonus
            self._parry_damage_bonus = bonus

        if self.dan >= 5:
            self._damage_reduction_charges = 2

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    # -- 5th Dan: Damage reduction after parry ------------------------------

    def damage_reduction(
        self, damage_total: int, had_extra_dice: bool,
    ) -> tuple[int, str]:
        """5th Dan: 10 fewer LW on attacker's next 2 damage rolls after parry."""
        if self._damage_reduction_charges > 0:
            self._damage_reduction_charges -= 1
            reduction = min(10, damage_total)
            new_total = max(0, damage_total - 10)
            note = (
                f" (hiruma 5th Dan: -{reduction} damage,"
                f" {self._damage_reduction_charges} charges remaining)"
            )
            return new_total, note
        return damage_total, ""
