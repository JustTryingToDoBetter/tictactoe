# server.py
import socket, threading, time, uuid
from collections import defaultdict, OrderedDict
from wire import send_obj, recv_obj, envelope

# Policies (locked)
HOST, PORT = "127.0.0.1", 12345
GAME_ID = "G-1"
HEARTBEAT_INTERVAL = 10
GRACE_PERIOD = 60
DEDUPE_WINDOW_MINUTES = 5


class GameState:
    def __init__(self):
        self.board = [[None] * 3 for _ in range(3)]
        self.players = {}  # player_id -> {"symbol": "X"/"O", "seat": 0/1, "conn": socket}
        self.order = []  # [player_id_X, player_id_O]
        self.turn = 0
        self.next_player_id = None
        self.status = "WAITING"  # WAITING | IN_PROGRESS | GAME_OVER

    def serialize(self):
        players_list = []
        for pid in self.order:
            p = self.players[pid]
            players_list.append({"player_id": pid, "symbol": p["symbol"], "seat": p["seat"]})
        return {
            "board": self.board,
            "players": players_list,
            "next_player_id": self.next_player_id if self.status == "IN_PROGRESS" else None,
            "turn": self.turn,
            "status": self.status,
            "version": getattr(self, "version", 0),
        }

    def try_join(self, player_id, nickname=None, symbol=None, seat=None):
        if player_id in self.players:
            # Reconnect: keep existing symbol/seat; connection set by caller
            return True, None
        if len(self.players) >= 2:
            return False, ("ROOM_FULL", "Two players already joined.")
        # Assign seats/symbols deterministically
        if not self.players:
            assigned = {"seat": 0, "symbol": "X"}
        else:
            assigned = {"seat": 1, "symbol": "O"}
        self.players[player_id] = {"symbol": assigned["symbol"], "seat": assigned["seat"], "conn": None}
        self.order.append(player_id)
        if len(self.players) == 2:
            self.status = "IN_PROGRESS"
            self.next_player_id = self.order[0]  # X starts
        return True, None

    def validate_move(self, player_id, x, y, client_turn=None):
        if self.status != "IN_PROGRESS":
            return False, ("NOT_IN_PROGRESS", "Game not in progress.")
        if player_id != self.next_player_id:
            return False, ("NOT_YOUR_TURN", f"Expected {self.next_player_id}.")
        if not (0 <= x <= 2 and 0 <= y <= 2):
            return False, ("OUT_OF_BOUNDS", "x,y must be in [0,2].")
        if self.board[y][x] is not None:
            return False, ("CELL_TAKEN", "Cell already filled.")
        if client_turn is not None and client_turn != self.turn:
            return False, ("TURN_MISMATCH", f"Server turn {self.turn}, got {client_turn}.")
        return True, None

    def apply_move(self, player_id, x, y):
        symbol = self.players[player_id]["symbol"]
        self.board[y][x] = symbol
        self.turn += 1
        # Check win/draw
        win_line = self._winner_line(symbol)
        if win_line:
            self.status = "GAME_OVER"
            return {"result": f"{symbol}_WIN", "winning_line": win_line}
        if all(self.board[r][c] is not None for r in range(3) for c in range(3)):
            self.status = "GAME_OVER"
            return {"result": "DRAW", "winning_line": None}
        # Next player
        self.next_player_id = self.order[1] if player_id == self.order[0] else self.order[0]
        return None

    def _winner_line(self, sym):
        b = self.board
        lines = [
            [(0, 0), (1, 0), (2, 0)],
            [(0, 1), (1, 1), (2, 1)],
            [(0, 2), (1, 2), (2, 2)],  # rows
            [(0, 0), (0, 1), (0, 2)],
            [(1, 0), (1, 1), (1, 2)],
            [(2, 0), (2, 1), (2, 2)],  # cols
            [(0, 0), (1, 1), (2, 2)],
            [(2, 0), (1, 1), (0, 2)],  # diags
        ]
        for line in lines:
            if all(b[y][x] == sym for (x, y) in line):
                return line
        return None


