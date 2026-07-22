# skills.sh listing draft

Use this copy for the public directory page, GitHub repo summary, and launch post.

Status: controlled-pilot draft only. Do not use as unrestricted public-launch copy until hosted readiness, credential activation, and the public-release review are complete.

## Directory identity

```text
lniass/social-skills
```

## Primary install

```bash
npx -y skills@1.5.19 add lniass/social-skills
```

## Short title

```text
Social Agent public workflows
```

## One-line description

```text
Controlled-pilot API workflows for onboarding, project updates, destination connection, and approval-gated social media operations.
```

## Longer description

Social Agent public workflows gives compatible agents a controlled-pilot UX layer for hosted social media workflows.

The skill teaches an agent how to:

- retrieve database-backed onboarding and update questions one at a time
- update audience, positioning, CTA, cadence, and pause intent
- guide Facebook Page connection through Social Connect
- inspect hosted recurrence status without inventing local configuration questions
- present approval batches before anything is scheduled
- refuse unsupported platform or autopilot behavior unless the hosted API enables it

The skill does **not** store state or questionnaire wording itself. It calls a hosted Social Agent Orchestrator API, which owns question text, options, questionnaire versions, answers, recurrence settings, usage caps, Social Connect proof, approval state, and scheduling intent records.

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
Use for controlled-pilot API-driven onboarding, project updates, destination connection, approvals, and recurrent-status checks.
```

### Install command

```bash
npx -y skills@1.5.19 add lniass/social-skills
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
- database-backed questions only
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
- [x] README has `npx -y skills@1.5.19 add lniass/social-skills` install command.
- [x] README explains source-of-truth boundary.
- [x] Skill does not include secrets.
- [x] Agent Skills CLI and complete-directory Hermes installations preserve the helper.
- [x] Confirmed the repo appears on skills.sh.
- [ ] Remove the controlled-pilot warning only after public activation and hosted readiness pass.
- [ ] Optional: add repo topics on GitHub: `agent-skills`, `social-media`, `marketing-automation`, `ai-agents`, `facebook-pages`.
