# Bridge Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable, separately deployable Python API foundation for Bridge.

**Architecture:** One FastAPI service exposes a versioned REST boundary, connects to PostgreSQL with SQLAlchemy, and tracks schema changes with Alembic. Supabase Auth owns sign-in; the API verifies bearer JWTs before protected routes.

**Tech Stack:** Python, FastAPI, Pydantic settings/models, PostgreSQL, SQLAlchemy 2.x, Alembic, Supabase Auth, Docker Compose for local PostgreSQL.

**Spec:** [Bridge Backend Foundation Design](../specs/2026-11-03-bridge-backend-foundation-design.md)

## Global Constraints

- Keep one deployable API service; do not introduce microservices, Redis, queues, or realtime infrastructure.
- Keep `/health` public and usable without Supabase configuration; protect user-specific `/v1/*` routes with verified identity.
- Never place secrets or Supabase service-role credentials in source control or client configuration.
- Do not add marketplace domain workflows in this foundation; later work follows the Bridge TRD and backend handoff.
- Use environment configuration and fail clearly when required settings are missing.
- This setup plan excludes automated test files and test execution; use the listed manual smoke checks only.

## Review Focus

- Missing/invalid database configuration: startup should report the missing setting clearly without logging its value.
- Database unavailable: `/health` remains available; database-dependent startup/checks report an actionable failure.
- Missing/invalid Supabase configuration: public health remains available and protected routes fail closed.
- Expired, wrong-issuer, or malformed JWT: protected routes return an authentication error without revealing token details.
- Development secrets or service-role credentials accidentally included in tracked files: `.env` remains ignored and `.env.example` contains placeholders only.

---

### Task 1: Bootstrap the FastAPI service

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.gitignore`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/README.md`

**Interfaces:**
- Produces: `app.main:app`, a FastAPI application with public `GET /health` returning a small status response.
- Produces: typed settings loaded from environment; no secret values checked into files.

- [ ] Create package metadata and dependencies for FastAPI, Uvicorn, Pydantic settings, SQLAlchemy, Alembic, PostgreSQL driver, and Supabase JWT verification.
- [ ] Create configuration for environment name, database URL, Supabase URL, and expected JWT issuer/audience as applicable; make secret values optional for public health startup.
- [ ] Add the health route and register it from `app.main:app`.
- [ ] Document environment setup and run command in `backend/README.md`.
- [ ] Manually start the service and request `/health`; confirm it succeeds without Supabase credentials.

### Task 2: Add local PostgreSQL and database migrations

**Files:**
- Create: `backend/compose.yaml`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/session.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial.py`
- Modify: `backend/README.md`
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: `app.core.config` settings from Task 1.
- Produces: SQLAlchemy engine/session factory and Alembic configuration using the same database URL.

- [ ] Add a PostgreSQL Compose service with local-only development credentials and a persistent named volume.
- [ ] Create a SQLAlchemy engine and session factory with explicit cleanup and connection settings.
- [ ] Configure Alembic to read the database URL from application settings and import the declarative metadata.
- [ ] Document how to start/stop the local database and run migrations.
- [ ] Manually start PostgreSQL, wait for its health check to pass, then run `alembic upgrade head`; confirm the initial migration creates no domain tables.

### Task 3: Establish Supabase JWT verification

**Files:**
- Create: `backend/app/core/auth.py`
- Create: `backend/app/api/dependencies.py`
- Create: `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/router.py`
- Create: `backend/app/api/v1/me.py`
- Modify: `backend/app/main.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env.example`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: settings from Task 1 and router registration from Task 1.
- Produces: a FastAPI auth dependency that verifies Supabase JWT signature, issuer, expiry, and subject using a maintained JWT/JWKS library; protected route `GET /v1/me` returns only verified identity claims.

- [ ] Implement fail-closed verification for Supabase asymmetric JWTs with ES256/RS256; do not decode-and-trust an unsigned token or accept caller-supplied identity.
- [ ] Configure the Supabase JWKS/issuer inputs and documented key-refresh behavior; keep credentials out of logs and responses.
- [ ] Add the protected `/v1/me` route and mount the versioned router.
- [ ] Document required Supabase configuration and that protected-route access tokens come from a signed-in Supabase Auth client.
- [ ] Manually confirm missing, malformed, and invalid tokens are rejected; confirm public `/health` still works without Supabase configuration.

### Task 4: Finalize the starter handoff

**Files:**
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: runnable API, database connection, migration setup, and auth boundary from Tasks 1-3.
- Produces: concise setup instructions, configuration reference, and clear next feature phases.

- [ ] Document the service boundary, local startup, migration command, health route, and protected identity route.
- [ ] List deferred next phases: profile/skills, task discovery and posting, applications/decisions, conversations/messages, and dashboard metrics.
- [ ] Manually follow the README from a clean local environment and ensure each documented command matches the created files.

## Implementation Notes

- This plan is for the starter foundation only. The profile, task, application, match, and messaging endpoints belong to later feature plans based on the Bridge TRD.
- Choose currently supported dependency versions when implementing and declare compatible constraints in `pyproject.toml`; create a lockfile after the package manager is selected and dependencies are resolved.
- Configure Supabase with asymmetric signing keys; the starter does not locally verify legacy HS256 shared-secret tokens.
- Keep PostgreSQL local development secrets distinct from production credentials.
- Deployments and hosting are not selected in the source materials and remain a later decision.
