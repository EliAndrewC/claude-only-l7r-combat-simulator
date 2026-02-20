"""AttackResolver: orchestrates a single attack action between two fighters.

Delegates to simulation._resolve_attack which uses CombatState directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState
    from src.engine.fighters.base import Fighter


class AttackResolver:
    """Resolves a single attack action in a combat phase.

    Orchestrates calls to both attacker and defender Fighter methods.
    """

    def __init__(
        self,
        state: CombatState,
        attacker: Fighter,
        defender: Fighter,
        phase: int,
    ) -> None:
        self._state = state
        self._attacker = attacker
        self._defender = defender
        self._phase = phase

    def resolve(self) -> None:
        """Execute the full attack resolution sequence."""
        from src.engine.simulation import _resolve_attack

        _resolve_attack(
            self._state,
            self._attacker,
            self._defender,
            self._phase,
        )
