# Guest questionnaire and Handled verification flow

## Purpose

The public Social Agent skill lets a new user complete the hosted questionnaire before login or payment. The public repository owns safe agent and helper behavior only. The hosted service owns question text, options, validation, branching, temporary guest state, identity, entitlement, consent, claim, and durable project state.

MCP is not part of current public onboarding.

## Current approved order

```text
guest helper starts or resumes the questionnaire
→ agent renders one server-returned question at a time
→ helper submits answers and preserves the private guest handle
→ questionnaire completes
→ helper creates a short-lived Handled verification session
→ agent displays the validated Handled verification URL
→ user logs in
→ user subscribes if needed
→ backend waits for provider-confirmed entitlement
→ user explicitly approves or denies agent access
→ helper polls privately
→ trusted backend atomically claims the guest draft
→ helper confirms the configured project
→ hosted service generates the first persisted caption
```

The agent must not ask the user to say `done`. Verification progresses through private helper polling and trusted server state only.

## Current helper commands

```bash
python3 scripts/guest_questionnaire.py resume
python3 scripts/guest_questionnaire.py start
python3 scripts/guest_questionnaire.py answer \
  --step-key '<server-returned-step-key>' \
  --answer-json '<JSON object matching the server-returned schema>'
python3 scripts/guest_questionnaire.py verify
python3 scripts/guest_questionnaire.py poll-verification
python3 scripts/guest_questionnaire.py forget
```

- `resume` reads the private local handle and asks the fixed production API for current state.
- `start` creates a guest draft only when no local state exists.
- `answer` submits one answer for the exact current server-returned step.
- `verify` creates or rotates one short-lived session, validates its exact Handled URL, and privately saves the polling capability.
- `poll-verification` sends only that private capability and returns bounded safe status, timing, and terminal caption fields.
- `forget` deletes local state only when the user explicitly discards the draft.

The helper stores the opaque resume handle at `${XDG_STATE_HOME:-$HOME/.local/state}/social-agent/guest-questionnaire.json` by default. It never prints that handle.

## Verification polling behavior

After `verify`, wait for its `retry_after_seconds` before calling `poll-verification`. Repeat automatically for `pending_login`, `pending_subscription`, `pending_entitlement_confirmation`, `pending_consent`, `claiming`, and `generating`. Do not ask the user for a chat acknowledgement. `caption_ready` returns the persisted caption and SHA-256 content hash, then clears private local state. `denied`, `expired`, and `failed` preserve the guest draft and stop safely. A later retry can run `verify` again without repeating the questionnaire.

## Verify your Handled account

When the released helper returns a validated verification action, the agent uses exactly this message:

> **Verify your Handled account**
>
> Click **Verify your Handled account** to sign in, subscribe if needed, and approve this agent to access your Social Agent project.
>
> [Verify your Handled account](SERVER_RETURNED_HANDLED_URL)
>
> Complete the steps in Handled. I will detect approval automatically. Do not paste passwords, codes, callback links, or tokens here.

The agent displays only the validated server-returned URL. It never constructs or modifies that URL.

## Subscription and consent behavior

- An already-entitled user proceeds from Handled login to the consent screen.
- A user without entitlement can purchase the required subscription in the same browser journey.
- Checkout success is not enough. The backend waits for authoritative provider-confirmed entitlement.
- Once entitlement is confirmed, the same browser flow advances to a separate explicit approve or deny action.
- Payment does not automatically grant agent access.
- After approval, the trusted backend performs the REST claim and updates verification status.
- The helper detects completion automatically. The user does not return to chat to say `done`.
- If billing confirmation is delayed, Handled shows a processing state while the helper continues bounded polling.
- Cancellation, denial, expiry, or failure preserves the guest draft until its normal expiry.

## Verification URL boundary

The displayed URL must be:

- HTTPS on the exact trusted Handled origin;
- short-lived and one-time;
- restricted to an approved verification path;
- free of userinfo, query strings, and unapproved ports;
- carrying exactly one bounded `gvd_` display capability in the URL fragment;
- bounded in length;
- free of guest resume tokens, polling credentials, OAuth tokens or codes, user IDs, workspace IDs, and tenant selectors.

Possession of the URL alone cannot authorize claim. The server must also verify the authenticated Handled user, authoritative entitlement, explicit consent, and the server-side binding to the original guest draft.

## Browser authorization and claim boundary

Handled and Supabase own browser login and session handling. The helper never receives passwords, cookies, callback URLs, authorization codes, access tokens, refresh tokens, or Supabase session material.

The helper stores only opaque guest and verification polling state in private local files. Polling credentials never appear in query strings, CLI arguments, stdout, stderr, logs, or chat. Polling accepts only a small fixed status set and bounded retry intervals.

A terminal claim is valid only when the server confirms the durable configured project. Private state is deleted only after that confirmation. Claim, replay, and continuation must be idempotent.

## Failure behavior

- Missing verification support: stop and preserve guest state.
- Pending login, subscription, entitlement confirmation, or consent: keep polling within server bounds.
- User denial or checkout cancellation: stop without claiming.
- Expired verification session: preserve the still-valid guest draft and offer a new server-created verification session when supported.
- Malformed status or missing configured-project proof: fail closed and preserve state.
- Network or server failure: do not infer success and do not switch transports.

## Future optional MCP

Remote MCP may later provide optional post-onboarding interoperability for supported agent clients. It is not the current verification, payment, consent, or guest-claim mechanism. It must start from a browser-claimed project or use a separate reviewed out-of-model handoff.
