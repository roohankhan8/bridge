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

Set `GOOGLE_CLIENT_IDS` to a JSON array of the mobile app's Google OAuth client IDs. Configure the SMTP settings and public app URL shown in `.env.example` to deliver verification and password reset links. Keep the signing secret and mail credentials on the server; Google ID-token verification does not need a Google client secret.

### Local email with Laragon

Laragon includes Mailpit for catching development email. Set these values in `.env`:

```dotenv
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_USE_TLS=false
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=dev@localhost
```

Mailpit needs no SMTP credentials. Open [http://localhost:8025](http://localhost:8025) to view verification and password-reset emails. `127.0.0.1` assumes the API runs directly on Windows; if it runs in a container, configure a host address reachable from that container.

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

- `POST /v1/auth/register` - create an email/password account; student signup starts a draft profile with step-one details, and the photo may be uploaded after email verification and login. Freelancer signup uses `"role": "freelancer"` without a profile. Public signup cannot grant `admin`.
- `POST /v1/auth/verify-email` - verify with the emailed 8-digit code and account email. Codes expire after 10 minutes and lock after five incorrect attempts.
- `POST /v1/auth/resend-verification` - request another verification code; responses are generic and resend is limited to once per 60 seconds.
- `POST /v1/auth/forgot-password` and `POST /v1/auth/reset-password` - request a reset link and set a new password. Reset requests use a generic response; resetting revokes existing refresh sessions.
- `POST /v1/auth/login` - verify email and password for a verified account.
- `POST /v1/auth/google` - exchange a Google ID token for Bridge tokens. New student accounts include the role and profile; existing accounts keep their saved role/profile. Matching an existing email returns `409`; identities aren’t linked implicitly.
- `POST /v1/auth/refresh` - rotate a refresh token. Reuse revokes that session family.
- `POST /v1/auth/logout` - revoke the presented refresh token’s entire session family.
- `GET /v1/me` - return the user ID, role, and student profile, if present. Send the access token as `Authorization: Bearer <access-token>`.
- `PUT /v1/me/student-profile` - save profile fields incrementally across the five onboarding steps. Profile photos can be supplied as an HTTP(S) URL or uploaded with the photo route below; digital-footprint entries are HTTP(S) URLs. The final step publishes a complete profile for public viewing; see OpenAPI for the publish operation and field enums.
- `POST /v1/me/student-profile/photo` - upload a multipart field named `photo` containing a PNG or JPEG image up to 5 MB. The API stores it locally under `PROFILE_UPLOAD_DIR/student_profiles` and returns the profile with its authenticated photo reference.
- `GET /v1/me/student-profile/photo` - read the authenticated student's photo, including a draft photo during onboarding.
- `GET /v1/students/{user_id}/profile` - read a verified, published student profile. Drafts are not public.
- `GET /v1/students/{user_id}/profile/photo` - read a photo only when its profile is published and the student's email is verified.

### Freelancer onboarding routes

Freelancers use a separate profile from student profiles. All routes require a freelancer bearer access token; profile reads and photos are private to the authenticated freelancer.

- `GET /v1/me/freelancer-profile` - return the saved onboarding profile, or empty defaults if onboarding has not started.
- `PATCH /v1/me/freelancer-profile` - save one or more fields: `full_name`, `professional_title`, `company_name`, `years_experience`, `core_skills`, `areas_of_expertise`, `portfolio_url`, `linkedin_url`, `project_domains`, `delegation_types`, and `preferred_student_skill_level`. Send `[]` to clear a list; omit fields to leave them unchanged.
- `POST /v1/me/freelancer-profile/photo` - upload a multipart field named `photo` containing a PNG or JPEG image up to 5 MB. The API stores it under `PROFILE_UPLOAD_DIR` in a private local directory and returns the profile, including its authenticated `profile_photo_url`.
- `GET /v1/me/freelancer-profile/photo` - read the authenticated freelancer’s photo.
- `POST /v1/me/freelancer-profile/publish` - publish after email verification and completion of the required name, professional title, experience range, and project domains.

Set `PROFILE_UPLOAD_DIR` in `.env` to choose the local photo directory; it defaults to `uploads`. Student photos are stored in its `student_profiles` subdirectory and freelancer photos in `freelancer_profiles`. Local files are instance-local and are not served as public static content. Back them up or move them when changing hosts; switching to S3 will require migrating the files and profile references.

Student profiles collect education and photo; experience, highlights, and work links; up to three core skills with depth plus supporting skills; availability, work type, arrangement, and duration; and a final public preview. Passwords use Argon2 hashes; refresh tokens and one-time auth tokens are stored only as hashes. Admin accounts must be provisioned through a trusted process.

## API docs for mobile

When the local API is running, use [Swagger UI](http://localhost:8000/docs) to explore and try endpoints, or fetch the [OpenAPI JSON](http://localhost:8000/openapi.json). The `/docs` page documents bearer auth, fields, examples, responses, and pagination. `localhost` only works from the machine running the API; configure a reachable development or deployed base URL in the mobile app. See the [mobile API quickstart](docs/bridge_backend_handoff.md#mobile-api-quickstart) for request and response examples.

## Task and application routes

All task and application routes require a Bridge bearer access token. Budgets are positive PKR amounts with up to two decimal places; deadlines are calendar dates and may be today or later in UTC.

- `POST /v1/tasks` - freelancer creates a task with `title`, `description`, `budget`, `deadline`, and 1–20 unique `required_skills`.
- `GET /v1/tasks` - browse open tasks whose deadline has not passed. Supports UUID `cursor` and `limit` pagination (default 20, maximum 100).
- `GET /v1/me/tasks` - freelancer lists their own open and closed tasks, with the same pagination.
- `GET /v1/tasks/{task_id}` - read an open task; its owner can also read it after closing or expiry.
- `PATCH /v1/tasks/{task_id}` and `POST /v1/tasks/{task_id}/close` - owner edits an open task or closes it. Closing is permanent.
- `POST /v1/tasks/{task_id}/applications` - student submits a `proposal` once per task, while it is open and before its deadline.
- `GET /v1/tasks/{task_id}/applications` - owner reviews paginated applications.
- `PATCH /v1/applications/{application_id}` - owner changes a pending application to `accepted` or `rejected`. Repeating the same decision is safe; a conflicting later decision returns `409`.

Task titles are 2–200 characters, descriptions 1–10,000, proposals 1–5,000, and each required skill is 1–60 characters. The API returns `404` for tasks outside the caller's owner visibility and `403` when the caller's role cannot perform the operation.

## Project documents

- [Product Requirements Document](docs/pdfs/bridge_prd.pdf)
- [Business Requirements Document](docs/pdfs/bridge_brd.pdf)
- [Technical Requirements Document](docs/pdfs/bridge_trd.pdf)
- [Backend Engineering Handoff](docs/pdfs/bridge_backend_handoff.pdf)
- [Backend Engineering Handoff (Markdown)](docs/bridge_backend_handoff.md)
- [Bridge-owned authentication design](docs/superpowers/specs/2026-11-05-bridge-owned-auth-design.md)
- [Bridge-owned authentication implementation plan](docs/superpowers/plans/2026-11-05-bridge-owned-auth.md)
- [Task and application API design](docs/superpowers/specs/2026-11-05-task-applications-design.md)
- [Task and application API implementation plan](docs/superpowers/plans/2026-11-05-task-applications.md)
