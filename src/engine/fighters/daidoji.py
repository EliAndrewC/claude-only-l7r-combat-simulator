"""DaidojiFighter: Daidoji Yojimbo school-specific overrides.

SA: Counterattack as interrupt for 1 action die; opponent gets free raise on WC
    from counterattack damage if Daidoji hits.
1st Dan: +1 rolled die on attack, counterattack, and wound checks.
2nd Dan: Free raise on counterattack rolls (+5 flat).
3rd Dan: When counterattacking, Daidoji's WC from original attack gets
         attack_rank * 5 bonus.
4th Dan: Water +1 (builder). May take damage for adjacent ally (no-op 1v1).
5th Dan: After WC, lower opponent's TN by WC excess for next attack.
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class DaidojiFighter(Fighter):
    """Daidoji Yojimbo fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._counterattack_wc_bonus: int = 0
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Daidoji prefers DA when available, else normal attack."""
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "attack", 0
        if da_rank > 0:
            return "double_attack", 0
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack and counterattack."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Standard void spending."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
        )

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """3rd Dan: Bonus from counterattack stored WC bonus."""
        if self._counterattack_wc_bonus > 0:
            bonus = self._counterattack_wc_bonus
            self._counterattack_wc_bonus = 0
            note = f" (daidoji 3rd Dan: +{bonus} from counterattack)"
            return bonus, note
        return 0, ""

    # -- 5th Dan: WC excess → TN reduction on opponent ----------------------

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """5th Dan: After WC, lower opponent's TN by WC excess."""
        if self.dan >= 5 and passed:
            wound_tracker = self.state.log.wounds[self.name]
            tn = wound_tracker.light_wounds
            excess = wc_total - tn
            if excess > 0:
                # Store as parry_tn_reduction (lowers opponent's TN for next attack)
                self.parry_tn_reduction += excess
        return passed, wc_total, ""

    # -- SA: Counterattack as interrupt for 1 die ---------------------------

    def can_interrupt(self) -> bool:
        """Daidoji can counterattack as interrupt."""
        ca_skill = self.char.get_skill("Counterattack")
        ca_rank = ca_skill.rank if ca_skill else 0
        return ca_rank > 0 and len(self.actions_remaining) >= 1

    def resolve_pre_attack_counterattack(
        self, attacker_name: str, phase: int,
    ) -> bool:
        """SA: Counterattack interrupt for 1 die."""
        if not self.can_interrupt():
            return False

        # Consume cheapest die
        cheapest = min(self.actions_remaining)
        self.actions_remaining.remove(cheapest)

        # Store 3rd Dan WC bonus
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            self._counterattack_wc_bonus = atk_rank * 5

        return True
