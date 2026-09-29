from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from .ai import GenerationError, generate_plan, revise_plan
from .config import get_settings
from .db import get_db
from .export import pdf_bytes
from .models import CheckIn, Plan, PlanVersion, User
from .schemas import ProfileInput, WorkoutPlan
from .security import check_csrf, csrf_token, hash_password, verify_password

ROOT = Path(__file__).resolve().parent
settings = get_settings()
app = FastAPI(title="FitBuddy", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key,
                   same_site="lax", https_only=settings.cookie_secure, max_age=7 * 24 * 3600)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


def render(request: Request, page: str, **context):
    context.update(user=getattr(request.state, "user", None), csrf_token=csrf_token(request),
                   flash=request.session.pop("flash", None), ai_ready=bool(settings.gemini_api_key))
    return templates.TemplateResponse(request=request, name=page, context=context)


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if isinstance(user_id, int) else None
    request.state.user = user
    return user


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


def require_coach(user: User = Depends(require_user)) -> User:
    if user.role != "coach":
        raise HTTPException(status_code=403, detail="Coach access required.")
    return user


def own_plan(plan_id: int, user: User, db: Session) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.user_id == user.id)
                     .options(selectinload(Plan.versions), selectinload(Plan.check_ins)))
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return plan


def profile_from_plan(plan: Plan) -> ProfileInput:
    return ProfileInput.model_validate({
        "age": plan.age, "weight_kg": plan.weight_kg, "goal": plan.goal,
        "intensity": plan.intensity, "experience": plan.experience,
        "location": plan.location, "equipment": plan.equipment,
        "days_available": plan.days_available, "minutes_per_day": plan.minutes_per_day,
        "limitations": plan.limitations,
    })


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: User | None = Depends(current_user)):
    return RedirectResponse("/dashboard" if user else "/login", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "auth.html", mode="register")


@app.post("/register")
def register(request: Request, name: str = Form(...), email: str = Form(...),
             password: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    name, email = name.strip(), email.strip().lower()
    if not (2 <= len(name) <= 100) or not ("@" in email and len(email) <= 254) or len(password) < 12:
        return render(request, "auth.html", mode="register", error="Enter a name, valid email, and password of at least 12 characters.")
    if db.scalar(select(User).where(User.email == email)):
        return render(request, "auth.html", mode="register", error="This email is already registered.")
    user = User(name=name, email=email, password_hash=hash_password(password), role="member")
    db.add(user)
    db.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "auth.html", mode="login")


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          csrf: str = Form(...), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        return render(request, "auth.html", mode="login", error="Invalid email or password.")
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    check_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    plans = db.scalars(select(Plan).where(Plan.user_id == user.id)
                       .options(selectinload(Plan.versions), selectinload(Plan.check_ins))
                       .order_by(Plan.created_at.desc())).all()
    return render(request, "dashboard.html", plans=plans)


@app.get("/plans/new", response_class=HTMLResponse)
def new_plan(request: Request, user: User = Depends(require_user)):
    return render(request, "new_plan.html")


@app.post("/plans")
def create_plan(request: Request, age: int = Form(...), weight_kg: str = Form(""),
                goal: str = Form(...), intensity: str = Form(...), experience: str = Form(...),
                location: str = Form(...), equipment: str = Form(""), days_available: int = Form(...),
                minutes_per_day: int = Form(...), limitations: str = Form(""), csrf: str = Form(...),
                db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request, csrf)
    try:
        profile = ProfileInput(age=age, weight_kg=weight_kg or None, goal=goal,
                               intensity=intensity, experience=experience, location=location,
                               equipment=equipment, days_available=days_available,
                               minutes_per_day=minutes_per_day, limitations=limitations)
        generated, model_name = generate_plan(profile)
    except ValidationError:
        return render(request, "new_plan.html", error="Check the profile values and try again.")
    except GenerationError as exc:
        return render(request, "new_plan.html", error=str(exc))
    plan = Plan(user_id=user.id, **profile.model_dump())
    db.add(plan)
    db.flush()
    db.add(PlanVersion(plan_id=plan.id, number=1, content_json=generated.model_dump_json(),
                       model_name=model_name))
    db.commit()
    return RedirectResponse(f"/plans/{plan.id}", status_code=303)


@app.get("/plans/{plan_id}", response_class=HTMLResponse)
def view_plan(request: Request, plan_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_user)):
    plan = own_plan(plan_id, user, db)
    version = plan.versions[-1]
    return render(request, "plan.html", plan=plan, version=version,
                  workout=WorkoutPlan.model_validate_json(version.content_json),
                  versions=list(reversed(plan.versions)), check_ins=list(reversed(plan.check_ins)))


