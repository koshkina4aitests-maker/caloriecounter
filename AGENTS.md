# AGENTS.md

## Cursor Cloud specific instructions

### Overview
LifeTracker is a single-process Python/FastAPI web app for tracking food intake, cardio, and strength workouts. It uses SQLite (auto-created `lifetracker.db`), Jinja2 templates, and has no external service dependencies.

### Running the app
See `README.md` for standard commands. Dev server: `source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### Lint and tests
- Lint: `source .venv/bin/activate && ruff check .`
- Tests: `source .venv/bin/activate && PYTHONPATH=. pytest -v` (PYTHONPATH=. is required since there is no installable package)

### Known dependency issue
The original `requirements.txt` pins `sqlmodel==0.0.37` and `SQLAlchemy==2.0.46`, but these versions have a compatibility bug with `from __future__ import annotations` in `app/models.py` — SQLModel fails to resolve `list["StrengthSet"]` forward references in `Relationship()` fields. The working combination is `sqlmodel==0.0.22` + `SQLAlchemy==2.0.36`. The `from __future__ import annotations` import was removed from `models.py` and forward references were quoted explicitly (e.g. `list["StrengthSet"]`).

### Notes
- The UI is entirely in Russian.
- SQLite DB file (`lifetracker.db`) is auto-created on first startup; delete it for a fresh state.
- No authentication — the app is single-user by design.
