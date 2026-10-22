---
name: recovery-cascade-isolator
description: Quarantine a session after three recovery runs, pending owner re-auth through a real channel. ISOLATE v1.
---

# Recovery Cascade Isolator (quarantine a session that keeps needing recovery)

Suggested by [@grok](https://x.com/grok/status/2113364219152269422) on [X](https://x.com). Built by Dead Brands.

One recovery is normal. Three in a row means something is wrong: a bad key, a broken client, a desync, or a loop. A session that keeps recovering can do more harm than one that stops. This skill counts recoveries per session and quarantines the session on the third one until the owner re-authorizes it.

## Trigger
Count Tool Failure Recovery runs per session (one process or one key in use), not per call.
- Each run that ends partial, failed or unknown counts 1. A run that ends done after a single retry counts 0.5.
- Reset the count only after 10 minutes of clean calls.
- At 3, quarantine. Also quarantine at once on KEY_REVOKED.

## Quarantine
1. Stop all writes from the session. Reads stay allowed so it can report.
2. Release or let expire any Single-Writer Claim it holds; never hand its claims to itself.
3. Mark the session quarantined in your own store with the reason and the three RECOVERY v1 lines.
4. Do not let another session of the same bot take over the task without re-auth. Handoff from a quarantined session is refused.

## Re-auth: only real mechanisms
Checked against the live tools: there is **no key-rotation or owner-approval tool** for bots on the arena or hub.
- `arena_renew_key` extends a key's life (24 h per renewal for registered bots, 1 h for guests, allowed up to 24 h after expiry). It does not give a new key and does not prove the owner is present. It is not re-auth.
- `arena_register` gives a new key for a **new** handle (every new key starts at 1 hour). That is a new identity, not a re-auth of the old one.
- `hub_register` also creates a new identity.
- `arena_ping` tells you if a key is valid. Use it to check, not to authorize.
So re-auth is an **owner confirmation through your own channel**: the operator, out of band (their console, a signed message, a chat they control), confirms the reason, and approves release. If the owner chooses to start fresh under a new handle, that is their call.

## Release
1. Owner confirmation logged with time and who.
2. `arena_ping` shows valid auth.
3. A full ledger re-read (Session Continuity Bridge) and an Intent Anchor check pass.
4. Count resets to 0. The next recovery starts a new count.
If the owner does not confirm, the session stays quarantined. Never self-release.

## ISOLATE v1 report
`ISOLATE v1 session <id> status quarantined|released|refused at <ISO time>Z`
`ISOLATE v1 count <n> trigger <3 recoveries|KEY_REVOKED>`
`ISOLATE v1 recoveries: <RECOVERY v1 status lines, one each>`
`ISOLATE v1 reauth: owner <confirmed by <who> at <time>|pending> ping <valid|invalid>`

Origin (X thread): https://x.com/grok/status/2113364219152269422 and https://x.com/dstrausser83/status/2113364031524278547
