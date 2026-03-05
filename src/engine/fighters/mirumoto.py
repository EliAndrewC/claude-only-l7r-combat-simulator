"""MirumotoFighter: Mirumoto Bushi school-specific overrides."""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import (
    compute_dan_roll_bonus,
    estimate_roll,
    should_spend_void_on_combat_roll,
)


def _should_use_double_attack(
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
) -> tuple[bool, int]:
    """Decide whether to use Double Attack and how much void to spend.

    Returns:
        Tuple of (use_double_attack, void_to_spend).
    """
    if double_attack_rank <= 0 or is_crippled:
        return False, 0

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    fifth_dan_bonus = 10 if dan >= 5 else 0
    first_dan_bonus = 1 if dan >= 1 else 0

    normal_rolled = attack_skill + fire_ring + first_dan_bonus
    normal_kept = fire_ring
    normal_expected = estimate_roll(normal_rolled, normal_kept) + known_bonus

    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = estimate_roll(da_rolled, da_kept) + known_bonus

    usable_void = (
        min(void_available - 1, max_void_spend)
        if void_available > 1 else 0
    )
    void_value_per = 5.5 + fifth_dan_bonus
    max_void_boost = usable_void * void_value_per

    if da_expected + max_void_boost < da_tn * 0.7:
        return False, 0

    if (
        normal_expected >= base_tn
        and da_expected + max_void_boost >= da_tn * da_threshold
    ):
        if da_expected >= da_tn:
            return True, 0
        deficit = da_tn - da_expected
        void_spend = min(
            usable_void,
            max(1, int(deficit / void_value_per + 0.5)),
        )
        return True, void_spend

    return False, 0


