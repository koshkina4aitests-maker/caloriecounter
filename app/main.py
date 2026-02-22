from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from starlette.templating import Jinja2Templates

from app.db import get_session, init_db
from app.models import (
    CardioEntry,
    Exercise,
    FoodLogEntry,
    FoodTemplate,
    Settings,
    StrengthSet,
    StrengthWorkout,
)
from app.services import (
    MET_PRESETS,
    cardio_kcal,
    epley_1rm,
    kcal_from_macros,
    parse_date,
    parse_datetime_local,
    to_datetime_local_input,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _tojson(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


templates.env.filters["tojson"] = _tojson


app = FastAPI(title="LifeTracker")


DEFAULT_EXERCISES: list[dict[str, str]] = [
    {"name": "Присед со штангой", "category": "strength", "muscle_group": "ноги"},
    {"name": "Жим лёжа", "category": "strength", "muscle_group": "грудь"},
    {"name": "Становая тяга", "category": "strength", "muscle_group": "спина"},
    {"name": "Жим стоя (OHP)", "category": "strength", "muscle_group": "плечи"},
    {"name": "Подтягивания", "category": "bodyweight", "muscle_group": "спина"},
    {"name": "Отжимания", "category": "bodyweight", "muscle_group": "грудь"},
    {"name": "Тяга штанги в наклоне", "category": "strength", "muscle_group": "спина"},
    {"name": "Тяга вертикального блока", "category": "strength", "muscle_group": "спина"},
    {"name": "Жим ногами", "category": "strength", "muscle_group": "ноги"},
    {"name": "Выпады", "category": "strength", "muscle_group": "ноги"},
    {"name": "Сгибания рук (бицепс)", "category": "strength", "muscle_group": "руки"},
    {"name": "Разгибания рук (трицепс)", "category": "strength", "muscle_group": "руки"},
    {"name": "Планка", "category": "bodyweight", "muscle_group": "кор"},
]


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with get_session() as session:
        settings = session.get(Settings, 1)
        if settings is None:
            session.add(Settings(id=1, body_weight_kg=60.0))
            session.commit()

        any_exercise = session.exec(select(Exercise).limit(1)).first()
        if any_exercise is None:
            for e in DEFAULT_EXERCISES:
                session.add(Exercise(**e))
            session.commit()


def get_settings(session: Session) -> Settings:
    settings = session.get(Settings, 1)
    if settings is None:
        settings = Settings(id=1, body_weight_kg=60.0)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min)
    end = start + timedelta(days=1)
    return start, end

def default_datetime_for_day(d: date) -> datetime:
    now = datetime.now().replace(second=0, microsecond=0)
    return datetime.combine(d, now.time())


def selected_date_from_query(request: Request) -> date:
    q = request.query_params.get("date")
    return parse_date(q) or date.today()

def redirect_url(*, next_url: str | None, params: dict[str, str], fallback_path: str) -> str:
    raw = (next_url or "").strip()
    if not raw.startswith("/"):
        raw = fallback_path
    parsed = urlparse(raw)
    query = dict(parse_qsl(parsed.query))
    query.update(params)
    return urlunparse(("", "", parsed.path, "", urlencode(query), ""))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    d = selected_date_from_query(request)
    start, end = day_bounds(d)
    flash = request.query_params.get("flash")

    with get_session() as session:
        settings = get_settings(session)

        food_entries = list(
            session.exec(
                select(FoodLogEntry)
                .where(FoodLogEntry.at >= start, FoodLogEntry.at < end)
                .order_by(FoodLogEntry.at.desc())
            ).all()
        )
        cardio_entries = list(
            session.exec(
                select(CardioEntry)
                .where(CardioEntry.at >= start, CardioEntry.at < end)
                .order_by(CardioEntry.at.desc())
            ).all()
        )
        strength_workouts = list(
            session.exec(
                select(StrengthWorkout)
                .where(StrengthWorkout.at >= start, StrengthWorkout.at < end)
                .order_by(StrengthWorkout.at.desc())
            ).all()
        )

    intake_kcal = sum(e.kcal for e in food_entries)
    p = sum(e.protein_g for e in food_entries)
    f = sum(e.fat_g for e in food_entries)
    c = sum(e.carbs_g for e in food_entries)
    intake_macros = f"Б {p:.1f} · Ж {f:.1f} · У {c:.1f}"

    cardio_k = sum(e.calories_burned for e in cardio_entries)
    strength_k = sum((w.calories_burned or 0) for w in strength_workouts)
    burned_kcal = cardio_k + strength_k
    net_kcal = intake_kcal - burned_kcal

    burned_details = f"кардио {cardio_k} · силовые {strength_k}"
    totals = {
        "intake_kcal": intake_kcal,
        "intake_macros": intake_macros,
        "burned_kcal": burned_kcal,
        "burned_details": burned_details,
        "net_kcal": net_kcal,
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Дашборд",
            "selected_date": d.isoformat(),
            "settings": settings,
            "totals": totals,
            "food_entries": food_entries,
            "cardio_entries": cardio_entries,
            "strength_workouts": strength_workouts,
            "flash": flash,
        },
    )


