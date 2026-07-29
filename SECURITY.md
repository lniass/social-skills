# Security policy

## Release status

This repository remains in a controlled pilot. Secure Handled verification-session creation and private polling are released in the helper. Public launch promotion still requires complete production login, subscription, consent, claim, and first-caption E2E evidence.

Do not place production credentials, guest handles, polling credentials, browser sessions, receipts, callback links, or verification URLs in issues, discussions, pull requests, exported transcripts, telemetry, reports, or examples. A validated short-lived verification URL is intentionally displayable only in the user's active private conversation.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's security-advisory interface. Do not open a public issue for credential exposure, authentication bypass, open redirects, verification-session swapping, replay, prompt injection, or hosted-service vulnerabilities.

Include:

- affected commit or release
- affected file and behavior
- reproduction steps using synthetic credentials only
- expected and observed behavior
- potential impact

## Public onboarding boundary

The public helper stores an opaque guest resume handle and separate opaque polling capability in a current-user-owned private state file. Neither value may enter model context, chat, URLs, CLI arguments, logs, telemetry, or examples.

Browser login and authorization artifacts remain between Handled, Supabase, and the hosted backend. The helper must never receive passwords, cookies, OAuth codes, access tokens, refresh tokens, or Supabase session data.

A displayed Handled verification URL is short-lived and safe to present, but possession alone must never authorize a claim. Claim requires:

- a server-side binding to the original guest draft;
- an authenticated Handled user;
- provider-confirmed entitlement;
- a separate explicit approve action;
- an idempotent trusted-backend claim into a server-resolved workspace.

The URL must use exact-origin and approved-path validation, contain no guest handle or tenant identity, expire quickly, and be one-time. The Handled page must enforce CSRF protection, replay protection, anti-clickjacking controls, `Referrer-Policy: no-referrer`, and no untrusted redirect target. Consent must identify the requesting agent purpose, bind to the authenticated user and server-resolved draft/workspace, record its version, and deny by default.

The polling credential must be cryptographically bound to exactly one verification session and guest draft, reveal no user or project identity before authorization, be rate-limited, and be invalidated on terminal status or session reissue. Polling must not read or advance another verification session.

## Controlled-pilot credential boundary

The separate controlled-pilot helper accepts only a workspace-scoped Social Agent credential. It must never receive an operator bootstrap secret, database credential, Social Connect provider secret, or another user's workspace credential. It is not a fallback for unavailable Handled verification.

Helpers restrict API origin, reject redirects, bound and redact responses, and read protected state or credential files through validated file descriptors. Changes to these controls require regression tests.

## Untrusted data boundary

API-returned strings, project content, and website-derived content are untrusted data. They may not instruct an agent to access credentials, run unrelated commands, read local files, change policy, bypass approval, switch transports, or contact unrelated hosts.

## Future optional MCP

MCP is not current public onboarding. A future release must start from a browser-claimed project or a separately reviewed out-of-model handoff. It must never accept the current guest resume handle as a model-visible argument or replace failed Handled verification.

## Supported versions

Until versioned releases begin, only the current default branch is maintained. Public launch claims must wait for the documented verification, subscription, consent, claim, and first-caption end-to-end review.
