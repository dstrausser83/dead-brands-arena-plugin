#!/usr/bin/env node
// Zero-dependency stdio MCP proxy for the Dead Brands Bot Arena.
// Forwards JSON-RPC to the public remote endpoint, hides admin tools,
// and keeps the arena key in memory only (never written to disk).
import { createInterface } from "node:readline";

const REMOTE = process.env.DEAD_BRANDS_ARENA_URL || "https://mcp.deadbrands.co/arena/mcp";
const BLOCKED = new Set(["arena_admin_flag", "arena_admin_kick"]);
const KEY_TOOLS = new Set(["arena_register", "arena_renew_key", "arena_join"]);
const BASE_TIMEOUT_MS = 30_000;
const WAIT_MARGIN_MS = 15_000;
let sessionId = null;
let initMsg = null; // last client initialize, replayed if the session expires
let reinit = null;  // in-flight re-initialize promise (shared by concurrent callers)
let key = process.env.DEAD_BRANDS_ARENA_KEY || null; // optional, env only

const out = (m) => process.stdout.write(JSON.stringify(m) + "\n");
const log = (...a) => process.stderr.write("[arena-proxy] " + a.join(" ") + "\n");
const rpcError = (id, code, message, data) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message, ...(data ? { data } : {}) } });

class HttpError extends Error {
  constructor(status, body) { super(`Upstream HTTP ${status}: ${body.slice(0, 300)}`); this.status = status; this.body = body; }
}

function timeoutFor(msg) {
  if (msg?.method === "tools/call" && msg.params?.name === "arena_wait") {
    const a = msg.params.arguments || {};
    const s = Number(a.timeout_s); // server caps at 25 s, default 20 s
    return (Number.isFinite(s) && s > 0 ? s * 1000 : 20_000) + WAIT_MARGIN_MS;
  }
  return BASE_TIMEOUT_MS;
}

function parseBody(text, contentType) {
  if (!text.trim()) return [];
  if (contentType.includes("text/event-stream")) {
    const msgs = [];
    for (const block of text.split(/\r?\n\r?\n/)) {
      const data = block.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("\n");
      if (data) try { const p = JSON.parse(data); Array.isArray(p) ? msgs.push(...p) : msgs.push(p); } catch {}
    }
    return msgs;
  }
  const p = JSON.parse(text);
  return Array.isArray(p) ? p : [p];
}

async function post(msg, timeoutMs) {
  const headers = { "content-type": "application/json", accept: "application/json, text/event-stream" };
  if (sessionId) headers["mcp-session-id"] = sessionId;
  if (key) headers.authorization = "Bearer " + key;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(REMOTE, { method: "POST", headers, body: JSON.stringify(msg), signal: ac.signal });
    const sid = res.headers.get("mcp-session-id");
    if (sid) sessionId = sid;
    const text = await res.text();
    if (!res.ok) throw new HttpError(res.status, text);
    try { return parseBody(text, res.headers.get("content-type") || ""); }
    catch { throw new HttpError(res.status, "Unparseable body: " + text); }
  } catch (e) {
    if (e.name === "AbortError") throw new Error(`Upstream timed out after ${timeoutMs} ms`);
    throw e;
  } finally { clearTimeout(timer); }
}

const isSessionError = (e) => e instanceof HttpError && (e.status === 404 || (e.status === 400 && /session/i.test(e.body)));

async function reinitialize() {
  if (!reinit) {
    reinit = (async () => {
      sessionId = null;
      const init = initMsg || { jsonrpc: "2.0", method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "dead-brands-arena-proxy", version: "0.2.0" } } };
      await post({ ...init, id: "proxy-reinit-" + Date.now() }, BASE_TIMEOUT_MS);
      await post({ jsonrpc: "2.0", method: "notifications/initialized" }, BASE_TIMEOUT_MS).catch(() => {});
      log("session re-initialized");
    })().finally(() => { reinit = null; });
  }
  return reinit;
}

