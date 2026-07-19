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

Primary Agent Skills install pattern, used by skills.sh examples:

```bash
npx skills add lniass/social-skills
```

Equivalent URL form for agents that prefer explicit GitHub URLs:

```bash
npx skills add https://github.com/lniass/social-skills
```

Direct Hermes install:

```bash
hermes skills install https://raw.githubusercontent.com/lniass/social-skills/main/skills/social-agent-public-workflows/SKILL.md
```

Manual/portable install for Claude Code, Codex-style agents, Cursor, Windsurf, or any agent that supports Agent Skills folders:

```bash
git clone https://github.com/lniass/social-skills.git
# Then add/select skills/social-agent-public-workflows/SKILL.md in the agent's skills UI or local skills directory.
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
