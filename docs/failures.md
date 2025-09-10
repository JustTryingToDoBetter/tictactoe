# Lab 5 — Failure modes and one-line remedies

Checklist
- [x] Disconnects (client → server, server → client)
- [x] Timeouts / heartbeats
- [x] Partial / garbled frames
- [x] Duplicates (retries)
- [x] Out-of-order messages
- [x] Invalid data / cheating
- [x] Slow consumer / backpressure

One-line remedies

- Disconnects: mark the player disconnected server-side, keep the game state for a short reconnect window, and require the client to resume with a sync request that fetches the authoritative `GAME_STATE`.
- Timeouts: send periodic heartbeat/ping messages and have the server mark peers dead or paused if no heartbeat or valid message arrives within the configured timeout `T`.
- Partial/garbled frames: use a clear framing protocol (newline-terminated JSON or length-prefixed), buffer until a complete frame is received, validate JSON, and reject or request retransmit on parse errors.
- Duplicates: require a client-generated unique `msg_id` and have the server keep a short-lived dedupe cache so repeated requests are idempotently ignored or replay the stored outcome.
- Out-of-order: attach a monotonically increasing `version` or sequence number to every accepted `GAME_STATE`; clients ignore older versions and request a full sync when they detect a gap.
- Invalid data: enforce strict server-side validation (player membership, turn, bounds) and require simple authentication/player tokens so spoofed or out-of-bounds requests are rejected and logged.
- Slow consumer: use per-client send queues and non-blocking writes with bounded buffers and backpressure policies (drop old updates, send deltas, or disconnect after a grace period) to avoid blocking the server.

