"""CourtierFighter: Courtier school-specific overrides.

The Courtier is a non-bushi school. Most abilities are social, but the SA
and several Dan techniques affect combat:

SA: Add Air to all attack and damage rolls.
1st Dan: +1 rolled die on wound checks.
3rd Dan: Pool of 2*tact free raises per adventure (max tact per roll).
4th Dan: Air +1 (handled by builder); first successful hit per target
         grants +1 temp void.
5th Dan: Add Air to all TN/contested rolls (stacks with SA on attacks).

The Courtier has no combat knacks -- only normal attacks.
"""

from __future__ import annotations

import math

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class CourtierFighter(Fighter):
    """Courtier fighter with school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on wound checks.
      2nd Dan: Free raise on manipulation (not combat-relevant).
      3rd Dan: 2*tact free raises per adventure, max tact per roll.
      4th Dan: Air +1 (builder); first hit per target grants temp void.
      5th Dan: Add Air to all TN/contested rolls (attacks, parry, WC).

    School Ability (SA): Add Air to all attack and damage rolls.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        tact_skill = self.char.get_skill("Tact")
        tact_rank = tact_skill.rank if tact_skill else 0
        self._free_raises = 2 * tact_rank if self.dan >= 3 else 0
        self._max_per_roll = tact_rank if self.dan >= 3 else 0
        self._targets_hit: set[str] = set()

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Courtier has no combat knacks -- always normal attack."""
        return "attack", 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Spend void on attack with known SA bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        air = self.char.rings.air.value
        known_bonus = 2 * air if self.dan >= 5 else air
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=known_bonus,
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """SA: Add Air to attack rolls; 5th Dan doubles it."""
        air = self.char.rings.air.value
        if self.dan >= 5:
            bonus = 2 * air
            note = f" (courtier SA+5th Dan: +{bonus})"
        else:
            bonus = air
            note = f" (courtier SA: +{bonus})"
        return bonus, note

    # -- SA damage hooks ----------------------------------------------------

    def sa_damage_flat_bonus(self) -> tuple[int, str]:
        """SA: Add Air to damage total."""
        air = self.char.rings.air.value
        return air, f" (courtier SA: +{air} damage)"

    # -- Post-attack roll bonus (3rd Dan free raises on miss) ---------------

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str,
    ) -> tuple[int, str]:
        """3rd Dan: Spend free raises to bridge attack deficit."""
        if self.dan < 3 or self._free_raises <= 0:
            return 0, ""

        deficit = tn - attack_total
        if deficit <= 0:
            return 0, ""

        raises_needed = math.ceil(deficit / 5)
        usable = min(self._max_per_roll, self._free_raises)
        if raises_needed > usable:
            # Can't bridge the gap -- don't waste raises
            return 0, ""

        self._free_raises -= raises_needed
        bonus = raises_needed * 5
        note = (
            f" (courtier 3rd Dan: {raises_needed} free raise(s)"
            f" +{bonus}, {self._free_raises} remaining)"
        )
        return bonus, note

    # -- Post-damage effect (4th Dan temp void) -----------------------------

    def post_damage_effect(self, defender_name: str) -> str:
        """4th Dan: First successful hit per target grants +1 temp void."""
        if self.dan < 4:
            return ""
        if defender_name in self._targets_hit:
            return ""
        self._targets_hit.add(defender_name)
        self.temp_void += 1
        return (
            f" (courtier 4th Dan: +1 temp void,"
            f" first hit on {defender_name})"
        )

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """5th Dan: Add Air to wound check total."""
        if self.dan >= 5:
            air = self.char.rings.air.value
            return air, f" (courtier 5th Dan: +{air})"
        return 0, ""

    def wc_bonus_pool_total(self) -> int:
        """3rd Dan: Remaining free raise pool affects conversion threshold."""
        if self.dan >= 3:
            usable = min(self._free_raises, self._max_per_roll)
            return usable * 5
        return 0

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: Spend free raises to reduce serious wounds on failed WC.

        Strategy:
        - NEVER spend to pass unless taking 1 more SW would be mortal.
        - Only spend to reduce the number of serious wounds taken.
        - Spend the minimum raises needed for the best SW reduction.
        """
        if self.dan < 3 or self._free_raises <= 0 or passed:
            return passed, wc_total, ""

        wound_tracker = self.state.log.wounds[self.name]
        base_tn = wound_tracker.light_wounds
        deficit = base_tn - wc_total

        if deficit <= 0:
            return passed, wc_total, ""

        current_sw = 1 + deficit // 10
        would_die = (sw_before_wc + current_sw >= wound_tracker.mortal_wound_threshold)

        usable = min(self._max_per_roll, self._free_raises)
        best_sw = current_sw
        best_spend = 0

        for spend in range(1, usable + 1):
            new_deficit = deficit - spend * 5
            if new_deficit <= 0:
                if would_die:
                    # Spend to pass only if we'd die otherwise
                    if spend < best_spend or best_sw > 0:
                        best_sw = 0
                        best_spend = spend
                # Don't spend to pass if not dying
                break
            new_sw = 1 + new_deficit // 10
            if new_sw < best_sw:
                best_sw = new_sw
                best_spend = spend

        if best_spend <= 0 or best_sw >= current_sw:
            return passed, wc_total, ""

        self._free_raises -= best_spend
        bonus = best_spend * 5
        new_total = wc_total + bonus
        new_deficit = base_tn - new_total

        # Recalculate serious wounds (following Shinjo pattern)
        sw_added_by_wc = wound_tracker.serious_wounds - sw_before_wc
        if new_deficit <= 0:
            new_sw_count = 0
            new_passed = True
        else:
            new_sw_count = 1 + new_deficit // 10
            new_passed = False
        wound_tracker.serious_wounds += (new_sw_count - sw_added_by_wc)

        note = (
            f" (courtier 3rd Dan: {best_spend} free raise(s)"
            f" +{bonus} on wound check,"
            f" {self._free_raises} remaining)"
        )
        return new_passed, new_total, note

    # -- Parry decision overrides ------------------------------------------

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Courtier never pre-declares parry — keep dice for Air-boosted attacks."""
        return False

    def can_interrupt(self) -> bool:
        """Courtier cannot interrupt-parry — 2-die cost never worth it."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Only parry when taking the hit unmitigated would be near-fatal.

        The Courtier's wound-check toolkit (1st Dan extra die, 3rd Dan free
        raises, 5th Dan +Air) means they can absorb most hits. Only parry
        when projected damage would push them to mortal wound territory.
        """
        from src.engine.simulation_utils import estimate_roll

        # 1. Project incoming damage
        extra_dice = max(0, (attack_total - attack_tn) // 5)
        damage_rolled = weapon_rolled + attacker_fire + extra_dice
        opponent = self.state.fighters[self.opponent_name]
        weapon_kept = opponent.weapon.kept
        expected_damage = estimate_roll(damage_rolled, weapon_kept)

        # 2. Project wound state after hit
        wound_info = self.state.log.wounds[self.name]
        projected_lw = wound_info.light_wounds + expected_damage

        # 3. Estimate wound check result with courtier bonuses
        water = self.char.rings.water.value
        water_rolled = water + (1 if self.dan >= 1 else 0)  # 1st Dan
        expected_wc = estimate_roll(water_rolled, water)

        # 5th Dan flat WC bonus
        flat_wc_bonus = self.char.rings.air.value if self.dan >= 5 else 0
        expected_wc += flat_wc_bonus

        # 3rd Dan free raise pool bonus
        pool_bonus = self.wc_bonus_pool_total()
        expected_wc += pool_bonus

        # 4. Project serious wounds if WC fails
        wc_deficit = projected_lw - expected_wc
        if wc_deficit <= 0:
            # Expected to pass WC — no need to parry
            return False
        projected_sw = 1 + int(wc_deficit) // 10

        # 5. Only parry if existing + projected SW would be mortal
        existing_sw = wound_info.serious_wounds
        return existing_sw + projected_sw >= wound_info.mortal_wound_threshold

    # -- Parry hooks (5th Dan) ----------------------------------------------

    def parry_bonus(self) -> int:
        """5th Dan: Add Air to parry (contested roll)."""
        if self.dan >= 5:
            return self.char.rings.air.value
        return 0

    def parry_bonus_description(self, bonus: int) -> str:
        """5th Dan: courtier-specific parry bonus description."""
        return f" (courtier 5th Dan: +{bonus})"
