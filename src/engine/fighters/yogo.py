"""YogoFighter: Yogo Warden school-specific overrides.

SA: Gain a temporary void point every time you take a serious wound.
1st Dan: +1 rolled die on attack, damage, and wound check rolls.
2nd Dan: Free raise on wound checks (+5 flat).
3rd Dan: When spending void, reduce LW by 2X (X = attack skill).
4th Dan: Earth +1 (builder). Extra free raise per void on WC rolls.
5th Dan: TBD (no-op).
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class YogoFighter(Fighter):
    """Yogo Warden fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._wc_void_spent: int = 0
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Yogo prefers DA when available."""
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "attack", 0
        if da_rank > 0:
            return "double_attack", 0
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
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

    # -- 1st Dan: +1 rolled die on damage -----------------------------------

    def weapon_rolled_boost(self, weapon_rolled: int, weapon_kept: int) -> int:
        """1st Dan: +1 rolled die on damage."""
        if self.dan >= 1:
            return weapon_rolled + 1
        return weapon_rolled

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """2nd Dan: +5 on WC. 4th Dan: +5 per void spent on WC."""
        bonus = 0
        notes: list[str] = []
        if self.dan >= 2:
            bonus += 5
            notes.append("yogo 2nd Dan: free raise +5")
        if self.dan >= 4 and self._wc_void_spent > 0:
            void_bonus = self._wc_void_spent * 5
            bonus += void_bonus
            notes.append(
                f"yogo 4th Dan: {self._wc_void_spent} void"
                f" = +{void_bonus} free raises"
            )
        note = f" ({'; '.join(notes)})" if notes else ""
        return bonus, note

    def wound_check_void_strategy(
        self, water_ring: int, light_wounds: int,
    ) -> int:
        """Store void spent for 4th Dan bonus."""
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

    # -- SA: Temp void on serious wound -------------------------------------

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """SA: Gain temp void for each serious wound taken."""
        self._wc_void_spent = 0
        wound_tracker = self.state.log.wounds[self.name]
        sw_gained = wound_tracker.serious_wounds - sw_before_wc
        if sw_gained > 0:
            self.temp_void += sw_gained
            note = f" (yogo SA: +{sw_gained} temp void from serious wound(s))"
            return passed, wc_total, note
        return passed, wc_total, ""

    # -- 3rd Dan: Void spending reduces LW -----------------------------------

    def on_void_spent(self, amount: int, context: str) -> str:
        """3rd Dan: Reduce LW by 2X per void spent (X = attack skill)."""
        if self.dan < 3:
            return ""
        atk_skill = self.char.get_skill("Attack")
        atk_rank = atk_skill.rank if atk_skill else 0
        reduction = 2 * atk_rank * amount
        if reduction <= 0:
            return ""
        wound_tracker = self.state.log.wounds[self.name]
        actual = min(reduction, wound_tracker.light_wounds)
        if actual <= 0:
            return ""
        wound_tracker.light_wounds -= actual
        return f" (yogo 3rd Dan: -{actual} LW)"
