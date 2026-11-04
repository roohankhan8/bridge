# Task and Application API Implementation Plan

> **For agentic workers:** The repository workflow in `AGENTS.md` is required: planner → coder → tester → reviewer → docs. Keep these roles sequential.

**Goal:** Add freelancer-managed task posting and student proposals with owner decisions.

**Architecture:** Persist tasks and applications through the existing SQLAlchemy models and Alembic migrations. Expose authenticated operations through the existing versioned FastAPI routes, applying role and ownership checks using current auth dependencies.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic, and the standard-library `unittest` framework.

**Spec:** `docs/superpowers/specs/2026-11-05-task-applications-design.md`

## Global Constraints

- Keep existing authentication and user/profile behavior unchanged.
- Budgets are PKR amounts; deadlines are calendar dates.
- A student can apply once per task; reject applications to closed or expired tasks.
- Only task owners can edit, close, list applications, or decide them; only students can apply.
- Do not add dependencies.

## Review Focus

- Non-freelancer attempts to create or mutate tasks are rejected.
- Users cannot edit, close, or inspect applications for tasks they do not own.
- Duplicate student/task applications are prevented under concurrent requests by a database uniqueness constraint.
- Applications to closed or expired tasks are rejected, including at the deadline boundary.
- Only pending applications can be accepted or rejected, by the task owner.

---

### Task 1: Persist tasks and applications

**Files:** `app/db/models.py`; add `alembic/versions/0003_tasks.py`.

- [x] Add task and application models with owner/student foreign keys, timestamps, required skills, PKR budget, date deadline, task state, application decision state, and unique student/task constraint.
- [x] Add appropriate indexes and reversible migration operations consistent with local conventions.
- [x] Check migration head and model imports without changing unrelated schema.

### Task 2: Add task and application APIs

**Files:** Add `app/api/v1/tasks.py`; modify `app/api/v1/router.py`.

- [x] Add validated request and response schemas for tasks, proposals, and application decisions.
- [x] Add create, list/detail, edit, and close task operations; add student apply and owner application-list/decision operations.
- [x] Enforce role, ownership, self-application, uniqueness, deadline, and state rules from the spec using existing HTTP error conventions.
- [x] Register the new routes in the existing API router.

### Task 3: Verify API behavior

**Files:** Add focused tests in `tests/test_tasks.py` using `unittest` and SQLite; no existing test suite or pytest dependency is present.

- [x] Cover successful task creation/edit/close, student application, and owner decision flows.
- [x] Cover role and ownership failures, invalid input, duplicate application, closed/expired task, and repeated decision cases.
- [x] Run focused tests and the repository's required checks; report exact commands and results.

### Task 4: Update API documentation

**Files:** Update the existing API handoff and/or README only where needed to document the new endpoints and behavior.

- [x] Document request fields, role restrictions, PKR budgets, deadline dates, and application decisions using current doc conventions.
- [x] Confirm examples match the implemented schemas and routes.

## Implementation decisions

- Required skills reuse the existing JSON skill-tag shape and limits: 1–20 unique, non-empty values up to 60 characters.
- Collection endpoints use UUID cursor pagination with a default limit of 20 and maximum of 100.
- The deadline is valid through the current UTC calendar date. A same-state decision retry is idempotent; changing a settled decision returns `409`.
- Focused tests use the standard library because pytest and HTTPX are not installed; route functions are tested directly with SQLite.
