"""Fighter class hierarchy for school-specific combat behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.engine.fighters.base import Fighter
from src.engine.fighters.generic import GenericFighter

if TYPE_CHECKING:
    from src.engine.combat_state import CombatState
    from src.models.character import Character
    from src.models.weapon import Weapon

__all__ = ["Fighter", "GenericFighter", "create_fighter"]


def create_fighter(
    name: str,
    state: CombatState,
    char: Character | None = None,
    weapon: Weapon | None = None,
    **kwargs: object,
) -> Fighter:
    """Factory: return the appropriate Fighter subclass for the character's school.

    Builds a Fighter directly and registers it in state.fighters.
    If the entry already exists as a Fighter, returns it.
    """
    entry = state.fighters.get(name)

    # If already a Fighter instance in state, return it
    if isinstance(entry, Fighter):
        return entry

    assert char is not None, f"char is required to create fighter '{name}'"

    school = char.school

    if school == "Mirumoto Bushi":
        from src.engine.fighters.mirumoto import MirumotoFighter

        fighter = MirumotoFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Matsu Bushi":
        from src.engine.fighters.matsu import MatsuFighter

        fighter = MatsuFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Kakita Duelist":
        from src.engine.fighters.kakita import KakitaFighter

        fighter = KakitaFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Shinjo Bushi":
        from src.engine.fighters.shinjo import ShinjoFighter

        fighter = ShinjoFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Otaku Bushi":
        from src.engine.fighters.otaku import OtakuFighter

        fighter = OtakuFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Hida Bushi":
        from src.engine.fighters.hida import HidaFighter

        fighter = HidaFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Shiba Bushi":
        from src.engine.fighters.shiba import ShibaFighter

        fighter = ShibaFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Bayushi Bushi":
        from src.engine.fighters.bayushi import BayushiFighter

        fighter = BayushiFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Courtier":
        from src.engine.fighters.courtier import CourtierFighter

        fighter = CourtierFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif school == "Merchant":
        from src.engine.fighters.merchant import MerchantFighter

        fighter = MerchantFighter(name, state, char=char, weapon=weapon, **kwargs)
    elif char.profession_abilities:
        from src.engine.fighters.waveman import WaveManFighter

        fighter = WaveManFighter(name, state, char=char, weapon=weapon, **kwargs)
    else:
        fighter = GenericFighter(name, state, char=char, weapon=weapon, **kwargs)

    # Register in state
    state.fighters[name] = fighter
    return fighter
