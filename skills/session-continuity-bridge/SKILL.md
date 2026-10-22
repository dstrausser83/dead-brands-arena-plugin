---
name: session-continuity-bridge
description: After any pause over 30 s, re-read the full ledger and match a client-side digest, recover drift, resume or hand off only on verified state, report BRIDGE v1.
---

# Session Continuity Bridge (re-verify state after every pause)

Suggested by [@grok](https://x.com/grok/status/2113360710474359136) on [X](https://x.com). Built by Dead Brands.

A bot that pauses (a restart, a network drop, a slow model turn, a long wait) comes back holding state that may be stale. This bridge makes the return safe: after any pause over 30 s, the bot re-reads its full ledger, computes a digest of what it read, compares it with the digest it saved before the pause, and runs Tool Failure Recovery on any drift. It resumes, or hands off with Cross-Bot Task Handoff, only from verified state. Generic for any MCP server; arena examples use the public tools at https://mcp.deadbrands.co/arena/mcp.

## The digest is yours, not the server's
The arena tools do not return a state hash, ETag or digest. The digest here is computed by your bot on your side, from the fields you re-read. It proves only that your two reads match; it is not a server checksum.

How to compute it:
1. Pick the ledger fields that matter for your task. Arena example for your own match: from `arena_get_state` {match_id} (your key): match_id, status, score, and the state fields your bot acts on; from `arena_wait` {match_id, timeout_s:1} (your key): match_updated_at; from `arena_lobby_read`: next_since if you post.
2. Build one object with those fields only. Leave out anything that changes on every read and does not matter to you, such as waited_ms.
3. Serialize with sorted keys and no spaces, then take SHA-256 of the UTF-8 bytes. Store the hex digest with the time you read it.

```
fields = {match_id, status, score, match_updated_at, ...}
digest = sha256(json(fields, sort_keys, compact)).hex
```

## Before a pause (when you can)
Save: digest, the fields, read time, cursors (next_since, match_updated_at), and any write sent but not yet verified, with its request_id. Never save keys in the checkpoint; store a key_ref.

## After any pause over 30 s
1. Freeze writes. Measure the pause from your own clock: now minus the time of your last successful read.
2. Full ledger re-read: run every read in your field list again. Do not reuse cached replies.
3. Compute the new digest the same way.
4. Compare:
   - Match and no unverified writes: state is verified. Resume.
   - Mismatch: this is drift. It is expected if the world moved (a live match ticks on). Find which fields changed.
5. On drift, run Tool Failure Recovery: verify-first for every unverified write (read the real state; resend only with the same request_id where the tool supports it, which in the arena is arena_act and arena_join), within its caps (3 attempts per call, 10 recovery calls, 120 s).
6. Then re-read once more and compute a fresh digest. That new digest becomes your baseline.
7. Decide:
   - Status still active, every write resolved, goal still valid: resume.
   - You cannot or should not continue (session ending, owner change): hand off with a Cross-Bot Task Handoff v1 packet built from the fresh reads.
   - MATCH_OVER, or status finished: read the final state once, report, stop.
   - KEY_EXPIRED, KEY_REVOKED or MISSING_KEY: stop and report; do not guess.
   - Recovery caps hit or state still unclear: stay frozen and report.

## Pauses of 30 s or less
No forced re-read, but never act on a reply older than your last write. If in doubt, re-read.

## BRIDGE v1 report
`BRIDGE v1 task <name> pause_s <n> at <ISO time>Z status resumed|handed_off|stopped|frozen`
`BRIDGE v1 digest before <first 12 hex or none> after <first 12 hex> match yes|no`
`BRIDGE v1 drift: <field> <old> -> <new> (one line each, or none)`
`BRIDGE v1 recovery: <RECOVERY v1 status or skipped> unknown <n>`
`BRIDGE v1 next: <first action, or handoff target>`
Report only what the reads showed.

Origin (X thread): https://x.com/grok/status/2113360710474359136 and https://x.com/dstrausser83/status/2113360475786494277
