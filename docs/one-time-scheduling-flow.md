# One-time scheduling flow

## Canonical boundary

```text
Onboarding
→ questionnaire and project readiness

Post workflows
→ text, image, carousel, or video post requests
→ revisions and regeneration

Approval workflows
→ approve or reject exact content versions

Scheduling workflows
→ one-time publication
→ recurring publication
```

The controlled-pilot scheduling helper handles only one-time publication intent. It requires an explicitly provisioned workspace-scoped Social Agent credential and is not yet a released guest/public continuation path. Recurring publication is deferred and must reuse the same approval, destination, idempotency, submission, and reconciliation path.

## Preconditions

The hosted service must return all of the following before the helper may run:

- an authenticated project reference;
- one exact approved content-version ID and lowercase SHA-256 content hash;
- one active, explicitly selected, server-verified Social Connect destination ID;
- an explicit user-confirmed timezone-aware future publication time;
- one stable idempotency key for that unchanged operation.

Do not derive IDs from display names. Do not choose the first destination. Do not reuse guest questionnaire capabilities. Do not call Postiz directly.

## Command

From the installed skill directory:

```bash
python3 scripts/scheduling_workflows.py schedule-one \
  --project-reference-id 'project-reference' \
  --content-version-id 'server-returned-uuid' \
  --content-hash 'server-returned-lowercase-sha256' \
  --destination-id 'server-returned-destination-uuid' \
  --publish-at '2026-08-01T09:00:00-04:00' \
  --idempotency-key 'stable-one-time-operation-key' \
  --confirm-user-schedule
```

The helper refuses to call the API without `--confirm-user-schedule`. It validates UUIDs, hash shape, project reference, idempotency-key shape, and a timezone-aware future time before sending one authenticated `schedule_posts` request.

## Truthful states

The current controlled-pilot result is only:

```text
intent_recorded
```

This means the hosted control plane accepted the exact local publication intent. It does **not** mean Social Connect accepted a schedule, and it does not mean the post was published.

Future states require server evidence:

- `externally_scheduled`: confirmed Social Connect acceptance and external schedule reference.
- `reconciliation_required`: provider outcome is ambiguous; lookup is required before any resubmission.
- `published`: reconciled external post evidence and actual publication time.
- `failed`: terminal provider or policy failure.

Never infer external scheduling from job acceptance, a local publication ID, or a `pending` publication row. Never infer publication from elapsed time.

## Media direction

Text-only posts remain valid when the approved post version does not require media. When an image is requested or project policy later defaults to images:

- use the project’s approved tenant-scoped asset profile and reference images by default;
- use provider-supported reference editing or image-to-image generation, not programmatic redraw;
- preserve regeneration and revision history;
- schedule only the exact approved rendered rendition version/checksum;
- fail closed rather than substituting a simulated specification or placeholder.

## Current limitation

The hosted service currently records the local intent only. External Social Connect submission, lookup, and reconciliation remain server-side implementation work. Do not present this helper as a working external scheduler until those provider-confirmed stages are released and tested.
