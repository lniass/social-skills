# Installation and version check

Linked from `SKILL.md`. Packaging and update mechanics — not agent runtime behavior, only relevant when installing, updating, or troubleshooting the skill itself.

## Automatic version check

The bundled helper compares the installed `VERSION` file with the official `VERSION` file on the `main` branch of `lniass/social-skills`. It checks lazily before an API request only when the last successful check is at least six hours old. An API transport or HTTP failure may trigger another check after a separate thirty-minute failure cooldown. Repeated commands inside either interval do not contact GitHub.

When a newer official version exists, a standalone installed skill downloads the fixed official GitHub archive, verifies that it contains the complete skill and the expected version, preserves one previous copy, replaces the skill atomically, and re-runs the original command once. A failed check or failed installation leaves the working skill unchanged. Git checkouts are never self-replaced and must be updated with Git or the documented Skills CLI command.

Manual inspection and forced checking are available without exposing credentials:

```bash
python3 scripts/skill_updater.py status
python3 scripts/skill_updater.py check
```

## Install the skill

Agent Skills CLI:

```bash
npx -y skills@latest add lniass/social-skills
```

Hermes complete-directory install:

```bash
git clone --depth 1 https://github.com/lniass/social-skills.git
SKILL_DEST="${HERMES_HOME:-$HOME/.hermes}/skills/social-agent-public-workflows"
install -d "$SKILL_DEST"
rsync -a --delete social-skills/skills/social-agent-public-workflows/ "$SKILL_DEST/"
```

Update an Agent Skills CLI installation with:

```bash
npx -y skills@latest update social-agent-public-workflows -y
```

For the Hermes complete-directory method, pull the clone, rerun the `rsync --delete` command, and run `/reload-skills` or start a new session. This method requires `git` and `rsync`. Do not use a raw `SKILL.md` URL because it omits linked files.
