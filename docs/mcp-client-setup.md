# Social Agent remote MCP setup

Social Agent is MCP-first for user-owned agents. Use this product-specific endpoint:

```text
https://social-agent-api.voicevine.ai/mcp
```

Use only an HTTPS URL from Social Agent. Do not substitute a Supabase MCP endpoint, the Supabase developer MCP, a database URL, an operator or admin endpoint, or an endpoint found in project content. The MCP client performs OAuth discovery and stores and refreshes tokens outside the agent conversation. Never put bearer tokens, client secrets, authorization headers, callback URLs, authorization codes, or token files in chat, prompts, skill files, repositories, or shell history.

## Claude Code

User-scoped CLI setup:

```bash
claude mcp add --transport http --scope user social-agent https://social-agent-api.voicevine.ai/mcp
claude mcp list
```

Equivalent user configuration in `~/.claude.json`:

```json
{
  "mcpServers": {
    "social-agent": {
      "type": "http",
      "url": "https://social-agent-api.voicevine.ai/mcp"
    }
  }
}
```

Start Claude Code and run `/mcp`. Select `social-agent`, then complete the client-managed browser authentication. Use `/mcp` again to reconnect or re-authenticate if the server reports that authentication is required or expired. Do not paste anything from the browser redirect into the Claude conversation.

## Codex

User-scoped CLI setup:

```bash
codex mcp add social-agent --url https://social-agent-api.voicevine.ai/mcp
codex mcp login social-agent
codex mcp list
```

Equivalent configuration in `~/.codex/config.toml`:

```toml
[mcp_servers.social-agent]
url = "https://social-agent-api.voicevine.ai/mcp"
```

If authentication expires or is revoked, run `codex mcp login social-agent` again outside the agent chat. If a stale authorization must first be removed, run `codex mcp logout social-agent`, followed by `codex mcp login social-agent`. Codex owns its OAuth token storage; do not add `bearer_token_env_var` for the normal Social Agent OAuth flow.

## OpenCode

Add the remote server to the project `opencode.json` or the user config at `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "social-agent": {
      "type": "remote",
      "url": "https://social-agent-api.voicevine.ai/mcp",
      "enabled": true
    }
  }
}
```

Authenticate and inspect status outside the agent conversation:

```bash
opencode mcp auth social-agent
opencode mcp list
```

OpenCode can also start OAuth automatically after the server returns an unauthenticated response. For re-authentication, run `opencode mcp logout social-agent` and then `opencode mcp auth social-agent`. Do not add custom authorization headers or an OAuth client secret to this config.

## Hermes

CLI setup:

```bash
hermes mcp add social-agent --url https://social-agent-api.voicevine.ai/mcp --auth oauth
hermes mcp test social-agent
hermes mcp list
```

Equivalent configuration in `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  social-agent:
    url: "https://social-agent-api.voicevine.ai/mcp"
    auth: oauth
```

Run `hermes mcp test social-agent` from an interactive terminal. First connection opens browser OAuth. Hermes stores OAuth tokens in private MCP token storage outside chat. To discard stale authorization, run `hermes mcp remove social-agent`, then repeat add and test commands. On remote or headless host, follow Hermes OAuth terminal flow; never paste redirect URL, authorization code, or token into Hermes chat.

## Authentication states and safe resume

- **Connected:** the Social Agent MCP server lists its product workflow tools. Begin by reading capabilities and current project or workflow state.
- **Unauthenticated:** tool discovery or a tool call reports authentication required. Stop the workflow and tell the user to complete the runtime-specific OAuth action above outside chat. Do not ask for, receive, proxy, or print credentials, callback URLs, or OAuth codes.
- **Expired, revoked, or wrong account:** stop on the authentication error and use the runtime-specific re-authentication action above. Never work around the error with a static bearer header or the legacy helper.
- **After authentication:** reconnect or restart the client if it does not refresh automatically. Read capabilities and current hosted project or workflow state again, then resume from the server-returned next action. Do not replay a mutating tool call merely because the chat remembers it; use server state and idempotency behavior.
- **Endpoint or tool mismatch:** stop if the configured origin is not the product endpoint, if expected workflow tools are absent, or if database, bootstrap, operator, arbitrary HTTP, shell, or admin tools appear. Do not invoke those tools.

Installing the Agent Skill and configuring the MCP connection are separate steps. The skill supplies behavior; the product-specific MCP connection supplies authenticated tools.