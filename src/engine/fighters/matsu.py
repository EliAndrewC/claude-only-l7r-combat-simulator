"""MatsuFighter: Matsu Bushi school-specific overrides."""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import estimate_roll


def _matsu_attack_choice(
    lunge_rank: int,
    double_attack_rank: int,
    attack_skill: int,
    fire_ring: int,
    defender_parry: int,
    void_available: int,
    max_void_spend: int,
    dan: int,
    is_crippled: bool,
    known_bonus: int = 0,
    da_threshold: float = 0.85,
) -> tuple[str, int]:
    """Decide whether Matsu uses Lunge or Double Attack, and void to spend.

    Matsu NEVER makes a normal attack -- always Lunge or Double Attack.

    Returns:
        Tuple of ("lunge" | "double_attack", void_to_spend).
    """
    if is_crippled or double_attack_rank <= 0:
        usable = (
            min(void_available, max_void_spend) if dan >= 3
            else (
                min(void_available - 1, max_void_spend)
                if void_available > 1 else 0
            )
        )
        lunge_rolled = lunge_rank + fire_ring
        lunge_kept = fire_ring
        base_tn = 5 + 5 * defender_parry
        expected = estimate_roll(lunge_rolled, lunge_kept) + known_bonus
        if expected >= base_tn or usable <= 0:
            return "lunge", 0
        deficit = base_tn - expected
        void_spend = min(usable, max(1, int(deficit / 5.5 + 0.5)))
        return "lunge", void_spend

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    first_dan_bonus = 1 if dan >= 1 else 0

    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = estimate_roll(da_rolled, da_kept) + known_bonus

    usable_void = (
        min(void_available, max_void_spend) if dan >= 3
        else (
            min(void_available - 1, max_void_spend)
            if void_available > 1 else 0
        )
    )
    max_void_boost = usable_void * 5.5

    if dan >= 4:
        effective_da_tn = da_tn - 20
        if da_expected + max_void_boost >= effective_da_tn * 0.6:
            if da_expected >= effective_da_tn:
                return "double_attack", 0
            deficit = effective_da_tn - da_expected
            void_spend = min(
                usable_void, max(1, int(deficit / 5.5 + 0.5)),
            )
            return "double_attack", void_spend
    else:
        if da_expected + max_void_boost >= da_tn * da_threshold:
            if da_expected >= da_tn:
                return "double_attack", 0
            deficit = da_tn - da_expected
            void_spend = min(
                usable_void, max(1, int(deficit / 5.5 + 0.5)),
            )
            return "double_attack", void_spend

    # DA not viable: Lunge
    lunge_rolled = lunge_rank + fire_ring
    lunge_kept = fire_ring
    expected = estimate_roll(lunge_rolled, lunge_kept) + known_bonus
    if expected >= base_tn or usable_void <= 0:
        return "lunge", 0
    deficit = base_tn - expected
    void_spend = min(usable_void, max(1, int(deficit / 5.5 + 0.5)))
    return "lunge", void_spend


class MatsuFighter(Fighter):
    """Matsu Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on attack (DA) and wound checks.
      3rd Dan: Void spending on any action generates wound-check bonus
               (3 * Attack rank per void point).  Stored bonuses can be
               applied to a failed wound check to pass it.  Skip void on
               wound checks when stored bonuses are sufficient.
      4th Dan: Near-miss DA (within 20 of TN) still hits (base damage only).
      5th Dan: On failed wound check, light wounds reset to 15 (not 0).

    School Ability (SA): Always rolls 10 dice for initiative.
    Matsu NEVER makes a normal attack -- always Lunge or Double Attack.
    """

    # -- Initiative hooks ---------------------------------------------------

    def initiative_extra_unkept(self) -> int:
        """SA: Always roll 10 dice for initiative (fill to 10)."""
        return max(0, 9 - self.char.rings.void.value)

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int
    ) -> tuple[str, int]:
        """Matsu always uses Lunge or DA -- never a normal attack."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "lunge", 0

        lunge_skill = self.char.get_skill("Lunge")
        lunge_rank = lunge_skill.rank if lunge_skill else 0
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        atk_skill = self.char.get_skill("Attack")
        atk_rank = atk_skill.rank if atk_skill else 0
        def_ctx = self.state.fighters[defender_name]
        def_parry_skill = def_ctx.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

        choice, void_spend = _matsu_attack_choice(
            lunge_rank,
            da_rank,
            atk_rank,
            self.char.rings.fire.value,
            def_parry_rank,
            self.total_void,
            self.char.rings.lowest(),
            self.dan,
            is_crippled,
            da_threshold=self.strategy.da_threshold,
        )
        return choice, void_spend

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack (applies to DA)."""
        return 1 if self.dan >= 1 else 0

    def on_near_miss_da(self) -> bool:
        """4th Dan: near-miss DA (within 20 of TN) still hits."""
        return self.dan >= 4

    def near_miss_da_description(self) -> str:
        """4th Dan: near-miss DA description."""
        return " (matsu 4th Dan: near-miss hit, base damage only)"

    def on_void_spent(self, amount: int, context: str) -> str:
        """3rd Dan: each void spent generates a wound-check bonus.

        The bonus is 3 * Attack rank per void point.
        """
        if self.dan >= 3 and amount > 0:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            bonus_value = 3 * atk_rank
            for _ in range(amount):
                self.matsu_bonuses.append(bonus_value)
            return (
                f" (matsu 3rd Dan: +{bonus_value}"
                f" wound check bonus stored)"
            )
        return ""

    # -- Wound check hooks (as defender) ------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_void_strategy(
        self, water_ring: int, light_wounds: int
    ) -> int:
        """3rd Dan: skip void when stored bonuses can plausibly help."""
        if self.dan >= 3 and self.matsu_bonuses:
            for bonus in self.matsu_bonuses:
                if bonus >= light_wounds * 0.3:
                    return 0  # skip void, rely on stored bonus
        return -1  # use default logic

    def post_wound_check(
        self, passed: bool, wc_total: int, attacker_name: str,
        sw_before_wc: int = 0,
    ) -> tuple[bool, int, str]:
        """3rd Dan: apply stored bonus to turn a failed wound check into pass."""
        if self.dan >= 3 and not passed and self.matsu_bonuses:
            effective_tn = self.state.log.wounds[self.name].light_wounds
            for i, bonus in enumerate(self.matsu_bonuses):
                if wc_total + bonus >= effective_tn:
                    self.matsu_bonuses.pop(i)
                    new_total = wc_total + bonus
                    note = f" (matsu 3rd Dan: applied +{bonus} bonus)"
                    return True, new_total, note
        return passed, wc_total, ""

    def on_wound_check_failed(self, attacker_name: str) -> tuple[int, str]:
        """5th Dan: light wounds reset to 15 instead of 0."""
        if self.dan >= 5:
            return 15, (
                " (matsu 5th Dan: light wounds reset"
                " to 15)"
            )
        return 0, ""
