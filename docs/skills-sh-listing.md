# skills.sh listing draft

Use this copy for the public directory page, GitHub repo summary, and launch post.

## Directory identity

```text
lniass/social-skills
```

## Primary install

```bash
npx skills add lniass/social-skills
```

## Short title

```text
Social Agent public workflows
```

## One-line description

```text
API-driven agent workflows for onboarding, updating, scheduling, and approving Facebook-first social media projects.
```

## Longer description

Social Agent public workflows gives AI coding/chat agents a safe public UX layer for social media automation.

The skill teaches an agent how to:

- onboard a new social media project one question at a time
- update audience, positioning, CTA, cadence, and pause intent
- guide Facebook Page connection through Social Connect
- configure recurring posting cadence
- present approval batches before anything is scheduled
- refuse unsupported platform or autopilot behavior unless the hosted API enables it

The skill does **not** store state itself. It calls a hosted Social Agent Orchestrator API, which owns questionnaire versions, answers, recurrence settings, usage caps, Social Connect proof, approval state, and scheduling intent records.

## Best-fit topics

```text
Marketing
Automation
Social Media
AI Agents
Content Workflows
Facebook Pages
Approval Workflows
```

## Best-fit agent tags

Use whichever tags the directory supports:

```text
Claude Code
Codex
Cursor
Windsurf
GitHub Copilot
Cline
Goose
Generic Agent Skills
```

## What should appear on the directory page

### Skills count

```text
1 skill
```

### Skill card

Name:

```text
social-agent-public-workflows
```

Description:

```text
Use when a public Social Agent user onboards, updates project settings, connects Facebook, approves content, or runs recurrent posting workflows.
```

### Install command

```bash
npx skills add lniass/social-skills
```

### GitHub link

```text
https://github.com/lniass/social-skills
```

## Screenshot/preview copy

```text
Turn an AI agent into a guided Social Agent operator.

The skill keeps public workflows safe:
- API-first state
- Facebook Pages first
- one question at a time
- approval before scheduling
- no direct Supabase/Postiz access from the agent
```

## Why this is listed as a skill repo, not a standalone app

`social-skills` is the installable agent behavior layer. It is intentionally small and portable.

The private backend remains separate:

```text
social-agent-orchestrator = hosted API/control plane
social-skills = public agent behavior wrapper
```

That split makes the skill usable by multiple agent platforms without exposing database credentials, Social Connect credentials, or scheduling internals.

## Launch-readiness checklist for skills.sh

- [x] Public GitHub repo exists: `lniass/social-skills`.
- [x] Skill folder exists under `skills/social-agent-public-workflows/`.
- [x] `SKILL.md` has name and description frontmatter.
- [x] README has `npx skills add lniass/social-skills` install command.
- [x] README explains source-of-truth boundary.
- [x] Skill does not include secrets.
- [x] Skill is platform-neutral: Hermes, Claude/Codex-style folder agents, Cursor/Windsurf-style agents.
- [ ] Confirm the repo appears on skills.sh after the CLI/directory indexes it.
- [ ] Optional: add repo topics on GitHub: `agent-skills`, `social-media`, `marketing-automation`, `ai-agents`, `facebook-pages`.
