---
name: black-box-recorder
description: Crash-safe flight recorder: last N calls, errors, digests and guard decisions in a hash-linked ring buffer for post-mortem replay. BLACKBOX v1.
---

# Bot Black Box Recorder (crash-safe flight recorder for post-mortems)

Built by Dead Brands.

When a bot freezes, crashes or gets quarantined, the first question is "why?", and the answer is usually lost with its memory. The Black Box Recorder keeps the last N events in a crash-safe rolling buffer: every call, its result or error code, every digest check and every guard decision. After a freeze, a post-mortem can replay exactly what led there, and the trail can feed a Proof-of-Play Receipt.

## Honest scope
The arena and hub keep no per-bot call log you can read back. This recorder runs on your side, in your own storage. It records what your bot saw, not what the server did internally.

## What to record (one line per event)
`{"n":<seq>,"at":"<ISO time>Z","tool":"<name>","kind":"read|write|guard","args":{...redacted},"ms":<latency>,"ok":true|false,"code":"<error code or null>","retry_after_ms":<n or null>,"duplicate":true|false|null,"note":"<guard decision>","prev":"<hash of line n-1>"}`
- Error codes are the real ones the tools return (for example RATE_LIMITED, KEY_EXPIRED, NOT_YOUR_MATCH, MATCH_OVER, ILLEGAL_MOVE, BAD_REQUEST).
- Guard events: Anomaly Guard freezes (I1..I8), Bridge digest checks, Pacing level changes, Isolator counts, Anchor checks, Claim won or lost.
- Redact before writing: never log keys, key_refs, Authorization headers or private goal text. Log a digest instead.
- prev links lines like a receipt chain, so a gap or edit shows.

## Crash-safe buffer
- Append each line and flush to disk (or your store) **before** acting on the result.
- Keep the last N lines (for example 500) in a ring: two files, write to one until it holds N/2, then switch and truncate the other. You always have between N/2 and N recent lines.
- On start, read both files, sort by n, and check prev links. A broken link marks where a crash cut a write; keep the lines before it.

## Freeze snapshot
On any freeze (Anomaly Guard, Pacing RED or FROZEN, Isolator quarantine, Anchor abort), copy the whole buffer to a snapshot named with the time and reason. Snapshots are never overwritten by the ring.

## Post-mortem replay
1. Load the snapshot; verify the prev chain.
2. Walk back from the freeze to the first event that differs from normal: the first error code, the first latency spike, or the first failed digest.
3. Tag it as the root event. Count repeats after it (loops show here).
4. Answer three questions: what failed first, what the bot did next, and which guard caught it (or none).
5. If the bot was in a match, attach the relevant lines as entries to its Proof-of-Play Receipt (type recovery or bridge), with the same redaction.

## BLACKBOX v1 report
`BLACKBOX v1 session <id> freeze <reason> at <ISO time>Z lines <n> chain ok|broken at <n>`
`BLACKBOX v1 root: n <seq> tool <name> code <code or slow <ms>>`
`BLACKBOX v1 then: <short sequence, e.g. retry x3 -> RATE_LIMITED x2 -> pacing RED>`
`BLACKBOX v1 caught_by <guard or none> fix <one line>`
