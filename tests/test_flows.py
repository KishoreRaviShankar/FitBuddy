import re

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main
from app.models import Plan, PlanVersion, User
from app.schemas import WorkoutPlan
from app.security import hash_password


def csrf(page):
    return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)


def sample_plan(title="A balanced week"):
    return WorkoutPlan.model_validate({
        "title": title, "summary": "Three manageable sessions and recovery.",
        "nutrition_tip": "Eat varied meals and drink water.",
        "days": [{"day_number": i, "focus": "Strength" if i <= 3 else "Recovery",
                  "is_rest_day": i > 3, "warmup": "Easy movement for five minutes.",
                  "exercises": [{"name": "Squat", "sets": "2", "reps_or_duration": "8 reps", "rest_seconds": 60}] if i <= 3 else [],
                  "cooldown": "Gentle stretches.", "note": "Use a comfortable pace."} for i in range(1, 8)],
    })


def register(client, name="Ada", email="ada@example.com"):
    token = csrf(client.get("/register"))
    response = client.post("/register", data={"name": name, "email": email,
                           "password": "long-password-123", "csrf": token}, follow_redirects=False)
    assert response.status_code == 303


def create_plan(client):
    token = csrf(client.get("/plans/new"))
    return client.post("/plans", data={"age": 29, "weight_kg": "", "goal": "general fitness",
                  "intensity": "medium", "experience": "beginner", "location": "home", "equipment": "mat",
                  "days_available": 3, "minutes_per_day": 30, "limitations": "low impact", "csrf": token},
                  follow_redirects=False)


def test_member_plan_revision_checkin_and_pdf(client_and_db, monkeypatch):
    client, engine = client_and_db
    monkeypatch.setattr(main, "generate_plan", lambda profile: (sample_plan(), "gemini-3.5-flash"))
    monkeypatch.setattr(main, "revise_plan", lambda profile, current, feedback: (sample_plan("Updated week"), "gemini-3.5-flash-lite"))
    register(client)
    response = create_plan(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/plans/1"
    page = client.get("/plans/1")
    assert "A balanced week" in page.text and "Recovery" in page.text
    token = csrf(page)
    response = client.post("/plans/1/revise", data={"feedback": "More cardio please", "csrf": token}, follow_redirects=False)
    assert response.status_code == 303
    assert "Updated week" in client.get("/plans/1").text
    assert "A balanced week" in client.get("/plans/1/versions/1").text
    with Session(engine) as db:
        versions = db.scalars(select(PlanVersion).order_by(PlanVersion.number)).all()
        assert [v.number for v in versions] == [1, 2]
        assert [v.model_name for v in versions] == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
    token = csrf(client.get("/plans/1"))
    response = client.post("/plans/1/check-ins", data={"completed_days": 2, "energy": 4,
                           "notes": "Felt good", "csrf": token}, follow_redirects=False)
    assert response.status_code == 303
    assert "Felt good" in client.get("/plans/1").text
    pdf = client.get("/plans/1/export.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_member_cannot_open_others_plan_or_coach_view(client_and_db, monkeypatch):
    client, engine = client_and_db
    monkeypatch.setattr(main, "generate_plan", lambda profile: (sample_plan(), "gemini-3.5-flash"))
    register(client)
    create_plan(client)
    token = csrf(client.get("/dashboard"))
    client.post("/logout", data={"csrf": token})
    register(client, "Grace", "grace@example.com")
    assert client.get("/plans/1").status_code == 404
    assert client.get("/plans/1/export.pdf").status_code == 404
    assert client.get("/coach").status_code == 403
    assert client.post("/plans", data={"csrf": "wrong-token"}).status_code in (403, 422)


def test_coach_can_review_member_and_plan(client_and_db, monkeypatch):
    client, engine = client_and_db
    monkeypatch.setattr(main, "generate_plan", lambda profile: (sample_plan(), "gemini-3.5-flash"))
    monkeypatch.setattr(main, "revise_plan", lambda profile, current, feedback: (sample_plan("Updated week"), "gemini-3.5-flash-lite"))
    register(client)
    create_plan(client)
    token = csrf(client.get("/plans/1"))
    client.post("/plans/1/revise", data={"feedback": "Less cardio please", "csrf": token})
    token = csrf(client.get("/dashboard"))
    client.post("/logout", data={"csrf": token})
    with Session(engine) as db:
        db.add(User(name="Coach", email="coach@example.com", password_hash=hash_password("long-password-123"), role="coach"))
        db.commit()
    token = csrf(client.get("/login"))
    client.post("/login", data={"email": "coach@example.com", "password": "long-password-123", "csrf": token})
    assert "Ada" in client.get("/coach").text
    assert "View full plan" in client.get("/coach/users/1").text
    assert "Updated week" in client.get("/coach/plans/1").text
    assert "A balanced week" in client.get("/coach/plans/1/versions/1").text


def test_plan_validator_rejects_bad_week():
    data = sample_plan().model_dump()
    data["days"] = data["days"][:6]
    from pydantic import ValidationError
    try:
        WorkoutPlan.model_validate(data)
    except ValidationError:
        pass
    else:
        raise AssertionError("Incomplete week was accepted")
