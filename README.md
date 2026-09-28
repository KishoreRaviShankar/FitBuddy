# FitBuddy AI Fitness Plan Generator

FitBuddy is a FastAPI web app that creates a seven-day adult fitness plan with Google's Gemini API. Members can revise a plan, keep all earlier versions, record weekly check-ins, and download the latest plan as a PDF. A coach account can review members, plans, feedback, and check-ins.

## What is included

- Responsive HTML/CSS interface with FastAPI and Jinja2
- Gemini `google-genai` SDK, default model `gemini-3.5-flash` with an optional `gemini-3.5-flash-lite` fallback for temporary 503 overloads
- Pydantic-validated structured plan with seven days and recovery time
- Account registration, password hashing, signed session cookies, CSRF protection, member-only plans, and a coach role
- SQLAlchemy 2.x models, SQLite for local development, and Alembic migrations
- Separate plan versions, progress check-ins, a protected coach dashboard, PDF export, and automated flow tests

The app requires Python 3.12 or newer and a Gemini API key for generation and revision. The site starts without a key, but disables AI generation until you add one. It does not require Node.js, npm, React, or a separate frontend server.

## 1. Extract and open the project

Unzip `FitBuddy.zip`. In VS Code, choose **File → Open Folder** and select the extracted `FitBuddy` folder. Open a terminal in that folder. All commands below run from the folder containing `requirements.txt` and `alembic.ini`.

## 2. Create and activate a virtual environment

**Windows PowerShell**:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `py -3.12` is unavailable, install Python 3.12 or later, then use `py -3 -m venv .venv`. If PowerShell blocks activation, use Command Prompt and run `.venv\Scripts\activate.bat` instead.

**macOS/Linux**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

In VS Code, select the `.venv` interpreter if prompted.

## 3. Add configuration and your Gemini API key

Copy `.env.example` to `.env`:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# macOS/Linux
cp .env.example .env
```

Create a random session secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open `.env` and replace `SECRET_KEY` with the printed string. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then set `GEMINI_API_KEY` in `.env`. Keep `.env` private; it is excluded by `.gitignore`.

```dotenv
SECRET_KEY=the-random-value-you-generated
GEMINI_API_KEY=your-real-key
MODEL_WORKOUT=gemini-3.5-flash
MODEL_FALLBACK=gemini-3.5-flash-lite
DATABASE_URL=sqlite:///./fitbuddy.db
COOKIE_SECURE=false
```

The default model is `gemini-3.5-flash`. The Google GenAI SDK retries transient errors with backoff; after an exhausted 503 response, FitBuddy tries `MODEL_FALLBACK` once (with its own bounded SDK retry). The version records which model succeeded. To disable the fallback, set `MODEL_FALLBACK=`. If your account does not have access to a model, choose one available for your key in AI Studio and update the corresponding setting. The models must support structured JSON responses. Gemini use is subject to your Google account's limits and pricing. `COOKIE_SECURE=false` is for local HTTP; set it to `true` behind HTTPS when hosting.

## 4. Create the database

```bash
python -m alembic upgrade head
```

This creates `fitbuddy.db` and applies the initial schema. Run the same command after future project updates that add migrations. Do not commit your database to GitHub.

## 5. Start the app

```bash
python -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). For the health check, open `/health`; the interactive API route listing is at `/docs`. Stop the server with **Ctrl+C**. Always run Uvicorn from the project root with `app.main:app`.

## 6. Try every feature

1. Open `/register`, create a member account using a password of at least 12 characters, and sign in.
2. Select **Create plan**. Set an adult age, goal, intensity, experience, location, equipment, available workout days, and minutes per day. Weight and movement limits are optional.
3. Click **Generate my plan**. The page shows seven days, including recovery days, warm-ups, exercises, cooldowns, and one general nutrition/recovery tip. AI requests may take some time.
4. Enter feedback such as `Use more low-impact cardio and two recovery days`, then click **Update plan**. Use **Versions** to reopen the original and revised plans.
5. Enter completed workout days, energy level, and notes in **Weekly check-in**. The entry appears on the plan page.
6. Click **Download PDF** for the newest version of the plan.
7. Open **My plans** to see all plans and their version and check-in counts.

### Create and use a coach account

Stop the server or open a second terminal with the same virtual environment active. Run:

```bash
python -m app.manage create-coach
```

Enter a new name, email, and password at the prompts. The password is hidden while typing. Start the server, sign in with that email, and select **Coach view**. A coach can review members, their full latest plans, revision feedback, and check-ins. Ordinary members cannot open coach pages. For a local demo you can use this account to inspect your test member; for real use, grant the coach role only to someone authorized to see all member data.

## Project structure

```text
FitBuddy/
├── app/
│   ├── main.py          # FastAPI routes and ownership rules
│   ├── ai.py            # Gemini generation, revision, and validation
│   ├── schemas.py       # Profile and structured workout schemas
│   ├── models.py        # SQLAlchemy database tables
│   ├── db.py            # Database sessions
│   ├── security.py      # Passwords and CSRF checks
│   ├── export.py        # PDF output
│   ├── manage.py        # Coach account command
│   ├── templates/       # Jinja2 pages
│   └── static/          # CSS
├── migrations/          # Alembic schema migration
├── tests/               # Automated flow tests
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## Run the automated tests

Install the extra test dependencies and run pytest from the project root:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests substitute a sample AI response so no key or paid Gemini request is needed. They cover registration, plan creation, revision history, check-ins, PDF output, member isolation, and coach access. For a live Gemini check, use the browser after setting a real API key.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `Set a random SECRET_KEY...` | Copy `.env.example` to `.env` and replace the placeholder with the generated secret. |
| `no such table: users` | Run `python -m alembic upgrade head` from the project root. |
| `Could not import module "app"` | Open the **FitBuddy** folder and run `python -m uvicorn app.main:app --reload` from it. |
| Gemini is not configured | Add `GEMINI_API_KEY` to `.env` and restart Uvicorn. |
| `503 UNAVAILABLE` or "Gemini is busy" | The model service is overloaded. FitBuddy retries and attempts Flash-Lite when configured. If both are busy, wait a few minutes and try again. Check model availability and limits in AI Studio. |
| AI service unavailable | Verify the key, model availability, connection, and rate limits in AI Studio; check the server console for the exception class. |
| Generated plan incomplete | Try again or revise the profile. The app refuses to save a malformed seven-day response. |
| Form expired | Refresh the page, then submit the form again. |
| Port 8000 already in use | Stop the old server or run `python -m uvicorn app.main:app --reload --port 8001` and open port 8001. |

## Privacy and scope

Only training inputs are sent to Gemini; account name, email, password, check-in notes, and prior versions are stored locally in the SQLite database. A revision sends the current plan and your feedback. Movement limitations in the profile are sent because they affect the requested plan; avoid entering medical history. A coach account can view member profiles and plans. This project is for general adult fitness guidance and does not diagnose conditions or replace a qualified professional. If deploying publicly, add HTTPS, backups, a data retention policy, and account recovery before collecting real users' data.
