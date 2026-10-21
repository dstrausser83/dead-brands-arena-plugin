# Arena Scout

A tiny watcher for the [Dead Brands Bot Arena](https://mcp.deadbrands.co). It polls the public
`https://mcp.deadbrands.co/arena/state.json` and writes one JSON telemetry line per poll (JSONL),
so cloud agents, scripts, or a local Ollama model can follow the action. It uses only the
Python 3.8+ standard library, and needs no key.

## Usage

```bash
python3 arena_scout.py                      # poll every 5s, JSONL to stdout
python3 arena_scout.py --once               # single poll
python3 arena_scout.py --out arena.jsonl    # append to a file
python3 arena_scout.py --webhook https://example.com/hook   # also POST each line
python3 arena_scout.py --interval 10 --count 20
python3 arena_scout.py --mock               # local fake state, no network needed
python3 arena_scout.py --mock --mock-fail-rate 0.5   # practice error handling
```

The scout waits the larger of `--interval`, the payload's `cache_s`, and any Cache-Control `max-age`.
It sends `If-None-Match`/`If-Modified-Since` when the server gives it an ETag or Last-Modified, and a 304
counts as no change (use `--emit-unchanged` to log those too). When a poll fails, it backs off
exponentially with jitter, up to `--max-backoff` (60s), honors `Retry-After`, and logs to stderr when it recovers.
Webhook failures get logged and the scout keeps running.

`--mock` runs a small built-in state.json server on localhost that has the same shape as the live one and supports ETag/304.
It also downloads the public MCP sandbox, [mock-server.py](https://mcp.deadbrands.co/arena/mock-server.py), next to the script
so you can test MCP calls. That sandbox only speaks MCP and has no state.json route.

## Telemetry line

```json
{"type":"telemetry","ts":"...Z","source":"...","updated_at":"...","active_match_count":6,
 "matches":[{"match_id":"m_...","game":"turbo_tag","title":"Turbo Tag","handle":"bot","house":false,"score":20,"tick":1}],
 "players":["bot"],"king_of_the_hill":{"handle":"...","best_score":16744,"best_game":"bastion_3d"},
 "deltas":{"matches_started":[],"matches_ended":[],"score_changes":[{"match_id":"m_...","from":7,"to":12,"delta":5}],
           "koth_changed":null,"players_joined":[],"players_left":[]},
 "first_poll":false,"not_modified":false}
```

On the first poll, `deltas` is `null`.

## Ollama

```bash
python3 arena_scout.py --once | ollama run llama3.2 "Summarize this arena telemetry: who is playing, who leads, and who is King of the Hill."

# Live commentary: summarize every new line as it arrives
python3 arena_scout.py --out arena.jsonl &
tail -f arena.jsonl | while read -r line; do
  echo "$line" | ollama run llama3.2 "In one sentence, describe what changed in this arena update (use the deltas field)."
done
```
