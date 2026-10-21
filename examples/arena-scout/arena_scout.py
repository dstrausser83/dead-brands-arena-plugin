#!/usr/bin/env python3
"""Dead Brands Bot Arena scout: polls the public arena state.json and emits JSONL telemetry.

Stdlib only (Python 3.8+). No keys needed; state.json is public.

Data shape (public https://mcp.deadbrands.co/arena/state.json):
  ArenaState = {
    updated_at: ISO str, cache_s: int, active_match_count: int, note: str,
    active_games: [ { game, title, tv, players: [ PlayerSlot ] } ],
    king_of_the_hill: { handle, best_score, best_game, best_game_title,
                        matches_30d, day_streak, basis } | null,
    stormed_out: [ { match_id, comic, round, set, at } ]       # optional
  }
  PlayerSlot = { handle, house: bool, tick, score, match_id, updated_at, ...game extras }

Telemetry line (one JSON object per line):
  { type: "telemetry", ts, source, updated_at, active_match_count,
    matches: [ {match_id, game, handle, house, score, tick} ], players: [handles],
    king_of_the_hill, deltas: { matches_started, matches_ended, score_changes,
    koth_changed, players_joined, players_left }, first_poll, not_modified }
"""
import argparse, json, random, re, sys, threading, time, os, urllib.request, urllib.error
from datetime import datetime, timezone

LIVE_URL = "https://mcp.deadbrands.co/arena/state.json"
MOCK_SERVER_URL = "https://mcp.deadbrands.co/arena/mock-server.py"
UA = "dead-brands-arena-scout/0.1"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def log(msg):
    sys.stderr.write("[scout %s] %s\n" % (now_iso(), msg)); sys.stderr.flush()


def summarize(state):
    matches = {}
    for g in state.get("active_games") or []:
        for p in g.get("players") or []:
            mid = p.get("match_id") or "%s:%s" % (g.get("game"), p.get("handle"))
            matches[mid] = {"match_id": mid, "game": g.get("game"), "title": g.get("title"),
                            "handle": p.get("handle"), "house": bool(p.get("house")),
                            "score": p.get("score"), "tick": p.get("tick")}
    return matches


def diff(prev, cur, prev_koth, koth):
    if prev is None:
        return None
    started = sorted(set(cur) - set(prev)); ended = sorted(set(prev) - set(cur))
    scores = []
    for mid in sorted(set(cur) & set(prev)):
        a, b = prev[mid].get("score"), cur[mid].get("score")
        if a != b:
            d = (b - a) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
            scores.append({"match_id": mid, "handle": cur[mid]["handle"], "game": cur[mid]["game"], "from": a, "to": b, "delta": d})
    ph = {m["handle"] for m in prev.values()}; ch = {m["handle"] for m in cur.values()}
    koth_changed = None
    if (prev_koth or {}) != (koth or {}):
        koth_changed = {"from": prev_koth, "to": koth,
                        "new_king": (prev_koth or {}).get("handle") != (koth or {}).get("handle")}
    return {"matches_started": started, "matches_ended": ended, "score_changes": scores,
            "koth_changed": koth_changed, "players_joined": sorted(ch - ph), "players_left": sorted(ph - ch)}


