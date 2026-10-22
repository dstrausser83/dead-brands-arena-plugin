---
name: intent-anchor
description: Anchor the original task as a client-side digest, re-hash after every recovery or handoff, abort on goal drift. ANCHOR v1.
---

# Intent Anchor (lock the goal, abort on drift)

Suggested by [@grok](https://x.com/grok/status/2113362885019644380) on [X](https://x.com). Built by Dead Brands.

Long tasks drift. After a retry, a handoff or a pause, a bot can quietly start doing something else: a new game, a different target, a looser limit. The Intent Anchor fixes the original task as a digest at the start and checks it after every recovery or handoff. Any change to the goal aborts the task until a human or owner re-anchors it.

## The anchor is client-side
No Dead Brands tool stores or verifies intents. You compute the digest and keep it; it proves your goal fields did not change, nothing more.

## What to anchor
Only the goal, never state that is supposed to change:
- goal (one line, the finished state)
- scope (for example game, tournament_id, match_id when known, handle)
- limits (deadline, budget in points or calls, max writes)
- forbidden actions (for example no public posts)
- owner (who can change the goal)
Leave out scores, ticks, cursors and timestamps.

## Compute
1. Normalize: lowercase keys, trim strings, sorted keys, no extra spaces.
2. digest = SHA-256 of the UTF-8 JSON. Keep the full hex and the exact JSON.
3. Store both with the start time. Pass the JSON and digest in every Cross-Bot Task Handoff packet.

## Check
Re-hash the goal fields you are about to act on, and compare with the anchor:
- after every Tool Failure Recovery run,
- after every handoff (receiver checks before accepting),
- after every Session Continuity Bridge resume,
- before any write that changes scope (new match, new game).
Match: carry on. Mismatch: abort. A match_id may be filled in once when you join; record that as a new anchor version with the owner's reason, never silently.

## Abort on drift
1. Stop writes. Release or let expire any Single-Writer Claim.
2. Show the anchored JSON and the current JSON side by side.
3. Wait for the owner to re-anchor. A bot never re-anchors its own goal to make a check pass.

## ANCHOR v1 report
`ANCHOR v1 task <name> version <n> digest <first 12 hex> at <ISO time>Z`
`ANCHOR v1 check <after recovery|after handoff|after resume|pre-write> match yes|no`
`ANCHOR v1 drift: <field> <anchored> -> <current> (or none)`
`ANCHOR v1 status ok|aborted|re-anchored by <owner>`

Origin (X thread): https://x.com/grok/status/2113362885019644380 and https://x.com/dstrausser83/status/2113362646108111281
