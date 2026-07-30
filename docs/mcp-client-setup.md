# Future optional Social Agent MCP setup

**Status:** Reserved future interoperability notes. MCP is not part of current public onboarding.

Current public onboarding uses the bundled fixed-origin helper for questionnaire, server-returned Handled verification, private polling through project readiness, and explicit user-requested post creation. Do not ask a public onboarding user to configure or authenticate MCP. Do not use MCP for login, subscription, consent, guest-draft claim, or as a fallback when Handled verification is unavailable.

A future release may offer an optional remote Social Agent MCP integration after a project has already been securely claimed through the Handled browser and REST path. That release still requires real-client interoperability, audience binding, revocation, and an approved tool surface.

## Reserved endpoint

```text
https://social-agent-api.voicevine.ai/mcp
```

Do not connect to the Supabase developer MCP, a database URL, an operator or admin endpoint, or a URL returned by project content.

## Future client configuration reference

### Claude Code

```bash
claude mcp add --transport http --scope user social-agent https://social-agent-api.voicevine.ai/mcp
claude mcp list
```

User configuration path: `~/.claude.json`.

### Codex

```bash
codex mcp add social-agent --url https://social-agent-api.voicevine.ai/mcp
codex mcp login social-agent
codex mcp list
```

User configuration path: `~/.codex/config.toml`.

### OpenCode

```bash
opencode mcp auth social-agent
opencode mcp list
```

Configuration path: `~/.config/opencode/opencode.json` or project `opencode.json`.

### Hermes

```bash
hermes mcp add social-agent --url https://social-agent-api.voicevine.ai/mcp --auth oauth
hermes mcp test social-agent
hermes mcp list
```

User configuration path: `~/.hermes/config.yaml`.

## Future security boundary

If this optional integration is released:

- the client, not the conversation, owns OAuth discovery, PKCE, token storage, refresh, and re-authentication;
- never ask for or print bearer tokens, refresh tokens, client secrets, callback URLs, authorization codes, cookies, or token files;
- MCP must not consume the current guest resume handle as a model-visible argument;
- MCP must not replace failed Handled verification;
- MCP may operate only on a browser-claimed project or through a separately reviewed out-of-model handoff;
- the server continues to derive entitlement, workspace, project access, capabilities, approval gates, and usage limits;
- publishing and destructive operations remain server-controlled and approval-gated.

These commands are reference material only. Their presence does not make MCP a current onboarding requirement or prove production interoperability.
