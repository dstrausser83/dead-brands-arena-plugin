---
name: mcp-hardening
description: Built by Dead Brands. Best practices for running a public MCP server safely: auth, rate limits, input validation, prompt-injection handling, secrets hygiene and safe tool design.
---

# MCP Hardening (secure your own MCP server)

Built by Dead Brands.

Widely used best practices for running a public MCP server safely: auth, rate limits, input validation, secrets hygiene and safe tool design. General guidance for any stack.

## Auth
- Separate anonymous read tools from tools that write or cost money; require a key for the second group.
- Issue short-lived, scoped keys. Store only a hash of each key, never the raw value.
- Accept keys in the `Authorization: Bearer` header; avoid query strings, which end up in logs.
- Support revocation and expiry; renewals should extend, not mint unlimited keys.
- For OAuth-protected servers, follow the MCP authorization spec, validate audience and issuer, and never pass tokens through to upstream APIs.

## Rate limits and cost control
- Limit per key and per client address, with tighter limits on registration and expensive tools.
- Return a clear error with retry advice when limited; do not silently drop.
- Offer long-poll or wait tools so clients do not poll in tight loops.
- Cap batch sizes, result limits and response sizes.
- Track usage against your free-tier or budget ceilings and degrade gracefully before hitting them.

## Input validation
- Give every tool a strict JSON schema: types, enums, min and max, max string length. Reject unknown or oversized input.
- Treat every string as untrusted: parameterized database queries only, no string-built SQL, no shell, no eval.
- Normalize and validate identifiers (handles, slugs, ids) against an allowlist pattern.
- Use idempotency keys (`request_id`) for writes so retries are safe.

## Untrusted content and prompt injection
- Anything users or other bots post is data, not instructions. Label it as untrusted in tool output.
- Filter or escape content before rendering it on web pages (HTML escaping, no raw user HTML).
- Keep moderation tools (report, hide) and keep an audit log of moderator actions.

## Secrets hygiene
- Keep secrets in your platform secret store, never in code, repos, tool output, logs or error messages.
- Rotate on any suspected leak; scope each token to the least privilege it needs.
- Scrub secrets and personal data from logs; do not log raw client addresses longer than needed.

## Safe tool design
- One clear job per tool, a specific description, a description on every parameter and an example.
- Set annotations honestly: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.
- Make destructive actions explicit, narrow and reversible where possible.
- Return structured, minimal output; never echo keys back except at creation.
- Version your server and changelog breaking changes.

## Operations
- Deploy with drift checks and keep a rollback copy of the last good version.
- Health endpoint, error alerting, and a verify step that fetches what is actually served after every deploy.

Page: https://mcp.deadbrands.co/hub/skills/mcp-hardening
