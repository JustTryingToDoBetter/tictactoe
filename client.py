# client.py
import socket, threading, json
from wire import send_obj, recv_obj, envelope

HOST, PORT = "127.0.0.1", 12345
GAME_ID = "G-1"

class Client:
    def __init__(self, player_id, nickname=""):
        self.player_id = player_id
        self.nickname = nickname
        self.state = None  # last GAME_STATE
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self):
        self.sock.connect((HOST, PORT))
        # Join
        join = envelope("PLAYER_JOINED", GAME_ID, {"player_id": self.player_id, "nickname": self.nickname})
        send_obj(self.sock, join)
        # Listen thread
        threading.Thread(target=self._listen, daemon=True).start()
        # Input loop
        while True:
            if self.state and self.state["status"] == "IN_PROGRESS" and self.state.get("next_player_id") == self.player_id:
                try:
                    raw = input("Your turn (x y): ").strip()
                    x, y = map(int, raw.split())
                    move = envelope("MOVE", GAME_ID, {
                        "player_id": self.player_id,
                        "x": x, "y": y,
                        "turn": self.state["turn"]
                    })
                    send_obj(self.sock, move)
                except Exception as e:
                    print("Invalid input. Use: 0 2")
            else:
                # Small idle to reduce busy-wait, or press Enter to refresh
                pass

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
