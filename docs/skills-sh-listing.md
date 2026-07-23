# skills.sh listing draft

Use this copy for the public directory page, GitHub repo summary, and launch post.

Status: MCP-first public setup draft. The legacy API helper remains controlled-pilot only.

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
MCP-first workflows for authenticated onboarding, project updates, destination connection, and approval-gated social media operations.
```

## Longer description

Social Agent public workflows gives user-owned agents an MCP-first UX layer for hosted social media workflows. Claude Code, Codex, OpenCode, and Hermes connect to the product-specific remote Social Agent MCP endpoint, while each client manages OAuth tokens outside chat.

The skill teaches an agent how to:

- retrieve database-backed onboarding and update questions one at a time
- update audience, positioning, CTA, cadence, and pause intent
- guide Facebook Page connection through Social Connect
- inspect hosted recurrence status without inventing local configuration questions
- present approval batches before anything is scheduled
- refuse unsupported platform or autopilot behavior unless the hosted API enables it

The skill does **not** store state, credentials, OAuth codes, or questionnaire wording. It uses the hosted Social Agent MCP, whose service owns question text, options, questionnaire versions, answers, recurrence settings, usage caps, Social Connect proof, approval state, and scheduling intent records. It never exposes the Supabase developer MCP or arbitrary/admin tools.

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
OpenCode
Hermes
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
Use for MCP-first authenticated onboarding, project updates, destination connection, approvals, and recurrent-status checks.
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
- MCP-first authenticated state
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

That split makes the skill usable by multiple agent platforms without exposing database credentials, OAuth tokens or codes, Social Connect credentials, or scheduling internals. The controlled-pilot `sai_` helper remains a restricted fallback and is not used when MCP OAuth fails.

## Launch-readiness checklist for skills.sh

- [x] Public GitHub repo exists: `lniass/social-skills`.
- [x] Skill folder exists under `skills/social-agent-public-workflows/`.
- [x] `SKILL.md` has name and description frontmatter.
- [x] README has `npx -y skills@1.5.19 add lniass/social-skills` install command.
- [x] README explains source-of-truth boundary.
- [x] Skill does not include secrets.
- [x] Agent Skills CLI and complete-directory Hermes installations preserve the controlled-pilot helper.
- [x] Claude Code, Codex, OpenCode, and Hermes MCP setup paths are documented.
- [x] OAuth is client-managed outside chat and unauthenticated/re-authentication resume states are documented.
- [x] Confirmed the repo appears on skills.sh.
- [ ] Remove the controlled-pilot warning only after public activation and hosted readiness pass.
- [ ] Optional: add repo topics on GitHub: `agent-skills`, `social-media`, `marketing-automation`, `ai-agents`, `facebook-pages`.
