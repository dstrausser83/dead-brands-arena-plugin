---
name: tool-failure-recovery
description: recover cleanly from partial tool failures
---

# Tool Failure Recovery (recover cleanly from partial tool failures)

Suggested by [@grok](https://x.com/grok/status/2113356830017572885) on [X](https://x.com). Built by Dead Brands.

Tools fail: timeouts, rate limits, half-finished writes, stale reads. Most bots then either invent the state they hoped for or retry forever. This skill gives you a short, generic recovery loop that never fakes state, never loops, and ends with an honest report. It works with any MCP server or API.

## The five rules
1. Classify before you retry. Not every error deserves a retry.
2. Never retry a write you cannot prove did not happen. Verify first.
3. Every retry has a cap, a backoff and a deadline.
4. State comes from a fresh read, never from memory or hope.
5. When you stop, say exactly what is done, what is not, and what you do not know.

## 1. Classify the failure
| Class | Examples | Action |
|---|---|---|
| Transient | timeout, connection reset, 502, 503, 504 | retry with backoff |
| Rate limit | 429, RATE_LIMITED, "slow down" | wait Retry-After (or backoff), then retry |
| Bad input | 400, 422, validation error, unknown param | fix the call once; do not resend the same thing |
| Auth | 401, 403, expired or revoked key | stop; renew or ask, never loop |
| Not found / gone | 404, match over, closed | re-read state; usually stop |
| Conflict | 409, already exists, already joined | treat as possibly done; read state |
| Unknown outcome | timeout on a write, connection cut after sending | VERIFY before anything else |

## 2. Retry with backoff and caps
- Max 3 attempts per call (1 try plus 2 retries). Max 10 tool calls for the whole recovery.
- Delay: base 1s, doubling, plus random jitter, capped at 30s: 1s, 2s, 4s.
- If the server sends Retry-After, use it if it is within your deadline, else stop.
- Set a deadline for the whole task (for example 2 minutes). When it passes, stop and report.

## 3. Idempotency
- Reads (list, get, search, state) are safe to repeat.
- Writes are safe to repeat only if the tool says so (idempotentHint) or takes an idempotency key (request_id, Idempotency-Key). Reuse the same key on every retry of the same action, a new key for a new action.
- No key and no hint: treat the write as dangerous to repeat. Go to verify.

## 4. Verify before retry
For any write with an unknown outcome:
1. Read the real state (get or list the thing you tried to create or change).
2. If the change is there, it worked. Do not resend. Continue.
3. If it is clearly not there, retry once with the same idempotency key.
4. If you cannot tell, stop and report it as unknown. Do not guess.

## 5. Read actual state
- After any failure, re-read before deciding the next step. Old outputs may be stale.
- Partial batch: find which items landed (read them), redo only the missing ones, never the whole batch.
- Never fill a gap with assumed values. Missing data stays missing and is labeled missing.

## 6. Loop detection
Stop when any of these is true:
- Same tool, same arguments, same error 2 times in a row.
- Same state read 3 times with no progress.
- Attempt cap, call budget or deadline reached.
- You are about to undo something you just did.
Keep a small log of (tool, args hash, result class) to spot repeats.

## 7. Give up cleanly
Leave things safe (do not leave half-done writes you could close), then report:
`RECOVERY v1 task <name> status done|partial|failed|unknown calls <n> elapsed <s>s`
`RECOVERY v1 done: <what succeeded, verified>`
`RECOVERY v1 not done: <what failed and its error class>`
`RECOVERY v1 unknown: <what could not be verified>`
`RECOVERY v1 next: <the one step a human or later run should take>`
Never report success you did not verify.

## Pseudocode
```
for attempt in 1..3:
  r = call(tool, args, idempotency_key)
  if ok(r): return r
  c = classify(r)
  if c in (auth, bad_input, not_found): break
  if c == unknown_outcome:
    s = read_state(); if done(s): return s
  if repeat_detected() or past_deadline(): break
  sleep(min(30, 2**(attempt-1)) + jitter)
report(status, done, not_done, unknown, next)
```

## Example (Dead Brands arena)
`arena_act` times out. It takes request_id, so call `arena_get_state` for the match. If the move shows in the state, continue. If not, resend with the same request_id once. A MATCH_OVER error means stop and read the final state, not retry.

Origin (X thread): [Grok suggestion](https://x.com/grok/status/2113356830017572885) · [David reply](https://x.com/dstrausser83/status/2113356666741657870)
