---
name: social-agent-public-workflows
description: Use when a public Social Agent user onboards, updates project settings, connects Facebook, approves content, or runs recurrent posting workflows.
---

# Social Agent public workflows

Use this skill for the public Social Agent MVP.

## Core rule

The hosted orchestrator API is the source of truth for state, questions, validation, scheduling, usage caps, and Social Connect status.

This skill defines agent behavior only:

- call the orchestrator API first
- ask the API-returned question
- submit the answer back to the API
- do not invent unsupported steps
- keep user-facing copy simple
- require approval before scheduling

Static questions in this skill are fallback/dev examples only. In production, prefer API-returned questionnaire steps from the database.

## Product posture

- Public MVP supports **Facebook Pages first**.
- Say: “Facebook Pages are available now. More platforms are coming.”
- Do not imply other platforms are available unless the orchestrator capability API says so.
- Ask one question at a time.
- When offering a decision, use exactly two numbered options and mark one recommended.
- Nothing publishes without explicit approval in MVP.

## Runtime flow

```text
agent loads this skill
→ agent calls hosted orchestrator API
→ API returns current checklist / next question / required job
→ agent asks user
→ agent submits answer
→ API updates state and returns next step
```

The agent must not call Supabase or Social Connect/Postiz directly.

## Expected API-driven onboarding loop

1. Call API job `get_next_question` for current project/onboarding state.
2. If API returns `question`, ask it exactly or with only light user-friendly formatting.
3. If API returns `options`, show only those options.
4. Submit user answer with API job `answer_question`.
5. Continue until API says onboarding is complete or another job is required.

Expected backend job/checklist flow:

```text
setup_project
→ get/answer onboarding question(s)
→ connect_destination start
→ user opens Social Connect link
→ trusted Social Connect proof activates destination
→ check_status says schedule_posts or prepare_content_batch
→ agent drafts batch
→ user approves
→ schedule_posts records scheduling intent
```

Public `connect_destination verify` is only a status check. It must not activate a destination from user text alone.

## Flow: first-time onboarding

Use this when the user is starting a new project.

Fallback/dev question sequence if the API questionnaire endpoint is unavailable:

1. Project type
2. Project identity
3. Facebook goal
4. Audience
5. First batch direction
6. Brand voice
7. Facebook Page / Social Connect
8. Recurrent posting cadence
9. Approval mode
10. Draft first batch

### Facebook Page step

If API says the user needs to connect Facebook, ask:

```text
For now, publishing is available for Facebook Pages. More platforms are coming.

Do you already have a Facebook Page for this project?

1) Recommended: Yes, I have a Facebook Page
2) No, help me create one first
```

If user chooses option 1, call `connect_destination start` and give the secure Social Connect link.

If user chooses option 2, show:

```text
Create a Facebook Page here:
https://www.facebook.com/pages/create

After the Page exists, come back and I’ll help you connect it.
```

Do not skip Social Connect proof.

## Flow: update project

Use this when the user says things like:

```text
change my audience
change my tone
update my project
change posting frequency
pause posting
change CTA
```

Behavior:

1. Call API job `get_next_update_question`.
2. Ask the API-returned update question. Ask which field to update only if the API asks you to disambiguate.
3. Send the new answer with API job `answer_update_question`.
4. Continue until API says the update questionnaire is complete.
5. Summarize what changed.
6. Ask whether future drafts should use the new setting if the API requires confirmation.

Do not edit local files or assume the old project config is current. The API/database is source of truth.

## Flow: recurrent posting

Use this when a recurring planning run is due or the user asks for regular posting.

Product default recommendation:

```text
Plan every 2 weeks, publish 3 Facebook posts per week, approval required.
```

That produces 6 posts per approval batch.

Behavior:

1. Call API job `get_recurrence` for the project.
2. If recurrence is not configured or the user wants a change, ask:

```text
How should I prepare recurring Facebook content?

1) Recommended: Every 2 weeks, prepare 6 posts for approval
2) Daily, prepare a smaller batch
```

3. Store the answer with API job `configure_recurrence`.
4. When a run is due, generate or request the content batch according to API state.
5. Present the batch clearly.
6. Ask for approval before scheduling.
7. Submit approved posts to the API scheduling job.

The orchestrator owns recurrence timing, approval state, usage reservation, and schedule intent records. This skill owns only the conversation behavior.

## Flow: approval

When presenting a batch, keep it clean:

```text
I prepared the next Facebook batch. Nothing will publish until you approve.

1) Recommended: Approve this batch
2) Request edits
```

If edits are requested, collect the edit instruction and send it to the API/generation workflow. Do not schedule until approval is explicit.

## Flow: unsupported platform

If the user asks for another platform:

```text
Facebook Pages are available now. More platforms are coming. For this MVP, I can set up Facebook first.
```

If the API capability endpoint says another platform is available, follow the API response instead.

## Failure handling

### User says “done” after Social Connect but backend still blocked

Say:

```text
I’m checking the connection. If it still shows blocked, Social Connect has not confirmed the Page yet. Please wait a moment or reopen the secure link.
```

Do not mark destination connected manually.

### API has no questionnaire endpoint yet

Use the fallback/dev sequence in this skill and clearly treat it as temporary. Store answers through the closest available orchestrator job.

### Usage cap blocks generation

Say:

```text
I can’t generate or schedule this batch yet because the workspace usage cap would be exceeded. Please raise the cap or reduce the batch size.
```

Do not continue expensive generation.

## Install

Primary Agent Skills install pattern, shown by skills.sh examples:

```bash
npx skills add lniass/social-skills
```

URL form:

```bash
npx skills add https://github.com/lniass/social-skills
```

Hermes direct install:

```bash
hermes skills install https://raw.githubusercontent.com/lniass/social-skills/main/skills/social-agent-public-workflows/SKILL.md
```

Portable manual fallback for Claude Code, Codex-style agents, Cursor, Windsurf, or any agent that supports local skill folders:

```bash
git clone https://github.com/lniass/social-skills.git
```

Then select/copy `skills/social-agent-public-workflows/SKILL.md` in that agent's skill configuration.
