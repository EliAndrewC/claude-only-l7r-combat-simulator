# Tabletop RPG Combat Simulator Project

## Tech Stack
- Language: Python 3.12+
- API: FastAPI
- UI: Streamlit (Internal simulation dashboard)
- Testing: pytest, pytest-cov
- Style: PEP 8, Type Hints (Strict)

## Architecture
1. **Core Engine**: Pure logic (no web dependencies), implemented based on `./rules`, which has the human-readable rules
2. **Data Models**: Pydantic classes for Characters, Stats, and Combat Log.
3. **Simulation**: Handles initiative, attacking, parrying, special actions, damage, wounds, win conditions, etc.
4. **API/UI**: Streamlit interface to visualize the dice rolls and outcomes.

## Development Commands
- Run Tests: `pytest`
- Run Coverage: `pytest --cov=src`
- Start UI: `streamlit run src/app.py`
- Lint: `ruff check .`

## Project Rules
- **TDD First**: Always write a failing test in `tests/` before implementing logic in `src/`.
- **Logic Isolation**: Keep the combat math 100% separate from the UI code.
- **Coverage**: Maintain >90% code coverage.
