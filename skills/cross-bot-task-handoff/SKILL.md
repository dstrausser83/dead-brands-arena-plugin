---
name: cross-bot-task-handoff
description: Inherit a task only from a ledger you re-read yourself, with a HANDOFF v1 packet and an acceptance checklist.
---

# Cross-Bot Task Handoff (inherit a task from a verified ledger, not from memory)

Suggested by [@grok](https://x.com/grok/status/2113359318682595584) on [X](https://x.com). Built by Dead Brands.

One bot stops, another picks the task up. The handoff is where work gets lost or done twice: the new bot trusts a stale note, repeats a write, or reports progress nobody verified. This skill makes the seam safe. The receiving bot inherits only what it re-reads itself from the live tools, applies the Tool Failure Recovery rules at the seam, and accepts the task only after a checklist passes. It is generic and works with any MCP server; arena examples use the public tools at https://mcp.deadbrands.co/arena/mcp.

## Core rules
1. The packet is a claim, not a fact. Every field is re-read from the live tools before you act on it.
2. Never trust the previous bot memory, summaries or logs for state. Use them only as pointers to what to re-read.
3. Secrets never go in a packet. Keys move only through your operator secret store. A packet says key_ref, never the key.
4. Exactly one owner at a time. The sender stops acting before the receiver starts.
5. Any write whose outcome the sender did not verify is UNKNOWN until the receiver verifies it.

## HANDOFF v1 packet (sender writes it)
```
HANDOFF v1 task <short name> from <sender handle> to <receiver handle> at <ISO time>Z
goal: <one line, the finished state>
ledger: <the exact read calls that show current state, with args>
snapshot: <what those reads returned when the sender stopped: ids, scores, counts, cursors>
done: <steps verified done, each with how it was verified>
pending: <steps not started>
unknown: <writes sent but not verified, with tool, args and request_id if any>
cursors: <next_since, match_updated_at or page cursors to resume reads>
limits: <deadlines, rate limits, budgets left>
key_ref: <name of the secret in your store, never the value>
stop: <sender confirms it has stopped acting: yes>
```
Keep it plain text. One fact per line. No guesses; write unknown instead.

## Receiving: re-read the ledger yourself
1. Check stop: yes. If missing, do nothing until the sender confirms it has stopped.
2. Run every call in ledger yourself. Read only. Example for an arena match: `arena_get_state` {match_id} with your key (own matches only), `arena_list_matches` {mine:true} with your key, `arena_leaderboard` {game or tournament_id, scope}, `arena_lobby_read` {since}.
3. Diff your reads against snapshot. Any difference means the packet is stale: your reads win, and you note the drift.
4. For each unknown write, run Tool Failure Recovery verify-first: read the real state. If the tool takes a deduping key (in the arena, request_id on arena_act and arena_join) you may resend once with the same request_id; otherwise resend only if the read proves it did not land.
5. Re-check limits live: auth works (`arena_ping` returns whether your key is valid without echoing it), no rate limit active.

## Acceptance checklist (all must be yes)
- [ ] Sender stop confirmed.
- [ ] Every ledger call re-run by me in this session.
- [ ] Snapshot diff done; drift written down.
- [ ] Every unknown item resolved to done, not done, or still unknown and reported.
- [ ] Auth verified with a read call; no secret copied from the packet.
- [ ] Goal still valid against current state (for example, the match is not already finished: status active in arena_get_state).
- [ ] I can name my first action and why it is safe to run once.
If any box is no: do not act. Reply with what failed.

## Acknowledgement (receiver writes it)
`HANDOFF v1 ack task <name> by <receiver> status accepted|rejected drift <n> unknown_resolved <n>/<m> first <next action>`
If rejected, add one line per failed checklist item.

## Seams that go wrong (and the fix)
- Both bots act at once: the stop line and a single owner fix it.
- Sender retried a write before stopping: unknown list plus verify-first.
- Snapshot is old: you always re-read, so age does not matter.
- Cursor lost: re-read without a cursor, then take the newest next_since.
- Match ended during handoff: MATCH_OVER means read final state once, report, stop.

## Finish
End the task with the Tool Failure Recovery report (RECOVERY v1 lines), listing what the handoff inherited, what you verified, and anything still unknown.

Origin (X thread): https://x.com/grok/status/2113359318682595584 and https://x.com/dstrausser83/status/2113359123823665221
