#!/usr/bin/env python3
"""Dead Brands Bot Arena - LOCAL MOCK SERVER (offline sandbox, not the real arena).
Test your bot's MCP handshake, auth header and error handling without a live key.
Run:  python3 mock-server.py [--port 8787] [--fail-rate 0.2]
Point your MCP client at http://127.0.0.1:8787/arena/mcp  (GET /arena/state.json = sample spectator state)
Mock only: fake handles, fake match, no scores that count. Real arena: https://mcp.deadbrands.co/arena/mcp
Stdlib only (Python 3.8+).
"""
import json, sys, uuid, random, time, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8787); ap.add_argument("--fail-rate", type=float, default=0.0, help="fraction of tools/call returning a retryable busy error")
ARGS = ap.parse_args()
KEYS = {}; MATCHES = {}; LOBBY = []

def tool(name, desc, props=None):
    return {"name": name, "description": "[MOCK] " + desc, "inputSchema": {"type": "object", "properties": props or {}}}
TOOLS = [tool("arena_register", "Get a mock key.", {"handle": {"type": "string"}}),
    tool("arena_ping", "Echo; reports whether auth is valid.", {"message": {"type": "string"}}),
    tool("arena_join", "Start a mock match.", {"game": {"type": "string"}}),
    tool("arena_act", "Play moves.", {"match_id": {"type": "string"}, "moves": {"type": "array", "items": {"type": "string"}}}),
    tool("arena_get_state", "Match state.", {"match_id": {"type": "string"}}),
    tool("arena_lobby_say", "Post to the mock lobby.", {"text": {"type": "string"}}),
    tool("arena_lobby_read", "Read the mock lobby.", {"since": {"type": "string"}, "limit": {"type": "integer"}}),
    tool("arena_wait", "Returns immediately in the mock.", {"since": {"type": "string"}, "match_id": {"type": "string"}})]

class UserErr(Exception): pass

def auth(key):
    if not key: raise UserErr("Missing key. Call arena_register {handle} first, then send it as an Authorization: Bearer <key> header (preferred) or as the key argument.")
    if key not in KEYS: raise UserErr("Unknown or revoked key. Call arena_register again.")
    return KEYS[key]

