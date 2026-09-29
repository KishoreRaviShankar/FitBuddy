import pytest

from app import ai
from google.genai import errors
from app.schemas import ProfileInput


def profile():
    return ProfileInput(age=30, weight_kg=None, goal="general fitness", intensity="medium",
                        experience="beginner", location="home", equipment="mat",
                        days_available=3, minutes_per_day=30, limitations="low impact")


def sample_response():
    return {"title": "Test week", "summary": "Three sessions.", "nutrition_tip": "Stay hydrated.",
            "days": [{"day_number": i, "focus": "Workout" if i <= 3 else "Rest",
                      "is_rest_day": i > 3, "warmup": "Walk", "cooldown": "Stretch", "note": "Easy pace",
                      "exercises": [{"name": "Squat", "sets": "2", "reps_or_duration": "8 reps",
                                     "rest_seconds": 60}] if i <= 3 else []}
                     for i in range(1, 8)]}


def test_provider_uses_structured_schema_and_validates(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    observed = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            observed.update(model=model, contents=contents, config=config)
            return type("Response", (), {"parsed": sample_response(), "text": ""})()

    class FakeClient:
        def __init__(self, **kwargs):
            observed["client"] = kwargs
            self.models = FakeModels()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(ai.genai, "Client", FakeClient)
    plan, model = ai.generate_plan(profile())
    assert plan.title == "Test week"
    assert model == "gemini-3.5-flash"
    assert observed["model"] == "gemini-3.5-flash"
    assert observed["config"].response_mime_type == "application/json"
    assert "days_available" in observed["contents"]


def test_generation_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ai.GenerationError, match="GEMINI_API_KEY"):
        ai.generate_plan(profile())


def test_503_uses_flash_lite_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    attempts = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            attempts.append(model)
            if model == "gemini-3.5-flash":
                raise errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "High demand"}})
            return type("Response", (), {"parsed": sample_response(), "text": ""})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(ai.genai, "Client", FakeClient)
    plan, model = ai.generate_plan(profile())
    assert plan.title == "Test week"
    assert model == "gemini-3.5-flash-lite"
    assert attempts == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
