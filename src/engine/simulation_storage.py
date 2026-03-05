"""JSON file persistence for mass simulation results."""

from __future__ import annotations

import uuid
from pathlib import Path

from src.models.mass_simulation import SimulationResult

_DEFAULT_STORAGE_DIR = Path("simulations")


def save_simulation(
    result: SimulationResult,
    storage_dir: Path = _DEFAULT_STORAGE_DIR,
) -> Path:
    """Save a simulation result to a JSON file.

    Returns the path to the saved file.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{result.id}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


def load_simulation(
    simulation_id: uuid.UUID,
    storage_dir: Path = _DEFAULT_STORAGE_DIR,
) -> SimulationResult:
    """Load a simulation result by its ID.

    Raises FileNotFoundError if the file does not exist.
    """
    path = storage_dir / f"{simulation_id}.json"
    if not path.exists():
        msg = f"Simulation {simulation_id} not found in {storage_dir}"
        raise FileNotFoundError(msg)
    return SimulationResult.model_validate_json(path.read_text())


def list_simulations(
    storage_dir: Path = _DEFAULT_STORAGE_DIR,
) -> list[SimulationResult]:
    """List all saved simulations, newest first.

    Returns an empty list if the directory does not exist.
    """
    if not storage_dir.exists():
        return []
    results: list[SimulationResult] = []
    for path in storage_dir.glob("*.json"):
        results.append(SimulationResult.model_validate_json(path.read_text()))
    results.sort(key=lambda r: r.timestamp, reverse=True)
    return results


def delete_simulation(
    simulation_id: uuid.UUID,
    storage_dir: Path = _DEFAULT_STORAGE_DIR,
) -> None:
    """Delete a simulation result by its ID.

    Raises FileNotFoundError if the file does not exist.
    """
    path = storage_dir / f"{simulation_id}.json"
    if not path.exists():
        msg = f"Simulation {simulation_id} not found in {storage_dir}"
        raise FileNotFoundError(msg)
    path.unlink()
