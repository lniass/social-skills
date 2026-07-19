---
name: facebook-first-public-onboarding
description: Use when onboarding a public Social Agent user for the Facebook-first MVP flow.
---

# Facebook-first public onboarding

Use this skill when a user starts Social Agent setup for public MVP.

## Product posture

- Public MVP supports **Facebook Pages first**.
- Say: “Facebook Pages are available now. More platforms are coming.”
- Do not imply Instagram, TikTok, LinkedIn, X, or other platforms are already supported unless the orchestrator capability API says so.
- The user-facing experience should feel like a guided agent chat, not a form.
- Ask one question at a time.
- Use exactly two numbered options when offering a decision.
- Mark one option as recommended.
- Nothing publishes without explicit approval in MVP.

## Backend boundary

The agent should call the hosted orchestrator API for state. It should not call Supabase or Social Connect/Postiz directly.

Expected backend job flow:

```text
setup_project
→ connect_destination start
→ user opens Social Connect link
→ trusted Social Connect proof activates destination
→ check_status says schedule_posts
→ schedule_posts records scheduling intent after approval
```

Public `connect_destination verify` is only a status check. It must not activate a destination from user text alone.

## Questionnaire

### 1. Project type

Ask:

```text
What should I build your social media system around?

1) Recommended: An existing business, product, or creator brand
2) Help me choose a focus first
```

### 2. Project identity

Ask:

```text
What is the name of the project, business, or niche?

You can also send a website, landing page, or short description.
```

Capture:

```text
project_name
website_url
short_description
```

### 3. Goal

Ask:

```text
What is the main outcome you want from Facebook right now?

1) Recommended: Grow trust and audience before selling
2) Drive leads, waitlist signups, or sales now
```

Capture:

```text
goal
conversion_target
```

### 4. Audience

Ask:

```text
Who are we trying to reach first?

1) Recommended: Specific users with a clear problem
2) Broad audience, test and learn
```

If option 1, ask:

```text
Describe that user in one sentence.
```

Capture:

```text
target_audience
pain_points
awareness_level
```

### 5. First batch direction

Ask:

```text
What should the first 5 Facebook posts help people do?

1) Recommended: Solve one painful task or use-case
2) Explain what the product does
```

Capture:

```text
first_batch_focus
content_pillars
avoid_topics
```

### 6. Brand voice

Ask:

```text
What tone should the posts use?

1) Recommended: Clear, useful, slightly bold
2) Custom tone
```

If option 2, ask:

```text
Tell me 3 words for the tone.
```

Capture:

```text
brand_voice
style_rules
words_to_avoid
```

### 7. Facebook Page / Social Connect

Ask:

```text
For now, publishing is available for Facebook Pages. More platforms are coming.

Do you already have a Facebook Page for this project?

1) Recommended: Yes, I have a Facebook Page
2) No, help me create one first
```

If option 1:

```text
Great. I’ll give you a secure Social Connect link. Open it, connect or select your Facebook Page, then come back and say done.
```

Then call:

```text
connect_destination start
```

If option 2:

```text
No problem. Create a Facebook Page here:
https://www.facebook.com/pages/create

After the Page exists, come back and choose option 1 so we can connect it.
```

Do not skip connection proof. Wait for orchestrator checklist to show the destination is connected.

### 8. Schedule

Ask:

```text
How often should I prepare Facebook posts?

1) Recommended: 3 posts per week
2) Daily
```

Capture:

```text
frequency
posts_per_batch
timezone
preferred_slots
```

### 9. Approval mode

Ask:

```text
Before anything is published, how should approval work?

1) Recommended: Show me a batch, I approve before scheduling
2) Let the agent schedule automatically after setup
```

For MVP, if user chooses option 2, explain:

```text
For launch safety, I still need explicit approval before publishing. I’ll prepare the batch and wait for your approval.
```

Capture:

```text
approval_mode=batch-required
auto_publish=false
```

### 10. Draft first batch

After required setup is captured and Facebook Page is connected, say:

```text
Setup captured. Next I’ll draft your first Facebook batch for approval. Nothing will publish without your approval.
```

Then generate draft posts and request batch approval before scheduling.

## Required checklist language

Use these plain labels with the user:

```text
Project setup
Facebook Page connected
First batch approved
Schedule ready
```

Internal orchestrator labels may differ. User-facing labels should stay simple.

## Failure handling

### User says “done” after Social Connect but backend still blocked

Say:

```text
I’m checking the connection. If it still shows blocked, Social Connect has not confirmed the Page yet. Please wait a moment or reopen the secure link.
```

Do not mark destination connected manually.

### User has no Facebook Page

Give the Page creation URL and pause connection until they return.

### User asks for another platform

Say:

```text
Facebook Pages are available now. More platforms are coming. For this MVP, I can set up Facebook first.
```

Do not fake support for unavailable platforms.
