# Bridge

Bridge is a student talent marketplace concept. The product screens describe student profiles, task discovery and applications, task-owner applicant review, matches, and conversations.

## Project contents

- [`backend/`](backend/) - separate Python FastAPI service with PostgreSQL, SQLAlchemy, Alembic, Bridge-owned authentication, and Google sign-in.
- [`docs/`](docs/) - product, business, technical, and engineering handoff documents.

## Start the backend

See the [backend setup guide](backend/README.md) for prerequisites, local PostgreSQL setup, configuration, and run commands.

The backend provides email/password and Google sign-in APIs, Bridge access and refresh tokens, student onboarding profiles, a public health route, and a protected identity route. Marketplace workflows are not implemented yet.

## Key documents

- [Product Requirements Document](docs/pdfs/bridge_prd.pdf)
- [Business Requirements Document](docs/pdfs/bridge_brd.pdf)
- [Technical Requirements Document](docs/pdfs/bridge_trd.pdf)
- [Backend Engineering Handoff](docs/pdfs/bridge_backend_handoff.pdf)
- [Backend Engineering Handoff (Markdown)](docs/bridge_backend_handoff.md)
- [Backend Foundation Implementation Plan](docs/superpowers/plans/2026-11-03-bridge-backend-foundation.md)
- [Bridge-owned authentication design](docs/superpowers/specs/2026-11-05-bridge-owned-auth-design.md)
- [Bridge-owned authentication implementation plan](docs/superpowers/plans/2026-11-05-bridge-owned-auth.md)
