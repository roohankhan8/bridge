# Bridge-owned authentication design

## Intent

Replace the backend's Supabase JWT verification with Bridge-owned account and session APIs. Google remains an identity provider for users who choose Google sign-in; Supabase is removed from runtime authentication.

## Goals

- Support email/password registration and login.
- Accept a Google ID token from the client, verify it server-side, and sign the user into a Bridge account.
- Issue Bridge access tokens and rotating refresh tokens for both sign-in methods.
- Protect `GET /v1/me` using Bridge access tokens.
- Persist users and refresh sessions in the existing PostgreSQL database.
- Store one role per user: `admin`, `freelancer`, or `student`; expose it through `/v1/me`.
- Keep existing protected routes compatible with an authenticated identity subject where practical.

## Non-goals

- Google browser redirect/callback handling in the backend.
- Email verification, password reset, MFA, account deletion, or admin tooling.
- Client implementation (this repository contains only the backend).
- Marketplace profile management beyond the fields collected at student signup.

## Approaches

1. **Client Google ID token exchange, Bridge access JWT plus stored rotating refresh tokens (selected).** Fits a mobile client and the existing bearer-token API. Google credentials are validated by Bridge; Bridge owns subsequent API sessions and can revoke refresh sessions.
2. **Backend Google redirect/callback flow.** Centralizes the browser flow, but changes the API into a browser-oriented OAuth client and is less suited to the described mobile client.
3. **Database-backed session on every request.** Simple revocation, but adds a database lookup to every protected request. A short-lived signed access token plus persisted refresh sessions gives a smaller runtime dependency while retaining refresh revocation.

## API and behavior

- `POST /v1/auth/register`: accept email and password, create an account, and return a Bridge token pair.
- `POST /v1/auth/login`: verify email and password and return a Bridge token pair. Use a generic invalid-credentials response.
- `POST /v1/auth/google`: accept a Google ID token, verify signature, issuer, expiry, and configured audience using Google's maintained verification library; require a verified email. Find an existing account by Google subject or create a new one; if the verified email belongs to an account without that Google subject, return a conflict rather than linking identities implicitly.
- `POST /v1/auth/refresh`: accept a refresh token, rotate it atomically, revoke the prior token, and return a new token pair. Reuse of a rotated token revokes its token family.
- `POST /v1/auth/logout`: revoke the presented refresh token's session family, including rotated descendants; access tokens expire on their short lifetime.
- `GET /v1/me`: return the authenticated Bridge user ID using the Bridge access token.

Access tokens are short-lived signed JWTs. Refresh tokens are random opaque values; only their hashes are stored in PostgreSQL. Passwords are hashed with Argon2 using a maintained password-hashing library. Email is normalized and unique. The user row has a nullable password hash and nullable unique Google subject. Each user has one role. Public registration and first-time Google sign-in may choose `student` or `freelancer` (default `student`); public endpoints cannot assign `admin`. Existing-account sign-in never changes a role. Admin assignment is provisioned outside public auth endpoints. Email/password and Google identities are not automatically linked by matching email; users with an existing account receive a conflict until an authenticated linking flow is implemented.

Student registration creates a `StudentProfile` in the same transaction with full name, 1–20 unique skill tags (up to 60 characters each), experience level (`beginner`, `intermediate`, or `advanced`), weekly availability (0–168 hours), and an optional HTTP(S) portfolio URL. Google sign-in for a new student account requires the same profile payload; later Google sign-ins ignore profile and role input.

## Data and configuration

Add users, student-profile, and refresh-session tables through an Alembic migration. User IDs are UUIDs. Sessions store token hash, user ID, family ID, expiry, revocation, and creation timestamps. Keep database transactions around account creation and refresh rotation.

Remove `SUPABASE_URL` and Supabase audience settings. Add a required Bridge JWT signing secret and configured Google OAuth client ID(s) as server settings. Do not provide production signing-secret defaults; document local setup and fail closed when auth configuration is missing. No Google client secret is needed for ID-token verification.

## Security and compatibility

- Bound and validate credentials; never log passwords, tokens, or Google ID tokens.
- Return generic login failures and reject unverified Google email claims.
- Verify Google ID tokens with a maintained library and configured audience; never trust decoded claims without signature verification.
- Require bearer authentication on `/v1/me`; use the Bridge user UUID as JWT subject and response identity.
- There are currently no Supabase accounts to migrate, and the client is not included in this repository. Client auth integration and account recovery remain follow-up work.

## Acceptance

- Supabase settings and remote JWKS verification are no longer required for protected Bridge routes.
- Email/password registration and login, Google ID token exchange, refresh rotation, and logout have documented request/response contracts and correct persistence behavior.
- `/v1/me` accepts only valid Bridge access tokens and identifies the Bridge user.
- Database schema can be created and rolled back through Alembic.
- Root README and auth handoff documentation describe the new configuration and flow.

## Builder decisions

- Use a maintained Argon2 password-hashing library and Google's official ID-token verification library.
- Use UUID identities, opaque refresh tokens hashed at rest, and short-lived JWT access tokens.
- Do not add verification or recovery flows without product requirements.
