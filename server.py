# server.py
import socket, threading
from wire import send_obj, recv_obj, envelope

HOST, PORT = "127.0.0.1", 12345
GAME_ID = "G-1"

class GameState:
    def __init__(self):
        self.board = [[None]*3 for _ in range(3)]
        self.players = {}  # player_id -> {"symbol": "X"/"O", "seat": 0/1, "conn": socket}
        self.order = []    # [player_id_X, player_id_O]
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
            [(0,0),(1,0),(2,0)], [(0,1),(1,1),(2,1)], [(0,2),(1,2),(2,2)], # rows
            [(0,0),(0,1),(0,2)], [(1,0),(1,1),(1,2)], [(2,0),(2,1),(2,2)], # cols
            [(0,0),(1,1),(2,2)], [(2,0),(1,1),(0,2)]                      # diags
        ]
        for line in lines:
            if all(b[y][x] == sym for (x,y) in line):
                return line
        return None

class Server:
    def __init__(self):
        self.gs = GameState()
        self.lock = threading.Lock()  # protect gs
        self.peers = {}  # player_id -> conn

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
                if mtype == "PLAYER_JOINED":
                    pid = payload["player_id"]
                    with self.lock:
                        ok, err = self.gs.try_join(pid)
                        if not ok:
                            self._send_error(conn, err)
                            continue
                        self.gs.players[pid]["conn"] = conn
                        self.peers[pid] = conn
                        player_id = pid
                        # Send current state to the joiner
                        self._send_state(to_conn=conn)
                        # If game started (second player), broadcast to all
                        if self.gs.status == "IN_PROGRESS":
                            self._broadcast_state()
                elif mtype == "MOVE":
                    pid, x, y = payload["player_id"], int(payload["x"]), int(payload["y"])
                    client_turn = payload.get("turn")
                    with self.lock:
                        ok, err = self.gs.validate_move(pid, x, y, client_turn)
                        if not ok:
                            self._send_error(self.peers.get(pid, conn), err)
                            continue
                        outcome = self.gs.apply_move(pid, x, y)
                        if self.gs.status == "GAME_OVER":
                            self._broadcast_game_over(outcome)
                        else:
                            self._broadcast_state()
                else:
                    self._send_error(conn, ("BAD_TYPE", f"Unsupported type {mtype}"))
        finally:
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
            "final_state": self.gs.serialize()
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
            try: send_obj(c, env)
            except: pass

if __name__ == "__main__":
    Server().start()
