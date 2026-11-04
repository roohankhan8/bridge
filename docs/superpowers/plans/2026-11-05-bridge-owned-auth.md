# Bridge-owned Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Supabase token verification with Bridge-owned email/password and Google sign-in APIs backed by PostgreSQL.

**Architecture:** Add Bridge user and refresh-session tables, issue short-lived Bridge JWT access tokens, and store only hashes of rotating opaque refresh tokens. Google clients exchange a Google ID token at the API; the API verifies it and issues the same Bridge tokens.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, PyJWT, Argon2 password hashing, Google ID token verification.

**Spec:** `docs/superpowers/specs/2026-11-05-bridge-owned-auth-design.md`

## Global Constraints

- Never store plaintext passwords or refresh tokens.
- Do not trust decoded Google claims without signature verification and configured audience validation.
- Keep `/health` independent of database and auth configuration.
- Do not add password recovery, email verification, MFA, or client implementation.

## Review Focus

- Missing or short Bridge signing secret: auth operations fail closed with a clear server configuration error.
- Malformed, expired, wrong-audience, or unverified-email Google ID token: Google exchange is rejected.
- Duplicate normalized emails or Google subjects: do not create or cross-link duplicate accounts.
- Invalid student profile fields: reject out-of-range skills, experience, availability, and URL inputs before persistence.
- Refresh token rotation race or replay: only one rotation succeeds and reuse revokes the session family.
- Existing Supabase token: protected routes reject it after the provider verifier is removed.

---

### Task 1: Add auth persistence and settings

**Files:**
- Create: `app/db/models.py`
- Modify: `app/core/config.py`
- Modify: `alembic/env.py`
- Create: `alembic/versions/0002_auth.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`

**Interfaces:**
- `User`: UUID `id`, normalized unique `email`, nullable `password_hash`, nullable unique `google_sub`, role constrained to `admin|freelancer|student` (default `student`), creation timestamp.
- `StudentProfile`: one-to-one with a student user; full name, 1–20 unique skill tags, beginner/intermediate/advanced experience, weekly availability hours (0–168), optional HTTP(S) portfolio URL.
- `RefreshSession`: UUID `id`, `user_id`, `family_id`, unique token hash, expiry, optional revoked timestamp, creation timestamp.
- Settings: optional `auth_jwt_secret` and `google_client_ids`; auth calls validate required values at use time so health remains independent.

- [ ] Define the user, student-profile, and refresh-session models; constrain user role and profile experience/availability; register them with `Base.metadata` for Alembic.
- [ ] Add reversible migration `0002_auth` creating all three tables, uniqueness constraints, and foreign keys.
- [ ] Add auth configuration and `google-auth` plus Argon2 password hashing dependencies; remove no runtime config until the auth verifier is switched in Task 2.
- [ ] Replace Supabase sample settings with Bridge signing-secret and Google client-ID settings.

### Task 2: Implement Bridge token verification and auth routes

**Files:**
- Create: `app/core/auth.py`
- Create: `app/api/v1/auth.py`
- Modify: `app/api/dependencies.py`
- Modify: `app/api/v1/me.py`
- Modify: `app/api/v1/router.py`

**Interfaces:**
- `get_current_user(...) -> User`: validate Bridge bearer JWT and resolve its UUID subject to an active database user.
- Auth routes: `POST /auth/register`, `/auth/login`, `/auth/google`, `/auth/refresh`, `/auth/logout`.
- Token response: `access_token`, `refresh_token`, `token_type="bearer"`, `expires_in`.
- Registration and first Google sign-in accept `role=student|freelancer` (default `student`); never accept public `admin` assignment; return the role from `/v1/me`.
- Student signup requires full name, unique key skills, experience level, weekly availability hours, and optional portfolio URL.

- [ ] Implement Argon2 password hashing, normalized-email registration/login, and generic invalid-credential responses.
- [ ] Verify Google ID tokens with `google-auth` against configured client IDs; require verified email; create or resolve one Bridge user by Google subject and reject email collisions rather than linking identities implicitly.
- [ ] Require student profile data for new student registrations and first-time Google sign-in; do not mutate existing user role or profile during Google sign-in.
- [ ] Issue short-lived signed access JWTs and random refresh tokens; store SHA-256 refresh-token hashes only.
- [ ] Rotate refresh tokens transactionally; revoke a session family on replay or logout.
- [ ] Replace Supabase JWKS verification with Bridge JWT validation and database user resolution; update `/v1/me` to return Bridge UUID.
- [ ] Mount auth routes under the v1 router and validate required signing-key and Google-audience configuration at relevant endpoints.

### Task 3: Update project documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/bridge_backend_handoff.md`
- Modify: `docs/mds/bridge_backend_handoff.md`
- Modify: `docs/mds/bridge_trd.md`

- [ ] Document database migration, local Bridge signing secret, Google client IDs, auth request/response shapes, and how clients send Bridge access tokens in the root README.
- [ ] Remove current-state claims that Supabase owns sign-in or that Supabase JWTs protect the API; leave dated historical design artifacts unchanged.
- [ ] State that no Supabase accounts need migration and that recovery/verification flows are future work.

## Completion checks

- Apply and roll back the Alembic auth migration against a local PostgreSQL database.
- Start the service with no auth settings and confirm `/health` works while auth endpoints fail closed.
- Review the route schemas and documentation for all five auth operations, student signup profile fields, and Bridge-only bearer token behavior.
