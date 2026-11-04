# Agent workflow

The main agent is the coordinator. For repository tasks, it assigns work to the role agents in `.agents/roles/` and supervises handoffs; it does not do the planner's, coder's, reviewer's, or docs agent's work itself.

## Required sequence

1. Start a fresh **planner** subagent with the user's request and `.agents/roles/planner.md`. Wait for it to finish. The planner inspects the repo and returns a scoped, ordered plan with files and checks; it does not edit files.
2. Give that plan and the original request to a fresh **coder** subagent with `.agents/roles/coder.md`. Wait for it to finish implementation and its requested checks.
3. Give the original request, plan, and resulting diff to a fresh **reviewer** subagent with `.agents/roles/reviewer.md`. Wait for a read-only review.
4. If review finds actionable issues, send them to a fresh coder subagent to fix, then have a fresh reviewer inspect the new diff. Repeat only until the review has no blocking findings.
5. After review passes, give the original request, plan, final diff, and review result to a fresh **docs** subagent with `.agents/roles/docs.md`. Wait for it to finish documentation updates.
6. The coordinator summarizes the outcome and checks the final working tree. It may create additional subagents for distinct specialist work when needed, but keeps this sequence for the core roles.

Each handoff must include the artifacts and decisions from the previous role. Do not start a downstream role before its prerequisite role is done. Keep agents independent: each receives a bounded role prompt and returns a result; the coordinator owns sequencing, resolving conflicts, and user communication. Do not ask agents to edit the same files concurrently.

If subagent tools are unavailable in the current session, tell the user this workflow is configured but cannot be run in that session; do not silently perform the specialist roles as the coordinator.

## Shared rules

- Preserve the existing FastAPI, SQLAlchemy, Alembic, and pytest conventions.
- Keep changes scoped to the user's request. Read relevant files and callers before editing.
- Do not add dependencies or tests unless needed for the requested change. Run checks appropriate to the change and report what ran.
- Never expose secrets from `.env`; use `.env.example` for configuration examples.
- The reviewer is read-only. The docs agent edits documentation only, after review passes.
