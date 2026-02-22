from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


def kcal_from_macros(*, protein_g: float, fat_g: float, carbs_g: float) -> int:
    """
    Calorie calculation by macros (БЖУ):
    - protein: 4 kcal/g
    - carbs: 4 kcal/g
    - fat: 9 kcal/g
    """
    kcal = protein_g * 4 + carbs_g * 4 + fat_g * 9
    return int(round(kcal))


def epley_1rm(*, weight_kg: float, reps: int) -> float:
    """
    Estimate 1RM with Epley formula:
      1RM = w * (1 + reps/30)
    """
    if reps <= 1:
        return float(weight_kg)
    return float(weight_kg) * (1.0 + float(reps) / 30.0)


def cardio_kcal(*, met: float, duration_min: float, body_weight_kg: float) -> int:
    """
    Calories burned estimation using MET:
      kcal = MET * 3.5 * weight(kg) / 200 * minutes
    """
    kcal = float(met) * 3.5 * float(body_weight_kg) / 200.0 * float(duration_min)
    return int(round(kcal))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_datetime_local(value: str | None) -> datetime | None:
    """
    Parse HTML datetime-local input (YYYY-MM-DDTHH:MM).
    Stored as naive local datetime.
    """
    if not value:
        return None
    return datetime.fromisoformat(value)


def to_datetime_local_input(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="minutes")


@dataclass(frozen=True)
class MetPreset:
    key: str
    label: str
    met: float


MET_PRESETS: list[MetPreset] = [
    MetPreset("walk_easy", "Прогулка (лёгкая)", 3.0),
    MetPreset("walk_brisk", "Ходьба (быстрая)", 4.3),
    MetPreset("run_easy", "Бег (лёгкий)", 8.3),
    MetPreset("run_mod", "Бег (умеренный)", 9.8),
    MetPreset("cycle_mod", "Велосипед (умеренный)", 7.5),
    MetPreset("stairs", "Лестница", 8.8),
    MetPreset("strength_mod", "Силовая (умеренная)", 3.5),
    MetPreset("strength_hard", "Силовая (интенсивная)", 6.0),
]

