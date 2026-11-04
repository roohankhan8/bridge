# Bridge Backend Engineering Handoff

**Student talent marketplace | Python API service and screen-to-backend handoff**

## Purpose and scope

This handoff translates the visible Bridge mobile prototype into backend work areas. The screens depict students presenting skills and portfolios, browsing paid tasks, submitting proposals, and communicating with task owners. Task owners can post work, review applicants, view talent profiles, manage matches, and exchange messages. The screens are evidence of intended interactions; endpoint names, persistence rules, and security behavior below are implementation recommendations unless explicitly marked as a selected technical decision.

**Evidence boundary:** Screen descriptions reflect the Google Stitch project. Proposed behavior is identified as such where the UI does not define the rule. No payment flow, ratings calculation, verification workflow, or operational policy is confirmed by the screens.

## Selected backend stack

| Layer | Selection | Responsibility |
|---|---|---|
| API service | Python with FastAPI | Separate, versioned HTTPS REST API between mobile clients and backend domain logic. |
| Request models | Pydantic | Parse and validate API input and produce OpenAPI schemas. |
| Database | PostgreSQL | Transactional persistence for profiles, tasks, applications, conversations, and messages. |
| Database access | SQLAlchemy 2.x | ORM and transaction/session management. |
| Schema migrations | Alembic | Versioned database schema changes. |
| Authentication | Bridge Auth API with Google ID token verification | Bridge owns email/password accounts and sessions; clients exchange Google ID tokens and use Bridge access JWTs. |

The mobile app calls FastAPI; it does not access marketplace tables directly. Bridge issues its own access and refresh tokens for email/password and Google sign-in. The API verifies Google ID tokens against configured client IDs, and validates Bridge access JWTs on protected routes.

Use SQLAlchemy transaction boundaries for multi-row state changes, and PostgreSQL constraints for uniqueness and referential integrity. If the API connects with a privileged database role that bypasses row-level security, RLS is not a substitute for API authorization. Use a least-privileged database role; treat RLS as defense in depth only when the request identity is safely propagated to the database.

Keep one API service for the initial scope. Add a worker, queue, realtime transport, or additional service only when a confirmed product capability requires it. The separate API service requirement is fulfilled by the FastAPI boundary; the prototype does not establish a microservice topology.

## Screen inventory

| Screen | Visible content and interaction | Backend implication |
|---|---|---|
| Splash screen | Bridge branding and loading state. | No domain operation shown; startup may later fetch session/config. |
| Prototype launch | “Double click to open” prototype card. | Design navigation only; not a product requirement. |
| Role selection | Student or Freelancer choice; Continue. | Persist selected account mode or use it to route onboarding. |
| Login / signup | Email, password, Login, Google continuation, sign-up link. | Use `/v1/auth/register`, `/v1/auth/login`, and `/v1/auth/google`; verify email before password login and support password recovery. |
| Student onboarding | Five steps: education/photo; experience/highlights/work links; core/supporting skills; availability/work preferences; public preview. | Save each step incrementally; publish only a complete profile after email verification. |
| Task details | Title, image, budget, deadline, description, skills; client/task summary. | Read task detail and related client metadata. |
| Student home | Active task count, pending payment amount, available task cards with budget and detail link. | Dashboard summary plus paginated task discovery; metric definitions remain open. |
| Apply to task | Task summary, proposal text, portfolio highlights and edit selection. | Create application/proposal linked to task and applicant. |
| Student profile | Name, avatar, title, experience, portfolio URL, skills, edit profile. | Read/update profile and portfolio references. |
| Freelancer home | Post New Task; suggested student cards with skill/rating summary and profile action. | Create-task entry point and candidate recommendations/search; ranking behavior is not specified. |
| Matches | Accepted, pending, and alternative/rejected-looking application cards; open chat; edit action on some cards. | List relationship/application states and create/open a conversation for eligible pairs. |
| Post a task | Title, description, required skills, budget, deadline, draft/review control. | Create/update task listing; draft/review meaning needs product definition. |
| Freelancer profile | Name, rating, verified badge, rate/earnings, completion percentage, active tasks. | Read public profile and task/aggregate metrics; verification source is unspecified. |
| Chat | Conversation history, message composer, send control, project goal/progress card. | Fetch conversation and append messages; project goal/progress behavior needs definition. |
| Task applicants | Applicant profile/rating/skills with Reject and Accept actions. | List applications and transition their state with authorization and concurrency checks. |

## User flows

### Sign in and build a student profile

