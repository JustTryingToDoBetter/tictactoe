import socket
import json
def send_message(sock, obj):
    line = json.dumps(obj, separators=(",", ":")) + "\n"
    sock.sendall(line.encode('utf-8'))

def receive_message(sock, buffer):
    try:
        chunk = sock.recv(4096)
        if not chunk:
            return None, buffer  # peer closed
        buffer += chunk.decode("utf-8")
        if "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip() == "":
                return None, buffer
            return json.loads(line), buffer
    except socket.timeout:
        return None, buffer

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('127.0.0.1', 12345))
server.listen(1)
print('server is listening')

conn, addr = server.accept()
print(f'connected by {addr}')

buffer = ""
while True:
    msg, buffer = receive_message(conn, buffer)
    if msg is None:
        break
    msg_type = msg.get("type")
    if msg_type == "MOVE":
        print(f"Received MOVE: {msg}")
        # Respond with updated game state
        send_message(conn, {"type": "GAME_STATE", "board": ["X", "O", "", 
                                                            "", "", "", 
                                                            "", "", ""], "current_player": 2})
    elif msg_type == "PLAYER_JOINED":
        print(f"Player joined: {msg}")
        send_message(conn, {"type": "GAME_STATE", "board": ["", "", "", 
                                                            "", "", "", 
                                                            "", "", ""], "current_player": 1})
    elif msg_type == "GAME_OVER":
        print(f"Game over: {msg}")
        break
    else:
        print(f"Unknown message type: {msg}")

conn.close()
server.close()
server.close() ## kill server


