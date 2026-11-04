# Bridge API

The Bridge FastAPI service owns authentication and marketplace API access. PostgreSQL stores Bridge users, student onboarding profiles, and refresh sessions. Google is used only to verify Google sign-in credentials; Supabase is not part of runtime authentication.

## Local setup (PowerShell)

From this directory:

```powershell
Copy-Item .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
docker compose up -d db
docker compose ps
# Wait until the db service shows healthy before continuing.
alembic upgrade head
uvicorn app.main:app --reload
```

Set `AUTH_JWT_SECRET` in `.env` to a random value at least 32 characters long. For example, generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set `GOOGLE_CLIENT_IDS` to a JSON array of the OAuth client IDs used by the mobile app. Google ID tokens must have one of these audiences. Never put a Google client secret or Bridge signing secret in the app.

The auth settings are optional at service startup so `/health` stays available. Auth operations fail closed until the Bridge signing key is configured; Google sign-in also requires Google client IDs. Do not use the sample signing secret in production.

## Authentication API

- `POST /v1/auth/register` - create an email/password account and issue Bridge tokens. Student role is the default and requires `student_profile`; freelancer accounts omit that field. Public signup cannot assign `admin`.
- `POST /v1/auth/login` - verify an email/password account and issue Bridge tokens.
- `POST /v1/auth/google` - verify a Google ID token and create or sign in to a Google-linked Bridge account. For a new student account, include the role and `student_profile`. An email already used by another Bridge account returns `409`; identities are not linked implicitly.
- `POST /v1/auth/refresh` - rotate a refresh token and return a new token pair.
- `POST /v1/auth/logout` - revoke the presented refresh token's session family (the full rotated token lineage).
- `GET /v1/me` - return the Bridge user ID, role, and student profile (if present); requires `Authorization: Bearer <access-token>`.

Student registration sends the onboarding fields in `student_profile`:

```json
{
  "email": "student@example.com",
  "password": "a-long-password",
  "role": "student",
  "student_profile": {
    "full_name": "Alex Student",
    "key_skills": ["Python", "Research"],
    "experience_level": "beginner",
    "availability_hours_per_week": 12,
    "portfolio_url": "https://example.com/portfolio"
  }
}
```

`key_skills` accepts 1-20 unique tags of up to 60 characters. Experience is `beginner`, `intermediate`, or `advanced`. Weekly availability is 0-168 hours. `portfolio_url` is optional and must use HTTP or HTTPS. A freelancer signup uses `"role": "freelancer"` and omits `student_profile`.

Google sign-in accepts `{ "id_token": "<Google ID token>", "role": "student", "student_profile": { ... } }`. Only the first sign-in creates the Bridge account; follow-up calls identify it by the verified Google subject and keep its stored role/profile. A verified email collision returns `409` rather than merging accounts.

Access tokens are short-lived signed JWTs. Refresh tokens are random opaque values; only their hashes are stored. Reuse of a rotated refresh token revokes its session family, and logout revokes that family. Passwords use Argon2 hashes. Admin roles must be provisioned through a trusted administrative process; no public API can grant them. Email verification, password recovery, and account linking are not implemented yet.

## Other routes

- `GET /health` - public liveness check; independent of PostgreSQL and auth settings.
- `/docs` - interactive FastAPI API documentation during local development.

Stop the local database with `docker compose down`. This keeps the named data volume so local records remain available the next time you start it.