The user chooses Student or Freelancer and creates a Bridge account with email/password or Google sign-in. Email/password registration sends a verification link; the account must be verified before password login. Forgot-password requests send a time-limited reset link, and successful resets revoke existing refresh sessions. Configure the SMTP settings and public app URL in `.env.example` for these emails. The client receives Bridge access and refresh tokens after sign-in and sends the access JWT as a bearer token to FastAPI.

Students can register with step-one fields only and save later steps independently through `PUT /v1/me/student-profile`. The steps collect full name, university, degree/program, graduation year and photo URL; experience, highlights and digital-footprint URLs; up to three core skills with depth plus supporting skills; availability (`10-15`, `15-20`, `20-30`, or `full-time-40`), paid-task and/or structured-internship preference, remote or hybrid arrangement, and project duration (`<2`, `2-4`, `4-12`, or `12+` weeks. The final preview is published only after all steps are complete and the email is verified. `GET /v1/me` returns the saved profile; public profile reads expose only verified, published profiles.

### Discover and apply to work

Students browse authenticated task listings and open task details, then submit a proposal before the task deadline. The API allows one application per student per task. Applications move from pending to accepted or rejected; repeating the same decision is safe, while changing a settled decision is rejected. Proposal editing and withdrawal are not part of the current API.

### Client posts and reviews a task

Freelancers create open tasks with a title, description, required skills, PKR budget, and calendar-date deadline. They can edit open tasks, close their own tasks, review applications, and accept or reject pending applications. Draft/review states are not part of the current API.

### Match and message

Matches groups candidates/application cards into visible status sections, and accepted matches expose Open Chat. A conversation screen shows messages and a project goal/progress card. Recommended: allow conversation access only for an accepted application or another explicitly approved relationship; enforce membership for every read/send.

## API surface

**Convention:** Use `/v1`, JSON, cursor pagination, and ISO-8601 UTC timestamps. Task and application rows marked **Implemented** describe the current API; other rows remain proposals. FastAPI/Pydantic schemas publish the OpenAPI contract.

| Method and path | Purpose | Key behavior | State |
|---|---|---|
| `POST /v1/auth/register`, `/v1/auth/login`, `/v1/auth/google` | Register with email/password or exchange a Google ID token. | Bridge issues access and refresh tokens; public roles are student or freelancer. Student signup requires the profile fields above. | Implemented |
| `POST /v1/auth/verify-email` | Verify a newly registered email. | Consume a one-time expiring token; required for email/password login. | Implemented |
| `POST /v1/auth/forgot-password`, `/v1/auth/reset-password` | Request a password reset and set a new password. | Generic request response; one-time expiring reset tokens; successful reset revokes refresh sessions. | Implemented |
| `POST /v1/auth/refresh`, `/v1/auth/logout` | Rotate or revoke a refresh session family. | Refresh token; only hashes are stored. | Implemented |
| `GET /v1/me` | Read Bridge user ID, role, and student profile if present. | Require a valid Bridge bearer JWT. | Implemented |
| `PUT /v1/me/student-profile` | Save student profile steps. | Authenticated student only; partial updates preserve fields saved in other steps. | Implemented |
| Profile publication operation (see OpenAPI) | Publish the final profile preview. | Requires verified email and complete required profile data. | Implemented |
| `GET /v1/students/{user_id}/profile` | Read a public student profile. | Only verified, published profiles are visible; private account fields are excluded. | Implemented |
| `GET /v1/tasks` | Browse tasks. | Authenticated; returns open tasks with deadline today or later (UTC date); UUID cursor pagination (`limit` 1–100, default 20). Skill/budget filters are not implemented. | Implemented |
| `GET /v1/me/tasks` | List the caller's tasks. | Freelancer only; includes open and closed tasks; UUID cursor pagination. | Implemented |
| `GET /v1/tasks/{task_id}` | Read task details. | Authenticated users can read open, unexpired tasks; the owner can also read their closed or expired task. | Implemented |
| `POST /v1/tasks` | Create a task. | Freelancer only. Required title, description, positive PKR budget (up to two decimal places), deadline date (today or later), and 1–20 unique required skills (1–60 characters each). New tasks are open. | Implemented |
| `PATCH /v1/tasks/{task_id}` | Edit a task. | Owner only; open tasks only; partial updates. | Implemented |
| `POST /v1/tasks/{task_id}/close` | Close a task. | Owner only; one-way; closed tasks stop accepting applications. | Implemented |
| `POST /v1/tasks/{task_id}/applications` | Submit a proposal. | Student only; one application per student/task; task must be open and unexpired; proposal is 1–5,000 characters. | Implemented |
| `GET /v1/tasks/{task_id}/applications` | Review applicants. | Task owner only; UUID cursor pagination (`limit` 1–100, default 20). | Implemented |
| `PATCH /v1/applications/{application_id}` | Accept/reject an application. | Owner only; pending → accepted/rejected. Same-decision retries are safe; a conflicting later decision returns `409`. Decisions do not close the task or change other applications. | Implemented |
| `GET /v1/me/applications` · `GET /v1/me/matches` | Student status lists. | Expose only caller's applications and permitted match states. | Proposed |
| `GET /v1/profiles/{profileId}` | Profile detail. | Return public profile fields; redact private account data. | Proposed |
| `GET /v1/conversations` · `GET /v1/conversations/{id}/messages` | List/read conversations. | Member-only, ordered by sent time, cursor paginated. | Proposed |
| `POST /v1/conversations/{id}/messages` | Send message. | Member-only; validate body; persist and return canonical message. | Proposed |

## Mobile API quickstart

### Base URL and interactive docs

For local development, start the API with `uvicorn app.main:app --reload` and open [Swagger UI](http://localhost:8000/docs). The machine-readable contract is at [OpenAPI JSON](http://localhost:8000/openapi.json). `localhost` is reachable only from the machine running the API; mobile simulators/devices need a base URL they can reach. Use the environment's configured API host rather than hard-coding a production URL.

All request and response bodies are JSON. After registration or sign-in, retain `access_token` for protected requests and send it as `Authorization: Bearer <access_token>`. Keep `refresh_token` for `/v1/auth/refresh` and `/v1/auth/logout`; do not send it as the bearer token.

### Register and sign in

Student registration includes a profile. Freelancer registration omits `student_profile` and sets `role` to `freelancer`.

```http
POST /v1/auth/register
Content-Type: application/json
```

```json
{
  "email": "student@example.com",
  "password": "<user-chosen-password>",
  "role": "student",
  "student_profile": {
    "full_name": "Ayesha Khan",
    "key_skills": ["Python", "FastAPI"],
    "experience_level": "intermediate",
    "availability_hours_per_week": 20,
    "portfolio_url": "https://example.com/portfolio"
  }
}
```

Registration returns `201 Created` with the same token shape shown below. The placeholder password is supplied by the user; clients must not hard-code it.

```http
POST /v1/auth/login
Content-Type: application/json
```

```json
{
  "email": "student@example.com",
  "password": "<account-password>"
}
```

Successful registration (`201`) and login (`200`) return the same token shape:

```json
{
  "access_token": "<bridge-access-token>",
  "refresh_token": "<bridge-refresh-token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

Student registration also requires a `student_profile`; freelancer registration uses `"role": "freelancer"` and omits that field. Public registration cannot create admins. For Google sign-in, send the ID token obtained through the mobile Google Sign-In SDK to `POST /v1/auth/google` as `id_token`.

### Create a task

Freelancers create tasks. Budget is a positive PKR amount with up to two decimal places. Deadline is a calendar date in `YYYY-MM-DD` form and must be today or later in UTC. Required skills are 1–20 unique, non-empty strings, each at most 60 characters.

```http
POST /v1/tasks
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "title": "Build a student dashboard",
  "description": "Create a responsive dashboard for tracking student projects.",
  "budget": 25000.00,
  "deadline": "2026-12-31",
  "required_skills": ["FastAPI", "PostgreSQL"]
}
```

The response is `201 Created` and includes server-generated IDs, `status: "open"`, and UTC timestamps:

```json
{
  "id": "9dd5d6d6-89ae-4d10-9cf4-4ccb06d785d9",
  "owner_id": "e88d05b8-bb5a-4b2c-9e48-1b926ba88a71",
  "title": "Build a student dashboard",
  "description": "Create a responsive dashboard for tracking student projects.",
  "budget": 25000.0,
  "deadline": "2026-12-31",
  "required_skills": ["FastAPI", "PostgreSQL"],
  "status": "open",
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:00:00Z"
}
```

### Browse tasks and continue a page

```http
GET /v1/tasks?limit=20
Authorization: Bearer <access-token>
```

The response has `items` and `next_cursor`. Continue with the returned cursor; when it is `null`, there are no more results. Cursors are UUIDs and `limit` must be between 1 and 100 (default 20).

```json
{
  "items": [],
  "next_cursor": null
}
```

### Apply to a task

Students can submit one application per task while it is open and not past its deadline.

```http
POST /v1/tasks/9dd5d6d6-89ae-4d10-9cf4-4ccb06d785d9/applications
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "proposal": "I have built similar FastAPI services and can deliver the dashboard in two weeks."
}
```

The response is `201 Created` with the application ID and initial `status: "pending"`.

```json
{
  "id": "6d0f9e79-14f4-46b4-aa85-42dbe9e80756",
  "task_id": "9dd5d6d6-89ae-4d10-9cf4-4ccb06d785d9",
  "student_id": "d49986b4-4e7e-4d2a-9d1e-663f49103f0c",
  "proposal": "I have built similar FastAPI services and can deliver the dashboard in two weeks.",
  "status": "pending",
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:00:00Z"
}
```

### Review and decide an application

Only the freelancer who owns the task can list its applications or decide them. List with `GET /v1/tasks/{task_id}/applications?limit=20`; use `next_cursor` the same way as task browsing. Accept or reject a pending application with:

```http
PATCH /v1/applications/6d0f9e79-14f4-46b4-aa85-42dbe9e80756
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "status": "accepted"
}
```

The response returns the application object with `status: "accepted"`; all other fields are unchanged from the submitted application. Repeating the same decision is safe; trying to change an already settled decision returns `409`.

```json
{
  "id": "6d0f9e79-14f4-46b4-aa85-42dbe9e80756",
  "task_id": "9dd5d6d6-89ae-4d10-9cf4-4ccb06d785d9",
  "student_id": "d49986b4-4e7e-4d2a-9d1e-663f49103f0c",
  "proposal": "I have built similar FastAPI services and can deliver the dashboard in two weeks.",
  "status": "accepted",
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:05:00Z"
}
```

### Common errors

Errors use FastAPI's `{"detail": ...}` shape. Validation errors (`422`) include a list of field-level details.

| Status | Meaning for the mobile client |
|---|---|
| `401` | Missing, invalid, or expired access token; sign in or refresh, then retry as appropriate. |
| `403` | Authenticated account role cannot perform the action. |
| `404` | Resource does not exist or is outside the caller's visibility. |
| `409` | State conflict: duplicate application, closed/expired task, own-task application, or an already settled decision. |
| `422` | Invalid JSON field, date, budget, skill list, cursor, or limit. |

## Current and suggested data model

| Entity | Fields | Notes |
|---|---|---|
| User | `id`, normalized unique `email`, nullable password hash, nullable Google subject, role (`admin`, `freelancer`, `student`), `created_at` | Passwords use Argon2; public signup cannot assign admin. |
| StudentProfile | `user_id`, full name, key skills, experience level, availability hours per week, optional portfolio URL | Created with student signup and returned by `/v1/me`. |
| Profile | `user_id`, `display_name`, `headline`, `avatar_url`, `experience_level`, `availability_hours_per_week`, `portfolio_url`, `rating_summary`, `verified_at` | Rating and verification calculation/source are unknown. |
| Skill | `id`, `canonical_name` | Canonical catalog supports consistent filtering. |
| ProfileSkill | `profile_id`, `skill_id`, proficiency or display order | Only add proficiency if product needs it; UI currently shows tags. |
| Task | `id`, `owner_id`, `title`, `description`, `budget` (positive PKR decimal, up to 2 places), `deadline` (date), `required_skills` (JSON list), `status` (`open`/`closed`), timestamps | Implemented. Required skills are 1–20 unique tags, each 1–60 characters. |
| TaskApplication | `id`, `task_id`, `student_id`, `proposal`, `status` (`pending`/`accepted`/`rejected`), timestamps | Implemented. One application per student/task is enforced in the database. |
| ApplicationPortfolioItem | `application_id`, `portfolio_item_id` or URL snapshot | UI lets applicant choose highlights; decide snapshot vs live profile reference. |
| Conversation | `id`, `task_id` nullable, `created_at` | Tie chat to accepted work if task-scoped conversation is confirmed. |
| ConversationMember | `conversation_id`, `user_id`, `joined_at` | Unique membership pair supports authorization. |
| Message | `id`, `conversation_id`, `sender_user_id`, `body`, `sent_at`, `read_at` nullable | Append-only preferred; read receipts are not clearly shown. |
| TaskProgress / ProjectGoal | `task_id`, goal text/status or progress fields | A progress/goal card appears in chat; exact fields and update controls need definition. |

## Authentication, authorization, and privacy

- Bridge Auth owns email/password and Bridge sessions. The client sends its Bridge access token to protected FastAPI routes as `Authorization: Bearer <JWT>`.
- Verify Google ID token signature, issuer, expiry, verified email, and configured audience with a maintained library. Validate Bridge JWT signature and claims. Never trust a user ID or role supplied only in the request body.
- Resolve the token subject to the Bridge user/profile record. Enforce object-level authorization: task owner edits tasks and decides applications; applicant accesses only their applications; conversation members alone read/send messages.
- Each account has one role: `admin`, `freelancer`, or `student`. Public registration cannot grant `admin`; admin provisioning uses a trusted process. Enforce role checks for role-restricted operations.
- Do not link a Google identity to an existing account by email alone. Without email verification, a matching email can belong to an unverified password signup; return `409` and require a future authenticated linking flow.
- Configure `AUTH_JWT_SECRET` with at least 32 random characters and `GOOGLE_CLIENT_IDS` as a JSON array on the API server; keep both out of client configuration.
- Return public profile fields through an explicit allowlist. Do not expose email, session data, or private applicant details in public cards.
- Use a least-privileged Postgres role. If privileged credentials bypass RLS, implement and test authorization in FastAPI; use RLS only as additional defense where the database connection carries safe user context.
- Rate-limit auth-related and abuse-prone actions at an appropriate edge/API layer. Do not store Bridge signing secrets in the mobile app or log passwords, tokens, or sensitive message contents.

## Validation and consistency

Use Pydantic schemas for input shape and field constraints, with domain-level checks and PostgreSQL constraints for rules that must survive concurrent requests.

| Input/action | Server-side checks to define |
|---|---|
| JWT | Signature, issuer, expiry, subject, and allowed authentication context; return generic 401 for invalid credentials. |
| Student and task skill tags | Student profile and task APIs accept 1–20 unique, non-empty text tags up to 60 characters each. |
| Availability | Non-negative bounded weekly hours; clarify whether required. |
| Portfolio URL | Allow approved schemes (normally HTTPS); length limit; do not fetch arbitrary URLs from the backend. |
| Task title/description | Title is 2–200 characters; description is 1–10,000; reject empty/whitespace-only values; safely render user text. |
| Budget/deadline | Budget is a positive PKR decimal with at most 12 digits and 2 decimal places. Deadline is a calendar date, today or later in UTC. |
| Application | Proposal is 1–5,000 characters; task must be open and not past its deadline; enforce one application per student/task in the database. |
| Accept/reject | Owner may decide pending applications; same-state retries are safe, conflicting decisions return `409`. Accepting does not close the task or decide other applications. |
| Message | Non-empty bounded body; safe display encoding; enforce membership at send time. |

## Open questions before implementation

1. How should admin accounts be provisioned and audited?
2. Which email verification and password recovery flows should be added?
3. Are additional task states such as draft or review needed beyond the current open/closed API?
4. Does the displayed budget represent a fixed task total, an hourly rate, or an estimate? Payment capabilities remain out of scope.
5. Should a future API allow proposals to be edited or withdrawn? The current API permits one application per student/task and leaves other applications unchanged after acceptance.
6. How are “matches” generated and what do accepted, pending, and other visible groups mean operationally?
7. What constitutes a verified profile, rating, completion percentage, earnings, or active task count?
8. What is the data model and update permission for the chat's project goal/progress card? Are read receipts, attachments, notifications, or realtime delivery required?
9. Should profile skills and portfolio highlights be snapshotted when an application is submitted?
10. What are retention, moderation/reporting, blocking, deletion, and audit requirements?

## Recommended delivery sequence

| Phase | Backend scope | Exit condition |
|---|---|---|
| 1. Identity and profile | Bridge auth APIs, Google token verification, roles, student onboarding profile, skill catalog. | A signed-in user can save/read their profile with enforced field permissions. |
| 2. Marketplace | Task CRUD/status, browse/detail, application submit/list/decision. | An owner can publish and review applications; a student can browse and apply. |
| 3. Match and messaging | Match/status list, conversation membership, message history/send. | Only authorized participants can access a conversation; decisions are consistent under retries/concurrency. |
| 4. Dashboard metrics | Active tasks, pending payment display, ratings/verification aggregates. | Metric definitions and source data are agreed and values reconcile. |

*Source: Bridge: Student Talent Marketplace, Google Stitch project 14483777616722284649. Screen descriptions reflect visible UI content; API and schema sections are proposed backend contracts.*