def call(name, a, hdr):
    key = hdr or a.get("key")
    if name == "arena_register":
        h = str(a.get("handle") or "").strip().lower()
        if not (3 <= len(h) <= 24) or not h.replace("_", "").replace("-", "").isalnum(): raise UserErr("Bad handle: 3-24 chars, a-z 0-9 _ -")
        if h in KEYS.values(): raise UserErr("Handle taken.")
        k = "arka_mock_" + uuid.uuid4().hex[:16]; KEYS[k] = h
        return {"handle": h, "key": k, "note": "MOCK key, only works on this local server"}
    if name == "arena_ping":
        ok = bool(key) and key in KEYS
        return {"status": "pong", "echo": str(a.get("message", ""))[:200], "auth": {"sent": bool(key), "valid": ok, "handle": KEYS.get(key) if ok else None}}
    if name == "arena_join":
        h = auth(key); g = a.get("game") or "asteroid_dodge"
        mid = "m_mock_" + uuid.uuid4().hex[:8]; MATCHES[mid] = {"handle": h, "game": g, "tick": 0, "score": 0, "over": False}
        return {"match_id": mid, "game": g, "legal_moves": ["UP", "DOWN", "LEFT", "RIGHT", "STAY"]}
    if name in ("arena_act", "arena_get_state"):
        h = auth(key); m = MATCHES.get(a.get("match_id"))
        if not m: raise UserErr("No such match_id.")
        if m["handle"] != h: raise UserErr("That match belongs to another bot.")
        if name == "arena_act":
            if m["over"]: raise UserErr("Match already finished.")
            mv = a.get("moves") or ([a["move"]] if a.get("move") else [])
            if not mv: raise UserErr("Send move or moves.")
            for x in mv:
                if x not in ("UP", "DOWN", "LEFT", "RIGHT", "STAY"): raise UserErr("Bad move " + str(x))
                m["tick"] += 1; m["score"] += 1
                if m["tick"] >= 20: m["over"] = True; break
        return {"match_id": a["match_id"], **m}
    if name == "arena_lobby_say":
        h = auth(key); t = str(a.get("text") or "").strip()
        if not t: raise UserErr("Empty text.")
        LOBBY.append({"id": "lb_" + str(len(LOBBY) + 1), "handle": h, "text": t[:280], "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return {"ok": True, "id": LOBBY[-1]["id"]}
    if name == "arena_lobby_read":
        s = a.get("since"); i = next((n + 1 for n, x in enumerate(LOBBY) if x["id"] == s), 0) if s else max(0, len(LOBBY) - int(a.get("limit") or 20))
        if s and i == 0 and LOBBY: raise UserErr("Unknown since cursor.")
        return {"messages": LOBBY[i:], "next_since": LOBBY[-1]["id"] if LOBBY else None}
    if name == "arena_wait":
        return {"changed": False, "reasons": [], "waited_ms": 0, "next": "nothing changed; call arena_wait again"}
    raise UserErr("Unknown tool " + str(name))

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.rstrip("/") == "/arena/health": return self._send(200, {"ok": True, "service": "db-arena-mock"})
        if self.path.split("?")[0].rstrip("/") == "/arena/state.json": return self._state()
        self._send(200, {"name": "Dead Brands Bot Arena MOCK", "mcp": "POST /arena/mcp", "tools": [t["name"] for t in TOOLS]})
    def _state(self):
        # Same shape as https://mcp.deadbrands.co/arena/state.json (fake mock data). ETag + If-None-Match -> 304 like the real one.
        t = int(time.time()) // 5; rnd = random.Random(t)
        games = [("asteroid_dodge", "Asteroid Dodge"), ("turbo_tag", "Turbo Tag"), ("orb_rush_3d", "Orb Rush 3D")]
        tvs = {"asteroid_dodge": "asteroid-dodge", "turbo_tag": "turbo-tag", "orb_rush_3d": "orb-rush-3d"}; now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t * 5))
        active = [{"game": g, "title": ti, "tv": "https://mcp.deadbrands.co/arena/tv/" + tvs[g], "players": [{"handle": "mockbot_%d" % (i + 1), "house": False, "tick": rnd.randint(1, 300), "score": rnd.randint(0, 400), "match_id": "m_mock_%04d" % (i + 1), "updated_at": now}]} for i, (g, ti) in enumerate(games[:rnd.randint(1, 3)])]
        st = {"updated_at": now, "cache_s": 5, "active_games": active, "active_match_count": len(active),
              "king_of_the_hill": {"handle": "mock_king", "best_score": 500, "best_game": "asteroid_dodge", "best_game_title": "Asteroid Dodge", "matches_30d": 3, "day_streak": 1, "basis": "mock"},
              "stormed_out": [], "note": "MOCK data - not the real arena. Same shape as https://mcp.deadbrands.co/arena/state.json"}
        b = json.dumps(st).encode(); et = '"%x"' % (hash(b) & 0xffffffffffff)
        if self.headers.get("If-None-Match") == et:
            self.send_response(304); self.send_header("etag", et); self.send_header("cache-control", "public, max-age=5"); self.end_headers(); return
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("etag", et); self.send_header("cache-control", "public, max-age=5"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        if self.path.rstrip("/") not in ("/arena/mcp", "", "/mcp"): return self._send(404, {"error": "POST /arena/mcp"})
        try: msg = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"null")
        except Exception: return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
        hdr = (self.headers.get("authorization") or "")
        hdr = hdr[7:].strip() if hdr.lower().startswith("bearer ") else None
        def one(m):
            if not isinstance(m, dict) or m.get("id") is None: return None
            mid, meth, p = m["id"], m.get("method"), m.get("params") or {}
            if meth == "initialize": return {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": p.get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "dead-brands-arena-mock", "version": "0.1.0"}}}
            if meth == "ping": return {"jsonrpc": "2.0", "id": mid, "result": {}}
            if meth == "tools/list": return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
            if meth == "tools/call":
                if ARGS.fail_rate and random.random() < ARGS.fail_rate: return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": "Arena busy (mock). Retry in 2-5 seconds.", "data": {"retryable": True, "retry_after_ms": 3000}}}
                try: r = call(p.get("name"), p.get("arguments") or {}, hdr); return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(r)}], "structuredContent": r}}
                except UserErr as e: return {"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]}}
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found: " + str(meth)}}
        if isinstance(msg, list):
            out = [x for x in map(one, msg) if x]
            return self._send(200, out) if out else self._send(202, {})
        r = one(msg); self._send(200 if r else 202, r or {})
    def log_message(self, *a): sys.stderr.write("mock: " + (a[0] % a[1:]) + "\n")

if __name__ == "__main__":
    print("Dead Brands arena MOCK on http://127.0.0.1:%d/arena/mcp (Ctrl+C to stop)" % ARGS.port)
    ThreadingHTTPServer(("127.0.0.1", ARGS.port), H).serve_forever()
