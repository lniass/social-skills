# Handling a user-supplied project image

Linked from `SKILL.md`. Covers the occasional case of an image the user attaches or references in chat — not part of the core create → approve → schedule flow.

## Flow: user-supplied project images

Treat an image attached in chat as private input. Never turn its filesystem path into a hosted URL, copy it into a project workspace, or use Shared-Hermes as storage. Use only the attachment path supplied by the agent runtime and the bundled helper.

If intent is absent, present exactly three numbered choices in one message:

1. Reusable visual library reference (recommends setting as a reference)
2. Exact future-post media (to bind to one specific post)
3. Background inspiration (for overall mood, theme, or backdrop guidance)

For natural-language intent, state the understood route and proceed without exposing internal table names. Exact future-post media must never enter the reusable visual library.

Reusable route:

```bash
python3 scripts/social_agent_api.py upload-visual --project-reference-id PROJECT_SLUG --image PRIVATE_ATTACHMENT_PATH --role style_example
python3 scripts/social_agent_api.py visual-assets --project-reference-id PROJECT_SLUG
```

The hosted worker analyzes the private image once. While status is `analyzing`, report that review is pending and poll with `visual-assets`. At `ready_for_review`, present the returned description, tags, best use, avoid use, and recommended kind. Do not activate without explicit confirmation. After confirmation, use one command:

```bash
python3 scripts/social_agent_api.py visual-lifecycle --project-reference-id PROJECT_SLUG --asset-id ASSET_ID --action activate --asset-kind reference
python3 scripts/social_agent_api.py visual-lifecycle --project-reference-id PROJECT_SLUG --asset-id ASSET_ID --action activate --asset-kind background
```

Use `--action archive` to remove a reusable image from future selection while preserving history. Treat this as "delete" in conversation: report it to the user as removed, and never show it again in a plain "list my reference images" answer. Archiving requires `--reason`, one of `user_requested` (the user asked to remove it), `superseded` (replaced by a better upload), `duplicate`, `quality_issue`, `no_longer_relevant`, or `other` -- pick the one that actually matches what the user said, defaulting to `user_requested` for a plain "delete this" with no further context. This reason is recorded for audit/traceability, not shown back to the user unless they ask why something was removed.

`visual-assets` always returns every status, including already-archived images -- the API does not filter, so the skill must. When answering "list my reference images" (or similar), show only `active` and `ready_for_review` entries; skip `archived` ones entirely. Only include archived entries if the user explicitly asks for history, deleted items, or "everything" -- and label them as archived when you do, together with why (from the recorded reason) if asked.

Exact future-post route:

```bash
python3 scripts/social_agent_api.py upload-post-media --project-reference-id PROJECT_SLUG --image PRIVATE_ATTACHMENT_PATH --role style_example
python3 scripts/social_agent_api.py post-media --project-reference-id PROJECT_SLUG
```

While lifecycle is `analyzing`, poll with `post-media`. At `ready_to_attach`, attach only after identifying the intended tenant-scoped content version:

```bash
python3 scripts/social_agent_api.py post-media-action --project-reference-id PROJECT_SLUG --asset-id ASSET_ID --action attach --content-version-id CONTENT_VERSION_ID
```

Then show the unchanged image with that post and use the normal separate post and media approval gates (Flow: approval, in `SKILL.md`). Use `--action archive` only before attachment when the user rejects the upload.
