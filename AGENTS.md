# Social Skills repository guidance

## Purpose

Public, installable Social Agent behavior and restricted helper scripts. The hosted orchestrator API and database remain authoritative for product state and workflow decisions.

## Architecture rules

Canonical product workflow boundaries:

```text
Onboarding
→ questionnaire and project readiness

Post workflows
→ text, image, carousel, or video post requests
→ revisions and regeneration

Approval workflows
→ approve or reject exact content versions

Scheduling workflows
→ one-time publication
→ recurring publication
```

Recurring publication must reuse the one-time publication path and must not bypass exact-version approval, destination selection, idempotency, external submission, or reconciliation.

- Classify every new operation before choosing a file, route, or contract: onboarding, post creation, approval/revision, destination connection, or scheduling/recurrence.
- Keep `guest_questionnaire.py` limited to questionnaire progress, verification, and `project_ready`. It must not own content creation, media generation, approval, or scheduling commands.
- Keep reusable post intent in `post_workflows.py`. Post format, such as text, image, carousel, or video, is a request attribute or later extension, not a reason to return post creation to onboarding.
- Keep scheduling and recurrence separate from content creation. A post request creates content; a schedule request publishes an approved version once or repeatedly.
- Prefer intent-level names such as `create-post` and `post-requests`. Do not name reusable product operations after an onboarding position or current artifact, such as `create-first-caption`.
- A `guest` route qualifier describes temporary authentication/continuation transport, not product ownership. Keep the underlying operation reusable for a later authenticated route.
- Shared private capability and HTTP handling may be reused internally, but secrets must never enter chat, prompts, generic tool arguments, logs, or redirects.
- Update helper commands, skill instructions, repository contracts, install completeness checks, and hosted API tests together.

## The server owns every question

The hosted service is the only source of questionnaire and update questions:
their text, options, order, recommendation flags, help URLs, validation, and
completion state. This repository contains **no fallback question copy**, and an
agent must never ask a locally invented question.

This is enforced mechanically, not by convention. `tests/test_repository_contracts.py`
asserts that **no installable file contains a literal question mark** — every
`.md`, `.py`, `.json`, and `.yaml` under the skill directory. If a change fails
that assertion, the fix is to remove the question, not to relax the test.

Why it is enforced this way: a locally phrased question drifts from the server's
schema silently. It keeps rendering, the user keeps answering, and the answers
stop matching the step keys and field names the server validates — so the damage
shows up later, as rejected answers or a mis-configured project, far from the
copy that caused it. A blunt check that no installable file can contain a
question at all is the cheap way to keep that impossible.

Practical consequence: build query strings with `urlsplit`/`urlunsplit` rather
than concatenating a literal separator. That is better code anyway, since it
extends an endpoint that already carries a query instead of corrupting it.

The same reasoning covers prompts and confirmations. If an agent needs to ask
the user something, the wording belongs in `SKILL.md` as a behavioral rule
phrased as an instruction, or it comes from a server response.

## Verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q skills tests
git diff --check
```