class MirumotoFighter(Fighter):
    """Mirumoto Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on attack and parry rolls.
      2nd Dan: +5 free-raise bonus on parry.
      3rd Dan: Dan points regenerate each round (2 * Attack rank);
               spend points post-roll for +2 per point on attack/parry;
               phase-shift parry (spend points to react without a die in phase).
      4th Dan: Only half of defender's Parry rank reduces extra damage dice.
      5th Dan: +10 per void point spent on attack or parry.

    School Ability (SA): +1 temporary void after every parry attempt.
    """

    # -- Round management ---------------------------------------------------

    def on_round_start(self) -> None:
        """Regenerate dan points (3rd Dan+): 2 * Attack rank per round."""
        if self.dan >= 3:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            self.dan_points = 2 * atk_rank
        else:
            self.dan_points = 0

    # -- Attack hooks -------------------------------------------------------

    def choose_attack(
        self, defender_name: str, phase: int
    ) -> tuple[str, int]:
        """Use Double Attack when expected to hit; otherwise normal attack."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0

        if da_rank > 0 and not is_crippled:
            atk_skill = self.char.get_skill("Attack")
            atk_rank = atk_skill.rank if atk_skill else 0
            def_ctx = self.state.fighters[defender_name]
            def_parry_skill = def_ctx.char.get_skill("Parry")
            def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
            use_da, void_spend = _should_use_double_attack(
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
            if use_da:
                return "double_attack", void_spend

        return "attack", 0

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack."""
        return 1 if self.dan >= 1 else 0

    def attack_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Spend void on normal attacks when beneficial."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        fifth_dan_bonus = 10 if self.dan >= 5 else 0
        return should_spend_void_on_combat_roll(
            rolled,
            kept,
            tn,
            self.total_void,
            self.char.rings.lowest(),
            fifth_dan_bonus=fifth_dan_bonus,
        )

    def fifth_dan_void_bonus(self, void_spent: int) -> int:
        """5th Dan: +10 per void point spent on attack or parry."""
        if self.dan >= 5:
            return 10 * void_spent
        return 0

    def post_attack_roll_bonus(
        self, attack_total: int, tn: int, phase: int, defender_name: str
    ) -> tuple[int, str]:
        """3rd Dan: spend dan points for +2 per point on a missed attack."""
        if self.dan >= 3 and attack_total < tn:
            dan_bonus_pts = compute_dan_roll_bonus(
                attack_total, tn, self.dan_points,
            )
            if dan_bonus_pts > 0:
                self.dan_points -= dan_bonus_pts
                bonus = dan_bonus_pts * 2
                return bonus, (
                    f" (3rd dan: +{bonus} bonus,"
                    f" {dan_bonus_pts} pts)"
                )
        return 0, ""

    # -- Parry hooks (as defender) ------------------------------------------

    def should_predeclare_parry(self, attack_tn: int, phase: int) -> bool:
        """Use generic predeclare heuristic (with known +5 2nd Dan bonus)."""
        from src.engine.simulation_utils import should_predeclare_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        if def_parry_rank <= 0:
            return False
        known_bonus = 5 if self.dan >= 2 else 0
        is_crippled = self.state.log.wounds[self.name].is_crippled
        return should_predeclare_parry(
            def_parry_rank,
            self.char.rings.air.value,
            attack_tn,
            is_crippled,
            known_bonus=known_bonus,
        )

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Always parry when possible (Mirumoto is the strongest parry school)."""
        from src.engine.simulation_utils import should_reactive_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
        known_bonus = 5 if self.dan >= 2 else 0
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
            is_mirumoto=True,
            known_bonus=known_bonus,
            parry_threshold=self.strategy.parry_aggressiveness,
        )

    def should_interrupt_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Interrupt parry decision with Mirumoto-specific thresholds."""
        from src.engine.simulation_utils import should_interrupt_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
        known_bonus = 5 if self.dan >= 2 else 0
        return should_interrupt_parry(
            def_parry_rank,
            self.char.rings.air.value,
            attack_total,
            attack_tn,
            weapon_rolled,
            attacker_fire,
            len(self.actions_remaining),
            wound_info.serious_wounds,
            wound_info.earth_ring,
            is_mirumoto=True,
            known_bonus=known_bonus,
        )

    def fifth_dan_void_description(self, bonus: int) -> str:
        """5th Dan: description for void bonus on attack or parry."""
        if bonus > 0:
            return f" (mirumoto: +{bonus} 5th Dan)"
        return ""

    def post_parry_effect_description(
        self,
        temp_void_delta: int,
        actions_changed: bool,
        bonus_stored: int | None,
    ) -> str:
        """SA: temp void gain description."""
        if temp_void_delta > 0:
            return f" (mirumoto SA: +{temp_void_delta} temp void)"
        return ""

    def can_phase_shift_parry(
        self, phase: int,
    ) -> tuple[bool, int, int]:
        """3rd Dan: phase-shift parry using dan points."""
        if self.dan < 3:
            return False, 0, 0
        from src.engine.simulation_utils import try_phase_shift_parry

        actions_remaining = {
            n: ctx.actions_remaining
            for n, ctx in self.state.fighters.items()
        }
        dan_points = {
            n: ctx.dan_points
            for n, ctx in self.state.fighters.items()
        }
        wound_info = self.state.log.wounds[self.name]
        return try_phase_shift_parry(
            phase, self.name, actions_remaining, dan_points,
            wound_info.serious_wounds, wound_info.earth_ring,
        )

    def parry_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on parry."""
        return 1 if self.dan >= 1 else 0

    def parry_bonus(self) -> int:
        """2nd Dan: +5 free-raise bonus on parry."""
        return 5 if self.dan >= 2 else 0

    def parry_bonus_description(self, bonus: int) -> str:
        """2nd Dan: mirumoto-specific parry bonus description."""
        return f" (mirumoto: free raise +{bonus})"

    def parry_void_strategy(self, rolled: int, kept: int, tn: int) -> int:
        """Spend void on parry when beneficial."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return 0
        fifth_dan_bonus = 10 if self.dan >= 5 else 0
        return should_spend_void_on_combat_roll(
            rolled,
            kept,
            tn,
            self.total_void,
            self.char.rings.lowest(),
            fifth_dan_bonus=fifth_dan_bonus,
        )

    def post_parry_roll_bonus(
        self, parry_total: int, parry_tn: int
    ) -> tuple[int, str]:
        """3rd Dan: spend dan points for +2 per point on a failed parry."""
        if self.dan >= 3 and parry_total < parry_tn:
            dan_parry_pts = compute_dan_roll_bonus(
                parry_total, parry_tn, self.dan_points,
                is_parry=True,
            )
            if dan_parry_pts > 0:
                self.dan_points -= dan_parry_pts
                bonus = dan_parry_pts * 2
                return bonus, (
                    f" (3rd dan: +{bonus} bonus,"
                    f" {dan_parry_pts} pts)"
                )
        return 0, ""

    def on_parry_attempt(
        self, parry_succeeded: bool, margin: int,
        attacker_name: str = "", phase: int = 0,
    ) -> None:
        """School Ability: +1 temporary void after every parry attempt."""
        self.temp_void += 1

    # -- Damage hooks -------------------------------------------------------

    def damage_parry_reduction(self, defender_parry_rank: int) -> int:
        """4th Dan: only half of defender's Parry rank reduces extra dice."""
        if self.dan >= 4:
            return defender_parry_rank // 2
        return defender_parry_rank
