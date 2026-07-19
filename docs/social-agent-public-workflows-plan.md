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
- [ ] Database-backed questionnaire definitions.
- [ ] API job/endpoint for next onboarding/update question.
- [ ] API job/endpoint for submitting answers.
- [ ] API-backed update-project flow.
- [ ] API-backed recurrence settings for public projects.
- [ ] Recurrent planning run state moved from old file templates into hosted API/database.

### Social skills owns agent behavior

- [x] Public workflow skill exists.
- [x] Skill says API/database is source of truth.
- [x] Skill includes first-time onboarding behavior.
- [x] Skill includes update-project behavior.
- [x] Skill includes recurrent posting behavior.
- [x] Skill includes approval behavior.
- [x] Skill includes Hermes direct install command.
- [x] Add API contract reference once orchestrator endpoints are implemented: `social-agent-orchestrator/docs/plans/api-driven-questionnaire-contract.md`.
- [x] Add example JSON session once API response shape is final for MVP: `examples/onboarding-session.json`.
- [ ] Add optional registry/tap metadata if a target platform requires it.

## Runtime loop

```text
agent loads social-agent-public-workflows
→ agent calls orchestrator API for current state/question
→ API reads current questionnaire from DB
→ agent asks returned question
→ agent submits answer to API
→ API updates project state and returns next step
```

Skills must not directly read or write Supabase/Postiz.

## Recurrent posting product default

Recommended public MVP default:

```text
Plan every 2 weeks
Publish 3 Facebook posts per week
Prepare 6 posts per approval batch
Approval required before scheduling
```

Old repo traces used:

```text
frequency: daily
posts_per_run: 5
approval_mode: batch-required
```

Those old defaults remain useful for tests/history but should not be the default public product posture.

## Remaining implementation queue

1. Add questionnaire schema/table or reuse existing onboarding state if sufficient.
2. Add `get_next_question` and `answer_question` job types or equivalent endpoints.
3. Add update-project flow using the same question engine.
4. Add recurrence settings to hosted API/database.
5. Add recurrent planning job that prepares approval batches from API state.
6. Add API response examples to this repo under `examples/`.
7. Verify direct `hermes skills install <raw SKILL.md URL>` works on a clean profile.

## Public install commands

Primary Agent Skills install pattern, shown by skills.sh examples:

```bash
npx skills add lniass/social-skills
```

URL form:

```bash
npx skills add https://github.com/lniass/social-skills
```

Hermes direct install:

```bash
hermes skills install https://raw.githubusercontent.com/lniass/social-skills/main/skills/social-agent-public-workflows/SKILL.md
```

Portable manual fallback:

```bash
git clone https://github.com/lniass/social-skills.git
```

Then select/copy `skills/social-agent-public-workflows/SKILL.md` in the agent platform that supports skills folders.
