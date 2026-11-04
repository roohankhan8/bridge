# Bridge API

Bridge is a student talent marketplace. The FastAPI service, PostgreSQL setup, and Python project now live at the repository root; product and engineering documents are in [`docs/`](docs/).

The API owns email/password accounts and sessions. Google sign-in exchanges a Google ID token for Bridge tokens. It stores user roles and student signup profiles. Supabase is not used for runtime authentication.

## Local setup (PowerShell)

From the repository root:

```powershell
Copy-Item .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Set `AUTH_JWT_SECRET` in `.env` to a random value of at least 32 characters. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `GOOGLE_CLIENT_IDS` to a JSON array of the mobile app's Google OAuth client IDs. Keep the signing secret on the server; Google ID-token verification does not need a Google client secret.

Then start PostgreSQL, apply migrations, and run the API:

```powershell
docker compose up -d db
docker compose ps
# Wait until the db service is healthy.
alembic upgrade head
uvicorn app.main:app --reload
```

The Compose project name is kept as `backend` so an existing local database volume continues to be used after moving the Compose file. `GET /health` works without auth configuration. Auth routes fail closed until their required settings are present.

## Authentication routes

- `POST /v1/auth/register` - create an email/password account; `student` is the default role and needs a `student_profile`. Freelancer signup uses `"role": "freelancer"` without that field. Public signup cannot grant `admin`.
- `POST /v1/auth/login` - verify email and password.
- `POST /v1/auth/google` - exchange a Google ID token for Bridge tokens. New student accounts include the role and profile; existing accounts keep their saved role/profile. Matching an existing email returns `409`; identities aren’t linked implicitly.
- `POST /v1/auth/refresh` - rotate a refresh token. Reuse revokes that session family.
- `POST /v1/auth/logout` - revoke the presented refresh token’s entire session family.
- `GET /v1/me` - return the user ID, role, and student profile, if present. Send the access token as `Authorization: Bearer <access-token>`.

Student signup includes full name, 1–20 unique skill tags (up to 60 characters each), experience (`beginner`, `intermediate`, or `advanced`), weekly availability (0–168 hours), and an optional HTTP(S) portfolio URL. Passwords use Argon2 hashes; refresh tokens are stored only as hashes. Email verification, password recovery, and account linking aren’t implemented. Admin accounts must be provisioned through a trusted process.

## Project documents

- [Product Requirements Document](docs/pdfs/bridge_prd.pdf)
- [Business Requirements Document](docs/pdfs/bridge_brd.pdf)
- [Technical Requirements Document](docs/pdfs/bridge_trd.pdf)
- [Backend Engineering Handoff](docs/pdfs/bridge_backend_handoff.pdf)
- [Backend Engineering Handoff (Markdown)](docs/bridge_backend_handoff.md)
- [Bridge-owned authentication design](docs/superpowers/specs/2026-11-05-bridge-owned-auth-design.md)
- [Bridge-owned authentication implementation plan](docs/superpowers/plans/2026-11-05-bridge-owned-auth.md)
