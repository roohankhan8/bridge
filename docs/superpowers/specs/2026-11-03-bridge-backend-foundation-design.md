# Bridge Backend Foundation Design

## Intent

Create a runnable backend foundation for Bridge in `D:\roohan\bridge\backend`. The repository currently contains documentation only. The backend will be a separately deployable Python API service so a future mobile or web client has one controlled integration boundary.

## Goals

- Start FastAPI locally with a health endpoint and clear versioned API structure.
- Configure PostgreSQL through environment settings and provide a local development database option.
- Set up SQLAlchemy 2.x database sessions and Alembic migrations.
- Establish a Supabase Auth JWT verification boundary for protected routes without implementing auth flows in the API.
- Include a practical README and a plan file that stages the subsequent Bridge backend work.

## Non-goals

- Implementing profiles, tasks, applications, matching, or messaging behavior now.
- Implementing signup, password, Google OAuth, refresh-token, or session management endpoints; Supabase Auth owns these.
- Payments, recommendations, realtime messaging, background workers, admin tools, deployment automation, or legal/policy material.
- Splitting the backend into microservices.

## Approaches

1. **One modular FastAPI service (selected):** One deployable API with small internal modules, PostgreSQL, SQLAlchemy/Alembic, and Supabase JWT validation. This meets the separate API requirement and keeps initial operations simple.
2. **Multiple microservices:** Split identity, marketplace, and messaging into separate services. Rejected for the foundation because no implemented workflows or independent scaling needs justify the extra deployment and data coordination.
3. **API-only stub without a database:** FastAPI health route and placeholder routes only. Rejected because it does not establish the requested persistence and migration foundation.

## Selected structure

Create a `backend/` directory under the Bridge project with a Python package under `app/`. Keep route registration, settings, database session setup, and auth verification as separate small modules. Add `alembic/` for migrations, `pyproject.toml` for dependencies/tool configuration, `.env.example` for non-secret configuration names, and `README.md` with local setup steps. Use a local PostgreSQL Compose service only for development; production hosting remains undecided.

## Constraints and security

- Stack: Python, FastAPI, Pydantic, PostgreSQL, SQLAlchemy 2.x, Alembic; Supabase Auth issues user tokens.
- API routes are versioned under `/v1`; all user and domain identity comes from a verified token, never from an untrusted request field.
- Keep `/health` public and independent of Supabase configuration; require verified identity for protected `/v1/*` routes.
- Verify JWT signature and require issuer, expiry, audience, subject, and the authenticated role using a maintained JWT library and Supabase signing keys/JWKS. This starter supports asymmetric ES256/RS256 keys; legacy HS256 tokens require changing the Supabase signing-key mode rather than sharing the secret with the API.
- Bind the local PostgreSQL port to loopback only; use a least-privileged database connection and do not assume PostgreSQL RLS protects data when connected with a role that bypasses it.
- Keep the starter small: no domain endpoints or extra services until the next implementation phase.
- Automated tests are excluded from this initial setup unless requested; provide runnable startup and manual health-check instructions instead.

## Open implementation choices

The engineer can choose a currently supported Python version available in the workspace and compatible package versions at implementation time. Hosting provider, database credentials, Supabase project URL/keys, user-mode rules, and production deployment are not known and must be configured later. The starter should fail with a clear configuration error when required settings are absent, rather than silently accepting insecure defaults.

## Approval boundary

This design describes a foundation only. After approval, create the project scaffold and a phased implementation plan. Do not implement Bridge marketplace workflows as part of this setup.
