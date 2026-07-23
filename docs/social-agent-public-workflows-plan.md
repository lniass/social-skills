# Social skills public workflow plan

Status: active plan.

## Product decision

Use one broad MVP skill:

```text
social-agent-public-workflows
```

Not a narrow `facebook-first-public-onboarding` skill.

Reason: the public agent must handle onboarding, project updates, Facebook connection, recurrent posting, and approval behavior. Facebook-first is a capability/posture inside the workflow, not the whole skill identity.

## Architecture split

### Orchestrator owns source of truth

- [x] Hosted API/control-plane exists.
- [x] Checklist routing exists.
- [x] Social Connect trusted proof exists.
- [x] Scheduling intent boundary exists.
- [x] Usage/cost cap reserve gate exists.
- [x] Database-backed questionnaire definitions.
- [x] API job/endpoint for next onboarding question.
- [x] API job/endpoint for submitting answers.
- [x] API-backed update-project flow.
- [x] API-backed recurrence settings for public projects.
- [ ] Recurrent planning run state moved from old file templates into hosted API/database.

### Social skills owns agent behavior

- [x] Public workflow skill exists.
- [x] Skill says API/database is source of truth.
- [x] Remove all local onboarding and update question copy; questions and options come only from database-backed API responses.
- [x] Skill includes first-time onboarding behavior.
- [x] Skill includes update-project behavior.
- [x] Skill includes recurrent posting behavior.
- [x] Skill includes approval behavior.
- [x] Skill includes a complete-directory Hermes install command that preserves linked scripts.
- [x] Add API contract reference once orchestrator endpoints are implemented: `social-agent-orchestrator/docs/plans/api-driven-questionnaire-contract.md`.
- [x] Add an API-driven example JSON session without hardcoded questionnaire wording: `examples/onboarding-session.json`.
- [x] Add a dependency-light API helper for capabilities, project listing, job creation, and job-status reads.
- [x] Read workspace credentials from environment or a protected file without exposing operator bootstrap.
- [x] Add helper tests for authentication headers, request shape, HTTPS policy, file permissions, and redaction.
- [x] Make the public user-owned-agent path guest-first, followed by client-managed MCP OAuth outside chat.
- [x] Document exact Claude Code, Codex, OpenCode, and Hermes remote MCP setup and re-authentication paths.
- [x] Preserve the `sai_` helper only as a controlled-pilot fallback without weakening its job allowlist.
- [x] Add a fixed-origin guest helper with private mode-`0600` resume state and no Authorization header.
- [x] Add start, resume, answer, and forget behavior without local questionnaire copy.
- [x] Add guest helper security, redirect, response-bound, state-file, and mock-server tests.
- [x] Treat `done` only as the trigger for MCP setup/OAuth, never as entitlement proof.
- [x] Preserve guest state until authenticated claim and configured-project confirmation.
- [ ] Verify the hosted authenticated MCP claim consumes the local guest handoff without exposing the resume token or OAuth token.
- [ ] Verify the hosted completed response includes a personalized plan preview and trusted Handled conversion action.
- [ ] Add optional registry/tap metadata if a target platform requires it.

## Runtime loop

```text
agent loads social-agent-public-workflows
→ guest helper starts or resumes temporary server state
→ API reads the current questionnaire from DB
→ agent asks returned question
→ guest helper submits the answer
→ API updates guest state and returns the next step or plan preview
→ user completes Handled conversion and returns with `done`
→ MCP client performs OAuth outside chat
→ hosted entitlement and claim materialize the configured project
→ hosted generation creates the first persisted caption
```

Skills must not directly read or write Supabase/Postiz and must never expose the Supabase developer MCP. The only pre-authentication HTTP lane is the bundled fixed-origin guest helper. Authenticated agents use only the product-specific Social Agent MCP; OAuth tokens remain in the MCP client outside chat.

## Recurrent posting source of truth

The hosted API/database owns recurrence state, defaults, validation, and any questions used to change recurrence. This repository contains no local recurrence question or fallback default. The current controlled-pilot skill can read recurrence and status, but recurrent planning remains incomplete and must not be marketed as production-ready.

## Remaining implementation queue

1. Add questionnaire schema/table or reuse existing onboarding state if sufficient. ✅
2. Add `get_next_question` and `answer_question` job types or equivalent endpoints. ✅
3. Add update-project flow using the same question engine. ✅
4. Add recurrence settings to hosted API/database. ✅
5. Add recurrent planning job that prepares approval batches from API state.
6. Add API response examples to this repo under `examples/`. ✅
7. Verify a clean Agent Skills CLI install contains both `SKILL.md` and the helper. ✅
8. Verify the complete-directory Hermes installation contains both files and the helper runs. ✅

## Public install commands

Primary Agent Skills install pattern, shown by skills.sh examples:

```bash
npx -y skills@1.5.19 add lniass/social-skills
```

URL form:

```bash
npx -y skills@1.5.19 add https://github.com/lniass/social-skills
```

Hermes complete-directory install:

```bash
git clone https://github.com/lniass/social-skills.git
SKILL_DEST="${HERMES_HOME:-$HOME/.hermes}/skills/social-agent-public-workflows"
install -d "$SKILL_DEST"
cp -R social-skills/skills/social-agent-public-workflows/. "$SKILL_DEST/"
```

Portable manual fallback:

```bash
git clone https://github.com/lniass/social-skills.git
```

Install or copy the complete `skills/social-agent-public-workflows/` directory in the target platform. Copying only `SKILL.md` omits the helper and is unsupported.
