"""FastAPI application for the L7R Combat Simulator."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.engine.presets import get_preset, list_preset_names
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


class PresetResponse(BaseModel):
    name: str
    character: Character
    weapon_type: WeaponType


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


@app.get("/presets")
def list_presets() -> list[str]:
    """List all preset character names."""
    return list_preset_names()


@app.get("/presets/{name}")
def get_preset_by_name(name: str) -> PresetResponse:
    """Get a preset character by name."""
    result = get_preset(name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    char, wt = result
    return PresetResponse(name=char.name, character=char, weapon_type=wt)
