# client.py
import socket, threading, json, time, uuid
from wire import send_obj, recv_obj, envelope

HOST, PORT = "127.0.0.1", 12345
GAME_ID = "G-1"
HEARTBEAT_INTERVAL = 10


class Client:
    def __init__(self, player_id, nickname="", host: str = HOST, port: int = PORT, resume: bool = False):
        self.player_id = player_id
        self.nickname = nickname
        self.host = host
        self.port = port
        self.resume = resume
        self.state = None  # last GAME_STATE
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._running = True

    def start(self):
        """Connects to the server and enters the main input loop."""
        # Connect to specified host/port
        self.sock.connect((self.host, self.port))
        # If we are resuming an existing session, send RESUME with known_version
        if self.resume:
            known_version = None
            if self.state and isinstance(self.state, dict):
                known_version = self.state.get("version")
            resume_payload = {"player_id": self.player_id}
            if known_version is not None:
                resume_payload["known_version"] = known_version
            msg = envelope("RESUME", GAME_ID, resume_payload)
            send_obj(self.sock, msg)
        else:
            # Join fresh game
            join = envelope("PLAYER_JOINED", GAME_ID, {
                "player_id": self.player_id,
                "nickname": self.nickname,
            })
            send_obj(self.sock, join)
        # Listen thread
        threading.Thread(target=self._listen, daemon=True).start()
        # Heartbeat thread
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        # Input loop
        while self._running:
            if self.state and self.state.get("status") == "IN_PROGRESS" and \
                    self.state.get("next_player_id") == self.player_id:
                try:
                    raw = input("Your turn (x y): ").strip()
                    x, y = map(int, raw.split())
                    msg_id = str(uuid.uuid4())
                    move = envelope("MOVE", GAME_ID, {
                        "player_id": self.player_id,
                        "x": x,
                        "y": y,
                        "turn": self.state.get("turn"),
                        "msg_id": msg_id,
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
                # Use version to ensure we don't regress state
                if self.state is None or p.get("version", 0) >= self.state.get("version", 0):
                    self.state = p
                    self._render(p)
                else:
                    # Ignored stale state
                    pass
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
        def cell(v):
            return v if v in ("X", "O") else "."
        print("\nTurn:", st["turn"], "Status:", st["status"])
        print("Next:", st.get("next_player_id"))
        for row in b:
            print(" ".join(cell(c) for c in row))
        print()


if __name__ == "__main__":
    # Usage examples:
    #   python client.py p1                # connect as player p1 to default localhost:12345
    #   python client.py p2 192.168.0.10   # connect as p2 to host 192.168.0.10 on default port 12345
    #   python client.py p1 192.168.0.10 5555 resume  # resume previous session to host:port
    import sys
    # Extract command-line args
    args = sys.argv[1:]
    pid = args[0] if len(args) >= 1 else "p1"
    host = args[1] if len(args) >= 2 else HOST
    # If the second argument looks like a port (numeric), treat accordingly
    port = PORT
    resume = False
    # Determine host/port/resume flags beyond the player_id
    # Accept forms: [player_id], [player_id host], [player_id host port], [player_id host port resume]
    if len(args) >= 3:
        # third arg could be port or the keyword 'resume'
        if args[2].isdigit():
            port = int(args[2])
            # check for resume flag as fourth arg
            if len(args) >= 4 and args[3].lower().startswith("res"):  # 'resume'
                resume = True
        else:
            # treat as resume flag
            resume = True
    elif len(args) >= 2:
        # if only two args and second arg is 'resume'
        if args[1].lower().startswith("res"):
            host = HOST
            resume = True
    # Create and start client
    client = Client(pid, host=host, port=port, resume=resume)
    client.start()
