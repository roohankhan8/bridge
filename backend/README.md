# Bridge API

The Bridge backend is a separate FastAPI service. It owns the API boundary for future marketplace features and uses PostgreSQL for persistence. Supabase Auth owns sign-in; the API verifies bearer access tokens on protected routes.

## Requirements

- Python 3.11 or newer
- Docker Desktop or another Docker Compose installation
- A Supabase project with asymmetric JWT signing keys for local JWKS verification

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

Set `SUPABASE_URL` in `.env` to the project URL before using protected routes. The API builds its JWKS URL and expected issuer from this URL. `SUPABASE_AUDIENCE` defaults to `authenticated`. Do not put a Supabase service-role key in this API's client-facing configuration.

Supabase's JWKS endpoint serves asymmetric public signing keys. This starter accepts ES256 and RS256 tokens. If the Supabase project uses the legacy HS256 shared-secret signing key, switch the project to an asymmetric signing key before relying on this local JWKS verifier; do not copy a shared signing secret into the app or client. See [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts).

For `/v1/me`, use an access token from a user session created by a signed-in Supabase Auth client. The Bridge client is not included in this backend starter, so the route becomes usable once a client is configured to sign users in and send its session token.

## Routes

- `GET /health` - public liveness check; it does not depend on PostgreSQL or Supabase.
- `GET /v1/me` - returns the verified Supabase user ID; requires `Authorization: Bearer <access-token>`.
- `/docs` - interactive FastAPI API documentation during local development.

The initial Alembic revision is intentionally empty. No Bridge domain tables or marketplace workflows are implemented yet. Add schema migrations alongside later profile, task, application, and conversation work.

Stop the local database with `docker compose down`. This keeps the named data volume so local records remain available the next time you start it.

## Configuration

Copy `.env.example` to `.env`. Local database defaults match `compose.yaml`. Keep `.env` private; it is excluded by `.gitignore`. Production hosting, credentials, allowed origins, and operational settings must be configured before deployment.
