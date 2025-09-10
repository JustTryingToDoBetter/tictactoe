# Game sync & networking policies (locked)

These policies are the source of truth for how the tic-tac-toe server and clients will behave; they are "locked in" and will be used when implementing and testing the code.

1) Authoritative state
- Server-only authoritative model: the server is the single source of truth for all game state; clients may propose intent (e.g. MOVE) but must never directly modify shared state.

2) Heartbeat cadence
- Heartbeat ping/pong: clients send a `PING` every 10 seconds; server replies with `PONG` immediately. The cadence is configurable via `HEARTBEAT_INTERVAL = 10` (seconds).

3) Disconnect grace period
- Disconnect grace: the server will mark a client as "disconnected" on missing heartbeats, but allow a `GRACE_PERIOD = 60` (seconds) for client reconnection and resumption before the player is considered forfeited; server policy upon expiry: default is to pause the game and allow manual admin/timeout resolution (for tic-tac-toe single match forfeiture is acceptable /* can be changed */).

4) Duplicate handling
- Deduplication: clients MUST include a client-generated `msg_id` (UUID string) on mutating requests (e.g. `MOVE`). The server stores recent `msg_id`s per client for `DEDUPE_WINDOW_MINUTES = 5` minutes and treats repeated `msg_id`s idempotently (replay stored outcome or return same ERROR/MOVE_OK result without reapplying).

5) Invalid data response
- Validation and errors: the server validates every request; for invalid inputs (out-of-bounds, wrong turn, wrong game, spoofed player) the server responds with an `ERROR` message that includes an error code and human-friendly reason, and keeps the connection open; bad game data never crashes or closes the connection automatically.

6) Resync strategy
- Resynchronization: on reconnect the client sends `RESUME` (or `SYNC_REQUEST`) with its `player_id` and optional `known_version`; the server responds with a `GAME_STATE` message containing the authoritative board, `version` number and `last_move` (or a full state) so the client can replace local state. If the client's known_version is ahead, server returns `ERROR` and forces a full sync.

7) Versioning and sequencing
- Every accepted state update increments a per-game monotonically increasing integer `version`; all `GAME_STATE` messages include `version`. Clients should ignore older versions and request `RESUME` when gaps are detected.

8) Backpressure & slow consumers
- Per-client send buffers are bounded; the server will avoid blocking writes by using non-blocking send with small queues and will apply backpressure policies: (1) send only latest `GAME_STATE` (drop older queued states), (2) if client remains slow beyond a `SLOW_CONSUMER_GRACE = 30` seconds, mark as slow/disconnected and apply the disconnect grace rules.

9) Security notes (minimal)
- Player identity must be tied to a stable `player_id` and an optional simple token; do not trust client-sent player_ids without server-side session mapping. For real deployments add TLS and proper auth.

10) Testing notes
- Tests will verify: heartbeat behavior and timeout, msg_id dedupe, version sequencing and out-of-order handling, invalid move rejection, RESUME syncing, and slow consumer handling.

If you'd like, I will now implement heartbeat + timeout + dedupe + versioned GAME_STATE in `server.py` and matching client changes in `client.py`, then run simple smoke tests. Which subset should I implement first? (I recommend heartbeat + timeout + versioned GAME_STATE + msg_id dedupe.)
