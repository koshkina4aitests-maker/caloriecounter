from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel


class Settings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    body_weight_kg: float = Field(default=60.0, ge=20.0, le=300.0)


class FoodTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, min_length=1, max_length=200)

    protein_per_100g: float = Field(default=0.0, ge=0.0, le=200.0)
    fat_per_100g: float = Field(default=0.0, ge=0.0, le=200.0)
    carbs_per_100g: float = Field(default=0.0, ge=0.0, le=200.0)


class FoodLogEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)

    name: str = Field(min_length=1, max_length=200)
    grams: float = Field(default=0.0, ge=0.0, le=5000.0)

    protein_g: float = Field(default=0.0, ge=0.0, le=1000.0)
    fat_g: float = Field(default=0.0, ge=0.0, le=1000.0)
    carbs_g: float = Field(default=0.0, ge=0.0, le=1000.0)
    kcal: int = Field(default=0, ge=0, le=20000)

    template_id: int | None = Field(default=None, foreign_key="foodtemplate.id")


class Exercise(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, min_length=1, max_length=200)
    category: str = Field(default="strength", max_length=50)  # strength | bodyweight | cardio
    muscle_group: str = Field(default="", max_length=100)

    sets: list["StrengthSet"] = Relationship(back_populates="exercise")


class StrengthWorkout(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)
    note: str = Field(default="", max_length=1000)

    duration_min: float | None = Field(default=None, ge=0.0, le=600.0)
    calories_burned: int | None = Field(default=None, ge=0, le=20000)
    met: float | None = Field(default=None, ge=0.0, le=30.0)

    sets: list["StrengthSet"] = Relationship(back_populates="workout")


class StrengthSet(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    workout_id: int = Field(foreign_key="strengthworkout.id", index=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)

    set_number: int = Field(default=1, ge=1, le=50)
    reps: int = Field(default=1, ge=0, le=200)
    load_kg: float = Field(default=0.0, ge=0.0, le=1000.0)

    workout: StrengthWorkout = Relationship(back_populates="sets")
    exercise: Exercise = Relationship(back_populates="sets")


class CardioEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)

    title: str = Field(min_length=1, max_length=200)
    duration_min: float = Field(default=0.0, ge=0.0, le=10000.0)
    distance_km: float | None = Field(default=None, ge=0.0, le=1000.0)

    met: float | None = Field(default=None, ge=0.0, le=30.0)
    body_weight_kg: float | None = Field(default=None, ge=20.0, le=300.0)
    calories_burned: int = Field(default=0, ge=0, le=20000)

