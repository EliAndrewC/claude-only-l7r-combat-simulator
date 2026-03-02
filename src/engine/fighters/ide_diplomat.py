"""IdeDiplomatFighter: Ide Diplomat school-specific overrides.

The Ide Diplomat is a hybrid diplomatic/combat school with feint + double attack
knacks, a void-based post-roll penalty mechanic, and strong void regeneration.

School Ring: Water
School Knacks: Double Attack, Feint, Worldliness

SA: After a feint which met its TN, lower the target's TN by 10 next time
    they are attacked, even if the feint was parried.
1st Dan: +1 rolled die on attack and wound check rolls.
2nd Dan: Free raise on wound check rolls (+5 flat).
3rd Dan: After any TN roll, spend 1 void to subtract Xk1 from opponent's
         roll, where X = tact rank. Applied to opponent's attack rolls and
         wound checks.
4th Dan: Water +1 (builder). Regain extra void point every night (start
         combat with +1 void).
5th Dan: Gain temp void whenever you spend a non-temp void point
         (effectively doubles regular + worldliness void).
"""

from __future__ import annotations

from src.engine.dice import roll_and_keep
from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    estimate_roll,
    should_spend_void_on_combat_roll,
)


class IdeDiplomatFighter(Fighter):
    """Ide Diplomat fighter with school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on attack and wound checks.
      2nd Dan: Free raise on wound check rolls (+5 flat).
      3rd Dan: Spend 1 void to subtract Xk1 from opponent's roll.
      4th Dan: Water +1 (builder); start combat with +1 void.
      5th Dan: Gain temp void when spending non-temp void.

    School Ability (SA): Feint that met TN → -10 TN on next attack.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        tact_skill = self.char.get_skill("Tact")
        self._tact_rank = tact_skill.rank if tact_skill else 0
        self._sa_feint_tn_bonus = 0
        self._last_5th_dan_gain = 0

        # 4th Dan: extra void from nightly recovery
        if self.dan >= 4:
            self.void_points += 1

    # -- Attack hooks -----------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int,
    ) -> tuple[str, int]:
        """Feint-aware attack strategy.

        1. If feint rank > 0 AND SA not active AND attack success low: feint
        2. Elif DA rank > 0: double_attack
        3. Else: normal attack
        """
        feint_skill = self.char.get_skill("Feint")
        feint_rank = feint_skill.rank if feint_skill else 0
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0

        void_spend = min(1, self.total_void) if self.total_void > 0 else 0

        # Feint to activate SA when attack success chance is low
        if feint_rank > 0 and self._sa_feint_tn_bonus == 0:
            # Estimate attack success
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            extra_rolled = 1 if self.dan >= 1 else 0
            rolled = atk_rank + extra_rolled + self.char.rings.fire.value
            kept = self.char.rings.fire.value

            defender = self.state.fighters.get(defender_name)
            if defender is not None:
                def_parry = defender.char.get_skill("Parry")
                def_parry_rank = def_parry.rank if def_parry else 0
                tn = 5 + def_parry_rank * 5
            else:
                tn = 15

            expected = estimate_roll(rolled, kept)
            if expected < tn * 0.8:
                return "feint", void_spend

        if da_rank > 0:
            return "double_attack", void_spend

        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Spend void on normal attack."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        return should_spend_void_on_combat_roll(
            rolled, kept, tn,
            self.total_void,
            self.char.rings.lowest(),
            known_bonus=0,
        )

    # -- SA: Feint TN reduction -------------------------------------------------

    def on_feint_result(
        self, feint_landed: bool, phase: int,
        defender_name: str = "", void_spent: int = 0,
        *, feint_met_tn: bool = False,
    ) -> None:
        """SA: Set TN bonus when feint met its TN (even if parried)."""
        if feint_met_tn:
            self._sa_feint_tn_bonus = 10

    def consume_sa_tn_bonus(self) -> tuple[int, str]:
        """Consume SA-based TN reduction from feint."""
        if self._sa_feint_tn_bonus > 0:
            bonus = self._sa_feint_tn_bonus
            self._sa_feint_tn_bonus = 0
            return bonus, f" (ide diplomat SA: feint TN -{bonus})"
        return 0, ""

    # -- 2nd Dan: Wound check free raise ----------------------------------------

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """2nd Dan: Free raise on wound check rolls (+5 flat)."""
        if self.dan >= 2:
            return 5, " (ide diplomat 2nd Dan: free raise +5)"
        return 0, ""

    # -- 3rd Dan: Opponent roll penalty -----------------------------------------

    def defend_against_attack(
        self, attack_total: int, tn: int, attacker_name: str,
    ) -> tuple[int, str]:
        """3rd Dan: Spend 1 void to subtract Xk1 from opponent's attack roll."""
        if self.dan < 3:
            return 0, ""
        if attack_total < tn:
            return 0, ""
        if self.total_void <= 1:
            return 0, ""

        # Estimate penalty
        expected_penalty = estimate_roll(self._tact_rank, 1)
        margin = attack_total - tn
        if margin >= expected_penalty * 1.5:
            return 0, ""

        # Spend 1 void and roll
        self.spend_void(1)
        _, kept_dice, penalty = roll_and_keep(
            self._tact_rank, 1, explode=True,
        )
        note = (
            f" (ide diplomat 3rd Dan: -{penalty} to attack,"
            f" rolled {self._tact_rank}k1)"
        )
        return penalty, note

    def penalize_opponent_wound_check(
        self, wc_total: int, wc_tn: int, defender_name: str,
    ) -> tuple[int, str]:
        """3rd Dan: Spend 1 void to subtract Xk1 from opponent's wound check."""
        if self.dan < 3:
            return 0, ""
        if wc_total < wc_tn:
            return 0, ""
        if self.total_void <= 1:
            return 0, ""

        # Estimate penalty
        expected_penalty = estimate_roll(self._tact_rank, 1)
        margin = wc_total - wc_tn
        if margin >= expected_penalty * 1.5:
            return 0, ""

        # Spend 1 void and roll
        self.spend_void(1)
        _, kept_dice, penalty = roll_and_keep(
            self._tact_rank, 1, explode=True,
        )
        note = (
            f" (ide diplomat 3rd Dan: -{penalty} to wound check,"
            f" rolled {self._tact_rank}k1)"
        )
        return penalty, note

    # -- Wound check hooks ------------------------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    # -- 5th Dan: Void regeneration ---------------------------------------------

    def spend_void(self, amount: int) -> tuple[int, int, int]:
        """5th Dan: Gain temp void when spending non-temp void."""
        from_temp, from_reg, from_wl = super().spend_void(amount)
        self._last_5th_dan_gain = 0
        if self.dan >= 5:
            non_temp = from_reg + from_wl
            if non_temp > 0:
                self.temp_void += non_temp
                self._last_5th_dan_gain = non_temp
        return from_temp, from_reg, from_wl

    def on_void_spent(self, amount: int, context: str) -> str:
        """Report temp void gain from 5th Dan."""
        if self._last_5th_dan_gain > 0:
            gain = self._last_5th_dan_gain
            self._last_5th_dan_gain = 0
            return (
                f" (ide diplomat 5th Dan: +{gain} temp void)"
            )
        return ""
