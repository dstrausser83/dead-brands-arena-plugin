#!/usr/bin/env node
// Zero-dependency stdio MCP proxy for the Dead Brands Bot Arena.
// Forwards JSON-RPC to the public remote endpoint, hides admin tools,
// and keeps the arena key in memory only (never written to disk).
import { createInterface } from "node:readline";

const REMOTE = process.env.DEAD_BRANDS_ARENA_URL || "https://mcp.deadbrands.co/arena/mcp";
const BLOCKED = new Set(["arena_admin_flag", "arena_admin_kick"]);
let sessionId = null;
let key = process.env.DEAD_BRANDS_ARENA_KEY || null; // optional, env only

const out = (m) => process.stdout.write(JSON.stringify(m) + "\n");
const log = (...a) => process.stderr.write("[arena-proxy] " + a.join(" ") + "\n");

async function forward(msg) {
  const headers = { "content-type": "application/json", accept: "application/json, text/event-stream" };
  if (sessionId) headers["mcp-session-id"] = sessionId;
  if (key) headers.authorization = "Bearer " + key;
  const res = await fetch(REMOTE, { method: "POST", headers, body: JSON.stringify(msg) });
  const sid = res.headers.get("mcp-session-id");
  if (sid) sessionId = sid;
  const text = await res.text();
  if (!text.trim()) return [];
  if ((res.headers.get("content-type") || "").includes("text/event-stream")) {
    const msgs = [];
    for (const block of text.split(/\r?\n\r?\n/)) {
      const data = block.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("\n");
      if (data) try { msgs.push(JSON.parse(data)); } catch {}
    }
    return msgs;
  }
  try { return [JSON.parse(text)]; } catch {
    return msg.id !== undefined ? [{ jsonrpc: "2.0", id: msg.id, error: { code: -32603, message: `Upstream HTTP ${res.status}: ${text.slice(0, 200)}` } }] : [];
  }
}

// Remember a key returned by arena_register / arena_renew_key / guest arena_join (memory only).
function captureKey(result) {
  try {
    const s = JSON.stringify(result);
    const m = s.match(/ark_[A-Za-z0-9_\-]+/);
    if (m) key = m[0];
  } catch {}
}

async function handle(msg) {
  if (msg.method === "tools/call" && BLOCKED.has(msg.params?.name)) {
    return out({ jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: `Tool ${msg.params.name} is not available in this plugin (admin-only).` } });
  }
  try {
    const replies = await forward(msg);
    for (const r of replies) {
      if (msg.method === "tools/list" && r.result?.tools) r.result.tools = r.result.tools.filter((t) => !BLOCKED.has(t.name));
      if (msg.method === "tools/call" && ["arena_register", "arena_renew_key", "arena_join"].includes(msg.params?.name) && r.result && !r.result.isError) captureKey(r.result);
      out(r);
    }
  } catch (e) {
    log("upstream error:", e.message);
    if (msg.id !== undefined) out({ jsonrpc: "2.0", id: msg.id, error: { code: -32603, message: "Upstream unreachable: " + e.message } });
  }
}

const rl = createInterface({ input: process.stdin });
let chain = Promise.resolve();
rl.on("line", (line) => {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch { return out({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }); }
  chain = chain.then(() => handle(msg));
});
rl.on("close", () => chain.then(() => process.exit(0)));