@app.get("/calculator", response_class=HTMLResponse)
def calculator(request: Request) -> HTMLResponse:
    def _num(name: str) -> float:
        raw = request.query_params.get(name)
        try:
            return float(raw) if raw not in (None, "") else 0.0
        except ValueError:
            return 0.0

    p = _num("p")
    f = _num("f")
    c = _num("c")
    kcal = kcal_from_macros(protein_g=p, fat_g=f, carbs_g=c)

    return templates.TemplateResponse(
        "calculator.html",
        {"request": request, "title": "Калькулятор БЖУ", "p": p, "f": f, "c": c, "kcal": kcal},
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    with get_session() as session:
        settings = get_settings(session)
    return templates.TemplateResponse(
        "settings.html", {"request": request, "title": "Настройки", "settings": settings}
    )


@app.post("/settings")
def settings_save(body_weight_kg: float = Form(...)) -> RedirectResponse:
    with get_session() as session:
        settings = get_settings(session)
        settings.body_weight_kg = float(body_weight_kg)
        session.add(settings)
        session.commit()
    return RedirectResponse(url="/settings?flash=Сохранено", status_code=303)


@app.get("/foods", response_class=HTMLResponse)
def foods_page(request: Request) -> HTMLResponse:
    flash = request.query_params.get("flash")
    with get_session() as session:
        templates_list = list(session.exec(select(FoodTemplate).order_by(FoodTemplate.name)).all())

    view = []
    for t in templates_list:
        kcal100 = kcal_from_macros(
            protein_g=t.protein_per_100g, fat_g=t.fat_per_100g, carbs_g=t.carbs_per_100g
        )
        view.append(
            {
                "id": t.id,
                "name": t.name,
                "protein_per_100g": t.protein_per_100g,
                "fat_per_100g": t.fat_per_100g,
                "carbs_per_100g": t.carbs_per_100g,
                "kcal_per_100g": kcal100,
            }
        )

    return templates.TemplateResponse(
        "foods.html",
        {"request": request, "title": "Продукты", "templates": view, "flash": flash},
    )


@app.post("/foods")
def foods_create(
    name: str = Form(...),
    protein_per_100g: float = Form(0.0),
    fat_per_100g: float = Form(0.0),
    carbs_per_100g: float = Form(0.0),
) -> RedirectResponse:
    with get_session() as session:
        session.add(
            FoodTemplate(
                name=name.strip(),
                protein_per_100g=float(protein_per_100g or 0),
                fat_per_100g=float(fat_per_100g or 0),
                carbs_per_100g=float(carbs_per_100g or 0),
            )
        )
        session.commit()
    return RedirectResponse(url="/foods?flash=Добавлено", status_code=303)


@app.post("/foods/{template_id}/delete")
def foods_delete(template_id: int) -> RedirectResponse:
    with get_session() as session:
        t = session.get(FoodTemplate, template_id)
        if t is not None:
            session.delete(t)
            session.commit()
    return RedirectResponse(url="/foods?flash=Удалено", status_code=303)


@app.get("/log/food", response_class=HTMLResponse)
def food_log(request: Request) -> HTMLResponse:
    d = selected_date_from_query(request)
    start, end = day_bounds(d)
    flash = request.query_params.get("flash")

    with get_session() as session:
        templates_list = list(session.exec(select(FoodTemplate).order_by(FoodTemplate.name)).all())
        entries = list(
            session.exec(
                select(FoodLogEntry)
                .where(FoodLogEntry.at >= start, FoodLogEntry.at < end)
                .order_by(FoodLogEntry.at.desc())
            ).all()
        )

    intake_kcal = sum(e.kcal for e in entries)
    p = sum(e.protein_g for e in entries)
    f = sum(e.fat_g for e in entries)
    c = sum(e.carbs_g for e in entries)
    totals = {"intake_kcal": intake_kcal, "intake_macros": f"Б {p:.1f} · Ж {f:.1f} · У {c:.1f}"}

    view_templates = []
    for t in templates_list:
        kcal100 = kcal_from_macros(
            protein_g=t.protein_per_100g, fat_g=t.fat_per_100g, carbs_g=t.carbs_per_100g
        )
        view_templates.append({"id": t.id, "name": t.name, "kcal_per_100g": kcal100})

    default_dt = to_datetime_local_input(default_datetime_for_day(d))

    return templates.TemplateResponse(
        "food_log.html",
        {
            "request": request,
            "title": "Еда",
            "selected_date": d.isoformat(),
            "templates": view_templates,
            "entries": entries,
            "totals": totals,
            "default_dt": default_dt,
            "flash": flash,
        },
    )


@app.post("/log/food/from-template")
def food_add_from_template(
    date_str: str = Form(..., alias="date"),
    template_id: int = Form(...),
    grams: float = Form(...),
    at: str | None = Form(None),
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    dt = parse_datetime_local(at) or default_datetime_for_day(d)

    with get_session() as session:
        t = session.get(FoodTemplate, template_id)
        if t is None:
            return RedirectResponse(url=f"/log/food?date={d.isoformat()}&flash=Нет+шаблона", status_code=303)

        grams_f = float(grams or 0)
        k = grams_f / 100.0
        p = t.protein_per_100g * k
        f = t.fat_per_100g * k
        c = t.carbs_per_100g * k
        kcal = kcal_from_macros(protein_g=p, fat_g=f, carbs_g=c)

        session.add(
            FoodLogEntry(
                at=dt,
                name=t.name,
                grams=grams_f,
                protein_g=p,
                fat_g=f,
                carbs_g=c,
                kcal=kcal,
                template_id=t.id,
            )
        )
        session.commit()

    return RedirectResponse(url=f"/log/food?date={d.isoformat()}&flash=Добавлено", status_code=303)


@app.post("/log/food/manual")
def food_add_manual(
    date_str: str = Form(..., alias="date"),
    name: str = Form(...),
    grams: float = Form(0.0),
    protein_g: float = Form(0.0),
    fat_g: float = Form(0.0),
    carbs_g: float = Form(0.0),
    at: str | None = Form(None),
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    dt = parse_datetime_local(at) or default_datetime_for_day(d)

    p = float(protein_g or 0)
    f = float(fat_g or 0)
    c = float(carbs_g or 0)
    kcal = kcal_from_macros(protein_g=p, fat_g=f, carbs_g=c)

    with get_session() as session:
        session.add(
            FoodLogEntry(
                at=dt,
                name=name.strip(),
                grams=float(grams or 0),
                protein_g=p,
                fat_g=f,
                carbs_g=c,
                kcal=kcal,
                template_id=None,
            )
        )
        session.commit()

    return RedirectResponse(url=f"/log/food?date={d.isoformat()}&flash=Добавлено", status_code=303)


@app.post("/log/food/{entry_id}/delete")
def food_delete(
    entry_id: int, date_str: str | None = Form(None, alias="date"), next: str | None = Form(None)
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    with get_session() as session:
        e = session.get(FoodLogEntry, entry_id)
        if e is not None:
            session.delete(e)
            session.commit()
    url = redirect_url(
        next_url=next,
        params={"date": d.isoformat(), "flash": "Удалено"},
        fallback_path="/log/food",
    )
    return RedirectResponse(url=url, status_code=303)


@app.get("/log/cardio", response_class=HTMLResponse)
def cardio_log(request: Request) -> HTMLResponse:
    d = selected_date_from_query(request)
    start, end = day_bounds(d)
    flash = request.query_params.get("flash")

    with get_session() as session:
        entries = list(
            session.exec(
                select(CardioEntry)
                .where(CardioEntry.at >= start, CardioEntry.at < end)
                .order_by(CardioEntry.at.desc())
            ).all()
        )

    totals = {"burned_kcal": sum(e.calories_burned for e in entries)}
    default_dt = to_datetime_local_input(default_datetime_for_day(d))

    return templates.TemplateResponse(
        "cardio_log.html",
        {
            "request": request,
            "title": "Кардио",
            "selected_date": d.isoformat(),
            "entries": entries,
            "totals": totals,
            "met_presets": MET_PRESETS,
            "default_dt": default_dt,
            "flash": flash,
        },
    )


def _met_value(met: str | None, met_preset: str | None) -> float | None:
    if met not in (None, ""):
        try:
            return float(met)
        except ValueError:
            return None
    if met_preset:
        preset = next((p for p in MET_PRESETS if p.key == met_preset), None)
        return preset.met if preset else None
    return None


@app.post("/log/cardio")
def cardio_add(
    date_str: str = Form(..., alias="date"),
    title: str = Form(...),
    duration_min: float = Form(...),
    distance_km: float | None = Form(None),
    met_preset: str | None = Form(None),
    met: str | None = Form(None),
    calories_burned: int | None = Form(None),
    at: str | None = Form(None),
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    dt = parse_datetime_local(at) or default_datetime_for_day(d)

    with get_session() as session:
        settings = get_settings(session)
        met_v = _met_value(met, met_preset)

        kcal = int(calories_burned) if calories_burned not in (None, "") else 0
        bw = settings.body_weight_kg
        if kcal == 0 and met_v is not None and float(duration_min or 0) > 0:
            kcal = cardio_kcal(met=met_v, duration_min=float(duration_min), body_weight_kg=bw)

        session.add(
            CardioEntry(
                at=dt,
                title=title.strip(),
                duration_min=float(duration_min or 0),
                distance_km=None if distance_km in (None, "") else float(distance_km),
                met=met_v,
                body_weight_kg=bw,
                calories_burned=int(kcal),
            )
        )
        session.commit()

    return RedirectResponse(url=f"/log/cardio?date={d.isoformat()}&flash=Добавлено", status_code=303)


@app.post("/log/cardio/{entry_id}/delete")
def cardio_delete(
    entry_id: int, date_str: str | None = Form(None, alias="date"), next: str | None = Form(None)
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    with get_session() as session:
        e = session.get(CardioEntry, entry_id)
        if e is not None:
            session.delete(e)
            session.commit()
    url = redirect_url(
        next_url=next,
        params={"date": d.isoformat(), "flash": "Удалено"},
        fallback_path="/log/cardio",
    )
    return RedirectResponse(url=url, status_code=303)


@app.get("/exercises", response_class=HTMLResponse)
def exercises_page(request: Request) -> HTMLResponse:
    flash = request.query_params.get("flash")
    with get_session() as session:
        exercises = list(session.exec(select(Exercise).order_by(Exercise.name)).all())
    return templates.TemplateResponse(
        "exercises.html",
        {"request": request, "title": "Упражнения", "exercises": exercises, "flash": flash},
    )


@app.post("/exercises")
def exercises_create(
    name: str = Form(...), category: str = Form("strength"), muscle_group: str = Form("")
) -> RedirectResponse:
    with get_session() as session:
        session.add(
            Exercise(name=name.strip(), category=category.strip()[:50], muscle_group=muscle_group.strip()[:100])
        )
        session.commit()
    return RedirectResponse(url="/exercises?flash=Добавлено", status_code=303)


@app.post("/exercises/{exercise_id}/delete")
def exercises_delete(exercise_id: int) -> RedirectResponse:
    with get_session() as session:
        e = session.get(Exercise, exercise_id)
        if e is not None:
            session.delete(e)
            session.commit()
    return RedirectResponse(url="/exercises?flash=Удалено", status_code=303)


@app.get("/workouts", response_class=HTMLResponse)
def workouts_page(request: Request) -> HTMLResponse:
    d = selected_date_from_query(request)
    start, end = day_bounds(d)
    flash = request.query_params.get("flash")

    with get_session() as session:
        workouts = list(
            session.exec(
                select(StrengthWorkout)
                .where(StrengthWorkout.at >= start, StrengthWorkout.at < end)
                .order_by(StrengthWorkout.at.desc())
            ).all()
        )

    default_dt = to_datetime_local_input(default_datetime_for_day(d))

    return templates.TemplateResponse(
        "workouts.html",
        {
            "request": request,
            "title": "Силовые",
            "selected_date": d.isoformat(),
            "workouts": workouts,
            "default_dt": default_dt,
            "flash": flash,
        },
    )


@app.post("/workouts")
def workouts_create(
    date_str: str = Form(..., alias="date"),
    at: str | None = Form(None),
    duration_min: float | None = Form(None),
    calories_burned: int | None = Form(None),
    note: str = Form(""),
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    dt = parse_datetime_local(at) or default_datetime_for_day(d)

    with get_session() as session:
        w = StrengthWorkout(
            at=dt,
            duration_min=None if duration_min in (None, "") else float(duration_min),
            calories_burned=None if calories_burned in (None, "") else int(calories_burned),
            note=note.strip(),
        )
        session.add(w)
        session.commit()
        session.refresh(w)
        workout_id = int(w.id)

    return RedirectResponse(url=f"/workouts/{workout_id}?flash=Создано", status_code=303)


@app.post("/workouts/{workout_id}/delete")
def workouts_delete(
    workout_id: int, date_str: str | None = Form(None, alias="date"), next: str | None = Form(None)
) -> RedirectResponse:
    d = parse_date(date_str) or date.today()
    with get_session() as session:
        w = session.get(StrengthWorkout, workout_id)
        if w is not None:
            for s in session.exec(select(StrengthSet).where(StrengthSet.workout_id == workout_id)).all():
                session.delete(s)
            session.delete(w)
            session.commit()
    url = redirect_url(
        next_url=next,
        params={"date": d.isoformat(), "flash": "Удалено"},
        fallback_path="/workouts",
    )
    return RedirectResponse(url=url, status_code=303)


@app.get("/workouts/{workout_id}", response_class=HTMLResponse)
def workout_detail(request: Request, workout_id: int) -> HTMLResponse:
    flash = request.query_params.get("flash")
    with get_session() as session:
        workout = session.get(StrengthWorkout, workout_id)
        if workout is None:
            return RedirectResponse(url="/workouts?flash=Не+найдено", status_code=303)

        exercises = list(session.exec(select(Exercise).order_by(Exercise.name)).all())
        sets = list(
            session.exec(
                select(StrengthSet, Exercise)
                .where(StrengthSet.workout_id == workout_id)
                .where(StrengthSet.exercise_id == Exercise.id)
                .order_by(StrengthSet.exercise_id, StrengthSet.set_number)
            ).all()
        )

    set_views = []
    for s, e in sets:
        set_views.append(
            {
                "id": s.id,
                "exercise_name": e.name,
                "set_number": s.set_number,
                "reps": s.reps,
                "load_kg": s.load_kg,
                "e1rm": epley_1rm(weight_kg=s.load_kg, reps=s.reps),
            }
        )

    return templates.TemplateResponse(
        "workout_detail.html",
        {
            "request": request,
            "title": "Тренировка",
            "workout": workout,
            "exercises": exercises,
            "sets": set_views,
            "met_presets": MET_PRESETS,
            "flash": flash,
        },
    )


@app.post("/workouts/{workout_id}/sets")
def workout_add_set(
    workout_id: int,
    exercise_id: int = Form(...),
    set_number: int = Form(1),
    reps: int = Form(8),
    load_kg: float = Form(0.0),
) -> RedirectResponse:
    with get_session() as session:
        workout = session.get(StrengthWorkout, workout_id)
        if workout is None:
            return RedirectResponse(url="/workouts?flash=Не+найдено", status_code=303)
        session.add(
            StrengthSet(
                workout_id=workout_id,
                exercise_id=int(exercise_id),
                set_number=int(set_number),
                reps=int(reps),
                load_kg=float(load_kg or 0),
            )
        )
        session.commit()
    return RedirectResponse(url=f"/workouts/{workout_id}?flash=Добавлено", status_code=303)


@app.post("/workouts/{workout_id}/sets/{set_id}/delete")
def workout_delete_set(workout_id: int, set_id: int) -> RedirectResponse:
    with get_session() as session:
        s = session.get(StrengthSet, set_id)
        if s is not None:
            session.delete(s)
            session.commit()
    return RedirectResponse(url=f"/workouts/{workout_id}?flash=Удалено", status_code=303)


@app.post("/workouts/{workout_id}/energy")
def workout_save_energy(
    workout_id: int,
    duration_min: float | None = Form(None),
    met_preset: str | None = Form(None),
    met: str | None = Form(None),
    calories_burned: int | None = Form(None),
) -> RedirectResponse:
    with get_session() as session:
        settings = get_settings(session)
        w = session.get(StrengthWorkout, workout_id)
        if w is None:
            return RedirectResponse(url="/workouts?flash=Не+найдено", status_code=303)

        dur = None if duration_min in (None, "") else float(duration_min)
        met_v = _met_value(met, met_preset) if (met not in (None, "") or met_preset) else w.met

        kcal = None if calories_burned in (None, "") else int(calories_burned)
        if (kcal is None or kcal == 0) and dur is not None and met_v is not None and dur > 0:
            kcal = cardio_kcal(met=met_v, duration_min=dur, body_weight_kg=settings.body_weight_kg)

        w.duration_min = dur
        w.met = met_v
        w.calories_burned = kcal
        session.add(w)
        session.commit()

    return RedirectResponse(url=f"/workouts/{workout_id}?flash=Сохранено", status_code=303)


@app.get("/progress", response_class=HTMLResponse)
def progress_index(request: Request) -> HTMLResponse:
    with get_session() as session:
        exercises = list(session.exec(select(Exercise).order_by(Exercise.name)).all())
    return templates.TemplateResponse(
        "progress_index.html",
        {"request": request, "title": "Прогресс", "exercises": exercises},
    )


@app.get("/progress/{exercise_id}", response_class=HTMLResponse)
def progress_detail(request: Request, exercise_id: int) -> HTMLResponse:
    with get_session() as session:
        exercise = session.get(Exercise, exercise_id)
        if exercise is None:
            return RedirectResponse(url="/progress?flash=Не+найдено", status_code=303)

        rows = list(
            session.exec(
                select(StrengthSet, StrengthWorkout)
                .where(StrengthSet.exercise_id == exercise_id)
                .where(StrengthSet.workout_id == StrengthWorkout.id)
                .order_by(StrengthWorkout.at.asc(), StrengthSet.set_number.asc())
            ).all()
        )

    best_by_workout: dict[int, dict[str, Any]] = {}
    for s, w in rows:
        e1rm = epley_1rm(weight_kg=s.load_kg, reps=s.reps)
        existing = best_by_workout.get(w.id)
        if existing is None or e1rm > existing["e1rm"]:
            best_by_workout[w.id] = {
                "workout_id": w.id,
                "date": w.at.date().isoformat(),
                "load_kg": s.load_kg,
                "reps": s.reps,
                "e1rm": e1rm,
            }

    points = list(best_by_workout.values())
    points.sort(key=lambda p: (p["date"], p["workout_id"]))

    chart = {"labels": [p["date"] for p in points], "data": [round(p["e1rm"], 2) for p in points]}

    return templates.TemplateResponse(
        "progress_detail.html",
        {
            "request": request,
            "title": f"Прогресс — {exercise.name}",
            "exercise": exercise,
            "points": points,
            "chart": chart,
        },
    )

