"""AkodoFighter: Akodo Bushi school-specific overrides.

SA: +4 temp void on successful feint, +1 on unsuccessful.
1st Dan: +1 rolled die on attack, double attack, and wound checks.
2nd Dan: Free raise on wound checks (+5 flat).
3rd Dan: After WC exceeds TN, store (excess/5 * attack_rank) as attack bonus pool.
4th Dan: Water +1 (builder). Void spent on WC gives free raises (+5 per void).
5th Dan: After taking damage, spend void to deal 10 LW per void to attacker
         (up to damage taken).
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    should_spend_void_on_combat_roll,
)


class AkodoFighter(Fighter):
    """Akodo Bushi fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._attack_bonus_pool: int = 0
        self._wc_void_spent: int = 0
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Round hooks --------------------------------------------------------

    def on_round_start(self) -> None:
        """Reset per-round state."""

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Akodo prefers feint when available, else DA, else normal attack."""
        feint_skill = self.char.get_skill("Feint")
        feint_rank = feint_skill.rank if feint_skill else 0
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled

        if is_crippled:
            return "attack", 0

        # Prefer feint for SA void generation
        if feint_rank > 0:
            return "feint", 0

        if da_rank > 0:
            return "double_attack", 0

        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack and double attack."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Spend void on attack with known bonus from pool."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """No flat SA attack bonus (2nd Dan is WC not attack)."""
        return 0, ""

    # -- 3rd Dan: Attack bonus pool -----------------------------------------

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str,
    ) -> tuple[int, str]:
        """3rd Dan: Spend stored attack bonus to bridge deficit or add raises."""
        if self.dan < 3 or self._attack_bonus_pool <= 0:
            return 0, ""

        deficit = tn - attack_total
        if deficit <= 0:
            # Already hitting — spend up to pool for extra raise dice
            # Strategy: spend if it would give at least 1 full raise (5+)
            usable = min(self._attack_bonus_pool, 15)  # cap at 3 raises
            if usable >= 5:
                self._attack_bonus_pool -= usable
                note = (
                    f" (akodo 3rd Dan: +{usable} from pool,"
                    f" {self._attack_bonus_pool} remaining)"
                )
                return usable, note
            return 0, ""

        # Bridge deficit: spend minimum needed to hit
        spend = min(deficit, self._attack_bonus_pool)
        if spend <= 0:
            return 0, ""

        # Also add up to 10 extra for raises if pool allows
        extra = min(self._attack_bonus_pool - spend, 10)
        total_spend = spend + extra
        self._attack_bonus_pool -= total_spend
        note = (
            f" (akodo 3rd Dan: +{total_spend} from pool,"
            f" {self._attack_bonus_pool} remaining)"
        )
        return total_spend, note

    # -- Feint SA: temp void ------------------------------------------------

    def on_feint_result(
        self,
        feint_landed: bool,
        phase: int,
        defender_name: str,
        void_spent: int,
        feint_met_tn: bool = False,
    ) -> None:
        """SA: +4 temp void on successful feint, +1 on unsuccessful."""
        if feint_met_tn:
            self.temp_void += 4
        else:
            self.temp_void += 1

    # -- 1st Dan: wound check -----------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    # -- 2nd Dan: free raise on WC ------------------------------------------

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """2nd Dan: +5 on wound checks. 4th Dan: +5 per void spent on WC."""
        bonus = 0
        notes: list[str] = []
        if self.dan >= 2:
            bonus += 5
            notes.append("akodo 2nd Dan: free raise +5")
        if self.dan >= 4 and self._wc_void_spent > 0:
            void_bonus = self._wc_void_spent * 5
            bonus += void_bonus
            notes.append(
                f"akodo 4th Dan: {self._wc_void_spent} void"
                f" = +{void_bonus} free raises"
            )
        note = f" ({'; '.join(notes)})" if notes else ""
        return bonus, note

    # -- 4th Dan: void on WC gives free raises ------------------------------

    def wound_check_void_strategy(
        self, water_ring: int, light_wounds: int,
    ) -> int:
        """Be more aggressive with void spending on WC at 4th Dan."""
        from src.engine.simulation_utils import should_spend_void_on_wound_check
        max_spend = self.char.rings.lowest()
        extra_rolled = self.wound_check_extra_rolled()
        tn_bonus = 5 if self.dan >= 2 else 0
        result = should_spend_void_on_wound_check(
            water_ring, light_wounds, self.total_void,
            max_spend=max_spend, extra_rolled=extra_rolled,
            tn_bonus=tn_bonus,
        )
        self._wc_void_spent = result
        return result

    # -- 3rd Dan: WC excess → attack bonus pool -----------------------------

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: After passing WC, store excess as attack bonus."""
        if self.dan >= 3 and passed:
            wound_tracker = self.state.log.wounds[self.name]
            tn = wound_tracker.light_wounds
            excess = wc_total - tn
            if excess > 0:
                atk_skill = self.char.get_skill("Attack")
                atk_rank = atk_skill.rank if atk_skill else 0
                increment = (excess // 5) * atk_rank
                if increment > 0:
                    self._attack_bonus_pool += increment

        self._wc_void_spent = 0
        return passed, wc_total, ""

    # -- 5th Dan: damage reflection -----------------------------------------

    def reflect_damage_after_wc(
        self, damage_taken: int, attacker_name: str,
    ) -> tuple[int, int, str]:
        """5th Dan: Spend void to deal 10 LW per void to attacker."""
        if self.dan < 5 or damage_taken <= 0:
            return 0, 0, ""

        max_void = damage_taken // 10
        if max_void <= 0:
            return 0, 0, ""

        available = self.total_void
        void_to_spend = min(max_void, available)
        if void_to_spend <= 0:
            return 0, 0, ""

        # Only spend if it would matter
        attacker_wounds = self.state.log.wounds[attacker_name]
        opp_water = self.state.fighters[attacker_name].char.rings.water.value
        opp_lw = attacker_wounds.light_wounds
        projected_lw = opp_lw + void_to_spend * 10
        expected_wc = estimate_roll(opp_water + 1, opp_water)
        if projected_lw <= expected_wc * 0.5 and not attacker_wounds.is_crippled:
            return 0, 0, ""

        self.spend_void(void_to_spend)
        reflect_damage = void_to_spend * 10
        note = (
            f" (akodo 5th Dan: spent {void_to_spend} void,"
            f" deals {reflect_damage} LW to {attacker_name})"
        )
        return reflect_damage, 0, note
