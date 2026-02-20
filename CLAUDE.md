# Tabletop RPG Combat Simulator Project

This project will simulate my game's combat system to facilitate playtesting.
This will eventually involve:
-> showing individual combats and how they play out
-> being able to test out what happens when we tweak the parameters / thresholds
    for the various decisions made by combatants to determine the optimal
    strategies for spending resources and applying bonuses
-> changing different decisions about how characters are built and which stats
    yield the most combat effectiveness given the various strategies
-> having groups of people fight to see which combinations of schools work best
    with one another (rather than 1-on-1)
-> implementing rules for duels and applying the same analysis to those
-> running mass simulations and summarizing the statistics and the effects that
    changing decisions has on them

## Tech Stack
- Language: Python 3.12+
- API: FastAPI
- UI: Streamlit (Internal simulation dashboard)
- Testing: pytest, pytest-cov
- Style: PEP 8, Type Hints (Strict)

## Architecture
1. **Core Engine**: Pure logic (no web dependencies), implemented based on `./rules`, which has the human-readable rules
2. **Simulation**: Handles initiative, attacking, parrying, special actions, damage, wounds, win conditions, etc.
3. **API/UI**: Streamlit interface to visualize the dice rolls and outcomes.

## Development Commands
- Run Tests: `pytest`
- Run Coverage: `pytest --cov=src`
- Start UI: `PYTHONPATH=. streamlit run src/app.py`
- Lint: `ruff check .`

## Project Rules
- **TDD First**: Always write a failing test in `tests/` before writing the code (linting should also always pass).
- **Logic Isolation**: Keep the combat math 100% separate from the UI code.
- **Coverage**: Maintain >90% code coverage.
