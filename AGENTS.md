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

## Verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q skills tests
git diff --check
```