class Fetcher:
    def __init__(self, url, timeout=10):
        self.url, self.timeout, self.etag, self.last_mod = url, timeout, None, None

    def get(self):
        """Returns (status, payload_or_None, max_age_or_None, retry_after_or_None)."""
        h = {"User-Agent": UA, "Accept": "application/json"}
        if self.etag: h["If-None-Match"] = self.etag
        if self.last_mod: h["If-Modified-Since"] = self.last_mod
        req = urllib.request.Request(self.url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read(); hdr = r.headers; status = r.status
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return 304, None, max_age(e.headers), None
            ra = None
            try: ra = float(e.headers.get("Retry-After"))
            except (TypeError, ValueError): pass
            raise FetchError("HTTP %d %s" % (e.code, e.read(200).decode("utf-8", "replace")), ra)
        except Exception as e:
            raise FetchError("%s: %s" % (type(e).__name__, e))
        try:
            data = json.loads(body)
        except ValueError as e:
            raise FetchError("bad JSON: %s" % e)
        if not isinstance(data, dict) or "active_games" not in data:
            raise FetchError("unexpected payload shape (no active_games)")
        self.etag = hdr.get("ETag") or self.etag
        self.last_mod = hdr.get("Last-Modified") or self.last_mod
        return status, data, max_age(hdr), None


class FetchError(Exception):
    def __init__(self, msg, retry_after=None):
        super().__init__(msg); self.retry_after = retry_after


def max_age(hdr):
    m = re.search(r"max-age=(\d+)", (hdr or {}).get("Cache-Control", "") or "")
    return int(m.group(1)) if m else None


class Sink:
    def __init__(self, out, webhook, wh_timeout=5):
        self.fh = open(out, "a", encoding="utf-8") if out else None
        self.webhook, self.wh_timeout = webhook, wh_timeout

    def emit(self, obj):
        line = json.dumps(obj, separators=(",", ":"), sort_keys=False)
        if self.fh:
            self.fh.write(line + "\n"); self.fh.flush()
        else:
            sys.stdout.write(line + "\n"); sys.stdout.flush()
        if self.webhook:
            try:
                req = urllib.request.Request(self.webhook, data=line.encode(), method="POST",
                                             headers={"Content-Type": "application/json", "User-Agent": UA})
                urllib.request.urlopen(req, timeout=self.wh_timeout).close()
            except Exception as e:
                log("webhook failed (ignored): %s" % e)


# ---------- --mock support ----------
# The public mock-server.py is an MCP-only sandbox (no state.json route), so --mock also runs
# a tiny in-process state.json server with the same shape, plus ETag/304 and failure injection.
def start_mock_state(port, fail_rate):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import hashlib
    games = [("asteroid_dodge", "Asteroid Dodge"), ("turbo_tag", "Turbo Tag"), ("orb_rush_3d", "Orb Rush 3D")]
    st = {"matches": {}, "n": 0, "koth": {"handle": "mock_king", "best_score": 500, "best_game": "asteroid_dodge"}, "ver": 0}
    lock = threading.Lock()

    def step():
        with lock:
            ms = st["matches"]
            if len(ms) < 2 or random.random() < 0.35:
                st["n"] += 1; g = random.choice(games)
                ms["m_mock_%04d" % st["n"]] = {"game": g, "handle": "mockbot_%d" % random.randint(1, 6), "score": 0, "tick": 0}
            for mid in list(ms):
                if random.random() < 0.5:
                    ms[mid]["score"] += random.randint(1, 40); ms[mid]["tick"] += 1
                if ms[mid]["tick"] > 6 and random.random() < 0.3:
                    m = ms.pop(mid)
                    if m["score"] > st["koth"]["best_score"]:
                        st["koth"] = {"handle": m["handle"], "best_score": m["score"], "best_game": m["game"][0]}
            st["ver"] += 1

    def ticker():
        while True:
            time.sleep(3); step()
    step(); threading.Thread(target=ticker, daemon=True).start()

    def payload():
        with lock:
            ag = {}
            for mid, m in st["matches"].items():
                g = ag.setdefault(m["game"][0], {"game": m["game"][0], "title": m["game"][1], "tv": None, "players": []})
                g["players"].append({"handle": m["handle"], "house": False, "tick": m["tick"], "score": m["score"], "match_id": mid, "updated_at": now_iso()})
            return {"updated_at": now_iso(), "cache_s": 2, "active_games": list(ag.values()),
                    "active_match_count": len(st["matches"]), "king_of_the_hill": dict(st["koth"]),
                    "note": "MOCK state (local, fake data)"}, st["ver"]

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] != "/arena/state.json":
                self.send_response(404); self.end_headers(); return
            if fail_rate and random.random() < fail_rate:
                b = b'{"error":"busy","retry_after_s":1}'
                self.send_response(503); self.send_header("Retry-After", "1")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
            data, ver = payload()
            etag = '"v%d-%s"' % (ver, hashlib.sha1(str(ver).encode()).hexdigest()[:8])
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304); self.send_header("ETag", etag); self.end_headers(); return
            b = json.dumps(data).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("ETag", etag); self.send_header("Cache-Control", "max-age=2")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a): pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d/arena/state.json" % srv.server_address[1]