class Server:
    def __init__(self):
        self.gs = GameState()
        self.gs.version = 0
        self.lock = threading.Lock()  # protect gs
        # player_id -> connection socket
        self.peers = {}
        # connection socket -> player_id for quick lookup
        self.conn_to_pid = {}
        # player_id -> last heartbeat timestamp
        self.last_seen = {}
        # dedupe: player_id -> OrderedDict(msg_id -> (timestamp, result_env))
        self.dedupe = defaultdict(OrderedDict)
        # start monitor thread
        threading.Thread(target=self._monitor_heartbeats, daemon=True).start()

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(5)
            print(f"Server listening on {HOST}:{PORT}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

    def handle_client(self, conn, addr):
        player_id = None
        try:
            while True:
                msg = recv_obj(conn)
                if msg is None:
                    break
                mtype, payload = msg.get("type"), msg.get("payload", {})
                # HEARTBEAT handling
                if mtype == "PING":
                    # On heartbeat, update last_seen for this player if known
                    pid = self.conn_to_pid.get(conn)
                    if pid:
                        self.last_seen[pid] = time.time()
                    send_obj(conn, envelope("PONG", GAME_ID, {}))
                    continue
                if mtype == "PLAYER_JOINED":
                    pid = payload["player_id"]
                    with self.lock:
                        ok, err = self.gs.try_join(pid)
                        if not ok:
                            self._send_error(conn, err)
                            continue
                        self.gs.players[pid]["conn"] = conn
                        self.peers[pid] = conn
                        # also map connection back to pid for heartbeat updates
                        self.conn_to_pid[conn] = pid
                        player_id = pid
                        self.last_seen[pid] = time.time()
                        # Send current state to the joiner
                        self._send_state(to_conn=conn)
                        # If game started (second player), broadcast to all
                        if self.gs.status == "IN_PROGRESS":
                            self._broadcast_state()
                elif mtype == "RESUME":
                    # Client is requesting to resume a previous session.
                    pid = payload.get("player_id")
                    known_version = payload.get("known_version")
                    if pid not in self.gs.players:
                        # Unknown player
                        self._send_error(conn, ("UNKNOWN_PLAYER", f"No such player {pid}"))
                        continue
                    with self.lock:
                        # Attach the new connection to this player
                        self.peers[pid] = conn
                        self.conn_to_pid[conn] = pid
                        self.gs.players[pid]["conn"] = conn
                        self.last_seen[pid] = time.time()
                        # If client believes it has a certain version, we ensure they are not ahead
                        if known_version is not None and known_version > self.gs.version:
                            self._send_error(conn, ("VERSION_AHEAD", "Client version ahead of server"))
                            continue
                        # Send current authoritative state
                        self._send_state(to_conn=conn)
                        # If both players connected, broadcast full state to others
                        if self.gs.status == "IN_PROGRESS":
                            self._broadcast_state()
                    continue
                elif mtype == "MOVE":
                    pid, x, y = payload["player_id"], int(payload["x"]), int(payload["y"])
                    client_turn = payload.get("turn")
                    msg_id = payload.get("msg_id")
                    # dedupe check
                    if msg_id:
                        cache = self.dedupe[pid]
                        if msg_id in cache:
                            # replay stored outcome
                            send_obj(conn, cache[msg_id][1])
                            continue
                    self.last_seen[pid] = time.time()
                    with self.lock:
                        ok, err = self.gs.validate_move(pid, x, y, client_turn)
                        if not ok:
                            env = envelope("ERROR", GAME_ID, {"code": err[0], "message": err[1]})
                            send_obj(self.peers.get(pid, conn), env)
                            # store error in dedupe cache
                            if msg_id:
                                self._cache_dedupe(pid, msg_id, env)
                            continue
                        outcome = self.gs.apply_move(pid, x, y)
                        # bump version
                        self.gs.version = getattr(self.gs, "version", 0) + 1
                        # send confirmation to actor
                        ack_env = envelope("MOVE_OK", GAME_ID, {"version": self.gs.version, "board": self.gs.serialize()["board"]})
                        send_obj(self.peers.get(pid, conn), ack_env)
                        if msg_id:
                            self._cache_dedupe(pid, msg_id, ack_env)
                        if self.gs.status == "GAME_OVER":
                            self._broadcast_game_over(outcome)
                        else:
                            self._broadcast_state()
                else:
                    self._send_error(conn, ("BAD_TYPE", f"Unsupported type {mtype}"))
        finally:
            # Clean up reverse mapping on disconnect
            try:
                pid = self.conn_to_pid.pop(conn, None)
                if pid:
                    # Do not remove gs.player; just mark connection as gone
                    self.peers.pop(pid, None)
                    self.gs.players[pid]["conn"] = None
            except Exception:
                pass
            conn.close()

    # --- send helpers ---
    def _send_state(self, to_conn=None):
        env = envelope("GAME_STATE", GAME_ID, self.gs.serialize())
        if to_conn:
            send_obj(to_conn, env)
        else:
            self._broadcast(env)

    def _broadcast_state(self):
        self._send_state(to_conn=None)

    def _broadcast_game_over(self, outcome):
        payload = {
            "result": outcome["result"],
            "winning_line": outcome["winning_line"],
            "final_state": self.gs.serialize(),
        }
        env = envelope("GAME_OVER", GAME_ID, payload)
        self._broadcast(env)

    def _send_error(self, to_conn, err_tuple):
        code, message = err_tuple
        env = envelope("ERROR", GAME_ID, {"code": code, "message": message})
        send_obj(to_conn, env)

    def _broadcast(self, env):
        # Snapshot peers to avoid holding lock while sending
        conns = list(self.peers.values())
        for c in conns:
            try:
                send_obj(c, env)
            except Exception:
                pass

    def _cache_dedupe(self, pid, msg_id, env):
        cache = self.dedupe[pid]
        cache[msg_id] = (time.time(), env)
        # purge old
        cutoff = time.time() - (DEDUPE_WINDOW_MINUTES * 60)
        keys = list(cache.keys())
        for k in keys:
            if cache[k][0] < cutoff:
                del cache[k]

    def _monitor_heartbeats(self):
        while True:
            now = time.time()
            to_forfeit = []
            for pid, last in list(self.last_seen.items()):
                if now - last > GRACE_PERIOD:
                    to_forfeit.append(pid)
            for pid in to_forfeit:
                print(f"Player {pid} exceeded grace period; marking disconnected")
                # remove peer and mark disconnected
                conn = self.peers.pop(pid, None)
                self.last_seen.pop(pid, None)
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
            time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    Server().start()
