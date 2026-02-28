# L7R Combat Simulator

A tabletop RPG combat simulator based on custom L7R (Legend of the Five Rings) house rules. Pick two samurai, choose their weapons, and watch them fight round-by-round with full dice rolls, parries, wounds, and a declared winner.

## Development

```bash
podman run --interactive --tty --rm \
  --name claude-only \
  --user 1001:1001 \
  --userns keep-id \
  --env HOME=/home/user \
  --tmpfs /home/user:rw \
  --volume "$(pwd)":/workspace \
  --workdir /workspace \
  --publish 8501:8501 \
  docker.io/docker/sandbox-templates:claude-code \
  bash
```

or on Docker:

```
docker run -it --rm --name claude-only -v "$(pwd):/workspace" -p 8501:8501 claude-code-sandbox:latest bash
```

## Setup

Requires Python 3.10+.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

### Streamlit Dashboard (primary UI)

```bash
streamlit run src/app.py
```

Opens a browser at `http://localhost:8501`. From there you can:

- **Pick fighters** — use the sidebar to select from 6 preset characters (Akodo, Kakita, Hida, Mirumoto, Bayushi, Matsu) or build a custom fighter by setting rings, skills, and weapon.
- **Choose weapons** — Katana (4k2), Wakizashi (3k2), Spear (3k2), Knife (2k2), or Unarmed (0k2).
- **Click Fight** — runs a full combat simulation and displays results: winner banner, combat stats (rounds, hits, parries, biggest hit), round-by-round action log with dice, and final wound status.

### FastAPI Server (programmatic access)

```bash
uvicorn src.api:app --reload
```

Runs at `http://localhost:8000`. Interactive docs at `/docs`.

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/characters/validate` | POST | Validate a character JSON |
| `/combat/simulate` | POST | Run a combat (accepts two characters + weapon types, returns full log) |
| `/weapons` | GET | List all weapons with dice stats |
| `/presets` | GET | List preset character names |
| `/presets/{name}` | GET | Get a preset character by name |

### Example: simulate via the API

```bash
curl -X POST http://localhost:8000/combat/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "char_a": {"name": "A", "skills": [{"name":"Attack","rank":3,"skill_type":"advanced","ring":"Fire"},{"name":"Parry","rank":2,"skill_type":"advanced","ring":"Air"}]},
    "char_b": {"name": "B", "skills": [{"name":"Attack","rank":3,"skill_type":"advanced","ring":"Fire"},{"name":"Parry","rank":2,"skill_type":"advanced","ring":"Air"}]},
    "weapon_a": "katana",
    "weapon_b": "spear",
    "max_rounds": 20
  }'
```

## Development

### Run tests

```bash
pytest
```

### Run tests with coverage

```bash
pytest --cov=src
```

Coverage target is >90%.

### Lint

```bash
ruff check .
```

### Project structure

```
src/
  models/         Pydantic data models (Character, Rings, Skills, Weapon, CombatLog, School)
  engine/         Pure logic — no web dependencies
    dice.py         Dice rolling (XkY, exploding 10s)
    combat.py       Combat primitives (initiative, attack, parry, damage, wound checks)
    skills.py       Skill checks, TN rolls, contested rolls
    simulation.py   Combat orchestrator — runs a full fight
    presets.py      6 preset characters
  api.py          FastAPI endpoints
  app.py          Streamlit dashboard
  ui_helpers.py   Rendering helpers for the dashboard
tests/            Mirrors src/ — one test file per module
rules/            Human-readable game rules
```
