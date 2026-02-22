"""IsawaDuelistFighter: Isawa Duelist school-specific overrides.

SA: Add Water instead of Fire to rolled damage dice.
1st Dan: +1 rolled die on double attack, lunge, and wound check rolls.
2nd Dan: Free raise on wound checks (+5 flat).
3rd Dan: Lower own TN by 5 → +3X on attack (X = attack rank). Penalty removed
         if opponent parries (success or fail).
4th Dan: Water +1 (builder). Once per turn, lunge as interrupt for 1 die
         (deferred — complex mechanic).
5th Dan: After successful WC, store excess for future WC bonus.
"""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import should_spend_void_on_combat_roll


class IsawaDuelistFighter(Fighter):
    """Isawa Duelist fighter with school technique overrides."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._tn_penalty_pending: bool = False
        self._wc_bonus_pool: int = 0
        worldliness_skill = self.char.get_skill("Worldliness")
        worldliness_rank = worldliness_skill.rank if worldliness_skill else 0
        self.worldliness_void = worldliness_rank

    # -- SA: Water for damage instead of Fire --------------------------------

    def damage_ring_value(self) -> int:
        """SA: Use Water instead of Fire for damage dice."""
        return self.char.rings.water.value

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Isawa Duelist prefers DA when available, else lunge, else attack."""
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        lunge_skill = self.char.get_skill("Lunge")
        lunge_rank = lunge_skill.rank if lunge_skill else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "attack", 0
        if da_rank > 0:
            return "double_attack", 0
        if lunge_rank > 0:
            return "lunge", 0
        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on DA and lunge (and normal attack for simplicity)."""
        return 1 if self.dan >= 1 else 0

    def lunge_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on lunge."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Void spending with known 3rd Dan bonus."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        known_bonus = 0
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            known_bonus = 3 * atk_rank
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=known_bonus,
        )

    def sa_attack_bonus(
        self, phase: int, die_value: int | None = None,
    ) -> tuple[int, str]:
        """3rd Dan: +3X on attack (X = attack rank), sets TN penalty."""
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            bonus = 3 * atk_rank
            self._tn_penalty_pending = True
            return bonus, f" (isawa 3rd Dan: +{bonus}, TN penalty pending)"
        return 0, ""

    # -- 3rd Dan: TN penalty (self-debuff) ----------------------------------

    def defender_tn_penalty(self) -> tuple[int, str]:
        """3rd Dan: TN lowered by 5 when being attacked (self-debuff).

        Consumed on use. Set by sa_attack_bonus, cleared by on_attack_parried.
        """
        if self._tn_penalty_pending:
            self._tn_penalty_pending = False
            return 5, " (isawa 3rd Dan: -5 TN self-debuff)"
        return 0, ""

    def on_attack_parried(self, parry_succeeded: bool) -> None:
        """3rd Dan: If attack was parried, clear TN penalty."""
        self._tn_penalty_pending = False

    # -- Wound check hooks --------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """2nd Dan: +5 on wound checks. 5th Dan: stored WC bonus."""
        bonus = 0
        notes: list[str] = []
        if self.dan >= 2:
            bonus += 5
            notes.append("isawa 2nd Dan: free raise +5")
        if self._wc_bonus_pool > 0:
            bonus += self._wc_bonus_pool
            notes.append(
                f"isawa 5th Dan: +{self._wc_bonus_pool} from WC pool"
            )
            self._wc_bonus_pool = 0
        note = f" ({'; '.join(notes)})" if notes else ""
        return bonus, note

    # -- 5th Dan: WC excess → future WC bonus --------------------------------

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """5th Dan: After successful WC, store excess for future WC."""
        if self.dan >= 5 and passed:
            wound_tracker = self.state.log.wounds[self.name]
            tn = wound_tracker.light_wounds
            excess = wc_total - tn
            if excess > 0:
                self._wc_bonus_pool += excess
        return passed, wc_total, ""
