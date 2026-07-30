# skills.sh listing draft

Use this copy only after complete production Handled login, subscription, consent, claim, and first-caption E2E verification.

Status: guest-first public listing draft. Verification helper and hosted endpoints are implemented; browser E2E launch evidence remains pending. MCP is future optional interoperability, not public onboarding.

## Directory identity

```text
lniass/social-skills
```

## Primary install

```bash
npx -y skills@latest add lniass/social-skills
```

## Short title

```text
Social Agent public workflows
```

## One-line description

```text
Guest-first onboarding with secure Handled account verification, private helper polling, and approval-gated social media workflows.
```

## Longer description

Social Agent public workflows lets user-owned agents begin a server-owned questionnaire before login. A restricted helper preserves the opaque guest handle in private local state. After the questionnaire, it creates a secure verification session and returns only a validated short-lived Handled URL. The user logs in or subscribes and explicitly approves access in the browser. The helper polls privately while the backend verifies entitlement, claims the draft, and creates the first persisted caption.

The skill teaches an agent how to:

- retrieve database-backed onboarding and update questions one at a time
- preserve private acquisition state outside chat
- display the exact **Verify your Handled account** action
- avoid treating login or payment as agent authorization
- guide Facebook Page connection through Social Connect after project setup
- present approval batches before anything is scheduled
- refuse unsupported platform or autopilot behavior unless the hosted API enables it

The hosted Social Agent service owns question text, options, versions, answers, entitlement, claim, recurrence, usage caps, Social Connect proof, approval state, and scheduling intent. The skill never exposes guest handles, polling credentials, OAuth artifacts, the Supabase developer MCP, or arbitrary admin tools.

## Topics

```text
Marketing
Automation
Social Media
AI Agents
Content Workflows
Facebook Pages
Approval Workflows
```

## Agent tags

```text
Claude Code
Codex
OpenCode
Hermes
Generic Agent Skills
```

## Skill card

Name:

```text
social-agent-public-workflows
```

Description:

```text
Use for guest-first onboarding, secure Handled verification, hosted project workflows, destination connection, approvals, and recurrent-status checks.
```

## Screenshot copy

```text
Turn an AI agent into a guided Social Agent operator.

The skill keeps public workflows safe:
- guest-first questionnaire with private resume state
- server-returned Handled verification URL and private polling
- explicit access approval after entitlement confirmation
- Facebook Pages first
- database-backed questions only
- approval before scheduling
- no direct Supabase or Postiz access from the agent
```

## Repository boundary

```text
social-agent-orchestrator = hosted API and control plane
social-skills = public agent behavior wrapper
```

The controlled-pilot `sai_` helper is not a fallback for unavailable Handled verification. Remote MCP remains future optional post-onboarding interoperability.

## Launch-readiness checklist

- [x] Public GitHub repository exists.
- [x] Installable skill folder exists.
- [x] README includes the Agent Skills install command.
- [x] Skill contains no questionnaire copy or secrets.
- [x] Current onboarding no longer requires MCP or a user `done` message.
- [x] Exact **Verify your Handled account** copy is documented.
- [x] Deploy secure verification-session creation and polling endpoints.
- [x] Add reviewed helper commands and exact URL validation.
- [x] Remove the questionnaire-only release stop.
- [ ] Verify existing-subscription and new-subscription browser paths.
- [ ] Verify delayed entitlement confirmation and explicit consent.
- [ ] Verify automatic claim, configured project, and first persisted caption.
