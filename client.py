# client.py
import socket, threading, json, time, uuid
from wire import send_obj, recv_obj, envelope

HOST, PORT = "127.0.0.1", 12345
GAME_ID = "G-1"
HEARTBEAT_INTERVAL = 10

class Client:
    def __init__(self, player_id, nickname=""):
        self.player_id = player_id
        self.nickname = nickname
        self.state = None  # last GAME_STATE
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._running = True

    def start(self):
        self.sock.connect((HOST, PORT))
        # Join
        join = envelope("PLAYER_JOINED", GAME_ID, {"player_id": self.player_id, "nickname": self.nickname})
        send_obj(self.sock, join)
        # Listen thread
        threading.Thread(target=self._listen, daemon=True).start()
        # Heartbeat thread
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        # Input loop
        while self._running:
            if self.state and self.state["status"] == "IN_PROGRESS" and self.state.get("next_player_id") == self.player_id:
                try:
                    raw = input("Your turn (x y): ").strip()
                    x, y = map(int, raw.split())
                    msg_id = str(uuid.uuid4())
                    move = envelope("MOVE", GAME_ID, {
                        "player_id": self.player_id,
                        "x": x, "y": y,
                        "turn": self.state["turn"],
                        "msg_id": msg_id
                    })
                    send_obj(self.sock, move)
                except Exception:
                    print("Invalid input. Use: 0 2")
            else:
                time.sleep(0.1)

    def _heartbeat_loop(self):
        while self._running:
            try:
                send_obj(self.sock, envelope("PING", GAME_ID, {}))
            except Exception:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def _listen(self):
        while True:
            msg = recv_obj(self.sock)
            if msg is None:
                print("Disconnected.")
                break
            t, p = msg["type"], msg["payload"]
            if t == "GAME_STATE":
                self.state = p
                self._render(p)
            elif t == "GAME_OVER":
                self.state = p["final_state"]
                self._render(self.state)
                print(f"GAME OVER: {p['result']}, line={p['winning_line']}")
            elif t == "ERROR":
                print(f"ERROR {p['code']}: {p['message']}")
            elif t == "PONG":
                # heartbeat reply
                pass
            elif t == "MOVE_OK":
                print(f"Move acknowledged (version={p.get('version')})")
            else:
                print("Unknown message:", t)

    def _render(self, st):
        b = st["board"]
        def cell(v): return v if v in ("X","O") else "."
        print("\nTurn:", st["turn"], "Status:", st["status"])
        print("Next:", st.get("next_player_id"))
        for row in b:
            print(" ".join(cell(c) for c in row))
        print()

if __name__ == "__main__":
    # Example: run two terminals:
    # python client.py p1
    # python client.py p2
    import sys
    pid = sys.argv[1] if len(sys.argv) > 1 else "p1"
    Client(pid).start()
