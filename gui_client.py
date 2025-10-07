"""
A simple Tkinter-based GUI client for the Tic-Tac-Toe network game.  This
module builds upon the existing networking logic defined in ``wire.py`` and
the client/server architecture.  It establishes a connection to the server,
listens for game-state updates on a background thread and allows the local
player to make moves by clicking cells in a 3×3 grid.  A heartbeat thread
keeps the connection alive.  Basic status feedback (whose turn it is, game
over messages) is displayed within the window.

Usage examples:

    # connect as player p1 to the default localhost:12345
    python3 gui_client.py p1

    # connect as player p2 to a specific host/port
    python3 gui_client.py p2 192.168.0.10 12345

    # resume an existing session (optional third argument "resume")
    python3 gui_client.py p1 192.168.0.10 12345 resume

This program depends only on the Python standard library.  Tkinter ships
with Python on most platforms, so no third‑party packages are required.

"""

import socket
import threading
import time
import uuid
import sys
import tkinter as tk
from tkinter import messagebox

from wire import send_obj, recv_obj, envelope


HOST, PORT = "127.0.0.1", 12345
GAME_ID = "G-1"
HEARTBEAT_INTERVAL = 10


class GUIClient:
    """GUI wrapper around the network client logic."""

    def __init__(self, player_id: str, nickname: str = "", host: str = HOST, port: int = PORT, resume: bool = False):
        self.player_id = player_id
        self.nickname = nickname
        self.host = host
        self.port = port
        self.resume = resume
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.state = None  # latest GAME_STATE dict
        self.root = tk.Tk()
        self.root.title(f"Tic‑Tac‑Toe: {self.player_id}")
        # Build the GUI elements
        self._build_widgets()
        # Start network threads
        self._running = True
        self._lock = threading.Lock()

    def _build_widgets(self):
        """Constructs the Tkinter widgets: a status label and 3×3 grid."""
        self.status_var = tk.StringVar(value="Connecting…")
        status_label = tk.Label(self.root, textvariable=self.status_var, font=("Arial", 14))
        status_label.pack(pady=10)
        # Frame for the 3×3 grid
        grid_frame = tk.Frame(self.root)
        grid_frame.pack(padx=10, pady=10)
        self.buttons = []  # matrix of buttons [row][col]
        for y in range(3):
            row_buttons = []
            for x in range(3):
                btn = tk.Button(grid_frame, text="", width=4, height=2,
                                 font=("Arial", 20), command=lambda r=y, c=x: self._on_cell_click(r, c))
                btn.grid(row=y, column=x, padx=5, pady=5)
                row_buttons.append(btn)
            self.buttons.append(row_buttons)

    def start(self):
        """Connects to the server and starts the GUI mainloop."""
        try:
            self.sock.connect((self.host, self.port))
        except Exception as exc:
            messagebox.showerror("Connection Error", f"Failed to connect to server: {exc}")
            return
        # Send join or resume envelope
        if self.resume:
            known_version = None
            if self.state and isinstance(self.state, dict):
                known_version = self.state.get("version")
            payload = {"player_id": self.player_id}
            if known_version is not None:
                payload["known_version"] = known_version
            msg = envelope("RESUME", GAME_ID, payload)
            send_obj(self.sock, msg)
        else:
            join = envelope("PLAYER_JOINED", GAME_ID, {"player_id": self.player_id, "nickname": self.nickname})
            send_obj(self.sock, join)
        # Launch background network listener and heartbeat threads
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        # Start the Tk event loop
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_cell_click(self, row: int, col: int):
        """Invoked when a user clicks a cell.  Sends a MOVE if allowed."""
        with self._lock:
            if not self.state:
                return
            if self.state.get("status") != "IN_PROGRESS":
                return
            if self.state.get("next_player_id") != self.player_id:
                # Not our turn
                return
            board = self.state.get("board")
            if board[row][col] is not None:
                return
            # Construct and send a MOVE
            msg_id = str(uuid.uuid4())
            move = envelope("MOVE", GAME_ID, {
                "player_id": self.player_id,
                "x": col,
                "y": row,
                "turn": self.state.get("turn"),
                "msg_id": msg_id,
            })
            try:
                send_obj(self.sock, move)
            except Exception as exc:
                # Connection might be down
                self.status_var.set(f"Send failed: {exc}")

    def _listen_loop(self):
        """Continuously receive messages from the server and update the GUI state."""
        while self._running:
            msg = recv_obj(self.sock)
            if msg is None:
                # Server closed connection
                self._running = False
                self._schedule(lambda: messagebox.showwarning("Disconnected", "Server closed the connection."))
                break
            mtype = msg.get("type")
            payload = msg.get("payload", {})
            if mtype == "GAME_STATE":
                self._handle_game_state(payload)
            elif mtype == "GAME_OVER":
                self._handle_game_over(payload)
            elif mtype == "ERROR":
                code, message = payload.get("code"), payload.get("message")
                self._schedule(lambda c=code, m=message: messagebox.showerror(f"Error {c}", m))
            elif mtype == "PONG":
                # ignore
                pass
            elif mtype == "MOVE_OK":
                # We could update board optimistically; server will also send GAME_STATE
                pass
            else:
                # Unknown type – ignore or log
                self._schedule(lambda t=mtype: messagebox.showinfo("Unknown", f"Unknown message type: {t}"))

    def _handle_game_state(self, st: dict):
        """Handles incoming GAME_STATE, updating local state and UI."""
        with self._lock:
            if self.state is None or st.get("version", 0) >= self.state.get("version", 0):
                self.state = st
                # Schedule UI update in the Tk thread
                self._schedule(self._update_board_and_status)

    def _handle_game_over(self, payload: dict):
        """Handles GAME_OVER message, updating state and notifying the user."""
        final_state = payload.get("final_state")
        result = payload.get("result")
        winning_line = payload.get("winning_line")
        with self._lock:
            self.state = final_state
            self._schedule(self._update_board_and_status)
        msg = f"Result: {result}"
        if winning_line:
            msg += f"\nWinning line: {winning_line}"
        self._schedule(lambda m=msg: messagebox.showinfo("Game Over", m))

    def _update_board_and_status(self):
        """Updates the GUI's board buttons and status label from self.state."""
        st = self.state
        if not st:
            return
        board = st.get("board")
        # Update each button's label and disable filled cells
        for y, row in enumerate(board):
            for x, cell in enumerate(row):
                btn = self.buttons[y][x]
                btn.config(text=cell if cell is not None else "")
                if cell is not None or st.get("status") != "IN_PROGRESS" or st.get("next_player_id") != self.player_id:
                    btn.config(state=tk.DISABLED)
                else:
                    btn.config(state=tk.NORMAL)
        # Update status text
        status = st.get("status")
        if status == "IN_PROGRESS":
            next_pid = st.get("next_player_id")
            if next_pid == self.player_id:
                self.status_var.set("Your turn")
            else:
                self.status_var.set(f"Waiting for {next_pid}")
        elif status == "WAITING":
            self.status_var.set("Waiting for opponent…")
        elif status == "GAME_OVER":
            self.status_var.set("Game over")

    def _heartbeat_loop(self):
        """Periodically send PING messages to keep the connection alive."""
        while self._running:
            try:
                send_obj(self.sock, envelope("PING", GAME_ID, {}))
            except Exception:
                # ignore errors – the listener will handle disconnection
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def _schedule(self, func):
        """Schedules a callable to run in the Tk main thread."""
        self.root.after(0, func)

    def _on_close(self):
        """Gracefully close the socket and exit the application."""
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass
        self.root.destroy()


def parse_args(argv):
    """Parses command-line arguments for the GUI client."""
    args = argv[1:]
    pid = args[0] if len(args) >= 1 else "p1"
    host = args[1] if len(args) >= 2 else HOST
    port = PORT
    resume = False
    if len(args) >= 3:
        if args[2].isdigit():
            port = int(args[2])
            if len(args) >= 4 and args[3].lower().startswith("res"):
                resume = True
        else:
            resume = True
    elif len(args) >= 2:
        if args[1].lower().startswith("res"):
            host = HOST
            resume = True
    return pid, host, port, resume


if __name__ == "__main__":
    pid, host, port, resume = parse_args(sys.argv)
    gui_client = GUIClient(pid, host=host, port=port, resume=resume)
    gui_client.start()