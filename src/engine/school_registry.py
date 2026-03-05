"""School-to-builder mapping for mass simulation.

Extracts the school→builder mapping into a pure-logic module so both the
Streamlit UI and the mass simulation engine can share it.
"""

from __future__ import annotations

from collections.abc import Callable

from src.engine.character_builders.akodo import build_akodo_from_xp
from src.engine.character_builders.bayushi import build_bayushi_from_xp
from src.engine.character_builders.brotherhood_monk import build_brotherhood_monk_from_xp
from src.engine.character_builders.courtier import build_courtier_from_xp
from src.engine.character_builders.daidoji import build_daidoji_from_xp
from src.engine.character_builders.doji_artisan import build_doji_artisan_from_xp
from src.engine.character_builders.hida import build_hida_from_xp
from src.engine.character_builders.hiruma import build_hiruma_from_xp
from src.engine.character_builders.ide_diplomat import build_ide_diplomat_from_xp
from src.engine.character_builders.ikoma_bard import build_ikoma_bard_from_xp
from src.engine.character_builders.isawa_duelist import build_isawa_duelist_from_xp
from src.engine.character_builders.isawa_ishi import build_isawa_ishi_from_xp
from src.engine.character_builders.kakita import build_kakita_from_xp
from src.engine.character_builders.kitsuki import build_kitsuki_from_xp
from src.engine.character_builders.kuni import build_kuni_from_xp
from src.engine.character_builders.matsu import build_matsu_from_xp
from src.engine.character_builders.merchant import build_merchant_from_xp
from src.engine.character_builders.mirumoto import build_mirumoto_from_xp
from src.engine.character_builders.otaku import build_otaku_from_xp
from src.engine.character_builders.priest import build_priest_from_xp
from src.engine.character_builders.shiba import build_shiba_from_xp
from src.engine.character_builders.shinjo import build_shinjo_from_xp
from src.engine.character_builders.shosuro import build_shosuro_from_xp
from src.engine.character_builders.togashi import build_togashi_from_xp
from src.engine.character_builders.waveman import build_waveman_from_xp
from src.engine.character_builders.yogo import build_yogo_from_xp
from src.models.character import Character
from src.models.weapon import WeaponType

# Each builder has signature: (name: str, earned_xp: int, non_combat_pct: float) -> Character
SCHOOL_BUILDERS: dict[str, Callable[[str, int, float], Character]] = {
    "Akodo Bushi": build_akodo_from_xp,
    "Bayushi Bushi": build_bayushi_from_xp,
    "Brotherhood Monk": build_brotherhood_monk_from_xp,
    "Courtier": build_courtier_from_xp,
    "Daidoji Yojimbo": build_daidoji_from_xp,
    "Doji Artisan": build_doji_artisan_from_xp,
    "Hida Bushi": build_hida_from_xp,
    "Hiruma Scout": build_hiruma_from_xp,
    "Ide Diplomat": build_ide_diplomat_from_xp,
    "Ikoma Bard": build_ikoma_bard_from_xp,
    "Isawa Duelist": build_isawa_duelist_from_xp,
    "Isawa Ishi": build_isawa_ishi_from_xp,
    "Kakita Duelist": build_kakita_from_xp,
    "Kitsuki Magistrate": build_kitsuki_from_xp,
    "Kuni Witch Hunter": build_kuni_from_xp,
    "Matsu Bushi": build_matsu_from_xp,
    "Merchant": build_merchant_from_xp,
    "Mirumoto Bushi": build_mirumoto_from_xp,
    "Otaku Bushi": build_otaku_from_xp,
    "Priest": build_priest_from_xp,
    "Shiba Bushi": build_shiba_from_xp,
    "Shinjo Bushi": build_shinjo_from_xp,
    "Shosuro Actor": build_shosuro_from_xp,
    "Togashi Ise Zumi": build_togashi_from_xp,
    "Wave Man": build_waveman_from_xp,
    "Yogo Warden": build_yogo_from_xp,
}

SCHOOL_DEFAULT_WEAPONS: dict[str, WeaponType] = {
    name: WeaponType.KATANA for name in SCHOOL_BUILDERS
}
SCHOOL_DEFAULT_WEAPONS["Wave Man"] = WeaponType.SPEAR
SCHOOL_DEFAULT_WEAPONS["Brotherhood Monk"] = WeaponType.UNARMED


def get_combat_schools() -> list[str]:
    """Return sorted list of school names suitable for mass simulation."""
    return sorted(SCHOOL_BUILDERS.keys())
