# social-skills

Reusable public skill packs for the Social Agent experience.

This repo is for agent behavior: what the agent asks, says, drafts, and enforces during onboarding/content workflows.

It complements `social-agent-orchestrator`:

- `social-agent-orchestrator`: hosted API, database-backed state machine, Supabase persistence, Social Connect proof, scheduling/usage gates.
- `social-skills`: installable agent behavior for public workflows. Skills call the orchestrator API for current questions/state. They do not replace the API or database.

## Current MVP skill pack

- `skills/social-agent-public-workflows/SKILL.md`

Public MVP supports Facebook Pages first. More platforms can be added later as API capabilities and workflow modules.

## Install

Direct Hermes install:

```bash
hermes skills install https://raw.githubusercontent.com/lniass/social-skills/main/skills/social-agent-public-workflows/SKILL.md
```

Future tap flow, once this repo has any required registry metadata:

```bash
hermes skills tap add https://github.com/lniass/social-skills
hermes skills install social-agent-public-workflows
```

## Source of truth

The orchestrator API/database owns:

- questionnaire versions
- current onboarding step
- answers collected
- validation rules
- recurrence settings
- approval status
- publication intents
- usage caps
- Social Connect state

This repo owns:

- agent conversation behavior
- public workflow instructions
- fallback/dev question examples
- approval wording
- Facebook-first public MVP guidance