async function forward(msg) {
  if (msg.method === "initialize") { initMsg = msg; sessionId = null; }
  try { return await post(msg, timeoutFor(msg)); }
  catch (e) {
    if (!isSessionError(e) || msg.method === "initialize" || !sessionId && !initMsg) throw e;
    log(`session error (HTTP ${e.status}); resetting and retrying once`);
    await reinitialize();
    return await post(msg, timeoutFor(msg));
  }
}

// Remember a key returned by arena_register / arena_renew_key / guest arena_join.
// Reads ONLY the top-level `key` field (structuredContent.key or JSON text .key).
function captureKey(result) {
  const ok = (k) => typeof k === "string" && /^ark_[A-Za-z0-9_\-]+$/.test(k);
  let k = result?.structuredContent?.key;
  if (!ok(k)) {
    for (const c of result?.content || []) {
      if (c.type !== "text") continue;
      try { const j = JSON.parse(c.text); if (ok(j?.key)) { k = j.key; break; } } catch {}
    }
  }
  if (ok(k)) { key = k; log("arena key captured from key field (memory only)"); }
}

// Returns the response for one message, or null for notifications.
async function handle(msg) {
  const isNote = msg?.id === undefined;
  if (!msg || typeof msg !== "object" || msg.jsonrpc !== "2.0") return isNote ? null : rpcError(msg.id, -32600, "Invalid Request");
  if (msg.method === "tools/call" && BLOCKED.has(msg.params?.name)) {
    return isNote ? null : rpcError(msg.id, -32601, `Tool ${msg.params.name} is not available in this plugin (admin-only).`);
  }
  try {
    const replies = await forward(msg);
    let reply = null;
    for (const r of replies) {
      if (msg.method === "tools/list" && r.result?.tools) r.result.tools = r.result.tools.filter((t) => !BLOCKED.has(t.name));
      if (msg.method === "tools/call" && KEY_TOOLS.has(msg.params?.name) && r.result && !r.result.isError) captureKey(r.result);
      if (r.id !== undefined && r.id === msg.id) reply = r; else out(r); // pass through server notifications
    }
    return isNote ? null : reply ?? rpcError(msg.id, -32603, "Upstream returned no response");
  } catch (e) {
    log("upstream error:", e.message);
    if (isNote) return null;
    return e instanceof HttpError
      ? rpcError(msg.id, -32603, e.message, { status: e.status, body: e.body.slice(0, 500) })
      : rpcError(msg.id, -32603, "Upstream unreachable: " + e.message);
  }
}

async function handleLine(line) {
  let msg;
  try { msg = JSON.parse(line); } catch { return out(rpcError(null, -32700, "Parse error")); }
  if (Array.isArray(msg)) {
    if (!msg.length) return out(rpcError(null, -32600, "Invalid Request: empty batch"));
    // initialize first (if present) so the rest share its session
    const i = msg.findIndex((m) => m?.method === "initialize");
    const results = new Array(msg.length);
    if (i >= 0) results[i] = await handle(msg[i]);
    await Promise.all(msg.map(async (m, j) => { if (j !== i) results[j] = await handle(m); }));
    const outArr = results.filter((r) => r);
    if (outArr.length) out(outArr);
    return;
  }
  const r = await handle(msg);
  if (r) out(r);
}

// Process lines concurrently; an initialize gates later requests so they share its session.
const rl = createInterface({ input: process.stdin });
const pending = new Set();
let initGate = Promise.resolve();
rl.on("line", (line) => {
  if (!line.trim()) return;
  const isInit = /"method"\s*:\s*"initialize"/.test(line);
  const p = isInit ? (initGate = initGate.then(() => handleLine(line))) : initGate.then(() => handleLine(line));
  pending.add(p); p.finally(() => pending.delete(p));
});
rl.on("close", () => Promise.allSettled([...pending]).then(() => process.exit(0)));
