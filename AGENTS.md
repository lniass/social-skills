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
- On `JOB_INPUT_CONTRACT_VIOLATION`, the helper must expose only the server's safe message and allowlisted field-error keys, then fetch and print the exact contract for that job type. Do not leave an agent to guess another payload.
- Before pushing helper or skill behavior to `main`, review the diff, fix findings, run the orchestrator's relevant real-agent simulation against this checkout, and rerun it after any simulation-driven fix. This public repository has no separate production branch; production promotion belongs to the orchestrator release.
- Update helper commands, skill instructions, reference files, repository contracts, install completeness checks, and hosted API tests together.

## Skill size and progressive disclosure

Per Anthropic's Agent Skills guidance ([overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview), [best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)):

- Keep `SKILL.md`'s body under 500 lines (roughly 5,000 tokens). Claude loads the whole body into context the moment the skill triggers, so every line in it is a standing cost paid on every session that uses this skill, not a one-time one.
- When a workflow is occasional rather than part of the core create → approve → schedule path, move it to a `reference/*.md` file linked from `SKILL.md`, not into a second top-level skill. This skill's flows share bootstrap, auth, and project-resolution state across every path a user might take in one conversation; splitting into separate skills would fragment that state or duplicate the bootstrap logic in each one, where a reference file keeps it in one place while still keeping unused detail out of context until a task actually needs it.
- Keep reference files one level deep from `SKILL.md`: a reference file may point back to a `SKILL.md` section by name, but must never point to another reference file. Claude may only partially read a file reached through a second hop, which can silently truncate what it sees.
- Give any reference file over 100 lines a short contents note at the top.

Current split: `SKILL.md` holds the happy path (bootstrap check, onboarding, create → approve → schedule). `reference/visual-assets.md` (user-supplied images), `reference/updating-project-settings.md` (standing profile changes, including deriving one from a reference image), and `reference/installation.md` (packaging/version-check mechanics, not agent behavior) hold everything else.

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
