# Updating project settings

Linked from `SKILL.md`. Covers standing changes to an existing project — a different domain from the core create → approve → schedule flow, and used far less often.

## Flow: update project (guided questionnaire fields)

Use this for a project field that the questionnaire itself owns (e.g. positioning, audience, cadence) — not for brand palette, typography, imagery rules, brand voice, or content pillars, which are a different mechanism covered next.

1. Read the current hosted update step.
2. Ask only the server-returned update question.
3. Submit the user's answer through the allowlisted hosted update operation.
4. Continue until hosted state confirms completion.
5. Summarize only server-confirmed changes.

Hosted state remains the source of truth.

## Flow: update visual style and other standing profiles

Use this when the user gives a standing instruction about a project's brand palette, typography, imagery rules, brand voice, or content pillars — phrased as a lasting preference ("from now on...", "always use...", "our brand voice should be...") rather than a one-off note about a single post. A one-off note about a single post belongs in that post's own revision instead (Copy review and copy gate, `regenerate_asset`'s `reason`, or `modify_asset`'s `instruction`, all in `SKILL.md`) — never write a standing profile change for something the user only wanted for one post.

This is `update_project_context`, a different mechanism from the guided update flow above: it replaces one whole profile in a single call, outside the questionnaire, and takes effect starting with the next batch generated after the call. Posts already generated keep the context they were approved under.

1. Read the contract before first use, and every time this flow runs after a version-check update, the same discipline as any other contract read in this skill:

   ```bash
   python3 scripts/social_agent_api.py job-contracts --job-type update_project_context
   ```

   Its `notes` name the exact keys each `profile_type` accepts — do not guess a key name or invent one, and do not carry a shape forward from a previous session without re-reading it.
2. Confirm which `profile_type` the user's instruction targets (most often `visual_rules` for anything about colors, look, or imagery). If ambiguous, ask rather than guess.
3. Submit `update_project_context` with that `profile_type` and a `content` object built only from the contract's documented keys for it.
4. This is a full replace, not a merge, and there is currently no way to read a profile's existing content back before overwriting it. If the user is changing only part of an existing profile (e.g. only the palette, not the typography or imagery rules) and has not stated the other fields in this conversation, say plainly that this update will replace the whole profile and ask the user to state the complete set of values, rather than guessing at or silently dropping a value they set previously.
5. Confirm back to the user in plain language what changed, without quoting the job type, field names, or raw JSON.

```bash
python3 scripts/social_agent_api.py create-job --job-type update_project_context \
  --project-reference-id PROJECT_SLUG --idempotency-key '<stable-operation-key>' \
  --inputs-json '{"profile_type":"visual_rules","content":{"palette":"...","typography":"...","imagery_rules":"...","avoid":"..."}}'
```

### Deriving visual_rules from an already-uploaded reference image

Use this when the standing instruction points at a specific reference image rather than describing a palette directly in words — "from now on, use the visual style of the karaoke reference," "match our reference image's colors going forward." This works even when that image was uploaded and activated in a past session: reference images are project state, not session state, and are retrievable regardless of which session uploaded them.

1. List the project's reference images:

   ```bash
   python3 scripts/social_agent_api.py visual-assets --project-reference-id PROJECT_SLUG
   ```

2. Match the user's description against every returned asset with `status` `active`, using its `display_name`, `vision_description`, and `visual_tags`. If more than one active asset plausibly matches, or none clearly does, ask the user to identify it rather than guessing — never derive a standing palette from the wrong image.
3. Build the `content` object from that asset's own `vision_description` and, when present, its `visual_analysis.reference_treatment` — never invent or paraphrase a palette from general impression. `reference_treatment` already states, for that specific image, what to carry forward (palette, composition, energy) and what not to copy (its literal subject matter); ground `content.palette` and `content.imagery_rules` in that language rather than composing new wording.
4. Present the derived `content` to the user in plain language before submitting — this still replaces the whole profile (step 4 above), so confirm it matches what they meant before calling `update_project_context`, the same as any other value in this flow.
