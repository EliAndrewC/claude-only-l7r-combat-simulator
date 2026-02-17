"""Tests for the FastAPI endpoints."""

from fastapi.testclient import TestClient

from src.api import app

client = TestClient(app)


class TestHealthCheck:
    def test_health_returns_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestValidateCharacter:
    def test_valid_character(self) -> None:
        response = client.post(
            "/characters/validate",
            json={"name": "Test Samurai"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "valid"
        assert data["name"] == "Test Samurai"

    def test_missing_name_fails(self) -> None:
        response = client.post("/characters/validate", json={})
        assert response.status_code == 422


class TestSimulateCombat:
    def test_simulate_returns_result(self) -> None:
        response = client.post(
            "/combat/simulate",
            json={
                "char_a": {
                    "name": "Fighter A",
                    "skills": [
                        {"name": "Attack", "rank": 3, "skill_type": "advanced", "ring": "Fire"},
                        {"name": "Parry", "rank": 2, "skill_type": "advanced", "ring": "Air"},
                    ],
                },
                "char_b": {
                    "name": "Fighter B",
                    "skills": [
                        {"name": "Attack", "rank": 3, "skill_type": "advanced", "ring": "Fire"},
                        {"name": "Parry", "rank": 2, "skill_type": "advanced", "ring": "Air"},
                    ],
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "winner" in data
        assert "rounds" in data
        assert "total_actions" in data
        assert "log" in data

    def test_simulate_with_weapon_choice(self) -> None:
        response = client.post(
            "/combat/simulate",
            json={
                "char_a": {"name": "A", "skills": [
                    {"name": "Attack", "rank": 2, "skill_type": "advanced", "ring": "Fire"},
                    {"name": "Parry", "rank": 2, "skill_type": "advanced", "ring": "Air"},
                ]},
                "char_b": {"name": "B", "skills": [
                    {"name": "Attack", "rank": 2, "skill_type": "advanced", "ring": "Fire"},
                    {"name": "Parry", "rank": 2, "skill_type": "advanced", "ring": "Air"},
                ]},
                "weapon_a": "spear",
                "weapon_b": "knife",
                "max_rounds": 5,
            },
        )
        assert response.status_code == 200


class TestWeapons:
    def test_list_weapons(self) -> None:
        response = client.get("/weapons")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        names = {w["name"] for w in data}
        assert "Katana" in names

    def test_weapon_has_dice_info(self) -> None:
        response = client.get("/weapons")
        data = response.json()
        katana = next(w for w in data if w["name"] == "Katana")
        assert katana["rolled"] == 4
        assert katana["kept"] == 2
        assert katana["dice"] == "4k2"


class TestPresets:
    def test_list_presets(self) -> None:
        response = client.get("/presets")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 6

    def test_get_preset_by_name(self) -> None:
        response = client.get("/presets/Akodo Taro")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Akodo Taro"
        assert "character" in data
        assert "weapon_type" in data

    def test_get_preset_not_found(self) -> None:
        response = client.get("/presets/Nonexistent")
        assert response.status_code == 404
