# Task and Application API Design

## Intent

Add authenticated APIs for freelancers to post and manage paid tasks and for students to apply with a proposal. This gives Bridge a basic task marketplace workflow.

## Goals

- A freelancer can create, view, edit, and close their own tasks.
- Users can browse and view open tasks.
- A student can submit one proposal per task before it closes or reaches its deadline.
- A freelancer can view applications to their tasks and accept or reject each application.
- Store budget in PKR and deadline as a calendar date.
- Enforce role and ownership checks on the server.

## Non-goals

- Payments, contracts, messaging, task milestones, proposal revisions, or notifications.
- Search ranking, pagination changes, or task recommendation logic beyond existing API conventions.
- Reopening closed tasks or changing a decision after it is made, unless existing conventions require another behavior.

## Approaches

1. **Task posting and applications only:** create/browse tasks and submit proposals. This leaves tasks and applications without a usable completion/selection lifecycle.
2. **Basic marketplace lifecycle (selected):** add task editing and closing, owner-only application listing, and accept/reject decisions. This matches the requested lifecycle while avoiding payments and other downstream product features.
3. **Full work-management system:** include assignment execution, payments, messaging, milestones, and dispute handling. This is substantially broader than the requested API.

## Proposed behavior

- Add task and application persistence using the repository's existing SQLAlchemy and Alembic patterns.
- Task fields: title, description, PKR budget, date deadline, required skills, freelancer owner, and open/closed state.
- Application fields: student, task, proposal, decision state (`pending`, `accepted`, `rejected`), and creation time. Enforce one application per student per task.
- Authenticated freelancers create, edit, close, and list applications only for tasks they own. Authenticated students browse/view open tasks and apply. Do not permit an owner to apply to their own task.
- Reject past deadlines on task creation or edits and prevent applications to closed or expired tasks. Closing a task prevents new applications. A decision can be made only by the task owner and only for a pending application.
- Add request/response schemas and routes under the existing versioned API structure, with validation and error responses consistent with current endpoints.
- Add a reversible Alembic migration and focused tests for role access, ownership, validation, duplicate applications, deadlines, closure, and decisions.
- Update the backend handoff or README only where the new API behavior needs to be documented.

## Assumptions for implementation

- Use the existing user role values (`freelancer` and `student`) and authenticated-user dependency.
- Represent budgets with the project's suitable fixed-precision numeric type; the amount is PKR, so no per-task currency selector is needed.
- Use a date field for deadlines. Compare it with the current date in the application's established timezone convention.
- Closing is one-way for this first version. Application decisions are one-way and do not implicitly close the task or alter other applications.
- Required skills use the existing JSON list representation and student skill limits: 1–20 unique non-empty tags, up to 60 characters each. Task and applicant collection routes use UUID cursor pagination (default 20, maximum 100).
- Deadlines are valid through the current UTC calendar date. Repeating the same application decision is idempotent; attempting to change a settled decision returns `409`.

## Constraints and risks

- Keep existing authentication and user/profile behavior unchanged.
- Enforce owner and applicant checks in shared API logic, not only in request validation.
- Ensure the unique task/student constraint is enforced in the database as well as handled cleanly by the API, to prevent concurrent duplicate applications.
- The focused tests use Python's standard-library `unittest` with SQLite; they exercise route functions directly rather than making HTTP requests.
