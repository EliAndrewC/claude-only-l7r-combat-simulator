"""FastAPI application for the L7R Combat Simulator."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from src.engine.simulation import simulate_combat
from src.models.character import Character
from src.models.combat import CombatLog
from src.models.weapon import WEAPONS, WeaponType

app = FastAPI(title="L7R Combat Simulator", version="0.1.0")


# --- Request / Response models ---


class CombatRequest(BaseModel):
    char_a: Character
    char_b: Character
    weapon_a: WeaponType = WeaponType.KATANA
    weapon_b: WeaponType = WeaponType.KATANA
    max_rounds: int = 20


class CombatResponse(BaseModel):
    winner: Optional[str]
    rounds: int
    total_actions: int
    log: CombatLog


# --- Endpoints ---


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/characters/validate")
def validate_character(character: Character) -> dict[str, str]:
    """Validate a character sheet."""
    return {"status": "valid", "name": character.name}


@app.post("/combat/simulate")
def api_simulate_combat(request: CombatRequest) -> CombatResponse:
    """Run a combat simulation between two characters."""
    weapon_a = WEAPONS[request.weapon_a]
    weapon_b = WEAPONS[request.weapon_b]
    log = simulate_combat(
        request.char_a, request.char_b, weapon_a, weapon_b, request.max_rounds
    )
    return CombatResponse(
        winner=log.winner,
        rounds=log.round_number,
        total_actions=len(log.actions),
        log=log,
    )


@app.get("/weapons")
def list_weapons() -> list[dict]:
    """List all available weapons with dice stats."""
    return [
        {
            "weapon_type": wt.value,
            "name": w.name,
            "rolled": w.rolled,
            "kept": w.kept,
            "dice": w.dice_str,
        }
        for wt, w in WEAPONS.items()
    ]
