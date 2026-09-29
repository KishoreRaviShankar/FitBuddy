from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ProfileInput(BaseModel):
    age: int = Field(ge=18, le=85)
    weight_kg: float | None = Field(default=None, ge=35, le=300)
    goal: Literal["general fitness", "weight loss", "muscle gain", "mobility"]
    intensity: Literal["low", "medium", "high"]
    experience: Literal["beginner", "intermediate", "advanced"]
    location: Literal["home", "gym"]
    equipment: str = Field(max_length=200)
    days_available: int = Field(ge=2, le=6)
    minutes_per_day: int = Field(ge=15, le=120)
    limitations: str = Field(default="", max_length=300)

    @field_validator("equipment", "limitations")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class Exercise(BaseModel):
    name: str = Field(description="Clear exercise name")
    sets: str = Field(description="Number of sets, or '—' for a timed activity")
    reps_or_duration: str = Field(description="Repetitions or time, with units")
    rest_seconds: int = Field(description="Seconds of rest between sets, zero when not applicable")


class DayPlan(BaseModel):
    day_number: int = Field(description="Day number, from 1 to 7")
    focus: str = Field(description="Short title for this day")
    is_rest_day: bool
    warmup: str = Field(description="Warm-up guidance or gentle recovery activity")
    exercises: list[Exercise]
    cooldown: str
    note: str


class WorkoutPlan(BaseModel):
    title: str
    summary: str
    days: list[DayPlan]
    nutrition_tip: str = Field(description="One general nutrition or recovery tip, not a medical prescription")

    @model_validator(mode="after")
    def validate_week(self):
        if len(self.days) != 7 or sorted(day.day_number for day in self.days) != list(range(1, 8)):
            raise ValueError("Plan must contain exactly days 1 through 7")
        if not any(day.is_rest_day for day in self.days):
            raise ValueError("Plan must include at least one rest or recovery day")
        for day in self.days:
            if day.is_rest_day and day.exercises:
                raise ValueError("Rest days must not contain workout exercises")
            if not day.is_rest_day and not day.exercises:
                raise ValueError("Workout days must contain exercises")
            for ex in day.exercises:
                if not 0 <= ex.rest_seconds <= 300:
                    raise ValueError("Exercise rest interval is outside the allowed range")
        return self
