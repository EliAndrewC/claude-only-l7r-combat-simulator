"""OtakuFighter: Otaku Bushi school-specific overrides."""

from __future__ import annotations

from src.engine.fighters.base import Fighter
from src.engine.simulation_utils import estimate_roll


def _otaku_attack_choice(
    lunge_rank: int,
    double_attack_rank: int,
    fire_ring: int,
    defender_parry: int,
    dan: int,
    is_crippled: bool,
) -> str:
    """Decide whether Otaku uses Lunge or Double Attack (never spends void).

    Returns:
        "lunge" or "double_attack".
    """
    if is_crippled or double_attack_rank <= 0:
        return "lunge"

    base_tn = 5 + 5 * defender_parry
    da_tn = base_tn + 20
    first_dan_bonus = 1 if dan >= 1 else 0

    da_rolled = double_attack_rank + fire_ring + first_dan_bonus
    da_kept = fire_ring
    da_expected = estimate_roll(da_rolled, da_kept)

    if da_expected >= da_tn * 0.85:
        return "double_attack"

    return "lunge"


class OtakuFighter(Fighter):
    """Otaku Bushi fighter with full school technique overrides.

    Dan techniques:
      1st Dan: +1 rolled die on lunge attacks and wound checks.
      2nd Dan: +5 flat bonus on wound checks (free raise).
      3rd Dan: After dealing damage, increase opponent's next X action dice
               by max(1, 6 - defender_fire), where X = attack skill rank.
      4th Dan: Fire +1 / XP discount (builder). Lunge bonus die is immune
               to parry reduction.
      5th Dan: If damage_rolled >= 12, trade 10 dice for 1 auto serious wound.

    School Ability (SA): After being attacked, counter-lunge by consuming
    highest action die. Guarded against Otaku-vs-Otaku recursion.

    Otaku NEVER spends void on attacks (saves void for wound checks where
    2nd Dan bonus makes it more efficient).
    """

    _in_counter_lunge: bool = False
    _pending_die: int | None = None
    _counter_lunge_die: int | None = None

    # -- Attack hooks -------------------------------------------------------

    def set_pending_die(self, value: int) -> None:
        """Store a pending die value for the next consume_attack_die call."""
        self._pending_die = value

    def consume_attack_die(
        self, phase: int, die_value: int | None = None,
    ) -> int | None:
        """Consume a die for attacking, checking pending die first."""
        if die_value is None and self._pending_die is not None:
            die_value = self._pending_die
            self._pending_die = None
        if die_value is not None:
            if die_value in self.actions_remaining:
                self.actions_remaining.remove(die_value)
                return die_value
            return None
        if phase in self.actions_remaining:
            self.actions_remaining.remove(phase)
            return phase
        return None

    def choose_attack(
        self, defender_name: str, phase: int
    ) -> tuple[str, int]:
        """Otaku uses Lunge or DA — never spends void on attacks."""
        is_crippled = self.state.log.wounds[self.name].is_crippled
        if is_crippled:
            return "lunge", 0

        da_skill = self.char.get_skill("Double Attack")
        da_rank = da_skill.rank if da_skill else 0
        lunge_skill = self.char.get_skill("Lunge")
        lunge_rank = lunge_skill.rank if lunge_skill else 0
        def_ctx = self.state.fighters[defender_name]
        def_parry_skill = def_ctx.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0

        choice = _otaku_attack_choice(
            lunge_rank,
            da_rank,
            self.char.rings.fire.value,
            def_parry_rank,
            self.dan,
            is_crippled,
        )
        return choice, 0

    # -- Parry hooks (Otaku is reluctant — save dice for counter-lunges) ----

    def should_predeclare_parry(
        self, attack_tn: int, phase: int,
    ) -> bool:
        """Otaku never pre-declares parries (save dice for SA)."""
        return False

    def should_reactive_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Otaku only parries when expected damage is very high."""
        from src.engine.simulation_utils import should_reactive_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
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
            is_kakita=True,
        )

    def should_interrupt_parry(
        self,
        attack_total: int,
        attack_tn: int,
        weapon_rolled: int,
        attacker_fire: int,
    ) -> bool:
        """Otaku only interrupt-parries against very high damage."""
        from src.engine.simulation_utils import should_interrupt_parry

        def_parry_skill = self.char.get_skill("Parry")
        def_parry_rank = def_parry_skill.rank if def_parry_skill else 0
        wound_info = self.state.log.wounds[self.name]
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
            is_kakita=True,
        )

    def attack_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on attack (applies to DA)."""
        return 1 if self.dan >= 1 else 0

    # -- Lunge / Damage hooks -----------------------------------------------

    def lunge_extra_rolled(self) -> int:
        """1st Dan: +1 extra rolled die on lunge attacks."""
        return 1 if self.dan >= 1 else 0

    def lunge_damage_survives_parry(self) -> bool:
        """4th Dan: lunge bonus die is immune to parry reduction."""
        return self.dan >= 4

    def should_trade_damage_for_wound(
        self, damage_rolled: int, *, is_double_attack: bool = False,
    ) -> tuple[bool, int, str]:
        """5th Dan: trade 10 damage dice for 1 automatic serious wound.

        Always trades on lunge/regular attacks when pool >= 10.
        Never trades on double attacks (which already inflict auto SW).
        """
        if is_double_attack:
            return False, 0, ""
        if self.dan >= 5 and damage_rolled >= 10:
            return True, 10, " (otaku 5th Dan: traded 10 dice for 1 auto SW)"
        return False, 0, ""

    def post_damage_effect(self, defender_name: str) -> str:
        """3rd Dan: increase opponent's next X action dice.

        Increase = max(1, 6 - defender_fire).
        X = attacker's Attack skill rank.
        Capped at phase 10.
        """
        if self.dan < 3:
            return ""

        atk_skill = self.char.get_skill("Attack")
        atk_rank = atk_skill.rank if atk_skill else 0
        if atk_rank <= 0:
            return ""

        def_ctx = self.state.fighters[defender_name]
        def_fire = def_ctx.char.rings.fire.value
        increase = max(1, 6 - def_fire)

        actions = def_ctx.actions_remaining
        if not actions:
            return ""

        # Increase the first X dice (lowest phases = next actions)
        actions.sort()
        count = min(atk_rank, len(actions))
        for i in range(count):
            actions[i] = min(10, actions[i] + increase)

        return (
            f" (otaku 3rd Dan: opponent's next {count}"
            f" dice +{increase})"
        )

    # -- Wound check hooks (as defender) ------------------------------------

    def wound_check_extra_rolled(self) -> int:
        """1st Dan: +1 rolled die on wound checks."""
        return 1 if self.dan >= 1 else 0

    def wound_check_flat_bonus(self) -> tuple[int, str]:
        """2nd Dan: +5 flat bonus on wound checks (free raise)."""
        if self.dan >= 2:
            return 5, " (otaku 2nd Dan: free raise +5)"
        return 0, ""

    # -- SA: Counter-lunge interrupt ----------------------------------------

    def resolve_post_attack_interrupt(
        self, attacker_name: str, phase: int,
        attack_total: int = 0,
    ) -> None:
        """SA: After being attacked, counter-lunge using highest action die.

        Guards against Otaku-vs-Otaku infinite recursion.
        """
        # Prevent recursion
        if self._in_counter_lunge:
            return

        # Need dice to counter-lunge
        if not self.actions_remaining:
            return

        # Don't counter if mortally wounded
        if self.state.log.wounds[self.name].is_mortally_wounded:
            return
        if self.state.log.wounds[attacker_name].is_mortally_wounded:
            return

        from src.engine.fighters import create_fighter
        from src.engine.simulation import _resolve_attack

        # Set highest die as pending so consume_attack_die finds it
        highest = max(self.actions_remaining)
        self.set_pending_die(highest)
        self._counter_lunge_die = highest

        # Force lunge attack
        self._in_counter_lunge = True
        self._force_lunge = True
        try:
            atk_fighter = create_fighter(attacker_name, self.state)
            _resolve_attack(self.state, self, atk_fighter, phase)
        finally:
            self._in_counter_lunge = False
            self._force_lunge = False
            self._counter_lunge_die = None