def fetch_mock_server_file():
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock-server.py")
    if not os.path.exists(dest):
        try:
            urllib.request.urlretrieve(MOCK_SERVER_URL, dest); log("downloaded %s -> %s" % (MOCK_SERVER_URL, dest))
        except Exception as e:
            log("could not download mock-server.py (ok, state mock is built in): %s" % e)


def main():
    ap = argparse.ArgumentParser(description="Poll the Dead Brands Arena state.json and emit JSONL telemetry.")
    ap.add_argument("--url", default=LIVE_URL)
    ap.add_argument("--interval", type=float, default=5.0, help="base poll seconds (default 5)")
    ap.add_argument("--once", action="store_true", help="single poll then exit")
    ap.add_argument("--count", type=int, default=0, help="stop after N emitted lines (0 = forever)")
    ap.add_argument("--out", help="append JSONL to this file instead of stdout")
    ap.add_argument("--webhook", help="POST each JSON line to this URL")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--max-backoff", type=float, default=60.0)
    ap.add_argument("--emit-unchanged", action="store_true", help="also emit a line on 304 Not Modified")
    ap.add_argument("--mock", action="store_true", help="use a local mock state endpoint instead of live")
    ap.add_argument("--mock-port", type=int, default=0, help="0 = pick a free port")
    ap.add_argument("--mock-fail-rate", type=float, default=0.0, help="mock: fraction of polls returning 503")
    a = ap.parse_args()

    url = a.url
    if a.mock:
        fetch_mock_server_file()
        url = start_mock_state(a.mock_port, a.mock_fail_rate)
        log("mock state endpoint at %s" % url)

    f = Fetcher(url, a.timeout); sink = Sink(a.out, a.webhook)
    prev = prev_koth = None; last = None; fails = 0; emitted = 0
    while True:
        wait = a.interval
        try:
            status, data, ma, _ = f.get()
            if fails:
                log("recovered after %d failure(s)" % fails); fails = 0
            if status == 304:
                if a.emit_unchanged and last is not None:
                    sink.emit(dict(last, ts=now_iso(), not_modified=True, deltas=diff({}, {}, None, None)))
                    emitted += 1
            else:
                cur = summarize(data); koth = data.get("king_of_the_hill")
                line = {"type": "telemetry", "ts": now_iso(), "source": url, "updated_at": data.get("updated_at"),
                        "active_match_count": data.get("active_match_count", len(cur)),
                        "matches": list(cur.values()), "players": sorted({m["handle"] for m in cur.values()}),
                        "king_of_the_hill": koth, "deltas": diff(prev, cur, prev_koth, koth),
                        "first_poll": prev is None, "not_modified": False}
                if data.get("stormed_out"): line["stormed_out"] = data["stormed_out"]
                sink.emit(line); emitted += 1; last = line; prev, prev_koth = cur, koth
            hint = data.get("cache_s") if data else None
            wait = max(a.interval, float(hint or 0), float(ma or 0))
        except FetchError as e:
            fails += 1
            back = min(a.max_backoff, a.interval * (2 ** (fails - 1)))
            back = back / 2 + random.uniform(0, back / 2)  # equal jitter
            if e.retry_after: back = max(back, e.retry_after)
            wait = back
            log("poll failed (#%d): %s; retrying in %.1fs" % (fails, e, wait))
            if a.once and fails >= 3:
                return 1
            if a.once:
                time.sleep(wait); continue
        except KeyboardInterrupt:
            return 0
        if a.once or (a.count and emitted >= a.count):
            return 0
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
