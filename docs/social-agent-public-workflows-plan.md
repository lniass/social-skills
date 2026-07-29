# Social skills public workflow plan

Status: scoped public-skill implementation plan. Current cross-repository priority and execution order are controlled by `social-agent-orchestrator/docs/plans/master-planning.md`. Current public onboarding is guest-first REST plus a future reviewed Handled verification-session handoff. MCP is future optional interoperability and is not part of current public onboarding.

## Product decision

Use one broad MVP skill:

```text
social-agent-public-workflows
```

Facebook-first is a capability and posture inside this broad workflow.

## Architecture split

### Orchestrator owns source of truth

- [x] Hosted API and control plane.
- [x] Database-backed questionnaire definitions and answer validation.
- [x] Guest start, resume, answer, and atomic REST claim foundations.
- [x] Project configuration, checklist routing, recurrence, approval, Social Connect proof, scheduling intent, and usage gates.
- [ ] Create a short-lived Handled verification session bound server-side to the private guest draft.
- [ ] Return only a narrow, one-time, model-displayable verification URL with no guest handle, OAuth artifact, user ID, workspace ID, or tenant selector.
- [ ] Implement browser login, subscription purchase when required, provider-confirmed entitlement, and explicit approve or deny consent.
- [ ] Have the trusted backend perform the idempotent REST claim after approval.
- [ ] Expose bounded safe verification polling states and configured-project confirmation.
- [ ] Trigger first-caption generation and status continuation after successful claim.

### Social skills owns agent behavior

- [x] Public workflow skill and fixed-origin guest helper.
- [x] No local onboarding or update question copy.
- [x] Private mode-`0600` guest state and strict fixed-origin behavior.
- [x] Select direct REST helper plus browser-based Handled authorization for current public onboarding.
- [x] Remove MCP setup, MCP OAuth, and MCP claim from current public onboarding.
- [x] Remove chat `done` from Handled verification.
- [x] Define the exact agent heading and message as **Verify your Handled account**.
- [x] Keep MCP documentation only as future optional post-onboarding interoperability.
- [x] Fail closed at questionnaire completion until secure verification creation and polling ship.
- [ ] Add reviewed `verify` and `poll-verification` helper commands after backend endpoint contracts are implemented.
- [ ] Validate the exact Handled HTTPS origin, approved path, expiry, and response shape before displaying a verification URL.
- [ ] Store polling credentials privately and never print them.
- [ ] Automatically poll without asking for `done`.
- [ ] Delete private guest and verification state only after server-confirmed claim and configured-project proof.
- [ ] Verify the complete Handled login, existing-subscription, new-subscription, delayed-entitlement, consent-denial, claim, and caption flow.

## Locked customer flow

```text
agent starts or resumes guest questionnaire through the fixed-origin helper
→ API returns one database-owned question at a time
→ helper submits answers and preserves the private guest handle
→ questionnaire completes
→ helper creates a secure Handled verification session
→ agent displays Verify your Handled account with the validated Handled URL
→ user logs in to Handled
→ user subscribes in the same browser journey if required
→ backend waits for provider-confirmed entitlement
→ Handled requires explicit agent-access approval
→ helper polls private server state automatically
→ trusted backend atomically claims the guest draft
→ helper observes configured-project proof
→ hosted generation creates the first persisted caption
```

The user does not say `done`. Payment alone does not grant agent access. Login, checkout, and entitlement confirmation advance the browser flow to a separate explicit consent action. Only the trusted backend can mark entitlement and claim complete.

## Exact agent message

> **Verify your Handled account**
>
> Click **Verify your Handled account** to sign in, subscribe if needed, and approve this agent to access your Social Agent project.
>
> [Verify your Handled account](SERVER_RETURNED_HANDLED_URL)
>
> Complete the steps in Handled. I will detect approval automatically. Do not paste passwords, codes, callback links, or tokens here.

## Security boundary

- The displayed URL is a narrow, short-lived, one-time capability, not tenant authority.
- Possession of the URL alone cannot authorize claim.
- The guest resume handle and polling credential remain outside model context.
- Handled and Supabase keep login sessions, cookies, OAuth codes, and tokens in browser and backend boundaries.
- The server binds verification session, guest draft, authenticated Handled user, confirmed entitlement, explicit consent, and claimed workspace.
- Claim and continuation are idempotent.
- Current public onboarding never falls back to MCP, static `sai_` credentials, direct Supabase, arbitrary HTTP, or a separate pricing URL.

## Current release boundary

The released helper supports only `start`, `resume`, `answer`, and `forget`. Until verification-session creation and polling are implemented and tested, the skill must stop after the guest questionnaire. This intentional stop prevents the old MCP onboarding path from being presented as current.

## Future optional MCP

Remote MCP OAuth remains a future post-onboarding interoperability phase. It may operate on a project already claimed through the Handled browser and REST path. It must not receive the guest resume handle as a model-visible argument and must not replace failed Handled verification.

## Public install

```bash
npx -y skills@1.5.19 add lniass/social-skills
```

Hermes complete-directory install:

```bash
git clone https://github.com/lniass/social-skills.git
SKILL_DEST="${HERMES_HOME:-$HOME/.hermes}/skills/social-agent-public-workflows"
install -d "$SKILL_DEST"
cp -R social-skills/skills/social-agent-public-workflows/. "$SKILL_DEST/"
```

Copy the complete `skills/social-agent-public-workflows/` directory. A raw `SKILL.md` URL omits linked files.