@app.post("/plans/{plan_id}/revise")
def revise(request: Request, plan_id: int, feedback: str = Form(...), csrf: str = Form(...),
           db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request, csrf)
    plan = own_plan(plan_id, user, db)
    feedback = feedback.strip()
    if not 4 <= len(feedback) <= 600:
        request.session["flash"] = "Feedback must be between 4 and 600 characters."
        return RedirectResponse(f"/plans/{plan_id}", status_code=303)
    current = WorkoutPlan.model_validate_json(plan.versions[-1].content_json)
    try:
        updated, model_name = revise_plan(profile_from_plan(plan), current, feedback)
    except GenerationError as exc:
        request.session["flash"] = str(exc)
        return RedirectResponse(f"/plans/{plan_id}", status_code=303)
    db.add(PlanVersion(plan_id=plan.id, number=plan.versions[-1].number + 1,
                       content_json=updated.model_dump_json(), feedback=feedback,
                       model_name=model_name))
    db.commit()
    request.session["flash"] = "Your updated plan is ready. The previous version is saved."
    return RedirectResponse(f"/plans/{plan_id}", status_code=303)


@app.get("/plans/{plan_id}/versions/{number}", response_class=HTMLResponse)
def view_version(request: Request, plan_id: int, number: int, db: Session = Depends(get_db),
                 user: User = Depends(require_user)):
    plan = own_plan(plan_id, user, db)
    version = next((v for v in plan.versions if v.number == number), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    return render(request, "plan.html", plan=plan, version=version,
                  workout=WorkoutPlan.model_validate_json(version.content_json),
                  versions=list(reversed(plan.versions)), check_ins=list(reversed(plan.check_ins)))


@app.post("/plans/{plan_id}/check-ins")
def check_in(request: Request, plan_id: int, completed_days: int = Form(...), energy: int = Form(...),
             notes: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db),
             user: User = Depends(require_user)):
    check_csrf(request, csrf)
    own_plan(plan_id, user, db)
    if not 0 <= completed_days <= 7 or not 1 <= energy <= 5 or len(notes) > 500:
        raise HTTPException(status_code=422, detail="Check-in values are outside the allowed range.")
    db.add(CheckIn(plan_id=plan_id, completed_days=completed_days, energy=energy, notes=notes.strip()))
    db.commit()
    request.session["flash"] = "Check-in saved."
    return RedirectResponse(f"/plans/{plan_id}", status_code=303)


@app.get("/plans/{plan_id}/export.pdf")
def export_pdf(plan_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    plan = own_plan(plan_id, user, db)
    version = plan.versions[-1]
    content = pdf_bytes(WorkoutPlan.model_validate_json(version.content_json), version.number)
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="fitbuddy-plan-{plan_id}.pdf"',
        "Cache-Control": "private, no-store",
    })


@app.get("/coach", response_class=HTMLResponse)
def coach_dashboard(request: Request, db: Session = Depends(get_db), coach: User = Depends(require_coach)):
    users = db.scalars(select(User).where(User.role == "member")
                       .options(selectinload(User.plans).selectinload(Plan.check_ins))
                       .order_by(User.created_at.desc())).all()
    return render(request, "coach.html", members=users)


@app.get("/coach/users/{user_id}", response_class=HTMLResponse)
def coach_user(request: Request, user_id: int, db: Session = Depends(get_db),
               coach: User = Depends(require_coach)):
    member = db.scalar(select(User).where(User.id == user_id, User.role == "member")
                       .options(selectinload(User.plans).selectinload(Plan.versions),
                                selectinload(User.plans).selectinload(Plan.check_ins)))
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    return render(request, "coach_user.html", member=member)


@app.get("/coach/plans/{plan_id}", response_class=HTMLResponse)
def coach_plan(request: Request, plan_id: int, db: Session = Depends(get_db),
               coach: User = Depends(require_coach)):
    return coach_plan_version(request, plan_id, None, db, coach)


@app.get("/coach/plans/{plan_id}/versions/{number}", response_class=HTMLResponse)
def coach_plan_version(request: Request, plan_id: int, number: int | None,
                       db: Session = Depends(get_db), coach: User = Depends(require_coach)):
    plan = db.scalar(select(Plan).where(Plan.id == plan_id)
                     .options(selectinload(Plan.owner), selectinload(Plan.versions),
                              selectinload(Plan.check_ins)))
    if plan is None or plan.owner.role != "member":
        raise HTTPException(status_code=404, detail="Plan not found.")
    selected = plan.versions[-1] if number is None else next((v for v in plan.versions if v.number == number), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    return render(request, "coach_plan.html", plan=plan, selected=selected,
                  workout=WorkoutPlan.model_validate_json(selected.content_json))


@app.get("/health")
def health():
    return {"status": "ok", "gemini_configured": bool(settings.gemini_api_key)}
