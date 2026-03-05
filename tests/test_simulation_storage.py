"""Tests for simulation storage (save/load/list/delete)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.engine.simulation_storage import (
    delete_simulation,
    list_simulations,
    load_simulation,
    save_simulation,
)
from src.models.mass_simulation import (
    MatchupConfig,
    MatchupResult,
    SimulationConfig,
    SimulationResult,
)


def _make_result(label: str = "test") -> SimulationResult:
    """Helper to create a SimulationResult for testing."""
    cfg = SimulationConfig(schools=["Akodo Bushi", "Matsu Bushi"])
    matchup_cfg = MatchupConfig(
        school_a="Akodo Bushi",
        school_b="Matsu Bushi",
        earned_xp_a=0,
        earned_xp_b=0,
        non_combat_pct=0.20,
        is_duel=False,
    )
    matchup = MatchupResult(
        config=matchup_cfg,
        num_combats=10,
        wins_a=6,
        wins_b=4,
        draws=0,
        avg_rounds=7.0,
        avg_wounds_a=2.0,
        avg_wounds_b=3.0,
    )
    return SimulationResult(
        config=cfg,
        matchup_results=[matchup],
        label=label,
    )


class TestSaveSimulation:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        result = _make_result()
        path = save_simulation(result, storage_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_uses_simulation_id_in_filename(self, tmp_path: Path) -> None:
        result = _make_result()
        path = save_simulation(result, storage_dir=tmp_path)
        assert str(result.id) in path.name

    def test_save_creates_directory_if_missing(self, tmp_path: Path) -> None:
        storage_dir = tmp_path / "nested" / "dir"
        result = _make_result()
        path = save_simulation(result, storage_dir=storage_dir)
        assert path.exists()
        assert storage_dir.exists()


class TestLoadSimulation:
    def test_load_roundtrip(self, tmp_path: Path) -> None:
        result = _make_result(label="roundtrip")
        save_simulation(result, storage_dir=tmp_path)
        loaded = load_simulation(result.id, storage_dir=tmp_path)
        assert loaded.id == result.id
        assert loaded.label == "roundtrip"
        assert len(loaded.matchup_results) == 1
        assert loaded.config == result.config

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_simulation(uuid.uuid4(), storage_dir=tmp_path)


class TestListSimulations:
    def test_list_empty_directory(self, tmp_path: Path) -> None:
        results = list_simulations(storage_dir=tmp_path)
        assert results == []

    def test_list_returns_all_saved(self, tmp_path: Path) -> None:
        r1 = _make_result(label="first")
        r2 = _make_result(label="second")
        save_simulation(r1, storage_dir=tmp_path)
        save_simulation(r2, storage_dir=tmp_path)
        results = list_simulations(storage_dir=tmp_path)
        assert len(results) == 2
        labels = {r.label for r in results}
        assert labels == {"first", "second"}

    def test_list_newest_first(self, tmp_path: Path) -> None:
        r1 = SimulationResult(
            config=SimulationConfig(schools=["A"]),
            matchup_results=[],
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            label="older",
        )
        r2 = SimulationResult(
            config=SimulationConfig(schools=["B"]),
            matchup_results=[],
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
            label="newer",
        )
        save_simulation(r1, storage_dir=tmp_path)
        save_simulation(r2, storage_dir=tmp_path)
        results = list_simulations(storage_dir=tmp_path)
        assert results[0].label == "newer"
        assert results[1].label == "older"

    def test_list_ignores_non_json_files(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("not json")
        results = list_simulations(storage_dir=tmp_path)
        assert results == []


class TestDeleteSimulation:
    def test_delete_removes_file(self, tmp_path: Path) -> None:
        result = _make_result()
        path = save_simulation(result, storage_dir=tmp_path)
        assert path.exists()
        delete_simulation(result.id, storage_dir=tmp_path)
        assert not path.exists()

    def test_delete_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            delete_simulation(uuid.uuid4(), storage_dir=tmp_path)
