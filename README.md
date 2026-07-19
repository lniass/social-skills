# social-skills

Public Agent Skills for Social Agent workflows.

Install:

```bash
npx skills add lniass/social-skills
```

## What this gives an agent

`social-skills` turns a compatible AI agent into a guided Social Agent operator for Facebook-first social media workflows.

Current skill:

```text
social-agent-public-workflows
```

It teaches the agent how to:

- onboard a new social media project one question at a time
- update project audience, positioning, CTA, cadence, or pause intent
- guide Facebook Page connection through Social Connect
- configure recurring posting cadence
- present content batches for approval before scheduling
- avoid unsupported platforms or autopilot behavior unless the hosted API enables them

## Architecture

This repo is the **agent behavior layer**.

It complements the private hosted control plane:

```text
social-agent-orchestrator = hosted API, database state, Social Connect proof, scheduling/usage gates
social-skills = installable public agent behavior
```

The skill calls the orchestrator API for current state. It does **not** replace the API/database.

## Current MVP skill pack

```text
skills/social-agent-public-workflows/SKILL.md
```

Public MVP supports **Facebook Pages first**. More platforms can be added later as API capabilities and workflow modules.

## Install

Primary Agent Skills install pattern, used by skills.sh examples:

```bash
npx skills add lniass/social-skills
```

Equivalent URL form:

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
- current onboarding/update step
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

## Directory listing copy

A skills.sh-ready listing draft lives at:

```text
docs/skills-sh-listing.md
```

Recommended topics:

```text
agent-skills
social-media
marketing-automation
ai-agents
facebook-pages
approval-workflows
```
